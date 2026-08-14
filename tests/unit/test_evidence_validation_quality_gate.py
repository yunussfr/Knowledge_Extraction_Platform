"""Phase 18 evidence status and confidence-independent quality gate tests."""

from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.agents.nodes.evidence_validation_node import evidence_validation_node
from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.quality_gate_node import quality_gate_node
from src.agents.nodes.record_merge_node import record_merge_node
from src.agents.nodes.validation_node import validation_node
from src.core.settings import settings
from src.schemas.models import ExtractionBatch
from src.state.state import create_initial_state


SOURCE_URL = "https://fixtures.example/phase18/statuses"
CHUNK_ID = "phase18_chunk_001"


def _schema() -> dict:
    return {
        "name": "phase18_statuses",
        "description": "Evidence status fixtures.",
        "fields": [
            {
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "Item name.",
                "extraction_instruction": "Extract the item name.",
            },
            {
                "field_name": "description",
                "type": "string",
                "required": True,
                "description": "Item description.",
                "extraction_instruction": "Extract the description.",
            },
            {
                "field_name": "category",
                "type": "string",
                "required": False,
                "nullable": True,
                "description": "Optional category.",
                "extraction_instruction": "Extract only an explicit category.",
            },
            {
                "field_name": "enabled",
                "type": "boolean",
                "required": False,
                "nullable": True,
                "description": "Optional enabled state.",
                "extraction_instruction": "Extract only an explicit state.",
            },
        ],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _evidence(text: str) -> dict:
    return {
        "source_url": SOURCE_URL,
        "chunk_id": CHUNK_ID,
        "evidence_text": text,
    }


def _record(
    local_record_id: str,
    data: dict,
    field_evidence: dict,
    *,
    confidence: float = 0.9,
) -> dict:
    return {
        "local_record_id": local_record_id,
        "source_url": SOURCE_URL,
        "segment_id": CHUNK_ID,
        "chunk_id": CHUNK_ID,
        "source_chunk_id": CHUNK_ID,
        "data": data,
        "confidence": confidence,
        "field_confidence": {field_name: confidence for field_name in data},
        "field_evidence": field_evidence,
        "extraction_method": "semantic",
    }


def _state(records: list[dict]) -> dict:
    content = (
        "Alpha Engine is a compact runtime. Category: runtime. "
        "Delta Tool is a documented runtime. Category is omitted. "
        "Missing Tool appears without factual detail. "
        "Toggle Tool is a feature switch. Enabled: false."
    )
    batch = ExtractionBatch.model_validate({
        "source_url": SOURCE_URL,
        "segment_id": CHUNK_ID,
        "chunk_id": CHUNK_ID,
        "records": records,
    })
    return {
        "approved_dataset_schema": _schema(),
        "document_chunks": [{
            "chunk_id": CHUNK_ID,
            "source_url": SOURCE_URL,
            "source_title": "Phase 18 fixtures",
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "token_count": len(content.split()),
            "source_metadata": {"source_provider": "fixture"},
        }],
        "evidenced_extraction_batches": [batch.model_dump(mode="json")],
        "source_evaluations": [{"url": SOURCE_URL, "final_score": 0.8}],
        "config": {"quality": {"minimum_evidence_quality": 0.7}},
        "rejected_records": [],
        "errors": [],
    }


def _status_records() -> list[dict]:
    return [
        _record(
            "supported",
            {
                "item_name": "Alpha Engine",
                "description": "compact runtime",
                "category": "runtime",
            },
            {
                "item_name": [_evidence("Alpha Engine")],
                "description": [_evidence("compact runtime")],
                "category": [_evidence("Category: runtime")],
            },
        ),
        _record(
            "partial",
            {
                "item_name": "Delta Tool",
                "description": "documented runtime",
                "category": "model",
            },
            {
                "item_name": [_evidence("Delta Tool")],
                "description": [_evidence("documented runtime")],
                "category": [_evidence("Category is omitted")],
            },
        ),
        _record(
            "unsupported",
            {
                "item_name": "Missing Tool",
                "description": "invented description",
            },
            {"item_name": [_evidence("Missing Tool")]},
        ),
        _record(
            "contradicted",
            {
                "item_name": "Toggle Tool",
                "description": "feature switch",
                "enabled": True,
            },
            {
                "item_name": [_evidence("Toggle Tool")],
                "description": [_evidence("feature switch")],
                "enabled": [_evidence("Enabled: false")],
            },
        ),
    ]


def test_deterministic_validation_assigns_all_four_support_statuses():
    result = evidence_validation_node(_state(_status_records()))

    assert result["status"] == "validating_evidence"
    assert {
        item["record"]["local_record_id"]: item["status"]
        for item in result["verified_records"]
    } == {
        "supported": "SUPPORTED",
        "partial": "PARTIALLY_SUPPORTED",
        "unsupported": "UNSUPPORTED",
        "contradicted": "CONTRADICTED",
    }
    partial = result["verified_records"][1]
    assert partial["field_validations"]["category"]["semantic_review_required"] is True
    assert result["evidence_validation_metrics"]["status_counts"] == {
        "SUPPORTED": 1,
        "PARTIALLY_SUPPORTED": 1,
        "UNSUPPORTED": 1,
        "CONTRADICTED": 1,
    }


def test_quality_gate_accepts_only_supported_records_and_excludes_confidence():
    state = _state(_status_records())
    verified = evidence_validation_node(state)
    gated = quality_gate_node({**state, **verified})

    assert [
        record["local_record_id"]
        for record in gated["quality_approved_extraction_batches"][0]["records"]
    ] == ["supported"]
    assert gated["quality_gate_metrics"]["accepted_records"] == 1
    assert gated["quality_gate_metrics"]["rejected_records"] == 3
    assert gated["quality_gate_metrics"]["unsupported_accepted_field_rate"] == 0.0
    assert gated["quality_gate_metrics"]["extractor_confidence_used"] is False
    assessment = gated["record_quality_assessments"][0]
    assert "extractor_confidence" not in assessment["components"]
    assert assessment["components"] == {
        "schema_validity": 1.0,
        "required_field_completeness": 1.0,
        "evidence_support_rate": 1.0,
        "source_score": 0.8,
        "provenance_completeness": 1.0,
        "duplicate_status": 0.5,
    }


def test_extractor_confidence_does_not_change_quality_score_or_acceptance():
    base_data = {"item_name": "Alpha Engine", "description": "compact runtime"}
    base_evidence = {
        "item_name": [_evidence("Alpha Engine")],
        "description": [_evidence("compact runtime")],
    }
    state = _state([
        _record("low-confidence", base_data, base_evidence, confidence=0.0),
        _record("high-confidence", base_data, base_evidence, confidence=1.0),
    ])
    verified = evidence_validation_node(state)
    gated = quality_gate_node({**state, **verified})

    assert [item["accepted"] for item in gated["record_quality_assessments"]] == [
        True,
        True,
    ]
    assert {
        item["final_quality_score"] for item in gated["record_quality_assessments"]
    } == {0.883333}


def test_later_schema_validation_does_not_reapply_confidence_as_final_gate():
    record = _record(
        "zero-confidence-supported",
        {"item_name": "Alpha Engine", "description": "compact runtime"},
        {
            "item_name": [_evidence("Alpha Engine")],
            "description": [_evidence("compact runtime")],
        },
        confidence=0.0,
    )
    state = _state([record])
    state["classified_data"] = [{
        "source": SOURCE_URL,
        "title": "Phase 18 fixtures",
        "cleaned_content": state["document_chunks"][0]["content"],
        "metadata": {"source_provider": "fixture"},
    }]
    verified = evidence_validation_node(state)
    gated = quality_gate_node({**state, **verified})
    merged = record_merge_node({**state, **verified, **gated})
    enriched = metadata_enrichment_node({**state, **verified, **gated, **merged})
    validated = validation_node({
        **state,
        **verified,
        **gated,
        **merged,
        **enriched,
    })

    assert len(validated["accepted_records"]) == 1
    metadata = validated["accepted_records"][0]["_metadata"]
    assert metadata["confidence_score"] == 0.0
    assert metadata["evidence_quality_score"] == 0.883333
    assert metadata["validation_method"] == "evidence_quality_gate_and_schema"


def test_compiled_graph_exposes_phase18_metrics_and_gold_quality_metadata(tmp_path):
    config = {
        "dataset": {
            "name": "phase18_graph",
            "topic": "Evidence quality",
            "purpose": "Graph integration proof",
        },
        "research": {"max_queries": 1, "max_sources": 1},
        "schema": {"require_user_approval": True},
        "quality": {"minimum_evidence_quality": 0.7},
        "output": {"format": "json", "directory": str(tmp_path)},
        "sources": [{
            "url": "https://example.test/phase18",
            "content": "Evidence-backed graph content.",
            "enabled": True,
        }],
    }
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        pipeline = build_phase2_pipeline()
        pending = pipeline.invoke(create_initial_state("phase18", config))
        completed = pipeline.approve_schema(pending)
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert completed["status"] == "completed"
    assert completed["evidence_validation_metrics"]["status_counts"]["SUPPORTED"] > 0
    assert completed["quality_gate_metrics"]["accepted_records"] > 0
    assert completed["quality_gate_metrics"]["extractor_confidence_used"] is False
    metadata = completed["accepted_records"][0]["_metadata"]
    assert metadata["evidence_quality_score"] >= 0.7
    assert metadata["evidence_support_statuses"] == ["SUPPORTED"]


def test_invalid_quality_gate_configuration_fails_clearly():
    state = _state([_status_records()[0]])
    verified = evidence_validation_node(state)
    state["config"]["quality"]["minimum_evidence_quality"] = 1.5

    result = quality_gate_node({**state, **verified})

    assert result["status"] == "failed"
    assert "minimum_evidence_quality must be a number from 0 to 1" in (
        result["errors"][-1]["error"]
    )
