"""Run the deterministic Phase 17 gold field-evidence contract benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.nodes.field_evidence_node import field_evidence_node
from src.agents.nodes.record_merge_node import record_merge_node
from src.evaluation import load_json
from src.schemas.models import EvidenceRef, ExtractedRecord, ExtractionBatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "evaluation" / "fixtures" / "extraction_gold.json"


def _approved_schema(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "phase17_gold",
        "description": "Frozen field-evidence contract schema.",
        "fields": [
            {
                "field_name": field_name,
                "type": definition["type"],
                "required": definition["required"],
                "nullable": not definition["required"],
                "description": f"Gold {field_name} field.",
                "extraction_instruction": f"Extract {field_name} from supplied content.",
            }
            for field_name, definition in fixture["schema"]["fields"].items()
        ],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "benchmark",
    }


def _benchmark_state(fixture: dict[str, Any]) -> dict[str, Any]:
    chunks = []
    batches = []
    for page_index, page in enumerate(fixture["pages"], start=1):
        chunk_id = f"gold_{page_index:03d}_chunk_001"
        content = page["content"]
        chunks.append({
            "chunk_id": chunk_id,
            "source_url": page["source_url"],
            "source_title": page["page_id"],
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "token_count": max(1, len(content.split())),
            "source_metadata": {"fixture_page_id": page["page_id"]},
        })
        records = []
        for record in page["expected_records"]:
            records.append(ExtractedRecord(
                local_record_id=record["record_id"],
                source_url=page["source_url"],
                segment_id=chunk_id,
                chunk_id=chunk_id,
                source_chunk_id=chunk_id,
                data=record["data"],
                confidence=1.0,
                field_confidence={field_name: 1.0 for field_name in record["data"]},
                field_evidence={
                    field_name: [
                        EvidenceRef(
                            source_url=page["source_url"],
                            chunk_id=chunk_id,
                            evidence_text=evidence_text,
                        )
                        for evidence_text in evidence_values
                    ]
                    for field_name, evidence_values in record["field_evidence"].items()
                },
            ))
        batches.append(ExtractionBatch(
            source_url=page["source_url"],
            segment_id=chunk_id,
            chunk_id=chunk_id,
            records=records,
        ).model_dump(mode="json"))
    return {
        "approved_dataset_schema": _approved_schema(fixture),
        "document_chunks": chunks,
        "extraction_batches": batches,
        "extraction_warnings": [],
        "rejected_records": [],
        "errors": [],
    }


def run_contract_benchmark() -> dict[str, Any]:
    fixture = load_json(FIXTURE_PATH)
    state = _benchmark_state(fixture)
    evidenced = field_evidence_node(state)
    merged = record_merge_node({**state, **evidenced})
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in state["document_chunks"]}
    evidenced_records = [
        record
        for batch in evidenced["evidenced_extraction_batches"]
        for record in batch["records"]
    ]
    evidence_refs = [
        evidence
        for record in evidenced_records
        for references in record["field_evidence"].values()
        for evidence in references
    ]
    traceable_refs = sum(
        evidence["source_url"] == chunks_by_id[evidence["chunk_id"]]["source_url"]
        and evidence["evidence_text"] in chunks_by_id[evidence["chunk_id"]]["content"]
        for evidence in evidence_refs
    )
    records_with_usable_evidence = sum(
        all(
            not (value is not None and value != "" and value != [] and value != {})
            or bool(record["field_evidence"].get(field_name))
            for field_name, value in record["data"].items()
        )
        for record in evidenced_records
    )
    return {
        "benchmark_version": "1.0",
        "contract": "phase17_field_evidence",
        "page_count": len(fixture["pages"]),
        "input_records": sum(
            len(page["expected_records"]) for page in fixture["pages"]
        ),
        "metrics": {
            "emitted_records": len(evidenced_records),
            "rejected_records": len(evidenced["evidence_rejections"]),
            "merged_records": len(merged["merged_records"]),
            "evidenced_fields": evidenced["evidence_metrics"]["evidenced_fields"],
            "evidence_refs": len(evidence_refs),
            "traceable_evidence_refs": traceable_refs,
            "records_with_usable_evidence": records_with_usable_evidence,
        },
    }


def main() -> None:
    print(json.dumps(run_contract_benchmark(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
