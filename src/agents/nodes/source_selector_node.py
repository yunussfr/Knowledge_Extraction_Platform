"""Select eligible high-quality sources with bounded diversity preference."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Dict
from urllib.parse import urlparse

from src.core.logging import get_logger
from src.core.source_registry import CandidateRegistry, normalize_candidate_url
from src.schemas.models import EvaluatedSource, SelectedSource, SourcePolicy


logger = get_logger(__name__)
DOMAIN_QUALITY_TOLERANCE = 0.15
TYPE_QUALITY_TOLERANCE = 0.08
IMPORTANCE_FACTORS = {"low": 0.5, "medium": 1.0, "high": 1.5}


def _canonical(url: str) -> str:
    try:
        return normalize_candidate_url(url)
    except ValueError:
        return url


def _quality_score(source: EvaluatedSource, policy: SourcePolicy) -> float:
    profile = source.source_profile
    technical_weight = 0.10 * IMPORTANCE_FACTORS[policy.importance.technical_depth]
    components = [
        (source.final_score, 0.70),
        (profile.information_density_score, 0.10),
        (profile.extractability_score, 0.10),
        (profile.technical_depth_score, technical_weight),
    ]
    score = sum(value * weight for value, weight in components) / sum(
        weight for _value, weight in components
    )
    return round(max(0.0, min(1.0, score)), 6)


def _mark_exact_preview_duplicates(
    evaluations: list[EvaluatedSource],
    previews: list[dict[str, Any]],
    policy: SourcePolicy,
) -> list[EvaluatedSource]:
    """Keep the strongest representative for identical successful preview text."""
    preview_text_by_url: dict[str, str] = {}
    for preview in previews:
        if not preview.get("fetch_success", False):
            continue
        text = re.sub(r"\s+", " ", str(preview.get("relevant_text", ""))).strip()
        if text:
            preview_text_by_url[_canonical(str(preview.get("url", "")))] = text

    grouped: dict[str, list[EvaluatedSource]] = {}
    for evaluation in evaluations:
        text = preview_text_by_url.get(_canonical(evaluation.url))
        if text:
            grouped.setdefault(text, []).append(evaluation)

    duplicate_of_by_url: dict[str, str] = {}
    for group in grouped.values():
        if len(group) < 2:
            continue
        representative = max(
            group,
            key=lambda item: (_quality_score(item, policy), -evaluations.index(item)),
        )
        for item in group:
            if item.url != representative.url:
                duplicate_of_by_url[item.url] = representative.url

    return [
        item.model_copy(update={"duplicate_of": duplicate_of_by_url.get(item.url)})
        for item in evaluations
    ]


def select_sources(
    evaluated_sources: list[EvaluatedSource],
    *,
    policy: SourcePolicy,
    max_sources: int,
) -> tuple[list[SelectedSource], list[EvaluatedSource]]:
    """Greedily prefer useful diversity only within a bounded quality band."""
    if max_sources < 1:
        raise ValueError("Source selection max_sources must be at least 1.")
    eligible = [
        source
        for source in evaluated_sources
        if source.decision == "select"
        and not source.hard_policy_rejected
        and source.preview_success
        and source.duplicate_of is None
    ]
    quality = {source.url: _quality_score(source, policy) for source in eligible}
    remaining = list(eligible)
    selected: list[SelectedSource] = []
    selected_domains: set[str] = set()
    selected_types: set[str] = set()

    while remaining and len(selected) < max_sources:
        best_quality = max(quality[item.url] for item in remaining)
        pool = remaining
        if selected_domains:
            new_domain = [
                item
                for item in pool
                if (urlparse(item.url).hostname or "").lower() not in selected_domains
                and quality[item.url] >= best_quality - DOMAIN_QUALITY_TOLERANCE
            ]
            if new_domain:
                pool = new_domain
        if selected_types:
            new_type = [
                item
                for item in pool
                if item.source_profile.source_type not in selected_types
                and quality[item.url] >= best_quality - TYPE_QUALITY_TOLERANCE
            ]
            if new_type:
                pool = new_type

        chosen = min(
            pool,
            key=lambda item: (-quality[item.url], evaluated_sources.index(item)),
        )
        domain = (urlparse(chosen.url).hostname or "").lower()
        source_type = chosen.source_profile.source_type
        reasons = ["Selected from eligible sources by request-specific quality score."]
        if selected and domain not in selected_domains:
            reasons.append("Adds a useful source-domain diversity contribution.")
        if selected and source_type not in selected_types:
            reasons.append("Adds a useful source-type diversity contribution.")
        selected.append(SelectedSource(
            url=chosen.url,
            rank=len(selected) + 1,
            selection_score=quality[chosen.url],
            final_score=chosen.final_score,
            domain=domain,
            source_type=source_type,
            selection_reasons=reasons,
        ))
        selected_domains.add(domain)
        selected_types.add(source_type)
        remaining.remove(chosen)

    selected_urls = {item.url for item in selected}
    not_selected = [
        source for source in evaluated_sources if source.url not in selected_urls
    ]
    return selected, not_selected


def _selection_metrics(
    evaluations: list[EvaluatedSource],
    selections: list[SelectedSource],
) -> dict[str, Any]:
    domains = Counter(item.domain for item in selections)
    source_types = Counter(item.source_type for item in selections)
    return {
        "evaluated_candidates": len(evaluations),
        "eligible_candidates": sum(
            item.decision == "select"
            and not item.hard_policy_rejected
            and item.preview_success
            and item.duplicate_of is None
            for item in evaluations
        ),
        "duplicate_candidates": sum(item.duplicate_of is not None for item in evaluations),
        "selected_sources": len(selections),
        "unique_selected_domains": len(domains),
        "selected_by_domain": dict(sorted(domains.items())),
        "selected_by_source_type": dict(sorted(source_types.items())),
    }


def source_selector_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        evaluations = [
            EvaluatedSource.model_validate(item)
            for item in state.get("source_evaluations", [])
        ]
        if not evaluations:
            raise ValueError("No policy-aware source evaluations are available for selection.")
        source_config = state.get("config", {}).get("sources", {})
        if not isinstance(source_config, dict):
            source_config = {}
        policy = SourcePolicy.model_validate(
            state.get("source_policy") or source_config.get("source_policy", {})
        )
        evaluations = _mark_exact_preview_duplicates(
            evaluations,
            list(state.get("source_previews", [])),
            policy,
        )
        max_sources = int(
            state.get("config", {}).get("research", {}).get("max_sources", len(evaluations))
        )
        selections, not_selected = select_sources(
            evaluations,
            policy=policy,
            max_sources=max_sources,
        )
        if not selections:
            raise ValueError("Source selector found no eligible source after hard-policy and evidence checks.")

        candidate_by_url = {
            _canonical(item.get("canonical_url") or item["url"]): item
            for item in state.get("candidate_sources", [])
        }
        selected_sources: list[dict[str, Any]] = []
        for selection in selections:
            candidate = candidate_by_url.get(_canonical(selection.url), {"url": selection.url})
            selected_sources.append({
                **candidate,
                "priority": selection.rank,
                "reason": "; ".join(selection.selection_reasons),
                "selection": selection.model_dump(mode="json"),
            })

        rejected_sources: list[dict[str, Any]] = []
        for source in not_selected:
            if source.duplicate_of:
                reason = f"Exact preview duplicate of {source.duplicate_of}."
            elif source.hard_policy_rejected:
                reason = "; ".join(source.reasons)
            elif not source.preview_success:
                reason = "; ".join(source.reasons)
            elif source.decision == "reject":
                reason = "; ".join(source.reasons)
            else:
                reason = "Eligible source was not selected within the source limit and diversity-aware ranking."
            rejected_sources.append({
                "url": source.url,
                "selected": False,
                "reason": reason,
            })

        registry = CandidateRegistry(state.get("source_registry"))
        registry.record_evaluation(
            selected_sources=selected_sources,
            rejected_sources=rejected_sources,
        )
        metrics = _selection_metrics(evaluations, selections)
        logger.info(
            "Selected %d sources across %d unique domains.",
            metrics["selected_sources"],
            metrics["unique_selected_domains"],
        )
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_selections": [item.model_dump(mode="json") for item in selections],
            "source_selection_metrics": metrics,
            "selected_sources": selected_sources,
            "rejected_sources": rejected_sources,
            "status": "sources_selected",
            "pipeline_status": "sources_selected",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{
                "node": "source_selector",
                "error": str(error),
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
