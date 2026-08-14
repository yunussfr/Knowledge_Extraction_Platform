"""Deterministic hard-rule enforcement and request-specific source scoring."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from src.schemas.models import EvaluatedSource, SourcePolicy, SourceProfile
from src.tools.web.models import SourcePreview


IMPORTANCE_WEIGHTS = {"low": 0.5, "medium": 1.0, "high": 2.0}
DEPTH_ORDER = {"unknown": 0, "shallow": 1, "medium": 2, "deep": 3}


def _labels(values: Iterable[str]) -> set[str]:
    return {
        value.strip().casefold().replace(" ", "_").replace("-", "_")
        for value in values
        if value.strip()
    }


def domain_matches(hostname: str, configured_domain: str) -> bool:
    host = hostname.casefold().rstrip(".")
    configured = configured_domain.casefold().rstrip(".")
    return host == configured or host.endswith("." + configured)


def _hard_rejection_reasons(
    *,
    url: str,
    profile: SourceProfile,
    policy: SourcePolicy,
    allowed_domains: list[str] | None,
    blocked_domains: list[str] | None,
) -> list[str]:
    reasons: list[str] = []
    hostname = urlparse(url).hostname or ""
    source_type = profile.source_type.casefold()
    allowed_types = _labels(policy.allowed_source_types or [])
    blocked_types = _labels(policy.blocked_source_types or [])

    if allowed_domains and not any(domain_matches(hostname, item) for item in allowed_domains):
        reasons.append("Domain is outside the explicitly allowed domains.")
    if blocked_domains and any(domain_matches(hostname, item) for item in blocked_domains):
        reasons.append("Domain matches an explicitly blocked domain.")
    if allowed_types and source_type not in allowed_types:
        reasons.append("Source type is outside the explicitly allowed source types.")
    if blocked_types and source_type in blocked_types:
        reasons.append("Source type matches an explicitly blocked source type.")
    minimum_depth = policy.minimum_content_depth
    if minimum_depth and DEPTH_ORDER[profile.content_depth] < DEPTH_ORDER[minimum_depth]:
        reasons.append(
            f"Content depth {profile.content_depth!r} is below explicit minimum {minimum_depth!r}."
        )
    return reasons


def _policy_alignment_score(
    *,
    url: str,
    profile: SourceProfile,
    policy: SourcePolicy,
    preferred_domains: list[str],
) -> tuple[float, list[str]]:
    importance = policy.importance
    components = [
        (profile.authority_score, IMPORTANCE_WEIGHTS[importance.authority]),
        (profile.technical_depth_score, IMPORTANCE_WEIGHTS[importance.technical_depth]),
        (profile.information_density_score, IMPORTANCE_WEIGHTS[importance.information_density]),
        (profile.extractability_score, IMPORTANCE_WEIGHTS[importance.extractability]),
    ]
    if profile.recency_score is not None:
        components.append((profile.recency_score, IMPORTANCE_WEIGHTS[importance.recency]))
    weighted_score = sum(score * weight for score, weight in components) / sum(
        weight for _score, weight in components
    )

    adjustments = 0.0
    reasons: list[str] = []
    source_type = profile.source_type.casefold()
    characteristics = _labels(profile.content_characteristics)
    preferred_types = _labels(policy.preferred_source_types)
    desired = _labels(policy.desired_content)
    avoided = _labels(policy.avoided_content)
    hostname = urlparse(url).hostname or ""

    if preferred_types and source_type in preferred_types:
        adjustments += 0.10
        reasons.append("Matches a soft preferred source type.")
    if preferred_domains and any(domain_matches(hostname, item) for item in preferred_domains):
        adjustments += 0.05
        reasons.append("Matches a soft preferred domain.")
    if desired:
        matches = characteristics & desired
        if matches:
            adjustments += 0.15 * (len(matches) / len(desired))
            reasons.append("Contains requested content characteristics: " + ", ".join(sorted(matches)) + ".")
    if avoided:
        matches = characteristics & avoided
        if matches:
            adjustments -= 0.20 * (len(matches) / len(avoided))
            reasons.append("Contains avoided content characteristics: " + ", ".join(sorted(matches)) + ".")
    return max(0.0, min(1.0, weighted_score + adjustments)), reasons


def evaluate_source_for_policy(
    *,
    url: str,
    profile: SourceProfile,
    topic_relevance_score: float,
    preview: SourcePreview | None,
    policy: SourcePolicy,
    preferred_domains: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    model_reasons: list[str] | None = None,
) -> EvaluatedSource:
    """Apply only explicit hard rules and deterministic soft policy weighting."""
    hard_reasons = _hard_rejection_reasons(
        url=url,
        profile=profile,
        policy=policy,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )
    alignment, policy_reasons = _policy_alignment_score(
        url=url,
        profile=profile,
        policy=policy,
        preferred_domains=preferred_domains or [],
    )
    relevance = max(0.0, min(1.0, float(topic_relevance_score)))
    final_score = round((0.55 * relevance) + (0.45 * alignment), 6)
    preview_success = bool(preview and preview.fetch_success)
    reasons = list(model_reasons or [])
    for reason in [*hard_reasons, *policy_reasons]:
        if reason not in reasons:
            reasons.append(reason)

    if not preview_success:
        limitation = "Source preview was unavailable; content-based evaluation is not verified."
        if preview and preview.error:
            limitation += f" Error: {preview.error}"
        reasons.append(limitation)
    hard_rejected = bool(hard_reasons)
    decision = (
        "select"
        if not hard_rejected and preview_success and relevance >= 0.5 and final_score >= 0.55
        else "reject"
    )
    if decision == "select":
        reasons.append("Meets the request-specific relevance and policy score threshold.")
    elif not hard_rejected and preview_success:
        reasons.append("Does not meet the request-specific relevance and policy score threshold.")

    return EvaluatedSource(
        url=url,
        source_profile=profile,
        topic_relevance_score=relevance,
        policy_alignment_score=round(alignment, 6),
        final_score=final_score,
        hard_policy_rejected=hard_rejected,
        decision=decision,
        reasons=list(dict.fromkeys(reasons)),
        preview_success=preview_success,
    )
