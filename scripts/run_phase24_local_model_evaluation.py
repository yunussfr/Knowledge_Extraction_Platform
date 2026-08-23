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
    return {
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
    return {
        "benchmark_version": "1.0",
        "benchmark": "phase24_local_model_evaluation",
        "status": "completed",
        "local_first_enabled": False,
        "provider": provider.provider_name,
        "metrics": metrics,
        "latency_seconds": round(elapsed, 6),
        "note": "Local-first routing requires an explicit quality comparison and is not enabled by this harness.",
    }


def main() -> None:
    print(json.dumps(run_local_model_benchmark(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
