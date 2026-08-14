"""Build and cache bounded page evidence before source evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict
from urllib.parse import urlsplit

from src.core.logging import get_logger
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry
from src.schemas.models import DiscoveryOrigin
from src.tools.web import get_acquisition_provider
from src.tools.web.models import AcquiredDocument, SourcePreview
from src.tools.web.preview_builder import build_source_preview


logger = get_logger(__name__)


def _ensure_registry(
    registry: CandidateRegistry,
    candidates: list[dict[str, Any]],
) -> CandidateRegistry:
    if len(registry):
        return registry
    for candidate in candidates:
        origins = candidate.get("discovery_origins") or []
        if not origins:
            query = str(candidate.get("search_query", "")).strip()
            is_seed = bool(candidate.get("user_supplied_reference"))
            origins = [{
                "method": "seed" if is_seed else ("search" if query else "mock"),
                "query": query if query and not is_seed else None,
                "seed_url": candidate.get("url") if is_seed else None,
                "source_provider": candidate.get("source_provider") or None,
            }]
        for raw_origin in origins:
            registry.add(
                candidate.get("canonical_url") or candidate["url"],
                origin=DiscoveryOrigin.model_validate(raw_origin),
                title=candidate.get("title", ""),
                description=candidate.get("description", ""),
                source_provider=candidate.get("source_provider", ""),
                preferred_domain_match=bool(candidate.get("preferred_domain_match")),
            )
    return registry


def _mock_preview(candidate: dict[str, Any]) -> SourcePreview:
    if "content" in candidate:
        content = str(candidate.get("content") or "")
    else:
        content = str(candidate.get("description") or "Mock source content.")
    source_url = candidate.get("canonical_url") or candidate["url"]
    success = bool(content.strip())
    document = AcquiredDocument(
        source_url=source_url,
        canonical_url=source_url,
        title=candidate.get("title", ""),
        domain=candidate.get("domain") or (urlsplit(source_url).hostname or ""),
        raw_markdown=content,
        fit_markdown=content or None,
        internal_links=list(candidate.get("internal_links", [])),
        external_links=list(candidate.get("external_links", [])),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_provider="mock",
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
        success=success,
        error=None if success else "Mock source has no previewable content.",
        provider_metadata=dict(candidate.get("provider_metadata", {})),
    )
    return build_source_preview(
        document,
        max_words=settings.crawl4ai_preview_max_words,
    )


def source_preview_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch each canonical candidate at most once and retain per-source failures."""
    try:
        candidates = list(state.get("candidate_sources", []))
        registry = _ensure_registry(
            CandidateRegistry(state.get("source_registry")),
            candidates,
        )
        cached = {
            preview.url: preview
            for preview in (
                SourcePreview.model_validate(item)
                for item in state.get("source_previews", [])
            )
        }
        provider = None
        previews: list[SourcePreview] = []

        logger.info("Building bounded previews for %d canonical sources.", len(candidates))
        for candidate in candidates:
            url = candidate.get("canonical_url") or candidate["url"]
            preview = cached.get(url)
            if preview is None:
                if settings.data_source_provider == "mock":
                    preview = _mock_preview(candidate)
                else:
                    if provider is None:
                        provider = get_acquisition_provider()
                    try:
                        preview = provider.preview(
                            url,
                            query=candidate.get("search_query") or None,
                        )
                    except Exception as exc:
                        preview = SourcePreview(
                            url=url,
                            title=candidate.get("title", ""),
                            domain=candidate.get("domain", ""),
                            fetch_success=False,
                            error=f"{type(exc).__name__}: {exc}",
                        )

                if preview.url != url or (not preview.title and candidate.get("title")):
                    preview = SourcePreview.model_validate({
                        **preview.model_dump(),
                        "url": url,
                        "title": preview.title or candidate.get("title", ""),
                    })
                cached[url] = preview

            registry.set_preview_status(
                url,
                "completed" if preview.fetch_success else "failed",
            )
            previews.append(preview)

        success_count = sum(preview.fetch_success for preview in previews)
        logger.info(
            "Source preview completed: %d successful, %d failed.",
            success_count,
            len(previews) - success_count,
        )
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_previews": [preview.model_dump(mode="json") for preview in previews],
            "status": "sources_previewed",
            "pipeline_status": "sources_previewed",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "source_preview", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
