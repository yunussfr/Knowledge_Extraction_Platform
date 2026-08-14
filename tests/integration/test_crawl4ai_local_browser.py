"""Opt-in browser-backed Crawl4AI tests; all pages are local fixtures."""

from __future__ import annotations

import os
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "web"
RUN_BROWSER_TESTS = os.getenv("RUN_CRAWL4AI_BROWSER_TESTS", "false").lower() == "true"


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
@pytest.mark.parametrize(
    ("fixture_name", "expected_text", "expected_success"),
    [
        ("normal_page.html", "Normal Research Page", True),
        ("empty_page.html", "", False),
        ("noisy_page.html", "Core Finding", True),
        ("turkish_unicode_page.html", "İstanbul’da Kahve Kültürü", True),
        ("headings_page.html", "Main Heading", True),
        ("lists_page.html", "First supporting item", True),
        ("tables_page.html", "Value A", True),
    ],
)
def test_real_crawl4ai_acquires_local_html_fixtures(
    fixture_name,
    expected_text,
    expected_success,
):
    path = FIXTURE_DIR / fixture_name
    provider = Crawl4AIAcquisitionProvider(cache_mode="disabled")

    document = provider.acquire(path.resolve().as_uri())

    assert document.success is expected_success
    assert document.source_provider == "crawl4ai"
    if expected_success:
        assert document.html is not None
        assert expected_text in document.raw_markdown
    else:
        assert document.raw_markdown.strip() == ""
        assert document.error


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
def test_real_crawl4ai_duplicate_fixtures_have_identical_content_hashes():
    provider = Crawl4AIAcquisitionProvider(cache_mode="disabled")

    first = provider.acquire((FIXTURE_DIR / "duplicate_content_a.html").resolve().as_uri())
    second = provider.acquire((FIXTURE_DIR / "duplicate_content_b.html").resolve().as_uri())

    assert first.success, first.error
    assert second.success, second.error
    assert first.content_hash == second.content_hash


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
def test_real_crawl4ai_acquires_multiple_local_fixtures_in_one_ordered_batch():
    fixture_names = [
        "normal_page.html",
        "headings_page.html",
        "turkish_unicode_page.html",
    ]
    urls = [(FIXTURE_DIR / name).resolve().as_uri() for name in fixture_names]
    provider = Crawl4AIAcquisitionProvider(
        cache_mode="disabled",
        batch_concurrency=2,
        batch_delay_seconds=0.01,
    )

    documents = provider.acquire_many(urls)

    assert [item.source_url for item in documents] == urls
    assert all(item.success for item in documents), [item.error for item in documents]
    assert "Normal Research Page" in documents[0].raw_markdown
    assert "Main Heading" in documents[1].raw_markdown
    assert "İstanbul’da Kahve Kültürü" in documents[2].raw_markdown


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
def test_real_crawl4ai_builds_bounded_preview_from_local_fixture():
    provider = Crawl4AIAcquisitionProvider(cache_mode="disabled", preview_max_words=12)

    preview = provider.preview(
        (FIXTURE_DIR / "headings_page.html").resolve().as_uri(),
        query="methods and limitations",
    )

    assert preview.fetch_success, preview.error
    assert preview.preview_word_count <= 12
    assert preview.approximate_word_count >= preview.preview_word_count
    assert "Main Heading" in preview.headings
    assert "headings" in preview.structure_hints


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
def test_real_crawl4ai_empty_fixture_preview_preserves_failure():
    provider = Crawl4AIAcquisitionProvider(cache_mode="disabled", preview_max_words=12)

    preview = provider.preview((FIXTURE_DIR / "empty_page.html").resolve().as_uri())

    assert preview.fetch_success is False
    assert preview.preview_word_count == 0
    assert preview.error


class _FixtureHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, fixture_directory: str, **kwargs):
        super().__init__(*args, directory=fixture_directory, **kwargs)

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/site/index.html":
            content = (FIXTURE_DIR / "site" / "index.html").read_text(encoding="utf-8")
            content = content.replace("{{PORT}}", str(self.server.server_port))
            payload = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


@pytest.fixture
def local_fixture_site():
    def handler(*args, **kwargs):
        return _FixtureHandler(
            *args,
            fixture_directory=str(FIXTURE_DIR),
            **kwargs,
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/site/index.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(
    not RUN_BROWSER_TESTS,
    reason="Set RUN_CRAWL4AI_BROWSER_TESTS=true after installing Playwright Chromium.",
)
def test_real_crawl4ai_site_exploration_is_bounded_and_cycle_safe(local_fixture_site):
    provider = Crawl4AIAcquisitionProvider(cache_mode="disabled")

    pages = provider.explore_site(
        local_fixture_site,
        query_terms=["technical", "methods", "evidence"],
        max_depth=2,
        max_pages=10,
        same_domain_only=True,
    )

    paths = {Path(page.url.split("?", 1)[0]).name for page in pages}
    assert paths == {"page-a.html", "page-b.html", "page-c.html"}
    assert len(pages) == len({page.url for page in pages}) == 3
    assert max(page.depth for page in pages) == 2
    assert all("localhost" not in page.url for page in pages)
    assert all(not page.url.endswith(".pdf") for page in pages)
