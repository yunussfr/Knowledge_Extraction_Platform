"""Phase 11 evidence-aware dataset schema design tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.agents.nodes.dataset_schema_designer_node import (
    build_dataset_schema_designer_input,
    dataset_schema_designer_node,
)
from src.core.settings import settings
from src.schemas.models import (
    DatasetSchemaField,
    DraftDatasetSchema,
    SourcePolicy,
)
from src.tools.web.models import SourcePreview


def _preview(url: str, text: str) -> dict:
    words = len(text.split())
    return SourcePreview(
        url=url,
        title=f"Title for {url}",
        domain=url.split("/")[2],
        headings=["Methods", "Results"],
        relevant_text=text,
        approximate_word_count=1000,
        preview_word_count=words,
        language="en",
        structure_hints=["headings", "table"],
        fetch_success=True,
    ).model_dump(mode="json")


def _state() -> dict:
    selected_url = "https://selected.example/evidence"
    other_url = "https://other.example/ignored"
    return {
        "dataset_name": "attention_records",
        "dataset_topic": "Attention implementation tradeoffs",
        "dataset_purpose": "RAG records for AI engineers",
        "research_plan": {
            "research_topic": "Attention implementation tradeoffs",
            "subtopics": ["kernels", "benchmarks"],
            "search_queries": ["attention kernel benchmark"],
        },
        "source_policy": SourcePolicy(
            desired_content=["implementation_details"],
        ).model_dump(mode="json"),
        "source_selections": [{
            "url": selected_url,
            "rank": 1,
            "selection_score": 0.91,
            "final_score": 0.90,
            "domain": "selected.example",
            "source_type": "independent_technical",
            "selection_reasons": ["Strong request-specific evidence."],
        }],
        "selected_sources": [{"url": selected_url, "priority": 1}],
        "source_previews": [
            _preview(selected_url, "Selected methods and benchmark evidence."),
            _preview(other_url, "This unselected evidence must not enter schema design."),
        ],
        "config": {
            "schema": {
                "constraints": "Create fields useful for retrieval and comparison."
            }
        },
        "errors": [],
    }


def _draft() -> DraftDatasetSchema:
    return DraftDatasetSchema(
        name="attention_records",
        description="Evidence-aware attention records.",
        fields=[DatasetSchemaField(
            field_name="implementation_detail",
            type="string",
            required=True,
            nullable=False,
            description="Observed implementation detail.",
            extraction_instruction="Extract only an implementation detail supported by content.",
        )],
    )


def test_schema_input_contains_full_request_and_only_final_selected_previews():
    designer_input = build_dataset_schema_designer_input(_state())

    assert designer_input.dataset_topic == "Attention implementation tradeoffs"
    assert designer_input.dataset_purpose == "RAG records for AI engineers"
    assert designer_input.research_plan.search_queries == ["attention kernel benchmark"]
    assert designer_input.source_policy.desired_content == ["implementation_details"]
    assert designer_input.user_schema_constraints.startswith("Create fields")
    assert [item.url for item in designer_input.selected_source_previews] == [
        "https://selected.example/evidence"
    ]
    assert designer_input.selected_source_previews[0].source_rank == 1
    assert designer_input.selected_source_previews[0].selection_score == 0.91


def test_live_schema_payload_is_typed_json_with_selected_real_evidence(monkeypatch):
    captured = {}

    def fake_complete_json(self, system_prompt, user_prompt, output_model):
        captured["payload"] = json.loads(user_prompt)
        captured["output_model"] = output_model
        return _draft()

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.dataset_schema_designer_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = dataset_schema_designer_node(_state())
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "waiting_for_schema_approval"
    assert captured["output_model"] is DraftDatasetSchema
    payload = captured["payload"]
    schema_input = payload["schema_designer_input"]
    assert schema_input["source_policy"]["desired_content"] == [
        "implementation_details"
    ]
    assert schema_input["selected_source_previews"][0]["relevant_text"] == (
        "Selected methods and benchmark evidence."
    )
    assert "unselected evidence" not in json.dumps(payload)
    assert "draft_dataset_schema_contract" in payload
    assert result["schema_design_input"] == schema_input


def test_schema_design_fails_if_final_selection_has_no_successful_preview(monkeypatch):
    state = _state()
    state["source_previews"] = state["source_previews"][1:]
    called = False

    def fake_complete_json(*args, **kwargs):
        nonlocal called
        called = True
        return _draft()

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.dataset_schema_designer_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = dataset_schema_designer_node(state)
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "failed"
    assert "lacks a successful bounded preview" in result["errors"][-1]["error"]
    assert called is False


@pytest.mark.parametrize(
    "field_name",
    ["source_url", "retrieved_at", "schema_version", "contributing_chunk_ids"],
)
def test_normal_provenance_fields_are_rejected_from_domain_schema(field_name):
    with pytest.raises(ValidationError, match="provenance belongs in record metadata"):
        DraftDatasetSchema(
            name="invalid",
            description="Invalid provenance placement.",
            fields=[DatasetSchemaField(
                field_name=field_name,
                type="string",
                description="Normal provenance field.",
                extraction_instruction="Do not extract this into domain data.",
            )],
        )


def test_mock_schema_still_waits_for_human_approval_and_stores_design_context():
    state = _state()
    state["config"]["schema"]["fields"] = [
        _draft().fields[0].model_dump(mode="json")
    ]

    result = dataset_schema_designer_node(state)

    assert result["status"] == "waiting_for_schema_approval"
    assert result["draft_dataset_schema"]["fields"][0]["field_name"] == (
        "implementation_detail"
    )
    assert result["schema_design_input"]["selected_source_previews"]
