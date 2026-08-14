"""Phase 19 schema-aware cross-source resolution and provenance tests."""

import pytest

from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.record_resolution_node import record_resolution_node
from src.schemas.models import ApprovedDatasetSchema, ExtractionBatch


SOURCE_A = "https://fixtures.example/source-a"
SOURCE_B = "https://fixtures.example/source-b"


def _schema(*, identity_fields: list[str] | None = None, composite: bool = False) -> dict:
    if composite:
        fields = [
            ("manufacturer", "string", True),
            ("model_code", "string", True),
            ("description", "string", True),
        ]
    else:
        fields = [
            ("item_name", "string", True),
            ("description", "string", True),
            ("category", "string", False),
        ]
    return {
        "name": "resolution",
        "description": "Cross-source resolution fixtures.",
        "fields": [
            {
                "field_name": name,
                "type": field_type,
                "required": required,
                "nullable": not required,
                "description": f"The {name} field.",
                "extraction_instruction": f"Extract {name}.",
            }
            for name, field_type, required in fields
        ],
        "identity_fields": identity_fields or [],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _chunk(source_url: str, chunk_id: str, content: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_url": source_url,
        "source_title": f"Title for {source_url.rsplit('-', 1)[-1]}",
        "chunk_index": 0,
        "total_chunks": 1,
        "content": content,
        "token_count": len(content.split()),
        "source_metadata": {"source_provider": "fixture"},
    }


def _record(
    source_url: str,
    chunk_id: str,
    local_id: str,
    data: dict,
    *,
    description_confidence: float = 0.9,
) -> dict:
    return {
        "local_record_id": local_id,
        "source_url": source_url,
        "segment_id": chunk_id,
        "chunk_id": chunk_id,
        "source_chunk_id": chunk_id,
        "data": data,
        "confidence": description_confidence,
        "field_confidence": {
            field_name: description_confidence for field_name in data
        },
        "field_evidence": {
            field_name: [{
                "source_url": source_url,
                "chunk_id": chunk_id,
                "evidence_text": str(value).strip(),
            }]
            for field_name, value in data.items()
        },
        "extraction_method": "semantic",
    }


def _batch(source_url: str, chunk_id: str, records: list[dict]) -> dict:
    return ExtractionBatch.model_validate({
        "source_url": source_url,
        "segment_id": chunk_id,
        "chunk_id": chunk_id,
        "records": records,
    }).model_dump(mode="json")


def _quality(source_url: str, local_id: str, score: float) -> dict:
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
        "reasons": [],
    }


def test_explicit_identity_merges_across_sources_and_preserves_conflict_provenance():
    chunk_a = "a_chunk"
    chunk_b = "b_chunk"
    data_a = {
        "item_name": "Atlas Retriever",
        "description": "fault-tolerant retrieval service",
        "category": "retrieval",
    }
    data_b = {
        "item_name": "  atlas   retriever ",
        "description": "resilient retrieval platform",
        "category": "retrieval",
    }
    record_a = _record(SOURCE_A, chunk_a, "record-a", data_a, description_confidence=0.9)
    record_b = _record(SOURCE_B, chunk_b, "record-b", data_b, description_confidence=0.7)
    state = {
        "approved_dataset_schema": _schema(identity_fields=["item_name"]),
        "document_chunks": [
            _chunk(SOURCE_A, chunk_a, "Atlas Retriever fault-tolerant retrieval service retrieval"),
            _chunk(SOURCE_B, chunk_b, "atlas retriever resilient retrieval platform retrieval"),
        ],
        "quality_gate_metrics": {"accepted_records": 2},
        "quality_approved_extraction_batches": [
            _batch(SOURCE_A, chunk_a, [record_a]),
            _batch(SOURCE_B, chunk_b, [record_b]),
        ],
        "record_quality_assessments": [
            _quality(SOURCE_A, "record-a", 0.9),
            _quality(SOURCE_B, "record-b", 0.8),
        ],
        "errors": [],
    }

    result = record_resolution_node(state)

    assert result["status"] == "resolving_records"
    assert len(result["resolved_records"]) == 1
    resolved = result["resolved_records"][0]
    assert resolved["resolution_method"] == "explicit_identity"
    assert resolved["source_urls"] == [SOURCE_A, SOURCE_B]
    assert {(item["source_url"], item["local_record_id"]) for item in resolved["contributors"]} == {
        (SOURCE_A, "record-a"),
        (SOURCE_B, "record-b"),
    }
    assert {
        item["source_url"]
        for item in resolved["field_evidence"]["item_name"]
    } == {SOURCE_A, SOURCE_B}
    assert resolved["data"]["description"] == data_a["description"]
    assert resolved["merge_conflicts"][0]["incoming_source_url"] == SOURCE_B
    assert resolved["merge_conflicts"][0]["existing_value"] == data_a["description"]
    assert resolved["merge_conflicts"][0]["incoming_value"] == data_b["description"]
    assert resolved["evidence_quality_score"] == 0.8
    assert result["record_resolution_metrics"]["cross_source_records"] == 1

    enriched = metadata_enrichment_node({
        **state,
        **result,
        "dataset_topic": "Retrievers",
        "classified_data": [
            {
                "source": SOURCE_A,
                "cleaned_content": state["document_chunks"][0]["content"],
                "metadata": {},
            },
            {
                "source": SOURCE_B,
                "cleaned_content": state["document_chunks"][1]["content"],
                "metadata": {},
            },
        ],
    })
    metadata = enriched["enriched_data"][0]["metadata"]
    assert metadata["source_urls"] == [SOURCE_A, SOURCE_B]
    assert len(metadata["contributors"]) == 2
    assert len(metadata["field_evidence"]["item_name"]) == 2


def test_inferred_normalized_name_merges_when_schema_has_no_explicit_identity():
    records = [
        _record(SOURCE_A, "a", "a", {
            "item_name": "Orbit Parser", "description": "Unicode parser"
        }),
        _record(SOURCE_B, "b", "b", {
            "item_name": " orbit   parser ", "description": "Unicode parser"
        }),
    ]
    state = {
        "approved_dataset_schema": _schema(),
        "document_chunks": [
            _chunk(SOURCE_A, "a", "Orbit Parser Unicode parser"),
            _chunk(SOURCE_B, "b", "orbit parser Unicode parser"),
        ],
        "quality_gate_metrics": {"accepted_records": 2},
        "quality_approved_extraction_batches": [
            _batch(SOURCE_A, "a", [records[0]]),
            _batch(SOURCE_B, "b", [records[1]]),
        ],
        "errors": [],
    }

    result = record_resolution_node(state)

    assert len(result["resolved_records"]) == 1
    assert result["resolved_records"][0]["resolution_method"] == "normalized_identity"


def test_composite_identity_merges_only_records_with_every_configured_component():
    schema = _schema(
        identity_fields=["manufacturer", "model_code"], composite=True
    )
    records = [
        _record(SOURCE_A, "a", "a-1", {
            "manufacturer": "Acme", "model_code": "XR-1", "description": "First"
        }),
        _record(SOURCE_B, "b", "b-1", {
            "manufacturer": " acme ", "model_code": "xr-1", "description": "Second"
        }),
        _record(SOURCE_B, "b", "b-2", {
            "manufacturer": "Acme", "model_code": "XR-2", "description": "Third"
        }),
        _record(SOURCE_B, "b", "b-missing", {
            "manufacturer": "Acme", "description": "Missing model code"
        }),
    ]
    state = {
        "approved_dataset_schema": schema,
        "document_chunks": [
            _chunk(SOURCE_A, "a", "Acme XR-1 First"),
            _chunk(SOURCE_B, "b", "acme xr-1 Second Acme XR-2 Third Missing model code"),
        ],
        "quality_gate_metrics": {"accepted_records": 4},
        "quality_approved_extraction_batches": [
            _batch(SOURCE_A, "a", [records[0]]),
            _batch(SOURCE_B, "b", records[1:]),
        ],
        "errors": [],
    }

    result = record_resolution_node(state)

    assert len(result["resolved_records"]) == 3
    assert result["record_resolution_metrics"]["method_counts"] == {
        "explicit_identity": 0,
        "normalized_identity": 0,
        "composite_identity": 2,
        "local_record": 1,
    }


def test_no_generic_identity_keeps_same_data_from_different_sources_distinct():
    schema = {
        **_schema(),
        "fields": [
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
    }
    record_a = _record(SOURCE_A, "a", "local", {"description": "Same text"})
    record_b = _record(SOURCE_B, "b", "local", {"description": "Same text"})
    state = {
        "approved_dataset_schema": schema,
        "document_chunks": [
            _chunk(SOURCE_A, "a", "Same text"),
            _chunk(SOURCE_B, "b", "Same text"),
        ],
        "quality_gate_metrics": {"accepted_records": 2},
        "quality_approved_extraction_batches": [
            _batch(SOURCE_A, "a", [record_a]),
            _batch(SOURCE_B, "b", [record_b]),
        ],
        "errors": [],
    }

    result = record_resolution_node(state)

    assert len(result["resolved_records"]) == 2
    assert all(
        item["resolution_method"] == "local_record"
        for item in result["resolved_records"]
    )


@pytest.mark.parametrize("identity_fields", [["missing_field"], ["category"]])
def test_invalid_identity_contract_fails_during_schema_validation(identity_fields):
    schema = _schema(identity_fields=identity_fields)
    if identity_fields == ["category"]:
        schema["fields"][2]["type"] = "array[string]"

    with pytest.raises(ValueError, match="Identity field"):
        ApprovedDatasetSchema.model_validate(schema)
