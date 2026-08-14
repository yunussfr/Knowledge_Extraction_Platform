"""Phase 8 tests for explicitly bounded Crawl4AI site exploration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.agents.nodes.site_exploration_node import site_exploration_node
from src.core.config_loader import load_domain_config
from src.core.source_registry import CandidateRegistry
from src.schemas.models import DiscoveryOrigin, SiteExplorationConfiguration
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.models import DiscoveredPage


def _crawl_result(
    url: str,
    *,
    depth: int,
    parent_url: str | None,
    title: str = "",
    success: bool = True,
):
    return SimpleNamespace(
        url=url,
        success=success,
        metadata={
            "depth": depth,
            "parent_url": parent_url,
            "title": title,
        },
    )


def test_site_exploration_config_is_typed_and_disabled_by_default():
    assert SiteExplorationConfiguration().model_dump() == {
        "enabled": False,
        "max_seed_domains": 5,
        "max_depth": 2,
        "max_pages_per_domain": 25,
        "same_domain_only": True,
    }
    for domain in ["turkish_culture", "space_science"]:
        config = load_domain_config(domain)
        assert config["site_exploration"] == SiteExplorationConfiguration().model_dump()


@pytest.mark.parametrize(
    "invalid",
    [
        {"max_seed_domains": 0},
        {"max_depth": 0},
        {"max_pages_per_domain": 0},
    ],
)
def test_site_exploration_config_rejects_unbounded_or_empty_limits(invalid):
    with pytest.raises(ValidationError):
        SiteExplorationConfiguration.model_validate({"enabled": True, **invalid})


def test_provider_enforces_depth_domain_url_filter_and_duplicate_limits():
    start = "https://example.com/start"
    results = [
        _crawl_result(start, depth=0, parent_url=None, title="Start"),
        _crawl_result("https://example.com/a#one", depth=1, parent_url=start, title="A"),
        _crawl_result("https://EXAMPLE.com:443/a#two", depth=1, parent_url=start, title="A duplicate"),
        _crawl_result("https://example.com/b", depth=2, parent_url="https://example.com/a", title="B"),
        _crawl_result("https://example.com/too-deep", depth=3, parent_url="https://example.com/b"),
        _crawl_result("https://external.test/out", depth=1, parent_url=start),
        _crawl_result("https://example.com/report.pdf", depth=1, parent_url=start),
        _crawl_result("https://example.com/failed", depth=1, parent_url=start, success=False),
    ]
    captured = {}

    def load(url, **limits):
        captured["url"] = url
        captured.update(limits)
        return results

    provider = Crawl4AIAcquisitionProvider(exploration_loader=load)

    pages = provider.explore_site(
        "HTTPS://Example.COM:443/start#seed",
        query_terms=["technical", "technical", "details"],
        max_depth=2,
        max_pages=10,
        same_domain_only=True,
    )

    assert pages == [
        DiscoveredPage(
            url="https://example.com/a",
            title="A",
            depth=1,
            parent_url="https://example.com/start",
        ),
        DiscoveredPage(
            url="https://example.com/b",
            title="B",
            depth=2,
            parent_url="https://example.com/a",
        ),
    ]
    assert captured == {
        "url": "https://example.com/start",
        "query_terms": ["technical", "technical", "details"],
        "max_depth": 2,
        "max_pages": 10,
        "same_domain_only": True,
    }


def test_provider_hard_page_cap_applies_after_result_normalization():
    results = [
        _crawl_result(
            f"https://example.com/page-{index}",
            depth=1,
            parent_url="https://example.com/start",
        )
        for index in range(10)
    ]
    provider = Crawl4AIAcquisitionProvider(
        exploration_loader=lambda _url, **_kwargs: results
    )

    pages = provider.explore_site(
        "https://example.com/start",
        query_terms=[],
        max_depth=1,
        max_pages=3,
    )

    assert [page.url for page in pages] == [
        "https://example.com/page-0",
        "https://example.com/page-1",
        "https://example.com/page-2",
    ]


def test_provider_can_allow_external_pages_only_when_explicit():
    provider = Crawl4AIAcquisitionProvider(
        exploration_loader=lambda _url, **_kwargs: [
            _crawl_result(
                "https://external.test/page",
                depth=1,
                parent_url="https://example.com/start",
            )
        ]
    )

    pages = provider.explore_site(
        "https://example.com/start",
        query_terms=[],
        max_depth=1,
        max_pages=2,
        same_domain_only=False,
    )

    assert [page.url for page in pages] == ["https://external.test/page"]


@pytest.mark.parametrize(
    ("max_depth", "max_pages", "message"),
    [(0, 1, "max_depth"), (1, 0, "max_pages")],
)
def test_provider_rejects_missing_hard_bounds(max_depth, max_pages, message):
    provider = Crawl4AIAcquisitionProvider(exploration_loader=lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match=message):
        provider.explore_site(
            "https://example.com/start",
            query_terms=[],
            max_depth=max_depth,
            max_pages=max_pages,
        )


def _registry(*urls: str) -> CandidateRegistry:
    registry = CandidateRegistry()
    for index, url in enumerate(urls, start=1):
        registry.add(
            url,
            origin=DiscoveryOrigin(method="search", query=f"query {index}"),
            title=f"Candidate {index}",
            source_provider="fixture",
        )
    return registry


def test_exploration_node_updates_registry_with_site_origin_and_preserves_selection(monkeypatch):
    registry = _registry("https://example.com/start")

    class FixtureProvider:
        def explore_site(self, start_url, **kwargs):
            assert start_url == "https://example.com/start"
            assert kwargs == {
                "query_terms": ["topic", "topic details"],
                "max_depth": 2,
                "max_pages": 3,
                "same_domain_only": True,
            }
            return [
                DiscoveredPage(
                    url="https://example.com/related",
                    title="Related",
                    depth=1,
                    parent_url=start_url,
                ),
                DiscoveredPage(
                    url="https://example.com/deeper",
                    title="Deeper",
                    depth=2,
                    parent_url="https://example.com/related",
                ),
            ]

    monkeypatch.setattr(
        "src.agents.nodes.site_exploration_node.get_acquisition_provider",
        lambda: FixtureProvider(),
    )
    state = {
        "config": {"site_exploration": {
            "enabled": True,
            "max_seed_domains": 1,
            "max_depth": 2,
            "max_pages_per_domain": 3,
            "same_domain_only": True,
        }},
        "research_plan": {"subtopics": ["topic"], "search_queries": ["topic details"]},
        "source_registry": registry.as_serialized(),
        "candidate_sources": registry.as_pipeline_candidates(),
        "selected_sources": [registry.as_pipeline_candidates()[0]],
        "explored_site_starts": [],
        "site_exploration_results": [],
        "errors": [],
    }

    result = site_exploration_node(state)

    assert result["status"] == "site_exploration_complete"
    assert result["explored_site_starts"] == ["https://example.com/start"]
    assert len(result["source_registry"]) == 3
    related = result["source_registry"]["https://example.com/related"]
    assert related["selection_state"] == "pending"
    assert related["preview_status"] == "pending"
    assert related["discovery_origins"] == [{
        "method": "site_exploration",
        "query": None,
        "seed_url": "https://example.com/start",
        "parent_url": "https://example.com/start",
        "depth": 1,
        "source_provider": "crawl4ai",
    }]


def test_exploration_node_avoids_repeat_start_and_duplicate_results(monkeypatch):
    registry = _registry("https://one.example/start", "https://two.example/start")
    calls = []

    class FixtureProvider:
        def explore_site(self, start_url, **_kwargs):
            calls.append(start_url)
            return [
                DiscoveredPage(
                    url="https://shared.example/page#first",
                    depth=1,
                    parent_url=start_url,
                ),
                DiscoveredPage(
                    url="https://shared.example/page#second",
                    depth=1,
                    parent_url=start_url,
                ),
            ]

    monkeypatch.setattr(
        "src.agents.nodes.site_exploration_node.get_acquisition_provider",
        lambda: FixtureProvider(),
    )
    candidates = registry.as_pipeline_candidates()
    result = site_exploration_node({
        "config": {"site_exploration": {
            "enabled": True,
            "max_seed_domains": 2,
            "max_depth": 1,
            "max_pages_per_domain": 2,
            "same_domain_only": False,
        }},
        "research_plan": {},
        "source_registry": registry.as_serialized(),
        "candidate_sources": candidates,
        "selected_sources": candidates,
        "explored_site_starts": ["https://one.example/start"],
        "site_exploration_results": [],
        "errors": [],
    })

    assert calls == ["https://two.example/start"]
    assert len(result["site_exploration_results"]) == 1
    assert result["explored_site_starts"] == [
        "https://one.example/start",
        "https://two.example/start",
    ]


def test_exploration_node_continues_after_one_domain_failure(monkeypatch):
    registry = _registry("https://bad.example/start", "https://good.example/start")

    class FixtureProvider:
        def explore_site(self, start_url, **_kwargs):
            if "bad.example" in start_url:
                raise TimeoutError("domain timed out")
            return [DiscoveredPage(
                url="https://good.example/related",
                depth=1,
                parent_url=start_url,
            )]

    monkeypatch.setattr(
        "src.agents.nodes.site_exploration_node.get_acquisition_provider",
        lambda: FixtureProvider(),
    )
    candidates = registry.as_pipeline_candidates()
    result = site_exploration_node({
        "config": {"site_exploration": {
            "enabled": True,
            "max_seed_domains": 2,
            "max_depth": 1,
            "max_pages_per_domain": 2,
            "same_domain_only": True,
        }},
        "research_plan": {},
        "source_registry": registry.as_serialized(),
        "candidate_sources": candidates,
        "selected_sources": candidates,
        "explored_site_starts": [],
        "site_exploration_results": [],
        "errors": [],
    })

    assert result["status"] == "site_exploration_complete"
    assert len(result["site_exploration_results"]) == 1
    assert result["errors"] == [{
        "node": "site_exploration",
        "source_url": "https://bad.example/start",
        "error": "TimeoutError: domain timed out",
    }]


def test_disabled_exploration_never_constructs_provider(monkeypatch):
    monkeypatch.setattr(
        "src.agents.nodes.site_exploration_node.get_acquisition_provider",
        lambda: (_ for _ in ()).throw(AssertionError("provider must stay disabled")),
    )

    result = site_exploration_node({
        "config": {"site_exploration": {"enabled": False}},
        "errors": [],
    })

    assert result == {
        "status": "site_exploration_complete",
        "pipeline_status": "site_exploration_complete",
    }
