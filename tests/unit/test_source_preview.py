"""Phase 7 tests for bounded evidence before source evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.nodes.source_evaluator_node import source_evaluator_node
from src.agents.nodes.source_preview_node import source_preview_node
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry
from src.schemas.models import (
    DiscoveryOrigin,
    EvaluatedSource,
    SourceEvaluationResult,
    SourceProfile,
)
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.models import AcquiredDocument, SourcePreview
from src.tools.web.preview_builder import build_source_preview


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "web"


def _document(
    *,
    raw_markdown: str,
    fit_markdown: str | None = None,
    success: bool = True,
    error: str | None = None,
) -> AcquiredDocument:
    return AcquiredDocument(
        source_url="https://example.com/source",
        canonical_url="https://example.com/source",
        title="Preview Source",
        domain="example.com",
        raw_markdown=raw_markdown,
        fit_markdown=fit_markdown,
        internal_links=["https://example.com/inside"],
        external_links=["https://external.test/reference"],
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_provider="fixture",
        content_hash=sha256(raw_markdown.encode("utf-8")).hexdigest(),
        success=success,
        error=error,
        provider_metadata={
            "language": "tr",
            "article:published_time": "2025-01-02",
            "article:modified_time": "2025-02-03",
        },
    )


def _sdk_result(raw_markdown: str, fit_markdown: str | None = None):
    return SimpleNamespace(
        success=True,
        url="https://example.com/source",
        redirected_url=None,
        html="<main>fixture</main>",
        markdown=SimpleNamespace(
            raw_markdown=raw_markdown,
            fit_markdown=fit_markdown,
        ),
        metadata={"title": "Preview Source", "language": "en"},
        links={"internal": [], "external": []},
        status_code=200,
        cache_status="miss",
        error_message=None,
    )


def test_preview_prefers_fit_markdown_and_bounds_without_losing_structure():
    raw = "# Raw Heading\n\n" + " ".join(f"raw{i}" for i in range(30))
    fit = (
        "# Relevant Heading\n\n"
        "- first item\n- second item\n\n"
        "| Key | Value |\n| --- | --- |\n| A | Evidence |\n\n"
        + " ".join(f"word{i}" for i in range(30))
    )

    preview = build_source_preview(
        _document(raw_markdown=raw, fit_markdown=fit),
        max_words=12,
    )

    assert preview.fetch_success is True
    assert preview.relevant_text.startswith("# Relevant Heading")
    assert "Raw Heading" not in preview.relevant_text
    assert preview.preview_word_count == 12
    assert preview.approximate_word_count == 33
    assert preview.headings == ["Raw Heading"]
    assert preview.structure_hints == ["headings", "unordered_list", "table"]
    assert preview.language == "tr"
    assert preview.publication_date == "2025-01-02"
    assert preview.updated_date == "2025-02-03"


def test_preview_falls_back_to_raw_markdown_and_preserves_unicode():
    raw = "# İstanbul’da Kahve\n\nÇeşitli öğütme yöntemleri ve misafirperverlik geleneği."

    preview = build_source_preview(_document(raw_markdown=raw), max_words=20)

    assert "İstanbul’da Kahve" in preview.relevant_text
    assert "öğütme" in preview.relevant_text
    assert preview.headings == ["İstanbul’da Kahve"]
    assert preview.preview_word_count == preview.approximate_word_count


def test_failed_document_becomes_visible_empty_preview():
    preview = build_source_preview(
        _document(
            raw_markdown="",
            success=False,
            error="provider timeout",
        ),
        max_words=20,
    )

    assert preview.fetch_success is False
    assert preview.error == "provider timeout"
    assert preview.relevant_text == ""
    assert preview.preview_word_count == 0
    assert preview.approximate_word_count == 0


def test_provider_preview_caches_same_url_and_query():
    calls = []

    def load(url):
        calls.append(url)
        return _sdk_result("# Evidence\n\nOne two three four five six.")

    provider = Crawl4AIAcquisitionProvider(
        result_loader=load,
        preview_max_words=5,
    )

    first = provider.preview("https://example.com/source", query="evidence")
    second = provider.preview("https://example.com/source", query="evidence")
    third = provider.preview("https://example.com/source", query="different")

    assert first.preview_word_count == 5
    assert second == first
    assert third.fetch_success is True
    assert calls == ["https://example.com/source", "https://example.com/source"]


def test_invalid_preview_bound_fails_before_fetch():
    with pytest.raises(ValueError, match="preview max words"):
        Crawl4AIAcquisitionProvider(preview_max_words=0)


def _registry_with_candidates(*urls: str) -> CandidateRegistry:
    registry = CandidateRegistry()
    for index, url in enumerate(urls, start=1):
        registry.add(
            url,
            origin=DiscoveryOrigin(method="search", query=f"query {index}"),
            title=f"Candidate {index}",
            source_provider="fixture",
        )
    return registry


def test_preview_node_continues_after_one_provider_failure(monkeypatch):
    registry = _registry_with_candidates(
        "https://example.com/good",
        "https://example.com/bad",
    )

    class MixedProvider:
        def preview(self, url, *, query=None):
            if url.endswith("/bad"):
                raise TimeoutError("preview timed out")
            return SourcePreview(
                url=url,
                title="Good Source",
                domain="example.com",
                relevant_text="Bounded real page evidence.",
                approximate_word_count=4,
                preview_word_count=4,
                fetch_success=True,
            )

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_preview_node.get_acquisition_provider",
        lambda: MixedProvider(),
    )
    try:
        result = source_preview_node({
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "sources_previewed"
    assert [item["fetch_success"] for item in result["source_previews"]] == [True, False]
    assert result["source_previews"][1]["error"] == "TimeoutError: preview timed out"
    assert result["source_registry"]["https://example.com/good"]["preview_status"] == "completed"
    assert result["source_registry"]["https://example.com/bad"]["preview_status"] == "failed"


def test_preview_node_reuses_state_cache_without_provider_call(monkeypatch):
    registry = _registry_with_candidates("https://example.com/cached")
    cached = SourcePreview(
        url="https://example.com/cached",
        title="Cached",
        domain="example.com",
        relevant_text="Already fetched evidence.",
        approximate_word_count=3,
        preview_word_count=3,
        fetch_success=True,
    )

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_preview_node.get_acquisition_provider",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be constructed")),
    )
    try:
        result = source_preview_node({
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [cached.model_dump()],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "sources_previewed"
    assert result["source_previews"] == [cached.model_dump(mode="json")]
    assert result["source_registry"]["https://example.com/cached"]["preview_status"] == "completed"


def test_mock_preview_is_offline_bounded_and_uses_candidate_content(monkeypatch):
    registry = CandidateRegistry()
    registry.add(
        "https://example.com/mock",
        origin=DiscoveryOrigin(method="mock", source_provider="mock"),
        source_provider="mock",
        candidate_metadata={"content": " ".join(f"token{i}" for i in range(20))},
    )
    original_provider = settings.data_source_provider
    original_bound = settings.crawl4ai_preview_max_words
    object.__setattr__(settings, "data_source_provider", "mock")
    object.__setattr__(settings, "crawl4ai_preview_max_words", 7)
    monkeypatch.setattr(
        "src.agents.nodes.source_preview_node.get_acquisition_provider",
        lambda: (_ for _ in ()).throw(AssertionError("mock preview must not build provider")),
    )
    try:
        result = source_preview_node({
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)
        object.__setattr__(settings, "crawl4ai_preview_max_words", original_bound)

    assert result["source_previews"][0]["preview_word_count"] == 7
    assert result["source_previews"][0]["relevant_text"].endswith("token6")


def test_mock_seed_without_content_uses_existing_acquisition_fallback():
    registry = CandidateRegistry()
    registry.add(
        "https://example.com/seed",
        origin=DiscoveryOrigin(
            method="seed",
            seed_url="https://example.com/seed",
            source_provider="user",
        ),
        source_provider="user",
    )
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        result = source_preview_node({
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["source_previews"][0]["fetch_success"] is True
    assert result["source_previews"][0]["relevant_text"] == "Mock source content."


def test_live_evaluator_payload_contains_bounded_source_preview(monkeypatch):
    captured = {}
    registry = _registry_with_candidates("https://example.com/evidence")
    candidates = registry.as_pipeline_candidates()
    preview = SourcePreview(
        url="https://example.com/evidence",
        title="Evidence",
        domain="example.com",
        relevant_text="Unique bounded page evidence for evaluation.",
        approximate_word_count=5000,
        preview_word_count=6,
        fetch_success=True,
    )

    def fake_complete_json(self, system_prompt, user_prompt, output_model):
        captured["user_prompt"] = user_prompt
        return SourceEvaluationResult(evaluated_sources=[EvaluatedSource(
            url="https://example.com/evidence",
            source_profile=SourceProfile(
                source_type="independent_technical",
                content_characteristics=["technical_explanation"],
                content_depth="deep",
                information_density_score=0.9,
                technical_depth_score=0.9,
                extractability_score=0.8,
            ),
            topic_relevance_score=0.95,
            reasons=["Preview supports the request."],
        )])

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_evaluator_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = source_evaluator_node({
            "dataset_topic": "Preview evidence",
            "research_plan": {},
            "config": {"research": {"constraints": ""}},
            "candidate_sources": candidates,
            "source_registry": registry.as_serialized(),
            "source_previews": [preview.model_dump(mode="json")],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "sources_evaluated"
    assert '"source_previews"' in captured["user_prompt"]
    assert "Unique bounded page evidence for evaluation." in captured["user_prompt"]
    assert "5000" in captured["user_prompt"]
    assert '"source_policy"' in captured["user_prompt"]
    assert '"evaluated_source_contract"' in captured["user_prompt"]
