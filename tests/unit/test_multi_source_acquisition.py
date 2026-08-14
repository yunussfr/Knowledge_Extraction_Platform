"""Phase 12 bounded multi-source acquisition tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic
from types import SimpleNamespace

from src.agents.nodes.acquisition_node import acquisition_node
from src.core.settings import settings
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.models import AcquiredDocument


def _result(url: str, *, cache_status: str = "miss") -> SimpleNamespace:
    markdown = f"# Evidence\n\nSource content for {url}."
    return SimpleNamespace(
        success=True,
        url=url,
        redirected_url=None,
        html=f"<p>{url}</p>",
        markdown=SimpleNamespace(raw_markdown=markdown, fit_markdown=None),
        metadata={"title": url.rsplit("/", 1)[-1]},
        links={"internal": [], "external": []},
        status_code=200,
        cache_status=cache_status,
        error_message=None,
    )


def _document(url: str, *, success: bool = True, cache_status: str = "miss"):
    content = f"# Evidence\n\n{url}" if success else ""
    return AcquiredDocument(
        source_url=url,
        canonical_url=url,
        title=url.rsplit("/", 1)[-1],
        domain=url.split("/")[2],
        raw_markdown=content,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_provider="fixture",
        content_hash=sha256(content.encode()).hexdigest(),
        success=success,
        error=None if success else "fixture failure",
        provider_metadata={"cache_status": cache_status},
    )


def test_acquire_many_enforces_concurrency_and_preserves_input_order():
    active = 0
    max_active = 0

    async def loader(url: str):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01 if url.endswith("slow") else 0.002)
        active -= 1
        return _result(url)

    urls = [
        "https://fixture.example/slow",
        "https://fixture.example/fast-a",
        "https://fixture.example/fast-b",
        "https://fixture.example/fast-c",
    ]
    provider = Crawl4AIAcquisitionProvider(
        result_loader=loader,
        batch_concurrency=2,
        batch_delay_seconds=0,
    )

    documents = provider.acquire_many(urls)

    assert max_active == 2
    assert [item.source_url for item in documents] == urls
    assert all(item.success for item in documents)


def test_acquire_many_throttles_start_times():
    starts: list[float] = []

    async def loader(url: str):
        starts.append(monotonic())
        return _result(url)

    provider = Crawl4AIAcquisitionProvider(
        result_loader=loader,
        batch_concurrency=3,
        batch_delay_seconds=0.02,
    )

    provider.acquire_many([
        "https://fixture.example/a",
        "https://fixture.example/b",
        "https://fixture.example/c",
    ])

    assert len(starts) == 3
    assert all(
        later - earlier >= 0.015
        for earlier, later in zip(starts, starts[1:])
    )


def test_acquire_many_isolates_one_loader_failure():
    async def loader(url: str):
        if url.endswith("bad"):
            raise TimeoutError("fixture timeout")
        return _result(url)

    urls = [
        "https://fixture.example/good-a",
        "https://fixture.example/bad",
        "https://fixture.example/good-b",
    ]
    documents = Crawl4AIAcquisitionProvider(
        result_loader=loader,
        batch_concurrency=2,
        batch_delay_seconds=0,
    ).acquire_many(urls)

    assert [item.success for item in documents] == [True, False, True]
    assert documents[1].source_url == urls[1]
    assert documents[1].error == "TimeoutError: fixture timeout"


def test_batch_configuration_is_validated_before_acquisition():
    try:
        Crawl4AIAcquisitionProvider(batch_concurrency=0)
    except ValueError as error:
        assert "concurrency" in str(error)
    else:
        raise AssertionError("Zero concurrency must be rejected.")

    try:
        Crawl4AIAcquisitionProvider(batch_delay_seconds=-0.1)
    except ValueError as error:
        assert "delay" in str(error)
    else:
        raise AssertionError("Negative delay must be rejected.")


def test_acquisition_node_uses_one_batch_and_preserves_failures_and_metrics(monkeypatch):
    urls = [
        "https://fixture.example/cached",
        "https://fixture.example/failed",
        "https://fixture.example/fresh",
    ]

    class FakeBatchProvider:
        calls: list[list[str]] = []

        def acquire_many(self, requested_urls):
            self.calls.append(list(requested_urls))
            return [
                _document(urls[0], cache_status="hit"),
                _document(urls[1], success=False),
                _document(urls[2]),
            ]

    provider = FakeBatchProvider()
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.acquisition_node.get_acquisition_provider",
        lambda: provider,
    )
    try:
        result = acquisition_node({
            "selected_sources": [{"url": url, "title": url} for url in urls],
            "approved_dataset_schema": {"name": "approved"},
            "raw_data": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert provider.calls == [urls]
    assert result["status"] == "processing"
    assert [item["source"] for item in result["raw_data"]] == [urls[0], urls[2]]
    assert [item["source_url"] for item in result["acquired_documents"]] == urls
    assert result["acquisition_metrics"]["requested_urls"] == 3
    assert result["acquisition_metrics"]["successful_urls"] == 2
    assert result["acquisition_metrics"]["failed_urls"] == 1
    assert result["acquisition_metrics"]["cache_hits"] == 1
    assert result["acquisition_metrics"]["acquisition_duration_seconds"] >= 0
    assert result["errors"][-1]["source_url"] == urls[1]


def test_acquisition_node_fails_only_when_every_batch_document_fails(monkeypatch):
    urls = ["https://fixture.example/a", "https://fixture.example/b"]

    class FailedBatchProvider:
        def acquire_many(self, requested_urls):
            return [_document(url, success=False) for url in requested_urls]

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.acquisition_node.get_acquisition_provider",
        lambda: FailedBatchProvider(),
    )
    try:
        result = acquisition_node({
            "selected_sources": [{"url": url} for url in urls],
            "approved_dataset_schema": {"name": "approved"},
            "raw_data": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "failed"
    assert result["acquisition_metrics"]["failed_urls"] == 2
    assert len(result["acquired_documents"]) == 2
    assert len(result["errors"]) == 2
