"""Tests for the real-source pipeline flow using deterministic mock providers."""

import pytest
import json

from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.agents.nodes.deduplication_node import deduplication_node
from src.agents.nodes.quality_analysis_node import quality_analysis_node
from src.agents.nodes.source_evaluator_node import _apply_evaluation
from src.agents.nodes.source_search_node import source_search_node
from src.agents.nodes.validation_node import validation_node
from src.core.config_loader import load_domain_config
from src.core.retry import is_retryable_provider_error
from src.core.settings import settings
from src.schemas.models import DatasetSchemaField, ExtractionResult, ResearchPlan, SourceEvaluationResult
from src.state.state import create_initial_state
from src.tools.firecrawl_tool import FirecrawlTool
from src.tools.groq_client import GroqClient


@pytest.fixture(autouse=True)
def force_mock_provider():
    """Keep this test module independent of a developer's local .env mode."""
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    yield
    object.__setattr__(settings, "data_source_provider", original_provider)


def _request_config(output_directory: str) -> dict:
    return {
        "dataset": {"name": "coffee_records", "topic": "Traditional coffee", "purpose": "Test data"},
        "research": {"queries": ["traditional coffee"], "max_sources": 2},
        "schema": {"require_user_approval": True},
        "quality": {"minimum_confidence": 0.7},
        "output": {"format": "json", "directory": output_directory},
        "sources": [
            {"url": "https://example.test/coffee", "title": "Coffee", "enabled": True},
        ],
    }


def test_pipeline_pauses_before_scraping_without_schema_approval(tmp_path):
    pipeline = build_phase2_pipeline()
    state = create_initial_state("coffee", _request_config(str(tmp_path)))

    pending = pipeline.invoke(state)

    assert pending["status"] == "waiting_for_schema_approval"
    assert pending["pipeline_status"] == "waiting_for_schema_approval"
    assert pending["selected_sources"]
    assert pending["raw_data"] == []
    assert pending["approved_dataset_schema"] == {}


def test_pipeline_resumes_after_domain_approval_and_exports_dataset(tmp_path):
    pipeline = build_phase2_pipeline()
    pending = pipeline.invoke(create_initial_state("coffee", _request_config(str(tmp_path))))

    completed = pipeline.approve_schema(pending)

    assert completed["status"] == "completed"
    assert completed["approved_dataset_schema"]["schema_version"] == 1
    assert completed["accepted_records"]
    assert completed["accepted_records"][0]["data"]["content"]
    assert (tmp_path / "coffee_records.json").exists()


def test_approval_rejects_invalid_edited_schema(tmp_path):
    pipeline = build_phase2_pipeline()
    pending = pipeline.invoke(create_initial_state("coffee", _request_config(str(tmp_path))))
    invalid_schema = {**pending["draft_dataset_schema"], "fields": [{
        "field_name": "content",
        "type": "unknown",
        "required": True,
        "nullable": False,
        "is_array": False,
        "description": "Content",
        "extraction_instruction": "Extract content.",
    }]}

    with pytest.raises(ValueError):
        pipeline.approve_schema(pending, invalid_schema)


def test_pending_approval_can_resume_after_process_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first_pipeline = build_phase2_pipeline()
    pending = first_pipeline.invoke(create_initial_state("coffee", _request_config(str(tmp_path))))
    review_path = first_pipeline.write_draft_review_file(pending)
    edited = json.loads(review_path.read_text(encoding="utf-8"))
    edited["fields"][0]["description"] = "Edited after the first process ended."
    review_path.write_text(json.dumps(edited), encoding="utf-8")

    restarted_pipeline = build_phase2_pipeline()
    resumed = restarted_pipeline.load_pending_review_state("coffee", "coffee_records")
    completed = restarted_pipeline.approve_schema(resumed, json.loads(review_path.read_text(encoding="utf-8")))

    assert completed["status"] == "completed"
    assert completed["approved_dataset_schema"]["fields"][0]["description"] == "Edited after the first process ended."


def test_deduplication_rejects_repeated_structured_data():
    first = {
        "data": {"content": "same"},
        "_metadata": {"source_url": "https://example.test/a", "contributing_chunk_ids": ["a_001"]},
    }
    duplicate = {
        "data": {"content": "same"},
        "_metadata": {"source_url": "https://example.test/b", "contributing_chunk_ids": ["b_001"]},
    }
    result = deduplication_node({"accepted_records": [first, duplicate], "rejected_records": [], "errors": []})

    assert len(result["accepted_records"]) == 1
    assert result["rejected_records"][0]["reasons"] == ["Duplicate extracted record; provenance merged into the retained record."]
    assert result["accepted_records"][0]["_metadata"]["source_urls"] == ["https://example.test/a", "https://example.test/b"]
    assert result["accepted_records"][0]["_metadata"]["contributing_chunk_ids"] == ["a_001", "b_001"]


def test_user_reference_url_is_retained_despite_domain_filter():
    result = source_search_node({
        "config": {
            "research": {
                "preferred_domains": ["preferred.example"],
                "reference_urls": ["https://manual.example/source"],
            },
            "sources": [{"url": "https://unwanted.example/source", "enabled": True}],
        },
        "research_plan": {"search_queries": []},
        "errors": [],
    })

    assert [source["url"] for source in result["candidate_sources"]] == ["https://manual.example/source"]
    assert result["candidate_sources"][0]["user_supplied_reference"] is True


def test_quality_report_includes_structured_extraction_confidence():
    result = quality_analysis_node({
        "enriched_data": [{
            "cleaned_content": "One two three four five six seven eight nine ten.",
            "entities": [{}],
            "relations": [{}],
            "metadata": {"confidence_score": 0.5},
        }],
        "config": {"quality": {"minimum_confidence": 0.7, "min_words": 1, "min_quality_score": 0.1}},
        "errors": [],
    })

    report = result["enriched_data"][0]["quality_report"]
    assert report["confidence"] == 0.5
    assert report["confidence_passed"] is False
    assert report["passed"] is False


def test_research_plan_accepts_camel_case_provider_output():
    plan = ResearchPlan.model_validate({
        "researchTopic": "Traditional coffee",
        "subTopics": ["history"],
        "searchQueries": ["coffee history"],
        "preferredSourceTypes": ["institutional"],
        "excludedSourceTypes": ["forums"],
    })

    assert plan.research_topic == "Traditional coffee"
    assert plan.search_queries == ["coffee history"]


def test_schema_field_accepts_camel_case_array_type():
    field = DatasetSchemaField.model_validate({
        "fieldName": "ingredients",
        "type": "array[string]",
        "required": False,
        "nullable": True,
        "description": "Ingredients",
        "extraction_instruction": "Extract only named ingredients.",
    })

    assert field.field_name == "ingredients"
    assert field.is_array is True


def test_extraction_result_derives_missing_overall_confidence_from_field_confidence():
    result = ExtractionResult.model_validate({
        "data": {"dish_name": "Analı Kızlı", "recipe": "Cook and serve."},
        "field_confidence": {"dish_name": 0.9, "recipe": 0.8},
    })

    assert result.confidence == pytest.approx(0.85)


def test_extraction_result_ignores_omitted_optional_field_for_fallback_confidence():
    result = ExtractionResult.model_validate({
        "data": {"dish_name": "Analı Kızlı"},
        "field_confidence": {"dish_name": 0.9, "recipe": 0.0},
    })

    assert result.confidence == 0.9


def test_extraction_result_keeps_explicit_overall_confidence():
    result = ExtractionResult.model_validate({
        "data": {"dish_name": "Analı Kızlı", "recipe": "Cook and serve."},
        "confidence": 0.65,
        "field_confidence": {"dish_name": 0.9, "recipe": 0.8},
    })

    assert result.confidence == 0.65


def test_extraction_result_still_rejects_a_response_with_no_confidence_evidence():
    with pytest.raises(ValueError, match="confidence"):
        ExtractionResult.model_validate({"data": {"dish_name": "Analı Kızlı"}})


def test_user_reference_becomes_manual_override_when_evaluator_selects_nothing():
    selected, rejected = _apply_evaluation(
        [{"url": "https://manual.example/source", "user_supplied_reference": True}],
        SourceEvaluationResult(),
    )

    assert rejected == []
    assert selected[0]["selection_origin"] == "manual_override"


def test_domain_config_loads_request_and_source_information():
    config = load_domain_config("turkish_culture")

    assert config["dataset"]["name"]
    assert "research" in config
    assert isinstance(config["sources"], list)


def test_provider_clients_fail_fast_when_api_keys_are_missing():
    original_groq_key = settings.groq_api_key
    original_firecrawl_key = settings.firecrawl_api_key
    object.__setattr__(settings, "groq_api_key", None)
    object.__setattr__(settings, "firecrawl_api_key", None)
    try:
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            GroqClient().complete_json("system", "user", ResearchPlan)
        with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
            FirecrawlTool()._client()
    finally:
        object.__setattr__(settings, "groq_api_key", original_groq_key)
        object.__setattr__(settings, "firecrawl_api_key", original_firecrawl_key)


def test_retry_policy_skips_authentication_errors_and_retries_transient_errors():
    class ProviderError(Exception):
        def __init__(self, message: str, status_code: int):
            super().__init__(message)
            self.status_code = status_code

    assert is_retryable_provider_error(ProviderError("Unauthorized", 401)) is False
    assert is_retryable_provider_error(ProviderError("Rate limit", 429)) is True


def test_empty_source_content_is_rejected_before_export():
    state = {
        "approved_dataset_schema": {
            "name": "empty_content",
            "description": "Test schema",
            "fields": [{
                "field_name": "content", "type": "string", "required": True,
                "nullable": False, "is_array": False, "description": "Content",
                "extraction_instruction": "Extract content.",
            }],
            "schema_version": 1,
            "approved_at": "2026-08-10T00:00:00+00:00",
            "approved_by": "user",
        },
        "enriched_data": [{
            "source": "https://example.test/empty",
            "cleaned_content": "",
            "extracted_data": {"content": ""},
            "metadata": {"confidence_score": 0.9},
        }],
        "config": {"quality": {"minimum_confidence": 0.7, "low_confidence_action": "reject"}},
        "rejected_records": [],
        "errors": [],
    }

    result = validation_node(state)

    assert result["validated_data"] == []
    assert result["rejected_records"][0]["reasons"] == ["Source content is empty."]


def test_jsonl_export_is_valid_serialized_output(tmp_path):
    config = _request_config(str(tmp_path))
    config["output"].update({"format": "jsonl", "save_raw_content": True, "save_clean_content": True})
    pipeline = build_phase2_pipeline()

    pending = pipeline.invoke(create_initial_state("coffee", config))
    completed = pipeline.approve_schema(pending)
    output_path = tmp_path / "coffee_records.jsonl"

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert completed["status"] == "completed"
    assert len(lines) == 1
    assert json.loads(lines[0])["data"]["content"]
    assert (tmp_path / "coffee_records_raw.json").exists()
    assert (tmp_path / "coffee_records_clean.json").exists()
