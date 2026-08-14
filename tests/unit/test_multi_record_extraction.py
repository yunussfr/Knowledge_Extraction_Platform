"""Phase 15 zero/one/many extraction and downstream record migration tests."""

import json
from pathlib import Path
import re

import pytest

from src.agents.nodes.deduplication_node import deduplication_node
from src.agents.nodes.export_node import export_node
from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.quality_analysis_node import quality_analysis_node
from src.agents.nodes.record_merge_node import record_merge_node
from src.agents.nodes.structured_extraction_node import structured_extraction_node
from src.agents.nodes.validation_node import validation_node
from src.core.settings import settings
from src.schemas.models import EvidenceRef, ExtractedRecord, ExtractionBatch
from src.tools.groq_client import GroqClient


SOURCE_URL = "https://fixtures.example/catalog/multi"
CHUNK_ID = "source_001_chunk_001"


def _schema() -> dict:
    return {
        "name": "catalog",
        "description": "Catalog records.",
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
                "extraction_instruction": "Extract category only when present.",
            },
        ],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _state(content: str = "Alpha item evidence. Beta item evidence.") -> dict:
    return {
        "approved_dataset_schema": _schema(),
        "config": {"quality": {"minimum_confidence": 0.7}},
        "document_chunks": [{
            "chunk_id": CHUNK_ID,
            "source_url": SOURCE_URL,
            "source_title": "Multi fixture",
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "token_count": max(1, len(content.split())),
            "source_metadata": {"source_provider": "crawl4ai"},
        }],
        "errors": [],
    }


def _record(index: int, *, category: bool = True) -> dict:
    data = {
        "item_name": f"Item {index}",
        "description": f"Description {index}",
    }
    if category:
        data["category"] = "fixture"
    return {
        "local_record_id": f"provider-record-{index}",
        "data": data,
        "confidence": 0.9,
        "field_confidence": {field: 0.9 for field in data},
        "field_evidence": {},
        "extraction_method": "semantic",
    }


@pytest.fixture
def live_provider(monkeypatch):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    yield monkeypatch
    object.__setattr__(settings, "data_source_provider", original_provider)


@pytest.mark.parametrize("record_count", [0, 1, 2, 7])
def test_semantic_chunk_returns_zero_one_two_or_many_without_truncation(
    live_provider, record_count
):
    captured = {}

    def complete_json(_, system_prompt, user_prompt, output_model, **kwargs):
        captured["prompt"] = user_prompt
        captured["model"] = output_model
        return output_model(records=[_record(index) for index in range(record_count)])

    live_provider.setattr(GroqClient, "complete_json", complete_json)
    result = structured_extraction_node(_state())

    assert captured["model"] is ExtractionBatch
    assert "zero, one, or every distinct" in captured["prompt"]
    assert result["status"] == "extracting_data"
    assert len(result["extraction_batches"]) == 1
    assert len(result["extraction_batches"][0]["records"]) == record_count
    assert len(result["chunk_extraction_results"]) == record_count
    assert [
        item["data"]["item_name"] for item in result["extraction_batches"][0]["records"]
    ] == [f"Item {index}" for index in range(record_count)]


def test_mixed_valid_invalid_provider_records_are_isolated_not_batch_fatal(live_provider):
    def complete_json(_, system_prompt, user_prompt, output_model, **kwargs):
        return output_model(records=[
            _record(1),
            {"local_record_id": "invalid", "data": "not-an-object", "confidence": 0.9},
            _record(2),
        ])

    live_provider.setattr(GroqClient, "complete_json", complete_json)
    result = structured_extraction_node(_state())

    assert len(result["extraction_batches"][0]["records"]) == 2
    assert len(result["chunk_extraction_results"]) == 2
    assert len(result["extraction_warnings"]) == 1
    assert "Record 1 was rejected" in result["extraction_warnings"][0]


def test_offline_mock_path_also_preserves_configured_many_records(monkeypatch):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    state = _state()
    state["document_chunks"][0]["source_metadata"]["mock_extraction_records"] = [
        _record(index)["data"] for index in range(4)
    ]
    try:
        result = structured_extraction_node(state)
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert len(result["extraction_batches"][0]["records"]) == 4
    assert len(result["chunk_extraction_results"]) == 4


def test_missing_optional_is_accepted_while_missing_required_and_wrong_type_reject():
    batch = ExtractionBatch(
        source_url=SOURCE_URL,
        segment_id=CHUNK_ID,
        chunk_id=CHUNK_ID,
        records=[
            ExtractedRecord(
                local_record_id="valid-missing-optional",
                source_url=SOURCE_URL,
                chunk_id=CHUNK_ID,
                source_chunk_id=CHUNK_ID,
                data={"item_name": "Orbit Parser", "description": "Unicode-safe parser"},
                confidence=0.95,
            ),
            ExtractedRecord(
                local_record_id="missing-required",
                source_url=SOURCE_URL,
                chunk_id=CHUNK_ID,
                source_chunk_id=CHUNK_ID,
                data={"item_name": "Missing Description"},
                confidence=0.95,
            ),
            ExtractedRecord(
                local_record_id="wrong-type",
                source_url=SOURCE_URL,
                chunk_id=CHUNK_ID,
                source_chunk_id=CHUNK_ID,
                data={"item_name": 123, "description": "Wrong identity type"},
                confidence=0.95,
            ),
        ],
    )
    state = {
        **_state("Orbit Parser Unicode-safe parser Missing Description Wrong identity type"),
        "extraction_batches": [batch.model_dump(mode="json")],
    }
    merged = record_merge_node(state)
    enriched = metadata_enrichment_node({
        **state,
        **merged,
        "classified_data": [{
            "source": SOURCE_URL,
            "title": "Multi fixture",
            "cleaned_content": state["document_chunks"][0]["content"],
            "metadata": {"source_provider": "crawl4ai"},
        }],
    })
    validated = validation_node({**state, **merged, **enriched})

    assert len(merged["merged_records"]) == 3
    assert [item["data"]["item_name"] for item in validated["accepted_records"]] == [
        "Orbit Parser"
    ]
    assert len(validated["rejected_records"]) == 2
    reasons = [reason for item in validated["rejected_records"] for reason in item["reasons"]]
    assert "Missing required field: description" in reasons
    assert "Field item_name must be string." in reasons


def test_zero_record_batch_does_not_become_a_synthetic_rejected_source_record():
    state = {
        **_state("Navigation only"),
        "extraction_batches": [ExtractionBatch(
            source_url=SOURCE_URL,
            segment_id=CHUNK_ID,
            chunk_id=CHUNK_ID,
            records=[],
        ).model_dump(mode="json")],
        "classified_data": [{
            "source": SOURCE_URL,
            "cleaned_content": "Navigation only",
            "metadata": {"source_provider": "crawl4ai"},
        }],
        "rejected_records": [],
    }
    merged = record_merge_node(state)
    enriched = metadata_enrichment_node({**state, **merged})
    validated = validation_node({**state, **merged, **enriched})

    assert merged["merged_records"] == []
    assert enriched["enriched_data"] == []
    assert validated["accepted_records"] == []
    assert validated["rejected_records"] == []


def test_repeated_evidence_and_duplicate_candidates_merge_without_losing_record_ids():
    evidence = EvidenceRef(
        source_url=SOURCE_URL,
        chunk_id=CHUNK_ID,
        evidence_text="Orion Store",
    )
    records = [ExtractedRecord(
        local_record_id=local_id,
        source_url=SOURCE_URL,
        segment_id=CHUNK_ID,
        chunk_id=CHUNK_ID,
        source_chunk_id=CHUNK_ID,
        data={"item_name": "Orion Store", "description": "Versioned feature store"},
        confidence=0.9,
        field_evidence={"item_name": [evidence, evidence]},
    ) for local_id in ("candidate-a", "candidate-b")]
    batch = ExtractionBatch(
        source_url=SOURCE_URL,
        segment_id=CHUNK_ID,
        chunk_id=CHUNK_ID,
        records=records,
    )

    merged = record_merge_node({
        **_state("Orion Store Versioned feature store"),
        "extraction_batches": [batch.model_dump(mode="json")],
    })

    assert len(merged["merged_records"]) == 1
    result = merged["merged_records"][0]
    assert result["contributing_record_ids"] == ["candidate-a", "candidate-b"]
    assert result["field_evidence"]["item_name"] == [{
        "source_url": SOURCE_URL,
        "chunk_id": CHUNK_ID,
        "evidence_text": "Orion Store",
    }]


def test_many_records_survive_merge_metadata_quality_validation_dedup_and_export(tmp_path):
    records = [ExtractedRecord(
        local_record_id=f"record-{index}",
        source_url=SOURCE_URL,
        segment_id=CHUNK_ID,
        chunk_id=CHUNK_ID,
        source_chunk_id=CHUNK_ID,
        data={"item_name": f"Item {index}", "description": f"Description {index}"},
        confidence=0.9,
        extraction_method="semantic",
    ) for index in range(7)]
    batch = ExtractionBatch(
        source_url=SOURCE_URL,
        segment_id=CHUNK_ID,
        chunk_id=CHUNK_ID,
        records=records,
    )
    content = " ".join(
        f"Item {index} Description {index}" for index in range(7)
    )
    state = {
        **_state(content),
        "domain": "fixtures",
        "dataset_name": "multi_records",
        "dataset_topic": "Fixture items",
        "config": {
            "quality": {"minimum_confidence": 0.7},
            "output": {"format": "json", "directory": str(tmp_path)},
        },
        "extraction_batches": [batch.model_dump(mode="json")],
        "classified_data": [{
            "source": SOURCE_URL,
            "title": "Multi fixture",
            "cleaned_content": content,
            "metadata": {"source_provider": "crawl4ai"},
        }],
        "rejected_records": [],
    }

    merged = record_merge_node(state)
    enriched = metadata_enrichment_node({**state, **merged})
    quality = quality_analysis_node({**state, **merged, **enriched})
    validated = validation_node({**state, **merged, **quality})
    deduplicated = deduplication_node({**state, **validated})
    exported = export_node({**state, **validated, **deduplicated})

    assert len(merged["merged_records"]) == 7
    assert len(enriched["enriched_data"]) == 7
    assert len(quality["enriched_data"]) == 7
    assert len(validated["accepted_records"]) == 7
    assert len(deduplicated["accepted_records"]) == 7
    assert exported["status"] == "completed"
    assert len(json.loads((tmp_path / "multi_records.json").read_text(encoding="utf-8"))) == 7


def test_core_extraction_paths_contain_no_first_record_cap():
    project_root = Path(__file__).resolve().parents[2]
    for relative_path in (
        "src/agents/nodes/extraction_router_node.py",
        "src/agents/nodes/structured_extraction_node.py",
        "src/agents/nodes/record_merge_node.py",
    ):
        source = (project_root / relative_path).read_text(encoding="utf-8")
        assert re.search(r"records\s*\[\s*0\s*\]", source) is None
        assert re.search(r"records\s*\[\s*:\s*1\s*\]", source) is None
