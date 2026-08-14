"""Phase 5 contract and local-fixture tests for Crawl4AI acquisition."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.models import AcquiredDocument


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "web"

FIXTURE_MARKDOWN = {
    "normal_page.html": (
        "# Normal Research Page\n\n"
        "This page contains a clear, evidence-bearing paragraph for acquisition tests."
    ),
    "empty_page.html": "",
    "noisy_page.html": (
        "Home Products Pricing Sign in Subscribe\n\n"
        "# Core Finding\n\nThe measured result was stable across three independently repeated trials."
    ),
    "turkish_unicode_page.html": (
        "# İstanbul’da Kahve Kültürü\n\n"
        "Çeşitli öğütme yöntemleri, közde pişirme ve misafirperverlik geleneği anlatılır. "
        "€ — ✓"
    ),
    "headings_page.html": (
        "# Main Heading\n\nOpening evidence.\n\n"
        "## Methods\n\nRepeatable details.\n\n### Limitations\n\nKnown limitations."
    ),
    "lists_page.html": (
        "# Evidence Checklist\n\n- First supporting item\n- Second supporting item\n\n"
        "1. Collect the observation\n2. Validate the observation"
    ),
    "tables_page.html": (
        "# Measured Values\n\n| Sample | Value |\n| --- | --- |\n| A | Value A |\n| B | Value B |"
    ),
}


def _result_for_fixture(path: Path, markdown: str, *, fit_markdown: str | None = None):
    return SimpleNamespace(
        success=True,
        url=f"https://fixture.test/{path.name}",
        redirected_url="https://www.fixture.test/canonical-page",
        html=path.read_text(encoding="utf-8"),
        markdown=SimpleNamespace(
            raw_markdown=markdown,
            fit_markdown=fit_markdown,
        ),
        metadata={
            "title": f"Fixture: {path.stem}",
            "canonical_url": "https://fixture.test/canonical-page",
            "nested": {"safe": True},
            "provider_object": SimpleNamespace(name="must be serialized"),
        },
        links={
            "internal": [
                {"href": "https://fixture.test/inside"},
                {"href": "https://fixture.test/inside"},
            ],
            "external": [{"href": "https://external.test/reference"}],
        },
        status_code=200,
        cache_status="miss",
        error_message=None,
    )


@pytest.mark.parametrize("fixture_name", list(FIXTURE_MARKDOWN))
def test_acquire_normalizes_local_html_fixture(fixture_name):
    path = FIXTURE_DIR / fixture_name
    raw_markdown = FIXTURE_MARKDOWN[fixture_name]
    fit_markdown = "# Core Finding\n\nStable result." if fixture_name == "noisy_page.html" else None
    provider = Crawl4AIAcquisitionProvider(
        result_loader=lambda _url: _result_for_fixture(
            path,
            raw_markdown,
            fit_markdown=fit_markdown,
        )
    )

    document = provider.acquire(f"https://fixture.test/{fixture_name}")

    assert isinstance(document, AcquiredDocument)
    assert document.success is True
    assert document.raw_markdown == raw_markdown
    assert document.fit_markdown == fit_markdown
    assert document.html == path.read_text(encoding="utf-8")
    assert document.title == f"Fixture: {path.stem}"
    assert document.canonical_url == "https://fixture.test/canonical-page"
    assert document.domain == "fixture.test"
    assert document.internal_links == ["https://fixture.test/inside"]
    assert document.external_links == ["https://external.test/reference"]
    assert document.content_hash == sha256(raw_markdown.encode("utf-8")).hexdigest()
    assert document.source_provider == "crawl4ai"
    json.dumps(document.model_dump())


def test_noisy_page_preserves_raw_and_fit_markdown_separately():
    path = FIXTURE_DIR / "noisy_page.html"
    raw_markdown = FIXTURE_MARKDOWN[path.name]
    fit_markdown = "# Core Finding\n\nStable result."
    provider = Crawl4AIAcquisitionProvider(
        result_loader=lambda _url: _result_for_fixture(
            path,
            raw_markdown,
            fit_markdown=fit_markdown,
        )
    )

    document = provider.acquire("https://fixture.test/noisy")

    assert "Home Products Pricing" in document.raw_markdown
    assert "Home Products Pricing" not in document.fit_markdown
    assert "Core Finding" in document.fit_markdown


def test_duplicate_content_has_identical_hash_across_source_urls():
    first_path = FIXTURE_DIR / "duplicate_content_a.html"
    second_path = FIXTURE_DIR / "duplicate_content_b.html"
    assert first_path.read_text(encoding="utf-8") == second_path.read_text(encoding="utf-8")
    markdown = "# Duplicate Evidence\n\nThe same evidence yields the same content hash."

    first = Crawl4AIAcquisitionProvider(
        result_loader=lambda _url: _result_for_fixture(first_path, markdown)
    ).acquire("https://one.fixture.test/evidence")
    second = Crawl4AIAcquisitionProvider(
        result_loader=lambda _url: _result_for_fixture(second_path, markdown)
    ).acquire("https://two.fixture.test/evidence")

    assert first.source_url != second.source_url
    assert first.content_hash == second.content_hash


def test_unsuccessful_provider_result_preserves_failure_details():
    result = SimpleNamespace(
        success=False,
        url="https://fixture.test/unavailable",
        redirected_url=None,
        html=None,
        markdown=None,
        metadata=None,
        links=None,
        status_code=503,
        cache_status=None,
        error_message="upstream service unavailable",
    )
    provider = Crawl4AIAcquisitionProvider(result_loader=lambda _url: result)

    document = provider.acquire("https://fixture.test/unavailable")

    assert document.success is False
    assert document.error == "upstream service unavailable"
    assert document.provider_metadata["status_code"] == 503
    assert document.raw_markdown == ""
    assert document.content_hash == sha256(b"").hexdigest()


def test_provider_exception_becomes_failed_acquired_document():
    def fail(_url):
        raise TimeoutError("fixture acquisition timed out")

    document = Crawl4AIAcquisitionProvider(result_loader=fail).acquire(
        "https://fixture.test/timeout"
    )

    assert document.success is False
    assert document.error == "TimeoutError: fixture acquisition timed out"
    assert document.provider_metadata == {"failure_type": "TimeoutError"}


@pytest.mark.asyncio
async def test_sync_provider_boundary_works_inside_running_event_loop():
    path = FIXTURE_DIR / "normal_page.html"

    async def load(_url):
        return _result_for_fixture(path, FIXTURE_MARKDOWN[path.name])

    document = Crawl4AIAcquisitionProvider(result_loader=load).acquire(
        "https://fixture.test/inside-event-loop"
    )

    assert document.success is True
    assert "Normal Research Page" in document.raw_markdown


@pytest.mark.parametrize("cache_mode", ["enabled", "disabled", "read_only", "write_only", "bypass"])
def test_supported_cache_modes_are_accepted(cache_mode):
    provider = Crawl4AIAcquisitionProvider(
        result_loader=lambda _url: None,
        cache_mode=cache_mode,
    )

    assert provider.cache_mode == cache_mode


def test_invalid_runtime_configuration_fails_before_browser_start():
    with pytest.raises(ValueError, match="cache mode"):
        Crawl4AIAcquisitionProvider(cache_mode="surprise")
    with pytest.raises(ValueError, match="timeout"):
        Crawl4AIAcquisitionProvider(page_timeout_ms=0)
    with pytest.raises(ValueError, match="threshold"):
        Crawl4AIAcquisitionProvider(pruning_threshold=1.1)


def test_windows_file_uri_is_adapted_without_changing_document_source():
    source_url = "file:///C:/fixtures/page.html"

    if os.name == "nt":
        assert Crawl4AIAcquisitionProvider._crawler_url(source_url) == (
            "file://C:/fixtures/page.html"
        )
    else:
        assert Crawl4AIAcquisitionProvider._crawler_url(source_url) == source_url
