"""Run the frozen Phase 20 staged deduplication benchmark."""

from __future__ import annotations

import json
from typing import Any

from src.agents.nodes.deduplication_node import deduplication_node


def _record(
    source_url: str,
    local_id: str,
    data: dict[str, Any],
    *,
    content_hash: str,
    quality: float = 0.8,
) -> dict[str, Any]:
    chunk_id = f"{local_id}_chunk"
    return {
        "data": data,
        "_metadata": {
            "source_url": source_url,
            "source_urls": [source_url],
            "source_content_hashes": {source_url: content_hash},
            "contributing_chunk_ids": [chunk_id],
            "contributing_record_ids": [local_id],
            "contributors": [{
                "source_url": source_url,
                "local_record_id": local_id,
                "chunk_id": chunk_id,
                "extraction_method": "semantic",
            }],
            "field_evidence": {
                field_name: [{
                    "source_url": source_url,
                    "chunk_id": chunk_id,
                    "evidence_text": str(value).strip(),
                }]
                for field_name, value in data.items()
            },
            "evidence_quality_score": quality,
            "evidence_support_statuses": ["SUPPORTED"],
        },
    }


def run_deduplication_benchmark() -> dict[str, Any]:
    schema = {
        "name": "phase20_deduplication",
        "description": "Frozen staged deduplication schema.",
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
    records = [
        _record("https://a.test/source", "source-a", {
            "item_name": "Source Duplicate", "description": "Same"
        }, content_hash="shared", quality=0.7),
        _record("https://mirror.test/source", "source-b", {
            "item_name": " source duplicate ", "description": "same"
        }, content_hash="shared", quality=0.9),
        _record("https://c.test/exact", "exact-a", {
            "item_name": "Exact Duplicate", "description": "Alpha   text"
        }, content_hash="c"),
        _record("https://d.test/exact", "exact-b", {
            "description": "alpha text", "item_name": " exact duplicate "
        }, content_hash="d"),
        _record("https://e.test/identity", "identity-a", {
            "item_name": "Identity Subset", "description": "Base"
        }, content_hash="e"),
        _record("https://f.test/identity", "identity-b", {
            "item_name": " identity subset ", "description": "base", "category": "tool"
        }, content_hash="f"),
        _record("https://g.test/conflict", "conflict-a", {
            "item_name": "Identity Conflict", "description": "First"
        }, content_hash="g"),
        _record("https://h.test/conflict", "conflict-b", {
            "item_name": " identity conflict ", "description": "Second"
        }, content_hash="h"),
    ]
    result = deduplication_node({
        "approved_dataset_schema": schema,
        "accepted_records": records,
        "rejected_records": [],
        "errors": [],
    })
    retained_source_duplicate = next(
        record for record in result["accepted_records"]
        if record["data"]["item_name"].strip().casefold() == "source duplicate"
    )
    return {
        "benchmark_version": "1.0",
        "contract": "phase20_staged_deduplication",
        "metrics": result["deduplication_metrics"],
        "rejection_count": len(result["rejected_records"]),
        "source_duplicate_provenance": {
            "source_urls": sorted(
                retained_source_duplicate["_metadata"]["source_urls"]
            ),
            "contributors": len(
                retained_source_duplicate["_metadata"]["contributors"]
            ),
            "evidence_refs": sum(
                len(references)
                for references in retained_source_duplicate["_metadata"]["field_evidence"].values()
            ),
            "deduplication": retained_source_duplicate["_metadata"]["deduplication"],
        },
    }


def main() -> None:
    print(json.dumps(run_deduplication_benchmark(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
