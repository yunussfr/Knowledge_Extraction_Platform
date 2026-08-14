"""Phase 17 field-evidence binding and downstream survival tests."""

import json

from src.agents.nodes.deduplication_node import deduplication_node
from src.agents.nodes.export_node import export_node
from src.agents.nodes.field_evidence_node import field_evidence_node
from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.record_merge_node import record_merge_node
from src.agents.nodes.validation_node import validation_node
from src.schemas.models import ExtractionBatch


SOURCE_URL = "https://fixtures.example/catalog/evidence"
CHUNK_ID = "source_001_chunk_001"


def _schema() -> dict:
    fields = [
        ("item_name", True, False),
        ("description", True, False),
        ("category", False, True),
        ("notes", False, False),
    ]
    return {
        "name": "evidence_catalog",
        "description": "Evidence contract records.",
        "fields": [
            {
                "field_name": name,
                "type": "string",
                "required": required,
                "nullable": nullable,
                "description": f"The {name} field.",
                "extraction_instruction": f"Extract {name} only from supplied content.",
            }
            for name, required, nullable in fields
        ],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _chunk(content: str, chunk_id: str = CHUNK_ID) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_url": SOURCE_URL,
        "source_title": "Evidence fixture",
        "chunk_index": 0,
        "total_chunks": 1,
        "content": content,
        "token_count": max(1, len(content.split())),
        "source_metadata": {"source_provider": "fixture"},
    }


def _batch(record: dict, chunk_id: str = CHUNK_ID) -> dict:
    return ExtractionBatch.model_validate({
        "source_url": SOURCE_URL,
        "segment_id": chunk_id,
        "chunk_id": chunk_id,
        "records": [record],
    }).model_dump(mode="json")


def test_contract_derives_exact_evidence_and_applies_optional_null_omit_policy():
    content = "Alpha Engine is a compact runtime."
    raw_batch = _batch({
        "local_record_id": "alpha",
        "data": {
            "item_name": "Alpha Engine",
            "description": "compact runtime",
            "category": "invented category",
            "notes": "invented notes",
            "unapproved": "invented extra",
        },
        "confidence": 0.9,
        "field_confidence": {
            "item_name": 0.9,
            "description": 0.9,
            "category": 0.9,
            "notes": 0.9,
            "unapproved": 0.9,
        },
        "field_evidence": {
            "description": [{
                "source_url": SOURCE_URL,
                "chunk_id": CHUNK_ID,
                "evidence_text": "compact   runtime",
            }],
            "category": [{
                "source_url": SOURCE_URL,
                "chunk_id": CHUNK_ID,
                "evidence_text": "fabricated evidence",
            }],
        },
    })
    state = {
        "approved_dataset_schema": _schema(),
        "document_chunks": [_chunk(content)],
        "extraction_batches": [raw_batch],
        "extraction_warnings": [],
        "rejected_records": [],
        "errors": [],
    }

    result = field_evidence_node(state)

    assert result["status"] == "binding_evidence"
    record = result["evidenced_extraction_batches"][0]["records"][0]
    assert record["data"] == {
        "item_name": "Alpha Engine",
        "description": "compact runtime",
        "category": None,
    }
    assert record["field_evidence"] == {
        "item_name": [{
            "source_url": SOURCE_URL,
            "chunk_id": CHUNK_ID,
            "evidence_text": "Alpha Engine",
        }],
        "description": [{
            "source_url": SOURCE_URL,
            "chunk_id": CHUNK_ID,
            "evidence_text": "compact runtime",
        }],
    }
    assert result["evidence_metrics"]["nulled_optional_fields"] == 1
    assert result["evidence_metrics"]["omitted_optional_fields"] == 1
    assert result["evidence_metrics"]["removed_unapproved_fields"] == 1
    assert state["extraction_batches"][0]["records"][0]["data"]["category"] == (
        "invented category"
    )


def test_unsupported_required_field_quarantines_record_before_merge():
    state = {
        "approved_dataset_schema": _schema(),
        "document_chunks": [_chunk("Alpha Engine appears here without a description.")],
        "extraction_batches": [_batch({
            "local_record_id": "unsupported-required",
            "data": {
                "item_name": "Alpha Engine",
                "description": "invented description",
            },
            "confidence": 0.9,
        })],
        "rejected_records": [],
        "errors": [],
    }

    evidenced = field_evidence_node(state)
    merged = record_merge_node({**state, **evidenced})

    assert evidenced["evidenced_extraction_batches"][0]["records"] == []
    assert evidenced["evidence_metrics"]["rejected_records"] == 1
    assert evidenced["evidence_rejections"][0]["stage"] == "field_evidence_contract"
    assert evidenced["evidence_rejections"][0]["reasons"] == [
        "Required field description has no traceable evidence."
    ]
    assert merged["merged_records"] == []


def test_deterministic_source_record_can_bind_to_the_actual_contributing_chunk():
    second_chunk_id = "source_001_chunk_002"
    state = {
        "approved_dataset_schema": _schema(),
        "document_chunks": [
            _chunk("Introduction only."),
            {**_chunk("Beta Engine is a stable runtime.", second_chunk_id), "chunk_index": 1},
        ],
        "extraction_batches": [_batch({
            "local_record_id": "beta",
            "data": {"item_name": "Beta Engine", "description": "stable runtime"},
            "confidence": 1.0,
            "extraction_method": "table",
        })],
        "errors": [],
    }

    result = field_evidence_node(state)
    record = result["evidenced_extraction_batches"][0]["records"][0]

    assert {
        evidence["chunk_id"]
        for references in record["field_evidence"].values()
        for evidence in references
    } == {second_chunk_id}


def test_field_evidence_survives_merge_validation_deduplication_and_export(tmp_path):
    content = "Alpha Engine is a compact runtime."
    state = {
        "domain": "catalog",
        "dataset_name": "phase17_records",
        "dataset_topic": "Runtime catalog",
        "approved_dataset_schema": _schema(),
        "document_chunks": [_chunk(content)],
        "extraction_batches": [_batch({
            "local_record_id": "alpha",
            "data": {"item_name": "Alpha Engine", "description": "compact runtime"},
            "confidence": 0.9,
            "field_confidence": {"item_name": 0.9, "description": 0.9},
        })],
        "classified_data": [{
            "source": SOURCE_URL,
            "title": "Evidence fixture",
            "cleaned_content": content,
            "metadata": {"source_provider": "fixture"},
        }],
        "config": {
            "quality": {"minimum_confidence": 0.7},
            "output": {"directory": str(tmp_path), "format": "json"},
        },
        "rejected_records": [],
        "errors": [],
    }

    evidenced = field_evidence_node(state)
    merged = record_merge_node({**state, **evidenced})
    enriched = metadata_enrichment_node({**state, **evidenced, **merged})
    validated = validation_node({**state, **evidenced, **merged, **enriched})
    deduplicated = deduplication_node({**state, **validated})
    exported = export_node({**state, **validated, **deduplicated})

    evidence = deduplicated["accepted_records"][0]["_metadata"]["field_evidence"]
    assert set(evidence) == {"item_name", "description"}
    assert all(
        reference["evidence_text"] in content
        for references in evidence.values()
        for reference in references
    )
    saved = json.loads((tmp_path / "phase17_records.json").read_text(encoding="utf-8"))
    assert saved[0]["_metadata"]["field_evidence"] == evidence
    assert exported["status"] == "completed"


def test_duplicate_provenance_merge_keeps_unique_evidence_from_both_records():
    first = {
        "data": {"item_name": "Alpha Engine", "description": "compact runtime"},
        "_metadata": {
            "source_url": "https://fixtures.example/a",
            "contributing_chunk_ids": ["a_chunk"],
            "contributing_record_ids": ["a_record"],
            "field_evidence": {
                "item_name": [{
                    "source_url": "https://fixtures.example/a",
                    "chunk_id": "a_chunk",
                    "evidence_text": "Alpha Engine",
                }],
            },
        },
    }
    duplicate = {
        "data": {"item_name": "Alpha Engine", "description": "compact runtime"},
        "_metadata": {
            "source_url": "https://fixtures.example/b",
            "contributing_chunk_ids": ["b_chunk"],
            "contributing_record_ids": ["b_record"],
            "field_evidence": {
                "item_name": [{
                    "source_url": "https://fixtures.example/b",
                    "chunk_id": "b_chunk",
                    "evidence_text": "Alpha Engine",
                }],
            },
        },
    }

    result = deduplication_node({
        "accepted_records": [first, duplicate],
        "rejected_records": [],
        "errors": [],
    })
    metadata = result["accepted_records"][0]["_metadata"]

    assert metadata["source_urls"] == [
        "https://fixtures.example/a",
        "https://fixtures.example/b",
    ]
    assert metadata["contributing_record_ids"] == ["a_record", "b_record"]
    assert len(metadata["field_evidence"]["item_name"]) == 2
