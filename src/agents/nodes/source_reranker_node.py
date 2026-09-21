"""Rerank candidate sources using cross-encoder before page preview and LLM evaluation."""

from __future__ import annotations

from typing import Any, Dict

from src.core.logging import get_logger
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry
from src.schemas.models import DiscoveryOrigin
from src.tools.reranker import get_reranker_provider

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


def source_reranker_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Score candidates with a cross-encoder, filter by minimum_confidence, and assign candidate IDs."""
    try:
        candidates = list(state.get("candidate_sources", []))
        if not candidates:
            logger.info("No candidates discovered to rerank.")
            return {
                "candidate_sources": [],
                "status": "sources_reranked",
                "pipeline_status": "sources_reranked",
            }

        topic = (
            state.get("dataset_topic")
            or state.get("topic")
            or state.get("research_plan", {}).get("dataset_topic")
            or ""
        ).strip()

        config = state.get("config", {})
        quality_config = config.get("quality") if isinstance(config.get("quality"), dict) else {}
        sources_config = config.get("sources") if isinstance(config.get("sources"), dict) else {}

        # Read threshold dynamically from domain request.yaml (quality.minimum_confidence)
        threshold_val = (
            quality_config.get("minimum_confidence")
            or sources_config.get("reranker_min_score")
            or settings.reranker_min_score
        )
        threshold = float(threshold_val)

        logger.info(
            "Reranking %d candidates against topic '%s' using threshold %.4f (from config.quality.minimum_confidence).",
            len(candidates),
            topic,
            threshold,
        )

        provider = get_reranker_provider()
        rerank_result = provider.rerank(
            query=topic,
            candidates=candidates,
            threshold=threshold,
        )

        registry = _ensure_registry(
            CandidateRegistry(state.get("source_registry")),
            candidates,
        )
        registry.record_reranker_results(
            rerank_result.ranked_items,
            threshold=threshold,
        )

        eligible_candidates = registry.active_pipeline_candidates()
        eligible_candidates.sort(
            key=lambda c: -(c.get("reranker_score") if c.get("reranker_score") is not None else 0.0)
        )

        logger.info(
            "Source reranker completed: %d/%d candidates passed threshold (>= %.2f).",
            len(eligible_candidates),
            len(candidates),
            threshold,
        )

        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": eligible_candidates,
            "reranker_metrics": {
                "provider": rerank_result.provider,
                "model": rerank_result.model,
                "total_candidates": len(candidates),
                "accepted_candidates": len(eligible_candidates),
                "rejected_candidates": len(rerank_result.rejected_items),
                "threshold": threshold,
            },
            "status": "sources_reranked",
            "pipeline_status": "sources_reranked",
        }
    except Exception as error:
        logger.error("Source reranker failed: %s", error, exc_info=True)
        return {
            "errors": state.get("errors", []) + [{"node": "source_reranker", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
