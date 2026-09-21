"""Unit tests for cross-encoder reranker node and candidate ID assignment."""

from __future__ import annotations

import pytest

from src.agents.nodes.source_evaluator_node import source_evaluator_node
from src.agents.nodes.source_reranker_node import source_reranker_node
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry
from src.schemas.models import (
    DiscoveryOrigin,
    EvaluatedSource,
    SourceEvaluationResult,
    SourceProfile,
)
from src.tools.reranker import MockRerankerProvider


class _MockEvaluatorProvider:
    provider_name = "mock_evaluator"

    def __init__(self, callback):
        self.callback = callback

    def generate(self, *, system_prompt, user_prompt, output_model, task_name):
        return self.callback(system_prompt, user_prompt, output_model)

    def metrics(self):
        return {"provider": "mock", "model": "test"}


def test_mock_reranker_provider_threshold_filtering():
    provider = MockRerankerProvider()
    candidates = [
        {
            "canonical_url": "https://example.com/turkish-music",
            "url": "https://example.com/turkish-music",
            "title": "Turkish Music and Classical Tradition",
            "description": "Historical development of Turkish classical and folk music.",
        },
        {
            "canonical_url": "https://example.com/random-topic",
            "url": "https://example.com/random-topic",
            "title": "Quantum Computing Fundamentals",
            "description": "Qubits, superposition, and quantum gates explained.",
        },
    ]

    result = provider.rerank(
        query="Turkish music history and culture",
        candidates=candidates,
        threshold=0.60,
    )

    assert len(result.accepted_items) == 1
    assert result.accepted_items[0].url == "https://example.com/turkish-music"
    assert result.accepted_items[0].candidate_id == "cand_1"
    assert result.accepted_items[0].passed_threshold is True

    assert len(result.rejected_items) == 1
    assert result.rejected_items[0].url == "https://example.com/random-topic"
    assert result.rejected_items[0].candidate_id is None
    assert result.rejected_items[0].passed_threshold is False
    assert "below minimum threshold" in (result.rejected_items[0].rejection_reason or "")


def test_source_reranker_node_uses_config_minimum_confidence():
    state = {
        "dataset_topic": "Turkish culture and Ottoman history",
        "config": {
            "quality": {
                "minimum_confidence": 0.55,
            },
        },
        "candidate_sources": [
            {
                "canonical_url": "https://example.com/ottoman-history",
                "url": "https://example.com/ottoman-history",
                "title": "Ottoman Culture and Heritage",
                "description": "Exploration of Ottoman Turkish history and cultural traditions.",
                "discovery_origins": [{"method": "search", "query": "ottoman"}],
            },
            {
                "canonical_url": "https://example.com/irrelevant",
                "url": "https://example.com/irrelevant",
                "title": "Car repair manual",
                "description": "Engine maintenance steps.",
                "discovery_origins": [{"method": "search", "query": "cars"}],
            },
        ],
    }

    result = source_reranker_node(state)
    assert result["status"] == "sources_reranked"
    accepted = result["candidate_sources"]
    assert len(accepted) == 1
    assert accepted[0]["url"] == "https://example.com/ottoman-history"
    assert accepted[0]["candidate_id"] == "cand_1"
    assert accepted[0]["reranker_score"] >= 0.55

    # Check that registry has the rejected candidate marked
    registry = CandidateRegistry(result["source_registry"])
    assert len(registry) == 2
    rejected_cand = registry._find("https://example.com/irrelevant")
    assert rejected_cand is not None
    assert rejected_cand.selection_state == "rejected"
    assert rejected_cand.preview_status == "skipped"


def test_source_evaluator_resolves_candidate_by_id(monkeypatch):
    """Verify that when a model outputs candidate_id instead of full URL, the evaluator resolves it."""
    candidate_url = "https://whc.unesco.org/en/statesparties/tr"
    state = {
        "dataset_topic": "Turkish World Heritage Sites",
        "candidate_sources": [
            {
                "url": candidate_url,
                "canonical_url": candidate_url,
                "candidate_id": "cand_1",
                "title": "UNESCO Turkey Sites",
                "description": "World heritage list for Turkey.",
            }
        ],
        "source_previews": [
            {
                "url": candidate_url,
                "title": "UNESCO Turkey Sites",
                "preview_text": "Turkey has 21 World Heritage sites.",
                "fetch_success": True,
            }
        ],
    }

    def _generate(system_prompt, user_prompt, output_model):
        # Model returns candidate_id = "cand_1" and omits or simplifies the URL
        return SourceEvaluationResult(
            evaluated_sources=[
                EvaluatedSource(
                    url="",  # Omitted by model
                    candidate_id="cand_1",  # Provided by model
                    source_profile=SourceProfile(
                        source_type="official_documentation",
                        content_depth="deep",
                    ),
                    topic_relevance_score=0.95,
                    reasons=["Highly authoritative UNESCO source."],
                )
            ]
        )

    monkeypatch.setattr(
        "src.agents.nodes.source_evaluator_node.get_source_evaluation_provider",
        lambda: _MockEvaluatorProvider(_generate),
    )
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    try:
        result = source_evaluator_node(state)
        assert result["status"] == "sources_evaluated"
        assert len(result["selected_sources"]) == 1
        # Evaluator resolved the URL correctly back to canonical URL
        assert result["selected_sources"][0]["url"] == candidate_url
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)


def test_score_normalization_1_to_5_scale():
    """Verify that scores on a 1-5 scale (from local LLMs) are automatically normalized to 0.0-1.0."""
    profile = SourceProfile(
        source_type="government",
        authority_score=3,  # 3 on 1-5 scale -> 0.60
        information_density_score=1.5,  # 1.5 on 1-5 scale -> 0.30
        technical_depth_score=2.5,  # 2.5 on 1-5 scale -> 0.50
        extractability_score=4.0,  # 4.0 on 1-5 scale -> 0.80
    )
    assert profile.authority_score == 0.60
    assert profile.information_density_score == 0.30
    assert profile.technical_depth_score == 0.50
    assert profile.extractability_score == 0.80

    evaluated = EvaluatedSource(
        url="https://example.com/test",
        source_profile=profile,
        topic_relevance_score=4.5,  # 4.5 on 1-5 scale -> 0.90
    )
    assert evaluated.topic_relevance_score == 0.90


def test_source_preview_node_returns_only_active_candidates():
    """Verify that source_preview_node only outputs active (rerank-accepted) candidates."""
    from src.agents.nodes.source_preview_node import source_preview_node

    registry = CandidateRegistry()
    c1 = registry.add("https://example.com/accepted", origin=DiscoveryOrigin(method="search", query="test query"), title="Accepted")
    c2 = registry.add("https://example.com/rejected", origin=DiscoveryOrigin(method="search", query="test query"), title="Rejected")
    c2.selection_state = "rejected"
    c2.preview_status = "skipped"

    state = {
        "source_registry": registry.as_serialized(),
        "candidate_sources": [c1.to_pipeline_candidate()],
        "source_previews": [],
    }

    result = source_preview_node(state)
    assert result["status"] == "sources_previewed"
    # Only the 1 active candidate is returned to candidate_sources
    assert len(result["candidate_sources"]) == 1
    assert result["candidate_sources"][0]["url"] == "https://example.com/accepted"
