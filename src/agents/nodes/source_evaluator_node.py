"""Characterize candidates and evaluate them against the current request policy."""

from __future__ import annotations

import json
from typing import Any, Dict

from src.agents.prompts import SOURCE_EVALUATOR_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.core.source_policy_evaluator import evaluate_source_for_policy
from src.core.source_registry import CandidateRegistry, normalize_candidate_url
from src.schemas.models import (
    DiscoveryOrigin,
    EvaluatedSource,
    SourceEvaluation,
    SourceEvaluationResult,
    SourceEvaluatorInput,
    SourcePolicy,
    SourceProfile,
)
from src.tools.groq_client import GroqClient
from src.tools.web.models import SourcePreview


logger = get_logger(__name__)


def build_source_evaluator_input(state: Dict[str, Any]) -> SourceEvaluatorInput:
    config = state.get("config", {})
    source_config = config.get("sources", {})
    if not isinstance(source_config, dict):
        source_config = {}
    policy = SourcePolicy.model_validate(
        state.get("source_policy") or source_config.get("source_policy", {})
    )
    return SourceEvaluatorInput(
        dataset_topic=state.get("dataset_topic", ""),
        dataset_purpose=state.get("dataset_purpose", ""),
        source_policy=policy,
        preferred_domains=source_config.get("preferred_domains", []),
        allowed_domains=source_config.get("allowed_domains"),
        blocked_domains=source_config.get("blocked_domains"),
        research_plan=state.get("research_plan", {}),
        research_constraints=config.get("research", {}).get("constraints", ""),
        candidate_sources=state.get("candidate_sources", []),
        source_previews=state.get("source_previews", []),
    )


def _preview_map(items: list[dict[str, Any]]) -> dict[str, SourcePreview]:
    previews: dict[str, SourcePreview] = {}
    for item in items:
        preview = SourcePreview.model_validate(item)
        try:
            key = normalize_candidate_url(preview.url)
        except ValueError:
            key = preview.url
        previews[key] = preview
    return previews


def _canonical_key(url: str) -> str:
    try:
        return normalize_candidate_url(url)
    except ValueError:
        return url


def _apply_policy_to_profiles(
    evaluator_input: SourceEvaluatorInput,
    proposed: list[EvaluatedSource],
) -> list[EvaluatedSource]:
    candidates = {
        _canonical_key(item.get("canonical_url") or item["url"]): item
        for item in evaluator_input.candidate_sources
    }
    proposed_by_url: dict[str, EvaluatedSource] = {}
    for item in proposed:
        key = _canonical_key(item.url)
        if key not in candidates:
            raise ValueError(f"SourceEvaluator returned an unknown URL: {item.url}")
        if key in proposed_by_url:
            raise ValueError(f"SourceEvaluator returned a duplicate URL: {item.url}")
        proposed_by_url[key] = item
    missing = [url for url in candidates if url not in proposed_by_url]
    if missing:
        raise ValueError(
            "SourceEvaluator omitted candidate URLs: " + ", ".join(missing)
        )

    previews = _preview_map(evaluator_input.source_previews)
    evaluated: list[EvaluatedSource] = []
    for url in candidates:
        proposed_item = proposed_by_url[url]
        evaluated.append(evaluate_source_for_policy(
            url=url,
            profile=proposed_item.source_profile,
            topic_relevance_score=proposed_item.topic_relevance_score,
            preview=previews.get(url),
            policy=evaluator_input.source_policy,
            preferred_domains=evaluator_input.preferred_domains,
            allowed_domains=evaluator_input.allowed_domains,
            blocked_domains=evaluator_input.blocked_domains,
            model_reasons=proposed_item.reasons,
        ))
    return evaluated


def _mock_profiles(evaluator_input: SourceEvaluatorInput) -> list[EvaluatedSource]:
    previews = _preview_map(evaluator_input.source_previews)
    proposed: list[EvaluatedSource] = []
    for candidate in evaluator_input.candidate_sources:
        url = _canonical_key(candidate.get("canonical_url") or candidate["url"])
        profile = SourceProfile.model_validate(candidate.get("source_profile") or {})
        preview = previews.get(url)
        proposed.append(EvaluatedSource(
            url=url,
            source_profile=profile,
            topic_relevance_score=float(
                candidate.get("topic_relevance_score", 1.0 if preview and preview.fetch_success else 0.0)
            ),
            reasons=["Mock profile evaluated deterministically for offline testing."],
            preview_success=bool(preview and preview.fetch_success),
        ))
    return _apply_policy_to_profiles(evaluator_input, proposed)


def _compatibility_result(
    evaluated: list[EvaluatedSource],
    *,
    max_sources: int,
) -> SourceEvaluationResult:
    eligible = sorted(
        (item for item in evaluated if item.decision == "select"),
        key=lambda item: -item.final_score,
    )
    selected_items = eligible[:max_sources]
    selected_urls = {item.url for item in selected_items}
    selected = [
        SourceEvaluation(
            url=item.url,
            selected=True,
            reason="; ".join(item.reasons),
            priority=priority,
        )
        for priority, item in enumerate(selected_items, start=1)
    ]
    rejected_items = [item for item in evaluated if item.url not in selected_urls]
    rejected = [
        SourceEvaluation(
            url=item.url,
            selected=False,
            reason=(
                "; ".join(item.reasons)
                if item.decision == "reject"
                else "Eligible but deferred by the configured source limit."
            ),
            priority=priority,
        )
        for priority, item in enumerate(rejected_items, start=len(selected) + 1)
    ]
    return SourceEvaluationResult(
        evaluated_sources=evaluated,
        selected_sources=selected,
        rejected_sources=rejected,
    )


def _mock_evaluation(state: Dict[str, Any]) -> SourceEvaluationResult:
    evaluator_input = build_source_evaluator_input(state)
    evaluated = _mock_profiles(evaluator_input)
    limit = state.get("config", {}).get("research", {}).get(
        "max_sources",
        len(evaluated),
    )
    return _compatibility_result(evaluated, max_sources=limit)


def _apply_evaluation(
    candidates: list[dict[str, Any]],
    evaluation: SourceEvaluationResult,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map compatibility decisions back without allowing unknown provider URLs."""
    candidate_urls = {candidate.get("url") for candidate in candidates}
    selected_by_url = {
        item.url: item
        for item in evaluation.selected_sources
        if item.url in candidate_urls
    }
    rejected = [
        item.model_dump()
        for item in evaluation.rejected_sources
        if item.url in candidate_urls
    ]
    selected_sources = []
    for candidate in candidates:
        decision = selected_by_url.get(candidate.get("url"))
        if decision:
            selected_sources.append({
                **candidate,
                "reason": decision.reason,
                "priority": decision.priority,
            })

    # Legacy adapter only. Rich policy evaluations never bypass a hard rejection.
    if not selected_sources and not evaluation.evaluated_sources:
        for priority, candidate in enumerate(
            (item for item in candidates if item.get("user_supplied_reference")),
            start=1,
        ):
            selected_sources.append({
                **candidate,
                "reason": "Selected as a user-supplied source because no source was selected automatically.",
                "priority": priority,
                "selection_origin": "manual_override",
            })
    selected_sources.sort(key=lambda item: item["priority"])
    return selected_sources, rejected


def _ensure_registry(
    registry: CandidateRegistry,
    candidates: list[dict[str, Any]],
) -> CandidateRegistry:
    if len(registry):
        return registry
    for candidate in candidates:
        query = str(candidate.get("search_query", "")).strip()
        is_seed = bool(candidate.get("user_supplied_reference"))
        registry.add(
            candidate["url"],
            origin=DiscoveryOrigin(
                method="seed" if is_seed else ("search" if query else "mock"),
                query=query if query and not is_seed else None,
                seed_url=candidate["url"] if is_seed else None,
                source_provider=candidate.get("source_provider") or None,
            ),
            title=candidate.get("title", ""),
            description=candidate.get("description", ""),
            source_provider=candidate.get("source_provider", ""),
        )
    return registry


def source_evaluator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate every supplied candidate from bounded evidence and explicit policy."""
    try:
        evaluator_input = build_source_evaluator_input(state)
        candidates = evaluator_input.candidate_sources
        logger.info("Evaluating %d candidate sources.", len(candidates))
        if not candidates:
            raise ValueError("No candidate sources were found for evaluation.")

        if settings.data_source_provider == "mock":
            evaluation = _mock_evaluation(state)
        else:
            user_payload = {
                "evaluator_input": evaluator_input.model_dump(mode="json"),
                "required_result_field": "evaluated_sources",
                "evaluated_source_contract": EvaluatedSource.model_json_schema(),
            }
            proposed = GroqClient().complete_json(
                SOURCE_EVALUATOR_SYSTEM_PROMPT,
                json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
                SourceEvaluationResult,
            )
            if not proposed.evaluated_sources:
                raise ValueError(
                    "SourceEvaluator returned no evaluated_sources; the policy-aware profile contract is required."
                )
            evaluated = _apply_policy_to_profiles(
                evaluator_input,
                proposed.evaluated_sources,
            )
            max_sources = state.get("config", {}).get("research", {}).get(
                "max_sources",
                len(evaluated),
            )
            evaluation = _compatibility_result(evaluated, max_sources=max_sources)

        selected_sources, rejected = _apply_evaluation(candidates, evaluation)
        logger.info(
            "Policy evaluation produced %d provisionally eligible and %d rejected compatibility sources.",
            len(selected_sources),
            len(rejected),
        )
        registry = _ensure_registry(
            CandidateRegistry(state.get("source_registry")),
            candidates,
        )
        serialized_evaluations = [
            item.model_dump(mode="json") for item in evaluation.evaluated_sources
        ]
        registry.record_policy_evaluations(serialized_evaluations)
        registry.record_evaluation(
            selected_sources=selected_sources,
            rejected_sources=rejected,
        )
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_evaluations": serialized_evaluations,
            "selected_sources": selected_sources,
            "rejected_sources": rejected,
            "status": "sources_evaluated",
            "pipeline_status": "sources_evaluated",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{
                "node": "source_evaluator",
                "error": str(error),
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
