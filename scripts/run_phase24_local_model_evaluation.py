"""Run the opt-in local-provider comparison on the frozen extraction gold set.

The script deliberately has no backend-specific dependency. Applications may
inject a ``StructuredGenerationProvider`` implementation; without one, the
result is an explicit unavailable checkpoint and local-first routing remains
disabled.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.evaluation import evaluate_extraction, load_json
from src.schemas.models import DocumentChunk, ExtractionBatch
from src.tools.structured_generation.base import StructuredGenerationProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "evaluation" / "fixtures" / "extraction_gold.json"


def _schema(fixture: dict[str, Any]) -> dict[str, Any]:
    result = {
        "name": "phase24_local_model_gold",
        "description": "Frozen Phase 24 comparison schema.",
        "fields": [
            {
                "field_name": field_name,
                "type": contract["type"],
                "required": contract["required"],
                "description": field_name,
                "extraction_instruction": f"Extract {field_name}.",
            }
            for field_name, contract in fixture["schema"]["fields"].items()
        ],
        "identity_fields": [fixture["schema"]["identity_field"]],
        "schema_version": 1,
        "approved_at": "2026-08-22T00:00:00+00:00",
        "approved_by": "phase24-benchmark",
    }


def run_local_model_benchmark(
    provider: StructuredGenerationProvider | None = None,
) -> dict[str, Any]:
    fixture = load_json(FIXTURE_PATH)
    if provider is None:
        return {
            "benchmark_version": "1.0",
            "benchmark": "phase24_local_model_evaluation",
            "status": "unavailable",
            "local_first_enabled": False,
            "reason": "No local structured-generation provider was injected.",
        }

    predictions: list[dict[str, Any]] = []
    started = time.perf_counter()
    for page in fixture["pages"]:
        chunk = DocumentChunk(
            chunk_id=f"phase24:{page['page_id']}",
            source_url=page["source_url"],
            source_title=page["page_id"],
            chunk_index=0,
            total_chunks=1,
            content=page["content"],
            token_count=max(1, len(page["content"].split())),
        )
        prompt = (
            f"Approved schema: {_schema(fixture)}\n"
            f"Page ID: {page['page_id']}\n"
            f"Source URL: {chunk.source_url}\n"
            "Return a JSON object with exactly records[] and warnings[]. "
            "Each record must be an object with local_record_id, data, confidence, field_confidence, and field_evidence. "
            "Put extracted schema fields inside data. For each populated data field, field_evidence must be a list "
            "of objects containing source_url, chunk_id, and exact evidence_text copied from the chunk. "
            "Return an empty records array when no supported record exists. "
            "For prose such as 'Solaris Engine is a compact inference runtime.', use item_name='Solaris Engine' "
            "and description='a compact inference runtime' rather than repeating the subject; remove sentence-ending "
            "punctuation from field values when the source value does not include it.\n"
            f"Chunk content:\n{chunk.content}"
        )
        batch = provider.generate(
            system_prompt="Return only evidence-backed ExtractionBatch records.",
            user_prompt=prompt,
            output_model=ExtractionBatch,
            task_name="phase24_local_model_evaluation",
        )
        predictions.append({
            "page_id": page["page_id"],
            "records": [record.model_dump(mode="json") for record in batch.records],
        })
    elapsed = time.perf_counter() - started
    metrics = evaluate_extraction(fixture, {"extraction_predictions": predictions})
    result = {
        "benchmark_version": "1.0",
        "benchmark": "phase24_local_model_evaluation",
        "status": "completed",
        "local_first_enabled": bool(getattr(provider, "local_first_enabled", False)),
        "provider": provider.provider_name,
        "metrics": metrics,
        "latency_seconds": round(elapsed, 6),
        "note": "Local-first routing requires an explicit quality comparison and is not enabled by this harness.",
    }
    if hasattr(provider, "local_calls"):
        result["routing_metrics"] = {
            "local_calls": provider.local_calls,
            "cloud_calls": provider.cloud_calls,
            "fallback_calls": provider.fallback_calls,
            "fallback_rate": round(provider.fallback_calls / provider.local_calls, 6) if provider.local_calls else 0.0,
        }
    return result


def main() -> None:
    print(json.dumps(run_local_model_benchmark(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
