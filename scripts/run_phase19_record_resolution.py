"""Run the frozen Phase 19 cross-source record-resolution benchmark."""

from __future__ import annotations

import json
from typing import Any

from src.agents.nodes.record_resolution_node import record_resolution_node
from src.schemas.models import ExtractionBatch


SOURCE_A = "https://fixtures.example/resolution/source-a"
SOURCE_B = "https://fixtures.example/resolution/source-b"


def _record(
    source_url: str,
    chunk_id: str,
    local_id: str,
    data: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    return {
        "local_record_id": local_id,
        "source_url": source_url,
        "segment_id": chunk_id,
        "chunk_id": chunk_id,
        "source_chunk_id": chunk_id,
        "data": data,
        "confidence": confidence,
        "field_confidence": {field_name: confidence for field_name in data},
        "field_evidence": {
            field_name: [{
                "source_url": source_url,
                "chunk_id": chunk_id,
                "evidence_text": str(value).strip(),
            }]
            for field_name, value in data.items()
        },
    }


def _quality(source_url: str, local_id: str, score: float) -> dict[str, Any]:
    return {
        "local_record_id": local_id,
        "source_url": source_url,
        "support_status": "SUPPORTED",
        "components": {
            "schema_validity": 1.0,
            "required_field_completeness": 1.0,
            "evidence_support_rate": 1.0,
            "source_score": score,
            "provenance_completeness": 1.0,
            "duplicate_status": 0.5,
        },
        "final_quality_score": score,
        "accepted": True,
    }


def run_resolution_benchmark() -> dict[str, Any]:
    schema = {
        "name": "phase19_resolution",
        "description": "Frozen cross-source resolution schema.",
        "fields": [
            {
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "Item name.",
                "extraction_instruction": "Extract item name.",
            },
            {
                "field_name": "description",
                "type": "string",
                "required": True,
                "description": "Description.",
                "extraction_instruction": "Extract description.",
            },
            {
                "field_name": "category",
                "type": "string",
                "required": False,
                "nullable": True,
                "description": "Category.",
                "extraction_instruction": "Extract category.",
            },
        ],
        "identity_fields": ["item_name"],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "benchmark",
    }
    records_a = [
        _record(SOURCE_A, "a_chunk", "atlas-a", {
            "item_name": "Atlas Retriever",
            "description": "fault-tolerant retrieval service",
            "category": "retrieval",
        }, 0.9),
        _record(SOURCE_A, "a_chunk", "orbit-a", {
            "item_name": "Orbit Parser",
            "description": "Unicode document parser",
            "category": "parser",
        }, 0.9),
    ]
    records_b = [
        _record(SOURCE_B, "b_chunk", "atlas-b", {
            "item_name": " atlas   retriever ",
            "description": "resilient retrieval platform",
            "category": "retrieval",
        }, 0.7),
    ]
    batches = [
        ExtractionBatch.model_validate({
            "source_url": SOURCE_A,
            "segment_id": "a_chunk",
            "chunk_id": "a_chunk",
            "records": records_a,
        }).model_dump(mode="json"),
        ExtractionBatch.model_validate({
            "source_url": SOURCE_B,
            "segment_id": "b_chunk",
            "chunk_id": "b_chunk",
            "records": records_b,
        }).model_dump(mode="json"),
    ]
    state = {
        "approved_dataset_schema": schema,
        "document_chunks": [
            {
                "chunk_id": "a_chunk",
                "source_url": SOURCE_A,
                "source_title": "Source A",
                "chunk_index": 0,
                "total_chunks": 1,
                "content": (
                    "Atlas Retriever fault-tolerant retrieval service retrieval "
                    "Orbit Parser Unicode document parser parser"
                ),
                "token_count": 11,
                "source_metadata": {"fixture": "a"},
            },
            {
                "chunk_id": "b_chunk",
                "source_url": SOURCE_B,
                "source_title": "Source B",
                "chunk_index": 0,
                "total_chunks": 1,
                "content": "atlas retriever resilient retrieval platform retrieval",
                "token_count": 6,
                "source_metadata": {"fixture": "b"},
            },
        ],
        "quality_gate_metrics": {"accepted_records": 3},
        "quality_approved_extraction_batches": batches,
        "record_quality_assessments": [
            _quality(SOURCE_A, "atlas-a", 0.9),
            _quality(SOURCE_A, "orbit-a", 0.9),
            _quality(SOURCE_B, "atlas-b", 0.8),
        ],
        "errors": [],
    }
    result = record_resolution_node(state)
    atlas = next(
        item for item in result["resolved_records"]
        if item["data"]["item_name"].strip() == "Atlas Retriever"
    )
    return {
        "benchmark_version": "1.0",
        "contract": "phase19_cross_source_resolution",
        "metrics": result["record_resolution_metrics"],
        "multi_source_record": {
            "resolution_method": atlas["resolution_method"],
            "source_urls": atlas["source_urls"],
            "contributors": len(atlas["contributors"]),
            "item_name_evidence_sources": sorted({
                evidence["source_url"]
                for evidence in atlas["field_evidence"]["item_name"]
            }),
            "conflicts": len(atlas["merge_conflicts"]),
            "kept_description": atlas["data"]["description"],
            "conflicting_description": atlas["merge_conflicts"][0]["incoming_value"],
            "evidence_quality_score": atlas["evidence_quality_score"],
        },
    }


def main() -> None:
    print(json.dumps(run_resolution_benchmark(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
