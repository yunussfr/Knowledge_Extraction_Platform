"""Regression tests for chunked extraction, merge rules, and final validation."""

import pytest

from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.agents.nodes.record_merge_node import record_merge_node
from src.agents.nodes.structured_extraction_node import structured_extraction_node
from src.core.settings import settings
from src.schemas.models import ExtractionResult
from src.state.state import create_initial_state
from src.tools.groq_client import GroqClient


def _approved_schema() -> dict:
    return {
        "name": "dishes",
        "description": "Food-culture records.",
        "fields": [
            {
                "field_name": "dish_name",
                "type": "string",
                "required": True,
                "nullable": False,
                "is_array": False,
                "description": "The dish name.",
                "extraction_instruction": "Extract the named dish.",
            },
            {
                "field_name": "ingredients",
                "type": "array[string]",
                "required": False,
                "nullable": True,
                "is_array": True,
                "description": "Source-supported ingredients.",
                "extraction_instruction": "Extract only named ingredients.",
            },
            {
                "field_name": "cultural_significance",
                "type": "string",
                "required": False,
                "nullable": True,
                "is_array": False,
                "description": "Source-supported cultural context.",
                "extraction_instruction": "Extract only explicit cultural context.",
            },
        ],
        "schema_version": 1,
        "approved_at": "2026-08-11T00:00:00+00:00",
        "approved_by": "user",
    }


def _chunk(chunk_id: str, index: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_url": "https://example.test/source",
        "source_title": "Example source",
        "chunk_index": index,
        "total_chunks": 2,
        "heading": "Dishes",
        "content": f"Content for {chunk_id}.",
        "token_count": 6,
        "overlap_token_count": 0,
        "source_metadata": {"source_provider": "firecrawl"},
    }


def _result(chunk_id: str, index: int, data: dict, confidence: float, field_confidence: dict | None = None) -> dict:
    return ExtractionResult(
        source_url="https://example.test/source",
        source_chunk_id=chunk_id,
        chunk_index=index,
        total_chunks=2,
        data=data,
        confidence=confidence,
        field_confidence=field_confidence or {},
    ).model_dump()


@pytest.fixture
def live_provider(monkeypatch):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    yield monkeypatch
    object.__setattr__(settings, "data_source_provider", original_provider)


def test_structured_extractor_calls_groq_once_per_chunk(live_provider):
    calls = []

    def complete_json(_, system_prompt, user_prompt, output_model):
        calls.append((system_prompt, user_prompt))
        return output_model(data={"dish_name": "Analı Kızlı"}, confidence=0.91)

    live_provider.setattr(GroqClient, "complete_json", complete_json)
    result = structured_extraction_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "errors": [],
    })

    assert len(calls) == 2
    assert len(result["chunk_extraction_results"]) == 2
    assert {item["source_chunk_id"] for item in result["chunk_extraction_results"]} == {
        "source_001_chunk_001", "source_001_chunk_002"
    }
    assert all(item["confidence"] == 0.91 for item in result["chunk_extraction_results"])


def test_failed_chunk_does_not_discard_successful_chunk(live_provider):
    def complete_json(_, system_prompt, user_prompt, output_model):
        if "source_001_chunk_001" in user_prompt:
            raise RuntimeError("Simulated provider timeout")
        return output_model(data={"dish_name": "Analı Kızlı"}, confidence=0.88)

    live_provider.setattr(GroqClient, "complete_json", complete_json)
    result = structured_extraction_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "errors": [],
    })

    assert result["status"] == "extracting_data"
    assert len(result["chunk_extraction_results"]) == 1
    assert result["chunk_extraction_results"][0]["source_chunk_id"] == "source_001_chunk_002"
    assert result["errors"][-1]["chunk_id"] == "source_001_chunk_001"


def test_all_failed_chunks_produce_a_traceable_pipeline_failure(live_provider):
    def complete_json(_, system_prompt, user_prompt, output_model):
        raise RuntimeError("Simulated provider failure")

    live_provider.setattr(GroqClient, "complete_json", complete_json)
    result = structured_extraction_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "errors": [],
    })

    assert result["status"] == "failed"
    assert {error["chunk_id"] for error in result["errors"]} == {
        "source_001_chunk_001", "source_001_chunk_002"
    }


def test_partial_same_entity_results_merge_arrays_and_conservative_confidence():
    result = record_merge_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "chunk_extraction_results": [
            _result("source_001_chunk_001", 0, {"dish_name": "Analı Kızlı", "ingredients": ["bulgur"]}, 0.96),
            _result("source_001_chunk_002", 1, {
                "dish_name": "Analı Kızlı",
                "ingredients": ["bulgur", "kıyma"],
                "cultural_significance": "A traditional dish.",
            }, 0.78),
        ],
        "errors": [],
    })

    assert len(result["merged_records"]) == 1
    merged = result["merged_records"][0]
    assert merged["data"]["ingredients"] == ["bulgur", "kıyma"]
    assert merged["data"]["cultural_significance"] == "A traditional dish."
    assert merged["confidence"] == 0.78
    assert merged["contributing_chunk_ids"] == ["source_001_chunk_001", "source_001_chunk_002"]


def test_different_entities_are_never_merged_only_because_source_matches():
    result = record_merge_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "chunk_extraction_results": [
            _result("source_001_chunk_001", 0, {"dish_name": "Dish A"}, 0.9),
            _result("source_001_chunk_002", 1, {"dish_name": "Dish B"}, 0.9),
        ],
        "errors": [],
    })

    assert len(result["merged_records"]) == 2


def test_conflicting_scalar_is_explainably_retained_by_field_confidence():
    result = record_merge_node({
        "approved_dataset_schema": _approved_schema(),
        "document_chunks": [_chunk("source_001_chunk_001", 0), _chunk("source_001_chunk_002", 1)],
        "chunk_extraction_results": [
            _result("source_001_chunk_001", 0, {
                "dish_name": "Analı Kızlı", "cultural_significance": "First evidence."
            }, 0.9, {"cultural_significance": 0.92}),
            _result("source_001_chunk_002", 1, {
                "dish_name": "Analı Kızlı", "cultural_significance": "Conflicting evidence."
            }, 0.8, {"cultural_significance": 0.70}),
        ],
        "errors": [],
    })

    merged = result["merged_records"][0]
    assert merged["data"]["cultural_significance"] == "First evidence."
    assert merged["merge_conflicts"][0]["kept"] == "existing"


def test_long_mock_document_flows_through_chunks_merge_validation_and_export(tmp_path):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        content = " ".join("Evidence-backed detail about traditional coffee." for _ in range(100))
        config = {
            "dataset": {"name": "long_records", "topic": "Traditional coffee", "purpose": "Test"},
            "research": {"max_queries": 1, "max_sources": 1},
            "schema": {"require_user_approval": True},
            "extraction": {"chunking": {"enabled": True, "target_tokens": 30, "overlap_tokens": 6}},
            "quality": {"minimum_confidence": 0.7},
            "output": {"format": "json", "directory": str(tmp_path)},
            "sources": [{"url": "https://example.test/coffee", "content": content, "enabled": True}],
        }
        pipeline = build_phase2_pipeline()
        pending = pipeline.invoke(create_initial_state("coffee", config))
        completed = pipeline.approve_schema(pending)
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert completed["status"] == "completed"
    assert len(completed["document_chunks"]) > 1
    assert len(completed["chunk_extraction_results"]) == len(completed["document_chunks"])
    assert completed["merged_records"]
    assert completed["accepted_records"]
    assert all(record["_metadata"]["contributing_chunk_ids"] for record in completed["accepted_records"])
    assert (tmp_path / "long_records.json").is_file()
