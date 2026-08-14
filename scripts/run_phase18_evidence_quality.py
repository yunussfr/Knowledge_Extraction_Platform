"""Run the frozen Phase 18 evidence-validation and quality-gate benchmark."""

from __future__ import annotations

import json
from typing import Any

from scripts.run_phase17_field_evidence_contract import _benchmark_state
from src.agents.nodes.evidence_validation_node import evidence_validation_node
from src.agents.nodes.field_evidence_node import field_evidence_node
from src.agents.nodes.quality_gate_node import quality_gate_node
from src.evaluation import load_json
from src.schemas.models import ExtractionBatch
from scripts.run_phase17_field_evidence_contract import FIXTURE_PATH


def _evidence(source_url: str, chunk_id: str, text: str) -> dict[str, str]:
    return {"source_url": source_url, "chunk_id": chunk_id, "evidence_text": text}


def _status_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = [
        (
            "partial",
            "https://fixtures.example/phase18/partial",
            "phase18_partial_chunk",
            "Delta Tool is a documented runtime. Category is omitted.",
            {"item_name": "Delta Tool", "description": "documented runtime", "category": "model"},
            {
                "item_name": ["Delta Tool"],
                "description": ["documented runtime"],
                "category": ["Category is omitted"],
            },
        ),
        (
            "unsupported",
            "https://fixtures.example/phase18/unsupported",
            "phase18_unsupported_chunk",
            "Missing Tool appears without factual detail.",
            {"item_name": "Missing Tool", "description": "invented description"},
            {"item_name": ["Missing Tool"]},
        ),
        (
            "contradicted",
            "https://fixtures.example/phase18/contradicted",
            "phase18_contradicted_chunk",
            "Toggle Tool is a feature switch. Category: not active.",
            {"item_name": "Toggle Tool", "description": "feature switch", "category": "active"},
            {
                "item_name": ["Toggle Tool"],
                "description": ["feature switch"],
                "category": ["Category: not active"],
            },
        ),
    ]
    chunks: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    for local_id, source_url, chunk_id, content, data, evidence_map in cases:
        chunks.append({
            "chunk_id": chunk_id,
            "source_url": source_url,
            "source_title": local_id,
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "token_count": len(content.split()),
            "source_metadata": {"fixture_status": local_id},
        })
        batches.append(ExtractionBatch.model_validate({
            "source_url": source_url,
            "segment_id": chunk_id,
            "chunk_id": chunk_id,
            "records": [{
                "local_record_id": local_id,
                "source_url": source_url,
                "segment_id": chunk_id,
                "chunk_id": chunk_id,
                "source_chunk_id": chunk_id,
                "data": data,
                "confidence": 0.01,
                "field_confidence": {field_name: 0.01 for field_name in data},
                "field_evidence": {
                    field_name: [
                        _evidence(source_url, chunk_id, text) for text in texts
                    ]
                    for field_name, texts in evidence_map.items()
                },
            }],
        }).model_dump(mode="json"))
    return chunks, batches


def run_evidence_quality_benchmark() -> dict[str, Any]:
    fixture = load_json(FIXTURE_PATH)
    state = _benchmark_state(fixture)
    evidenced = field_evidence_node(state)
    status_chunks, status_batches = _status_cases()
    validation_state = {
        **state,
        **evidenced,
        "document_chunks": [*state["document_chunks"], *status_chunks],
        "evidenced_extraction_batches": [
            *evidenced["evidenced_extraction_batches"],
            *status_batches,
        ],
        "config": {"quality": {"minimum_evidence_quality": 0.7}},
    }
    verified = evidence_validation_node(validation_state)
    gated = quality_gate_node({**validation_state, **verified})
    gold_ids = {
        record["record_id"]
        for page in fixture["pages"]
        for record in page["expected_records"]
    }
    accepted_ids = {
        record["local_record_id"]
        for batch in gated["quality_approved_extraction_batches"]
        for record in batch["records"]
    }
    return {
        "benchmark_version": "1.0",
        "contract": "phase18_evidence_validation_quality_gate",
        "gold": {
            "records": len(gold_ids),
            "supported_records": sum(
                item["status"] == "SUPPORTED"
                and item["record"]["local_record_id"] in gold_ids
                for item in verified["verified_records"]
            ),
            "accepted_records": len(gold_ids & accepted_ids),
        },
        "status_counts": verified["evidence_validation_metrics"]["status_counts"],
        "quality_gate": gated["quality_gate_metrics"],
    }


def main() -> None:
    print(json.dumps(run_evidence_quality_benchmark(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
