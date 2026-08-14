"""Phase 3 tests for the policy-aware ResearchPlanner boundary."""

import json

import pytest

from src.agents.nodes.research_planner_node import (
    build_research_planner_input,
    research_planner_node,
)
from src.core.settings import settings
from src.schemas.models import ResearchPlan
from src.state.state import create_initial_state


def _config(source_policy=None, **source_overrides):
    sources = {
        "seed_urls": ["https://seed.example/reference"],
        "preferred_domains": ["preferred.example"],
        "source_policy": source_policy or {},
        **source_overrides,
    }
    return {
        "dataset": {
            "name": "planner_contract",
            "topic": "Attention implementations",
            "purpose": "Technical RAG dataset",
        },
        "research": {"max_queries": 4, "constraints": "Use source evidence.", "queries": []},
        "sources": sources,
    }


def test_neutral_policy_survives_planner_boundary_without_hidden_restrictions():
    planner_input = build_research_planner_input(
        create_initial_state("planner", _config())
    )

    assert planner_input.source_policy.preferred_source_types == []
    assert planner_input.source_policy.allowed_source_types is None
    assert planner_input.source_policy.blocked_source_types is None
    assert planner_input.allowed_domains is None
    assert planner_input.blocked_domains is None


def test_technical_depth_policy_and_dataset_purpose_are_available_to_planner():
    state = create_initial_state("planner", _config({
        "desired_content": ["implementation_details"],
        "importance": {"authority": "low", "technical_depth": "high"},
    }))
    planner_input = build_research_planner_input(state)

    assert planner_input.dataset_purpose == "Technical RAG dataset"
    assert planner_input.source_policy.desired_content == ["implementation_details"]
    assert planner_input.source_policy.importance.technical_depth == "high"
    assert planner_input.source_policy.importance.authority == "low"


def test_explicit_source_type_and_domain_restrictions_are_available_to_planner():
    state = create_initial_state("planner", _config(
        {
            "allowed_source_types": ["academic"],
            "blocked_source_types": ["social_media"],
        },
        allowed_domains=["allowed.example"],
        blocked_domains=["blocked.example"],
    ))
    planner_input = build_research_planner_input(state)

    assert planner_input.source_policy.allowed_source_types == ["academic"]
    assert planner_input.source_policy.blocked_source_types == ["social_media"]
    assert planner_input.allowed_domains == ["allowed.example"]
    assert planner_input.blocked_domains == ["blocked.example"]


def test_seed_url_and_soft_domain_preference_remain_distinct_at_planner_boundary():
    planner_input = build_research_planner_input(
        create_initial_state("planner", _config())
    )

    assert planner_input.seed_urls == ["https://seed.example/reference"]
    assert planner_input.preferred_domains == ["preferred.example"]
    assert planner_input.allowed_domains is None


def test_live_planner_user_input_serializes_absent_blocklist_as_null(monkeypatch):
    captured = {}

    def fake_complete_json(self, system_prompt, user_prompt, output_model):
        captured["payload"] = json.loads(user_prompt)["planner_input"]
        return ResearchPlan(
            research_topic="Attention implementations",
            subtopics=["kernels"],
            search_queries=["attention kernel implementation"],
            query_families=[{
                "name": "implementation",
                "queries": ["attention kernel implementation"],
            }],
        )

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.research_planner_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = research_planner_node(create_initial_state("planner", _config()))
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "research_plan_ready"
    assert captured["payload"]["source_policy"]["allowed_source_types"] is None
    assert captured["payload"]["source_policy"]["blocked_source_types"] is None
    assert captured["payload"]["allowed_domains"] is None
    assert captured["payload"]["blocked_domains"] is None


def test_mock_plan_is_source_type_neutral_and_deduplicates_queries():
    config = _config()
    config["research"]["queries"] = [
        "attention implementation",
        " Attention Implementation ",
        "attention benchmark",
    ]
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        result = research_planner_node(create_initial_state("planner", config))
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["research_plan"]["search_queries"] == [
        "attention implementation", "attention benchmark"
    ]
    assert result["research_plan"]["preferred_source_types"] == []
    assert result["research_plan"]["query_families"][0]["queries"] == [
        "attention implementation", "attention benchmark"
    ]


def test_duplicate_queries_across_query_families_are_rejected():
    with pytest.raises(ValueError, match="more than one family"):
        ResearchPlan.model_validate({
            "research_topic": "Attention",
            "search_queries": ["attention implementation"],
            "query_families": [
                {"name": "implementation", "queries": ["attention implementation"]},
                {"name": "benchmarks", "queries": ["Attention Implementation"]},
            ],
        })
