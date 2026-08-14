"""Phase 6 tests for canonical candidates and conservative URL identity."""

from __future__ import annotations

import json

import pytest

from src.agents.nodes.source_evaluator_node import source_evaluator_node
from src.agents.nodes.source_preview_node import source_preview_node
from src.agents.nodes.source_search_node import source_search_node
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry, normalize_candidate_url
from src.schemas.models import DiscoveryOrigin
from src.tools.web.models import DiscoveredSource


@pytest.mark.parametrize(
    ("raw_url", "canonical_url"),
    [
        (" HTTPS://Example.COM:443 ", "https://example.com/"),
        ("http://Example.COM:80/path#section", "http://example.com/path"),
        ("https://example.com/path?b=2&a=1#fragment", "https://example.com/path?b=2&a=1"),
        ("https://EXAMPLE.com./resource", "https://example.com/resource"),
    ],
)
def test_url_normalization_applies_only_safe_identity_rules(raw_url, canonical_url):
    assert normalize_candidate_url(raw_url) == canonical_url


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("http://example.com/page", "https://example.com/page"),
        ("https://example.com/Page", "https://example.com/page"),
        ("https://example.com/page", "https://example.com/page/"),
        ("https://example.com/page?a=1&b=2", "https://example.com/page?b=2&a=1"),
        ("https://example.com/page?tracking=1", "https://example.com/page"),
        ("https://example.com/page?", "https://example.com/page"),
    ],
)
def test_conservative_normalization_keeps_potentially_distinct_resources(first, second):
    assert normalize_candidate_url(first) != normalize_candidate_url(second)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com/page",
        "ftp://example.com/page",
        "https://user:secret@example.com/page",
        "https://example.com:invalid/page",
    ],
)
def test_invalid_or_credential_bearing_candidate_urls_are_rejected(url):
    with pytest.raises(ValueError):
        normalize_candidate_url(url)


def test_same_url_from_multiple_queries_becomes_one_candidate_with_all_origins():
    registry = CandidateRegistry()
    registry.add(
        "HTTPS://Example.COM:443/paper#abstract",
        origin=DiscoveryOrigin(method="search", query="attention paper", source_provider="fixture"),
        title="Attention Paper",
        source_provider="fixture",
    )
    registry.add(
        "https://example.com/paper",
        origin=DiscoveryOrigin(method="search", query="transformer derivation", source_provider="fixture"),
        description="A detailed derivation.",
        source_provider="fixture",
    )

    serialized = registry.as_serialized()
    assert len(registry) == 1
    candidate = serialized["https://example.com/paper"]
    assert candidate["original_urls"] == [
        "HTTPS://Example.COM:443/paper#abstract",
        "https://example.com/paper",
    ]
    assert [origin["query"] for origin in candidate["discovery_origins"]] == [
        "attention paper",
        "transformer derivation",
    ]
    assert candidate["title"] == "Attention Paper"
    assert candidate["description"] == "A detailed derivation."


def test_seed_and_search_origin_survive_on_one_canonical_candidate():
    registry = CandidateRegistry()
    registry.add(
        "https://example.com/reference#overview",
        origin=DiscoveryOrigin(
            method="seed",
            seed_url="https://example.com/reference#overview",
            source_provider="user",
        ),
        source_provider="user",
    )
    registry.add(
        "https://EXAMPLE.com:443/reference",
        origin=DiscoveryOrigin(
            method="search",
            query="reference implementation",
            source_provider="firecrawl",
        ),
        source_provider="firecrawl",
    )

    candidate = next(iter(registry.as_serialized().values()))
    assert candidate["user_seed"] is True
    assert candidate["source_providers"] == ["user", "firecrawl"]
    assert [origin["method"] for origin in candidate["discovery_origins"]] == [
        "seed",
        "search",
    ]
    pipeline_candidate = registry.as_pipeline_candidates()[0]
    assert pipeline_candidate["url"] == "https://example.com/reference"
    assert pipeline_candidate["user_supplied_reference"] is True
    assert pipeline_candidate["search_query"] == "reference implementation"


def test_duplicate_discovery_does_not_reset_completed_preview_work():
    registry = CandidateRegistry()
    registry.add(
        "https://example.com/page",
        origin=DiscoveryOrigin(method="search", query="first query"),
    )
    registry.set_preview_status("https://example.com/page", "completed")
    registry.add(
        "https://EXAMPLE.com:443/page#details",
        origin=DiscoveryOrigin(method="search", query="second query"),
    )

    candidate = next(iter(registry.as_serialized().values()))
    assert candidate["preview_status"] == "completed"
    assert len(candidate["discovery_origins"]) == 2
    assert registry.pending_preview_urls() == []


def test_registry_state_and_compatibility_projection_are_json_serializable():
    registry = CandidateRegistry()
    registry.add(
        "https://example.com/page",
        origin=DiscoveryOrigin(method="mock", source_provider="fixture"),
        source_provider="fixture",
        provider_metadata={"sdk_value": object()},
        candidate_metadata={"content": "Mock evidence.", "type": "web"},
    )

    serialized = registry.as_serialized()
    pipeline_candidate = registry.as_pipeline_candidates()[0]

    json.dumps(serialized)
    json.dumps(pipeline_candidate)
    assert pipeline_candidate["content"] == "Mock evidence."
    assert pipeline_candidate["canonical_url"] == "https://example.com/page"


def test_source_search_uses_canonical_count_and_preserves_query_and_seed_origins(monkeypatch):
    class DuplicateDiscoveryProvider:
        def search(self, query, *, limit):
            assert limit == 5
            url = (
                "HTTPS://Example.COM:443/research#summary"
                if query == "first query"
                else "https://example.com/research"
            )
            return [DiscoveredSource(
                url=url,
                title="Research",
                domain="example.com",
                source_provider="fixture",
            )]

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_search_node.get_discovery_provider",
        lambda: DuplicateDiscoveryProvider(),
    )
    try:
        result = source_search_node({
            "config": {
                "research": {"max_sources": 5},
                "sources": {"seed_urls": ["https://example.com/research#seed"]},
            },
            "research_plan": {"search_queries": ["first query", "second query"]},
            "source_registry": {},
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "sources_discovered"
    assert len(result["source_registry"]) == 1
    assert len(result["candidate_sources"]) == 1
    candidate = result["candidate_sources"][0]
    assert candidate["url"] == "https://example.com/research"
    assert candidate["user_seed"] is True
    assert [origin["method"] for origin in candidate["discovery_origins"]] == [
        "seed",
        "search",
        "search",
    ]
    assert [
        origin["query"] for origin in candidate["discovery_origins"] if origin["query"]
    ] == ["first query", "second query"]


def test_evaluator_updates_registry_selection_and_rejection_history():
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        searched = source_search_node({
            "config": {
                "research": {"max_sources": 1},
                "sources": [
                    {"url": "https://example.com/selected", "content": "Selected."},
                    {"url": "https://example.com/rejected", "content": "Rejected."},
                ],
            },
            "research_plan": {"search_queries": []},
            "source_registry": {},
            "errors": [],
        })
        previewed = source_preview_node({
            "config": searched.get("config", {}),
            "candidate_sources": searched["candidate_sources"],
            "source_registry": searched["source_registry"],
            "source_previews": [],
            "errors": [],
        })
        evaluated = source_evaluator_node({
            "config": {"research": {"max_sources": 1}},
            "candidate_sources": previewed["candidate_sources"],
            "source_registry": previewed["source_registry"],
            "source_previews": previewed["source_previews"],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    selected = evaluated["source_registry"]["https://example.com/selected"]
    rejected = evaluated["source_registry"]["https://example.com/rejected"]
    assert selected["evaluation_status"] == "completed"
    assert selected["selection_state"] == "selected"
    assert selected["selected"] is True
    assert rejected["evaluation_status"] == "completed"
    assert rejected["selection_state"] == "rejected"
    assert rejected["selected"] is False
    assert rejected["rejection_reasons"] == [
        "Eligible but deferred by the configured source limit."
    ]
