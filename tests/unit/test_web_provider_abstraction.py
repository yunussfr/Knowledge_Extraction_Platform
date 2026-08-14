"""Phase 4 tests for provider-neutral web contracts and node boundaries."""

from datetime import datetime, timezone
from pathlib import Path

from src.agents.nodes.acquisition_node import acquisition_node
from src.agents.nodes.source_search_node import source_search_node
from src.core.settings import settings
from src.tools.web.acquisition_provider import WebAcquisitionProvider
from src.tools.web import get_acquisition_provider
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.discovery_provider import SourceDiscoveryProvider
from src.tools.web.firecrawl_provider import FirecrawlDiscoveryProvider
from src.tools.web.models import AcquiredDocument, DiscoveredSource


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeFirecrawlTool:
    def search(self, query, limit):
        assert query == "attention implementation"
        assert limit == 3
        return [{
            "url": "https://provider.example/attention",
            "title": "Attention",
            "description": "Implementation details",
            "sdk_only_field": "must not leak",
        }]

def test_firecrawl_discovery_adapter_returns_internal_models_only():
    provider = FirecrawlDiscoveryProvider(FakeFirecrawlTool())

    result = provider.search("attention implementation", limit=3)

    assert isinstance(provider, SourceDiscoveryProvider)
    assert result == [DiscoveredSource(
        url="https://provider.example/attention",
        title="Attention",
        description="Implementation details",
        domain="provider.example",
        source_provider="firecrawl",
    )]
    assert "sdk_only_field" not in result[0].model_dump()


def test_source_search_node_consumes_discovery_contract(monkeypatch):
    class FakeDiscoveryProvider:
        def search(self, query, *, limit):
            return [DiscoveredSource(
                url="https://internal.example/source",
                title="Internal contract",
                domain="internal.example",
                source_provider="fixture",
            )]

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_search_node.get_discovery_provider",
        lambda: FakeDiscoveryProvider(),
    )
    try:
        result = source_search_node({
            "config": {"research": {"max_sources": 2}, "sources": {}},
            "research_plan": {"search_queries": ["contract test"]},
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["candidate_sources"][0]["url"] == "https://internal.example/source"
    assert result["candidate_sources"][0]["source_provider"] == "fixture"
    assert result["candidate_sources"][0]["search_query"] == "contract test"


def test_acquisition_node_consumes_acquired_document_contract(monkeypatch):
    class FakeAcquisitionProvider:
        def acquire_many(self, urls):
            return [AcquiredDocument(
                source_url=url,
                canonical_url=url,
                title="Acquired",
                domain="internal.example",
                raw_markdown="# Acquired\n\nEvidence.",
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                source_provider="fixture",
                content_hash="abc123",
                success=True,
            ) for url in urls]

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.acquisition_node.get_acquisition_provider",
        lambda: FakeAcquisitionProvider(),
    )
    try:
        result = acquisition_node({
            "selected_sources": [{
                "url": "https://internal.example/source",
                "title": "Candidate",
                "search_query": "contract test",
            }],
            "approved_dataset_schema": {"name": "approved"},
            "raw_data": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    document = result["raw_data"][0]
    assert document["source"] == "https://internal.example/source"
    assert document["content"] == "# Acquired\n\nEvidence."
    assert document["metadata"]["source_provider"] == "fixture"
    assert document["metadata"]["content_hash"] == "abc123"


def test_graph_nodes_do_not_import_provider_sdk_or_legacy_firecrawl_tool():
    node_paths = [
        PROJECT_ROOT / "src/agents/nodes/source_search_node.py",
        PROJECT_ROOT / "src/agents/nodes/acquisition_node.py",
    ]

    for path in node_paths:
        source = path.read_text(encoding="utf-8")
        assert "from firecrawl" not in source
        assert "src.tools.firecrawl_tool" not in source
        assert "FirecrawlTool" not in source


def test_primary_acquisition_factory_returns_crawl4ai_provider():
    provider = get_acquisition_provider()

    assert isinstance(provider, Crawl4AIAcquisitionProvider)
    assert isinstance(provider, WebAcquisitionProvider)
