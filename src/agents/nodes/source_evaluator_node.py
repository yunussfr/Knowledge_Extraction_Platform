"""Characterize candidates and evaluate them against the current request policy."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from src.agents.prompts import SOURCE_EVALUATOR_SYSTEM_PROMPT
from src.observability.events import current_journal, emit, operation
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
from src.tools.structured_generation import get_source_evaluation_provider
from src.tools.web.models import SourcePreview


logger = get_logger(__name__)

GENERATION_IDENTITY_REJECTION_REASON = (
    "Source evaluation was excluded because local and cloud generation "
    "did not preserve the candidate identity."
)


class SourceEvaluationIdentityError(ValueError):
    """Raised when generated evaluations cannot be mapped to supplied candidates."""


def _evaluation_provider_metrics(
    provider: Any,
    *,
    candidate_count: int,
    batch_size: int,
    total_batches: int,
    completed_batches: int,
) -> dict[str, Any]:
    provider_metrics = provider.metrics() if provider is not None and hasattr(provider, "metrics") else {}
    return {
        **provider_metrics,
        "candidate_count": candidate_count,
        "batch_size": batch_size,
        "total_batches": total_batches,
        "completed_batches": completed_batches,
    }


def build_evaluation_user_payload(
    batch_input: SourceEvaluatorInput,
    *,
    batch_number: int,
    total_batches: int,
    candidate_start_position: int,
    candidate_end_position: int,
    total_candidates: int,
) -> dict[str, Any]:
    """Build the exact bounded provider payload used at runtime and in benchmarks."""
    return {
        "evaluation_batch_context": {
            "batch_number": batch_number,
            "total_batches": total_batches,
            "candidate_start_position": candidate_start_position,
            "candidate_end_position": candidate_end_position,
            "total_candidates": total_candidates,
            "ordering": "canonical_discovery_order",
            "instruction": (
                "Evaluate exactly this ordered batch. Global selection and "
                "ranking occur only after every batch has been evaluated."
            ),
        },
        "evaluator_input": batch_input.model_dump(mode="json"),
        "required_result_field": "evaluated_sources",
        "evaluated_source_contract": EvaluatedSource.model_json_schema(),
        "source_profile_requirements": {
            "source_type": (
                "Return one concise canonical lowercase label such as government, "
                "university, academic, official_documentation, independent_technical, "
                "news, dataset, forum, or social_media. Do not append words such as "
                "website, source, page, or portal. When supplied evidence clearly "
                "matches an explicit allowed_source_types label, use that exact label."
            ),
            "evidence_boundary": (
                "Characterize only from the candidate metadata and preview supplied "
                "in this batch."
            ),
            "candidate_id": (
                "Include the candidate_id (e.g. cand_1) for each evaluated source "
                "to ensure accurate mapping."
            ),
        },
    }


def generate_evaluated_batch(provider, batch_input, user_payload, *, task_name, max_retries, system_prompt=None):
    with operation(batch_id=task_name, source_urls=[candidate.get("canonical_url") or candidate["url"]
                                                  for candidate in batch_input.candidate_sources]):
        emit("evaluation_input", status="running", details=user_payload)
        result = _generate_evaluated_batch(provider, batch_input, user_payload,
            task_name=task_name, max_retries=max_retries, system_prompt=system_prompt)
        emit("batch_completed", details={"evaluations": result})
        return result


def _generate_evaluated_batch(
    provider: Any,
    batch_input: SourceEvaluatorInput,
    user_payload: dict[str, Any],
    *,
    task_name: str,
    max_retries: int,
    system_prompt: str | None = None,
) -> list[EvaluatedSource]:
    """Generate and fully validate one batch with bounded local retries."""
    if max_retries < 0:
        raise ValueError("SourceEvaluator max_retries must be at least 0.")
    resolved_system_prompt = system_prompt if system_prompt is not None else SOURCE_EVALUATOR_SYSTEM_PROMPT
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            def validate_result(
                proposed: SourceEvaluationResult,
            ) -> list[EvaluatedSource]:
                if not proposed.evaluated_sources:
                    raise ValueError(
                        "SourceEvaluator returned no evaluated_sources; the "
                        "policy-aware profile contract is required."
                    )
                try:
                    result = _apply_policy_to_profiles(batch_input, proposed.evaluated_sources)
                except Exception as error:
                    emit("evaluation_validated", status="error", details={"proposed": proposed, "validation": "failed", "error": str(error)})
                    raise
                emit("evaluation_validated", details={"proposed": proposed, "validation": "candidate_identity_and_policy_valid"})
                return result

            generation_args = {
                "system_prompt": resolved_system_prompt,
                "user_prompt": json.dumps(
                    user_payload, ensure_ascii=False, sort_keys=True
                ),
                "output_model": SourceEvaluationResult,
                "task_name": f"{task_name}_attempt_{attempt + 1}",
            }
            if hasattr(provider, "generate_validated"):
                return provider.generate_validated(
                    **generation_args,
                    validator=validate_result,
                )
            return validate_result(provider.generate(**generation_args))
        except Exception as error:
            last_error = error
            if attempt < max_retries:
                emit("retry", status="retry", details={"reason": str(error), "next_attempt": attempt + 2, "task": task_name})
    assert last_error is not None
    if isinstance(last_error, SourceEvaluationIdentityError):
        candidate_urls = [
            _canonical_key(candidate.get("canonical_url") or candidate["url"])
            for candidate in batch_input.candidate_sources
        ]
        logger.warning(
            "Excluding source evaluation batch after local/cloud candidate-identity "
            "validation failed. Candidates: %s. Error: %s",
            ", ".join(candidate_urls),
            last_error,
        )
        return _identity_failure_rejections(batch_input, last_error)
    raise last_error


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


def _batched_evaluator_input(
    evaluator_input: SourceEvaluatorInput,
    candidates: list[dict[str, Any]],
) -> SourceEvaluatorInput:
    """Keep one ordered candidate slice and only its matching previews."""
    candidate_urls = {
        _canonical_key(item.get("canonical_url") or item["url"])
        for item in candidates
    }
    previews = [
        preview
        for preview in evaluator_input.source_previews
        if _canonical_key(preview.get("url", "")) in candidate_urls
    ]
    return evaluator_input.model_copy(update={
        "candidate_sources": candidates,
        "source_previews": previews,
    })


def _canonical_key(url: str) -> str:
    try:
        return normalize_candidate_url(url)
    except ValueError:
        return url


def _unwrap_exact_markdown_url(value: str) -> str:
    """Unwrap only a Markdown link whose label and target are the same URL."""
    stripped = value.strip()
    match = re.fullmatch(
        r"\[(https?://[^\]\s]+)\]\((https?://[^)\s]+)\)",
        stripped,
    )
    if match is None:
        return stripped

    label_url, target_url = match.groups()
    if _canonical_key(label_url) == _canonical_key(target_url):
        return target_url
    return stripped


def _partition_candidates_by_preview(
    evaluator_input: SourceEvaluatorInput,
) -> tuple[list[dict[str, Any]], list[EvaluatedSource]]:
    """Send only successful previews to the model and reject failures deterministically."""
    previews = _preview_map(evaluator_input.source_previews)
    model_candidates: list[dict[str, Any]] = []
    deterministic_rejections: list[EvaluatedSource] = []

    for candidate in evaluator_input.candidate_sources:
        url = _canonical_key(
            candidate.get("canonical_url") or candidate["url"]
        )
        preview = previews.get(url)

        if preview is not None and preview.fetch_success:
            model_candidates.append(candidate)
            continue

        if preview is None:
            reason = (
                "Source preview was missing; skipped model-based "
                "source characterization."
            )
        else:
            reason = (
                "Source preview failed; skipped model-based "
                "source characterization."
            )

        deterministic_rejections.append(
            evaluate_source_for_policy(
                url=url,
                profile=SourceProfile(source_type="unknown"),
                topic_relevance_score=0.0,
                preview=preview,
                policy=evaluator_input.source_policy,
                preferred_domains=evaluator_input.preferred_domains,
                allowed_domains=evaluator_input.allowed_domains,
                blocked_domains=evaluator_input.blocked_domains,
                model_reasons=[reason],
            )
        )

    return model_candidates, deterministic_rejections


def _identity_failure_rejections(
    evaluator_input: SourceEvaluatorInput,
    error: SourceEvaluationIdentityError,
) -> list[EvaluatedSource]:
    """Reject an invalid generated batch without losing candidate provenance."""
    previews = _preview_map(evaluator_input.source_previews)
    rejected: list[EvaluatedSource] = []
    for candidate in evaluator_input.candidate_sources:
        url = _canonical_key(candidate.get("canonical_url") or candidate["url"])
        rejected.append(evaluate_source_for_policy(
            url=url,
            profile=SourceProfile(source_type="unknown"),
            topic_relevance_score=0.0,
            preview=previews.get(url),
            policy=evaluator_input.source_policy,
            preferred_domains=evaluator_input.preferred_domains,
            allowed_domains=evaluator_input.allowed_domains,
            blocked_domains=evaluator_input.blocked_domains,
            model_reasons=[
                GENERATION_IDENTITY_REJECTION_REASON,
                f"Candidate identity validation error: {error}",
            ],
        ))
    return rejected


def _apply_policy_to_profiles(
    evaluator_input: SourceEvaluatorInput,
    proposed: list[EvaluatedSource],
) -> list[EvaluatedSource]:
    candidates = {
        _canonical_key(item.get("canonical_url") or item["url"]): item
        for item in evaluator_input.candidate_sources
    }
    candidate_by_id = {
        str(item.get("candidate_id")): _canonical_key(item.get("canonical_url") or item["url"])
        for item in evaluator_input.candidate_sources
        if item.get("candidate_id")
    }
    proposed_by_url: dict[str, EvaluatedSource] = {}
    for item in proposed:
        matched_key = None
        returned_url = _unwrap_exact_markdown_url(item.url) if item.url else ""
        if item.candidate_id and str(item.candidate_id) in candidate_by_id:
            matched_key = candidate_by_id[str(item.candidate_id)]
        elif returned_url in candidate_by_id:
            matched_key = candidate_by_id[returned_url]
        elif returned_url:
            key = _canonical_key(returned_url)
            if key in candidates:
                matched_key = key

        if not matched_key:
            raise SourceEvaluationIdentityError(
                f"SourceEvaluator returned an unknown URL: {item.url}"
            )
        if matched_key in proposed_by_url:
            raise SourceEvaluationIdentityError(
                f"SourceEvaluator returned a duplicate URL: {matched_key}"
            )
        item.url = matched_key
        proposed_by_url[matched_key] = item
    missing = [url for url in candidates if url not in proposed_by_url]
    if missing:
        raise SourceEvaluationIdentityError(
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
    provider = None
    batch_size = settings.source_evaluation_batch_size
    total_batches = 0
    completed_batches = 0
    try:
        evaluator_input = build_source_evaluator_input(state)
        candidates = evaluator_input.candidate_sources
        logger.info("Evaluating %d candidate sources.", len(candidates))
        if not candidates:
            raise ValueError("No candidate sources were found for evaluation.")

        if settings.data_source_provider == "mock":
            evaluation = _mock_evaluation(state)
            source_evaluation_metrics = {
                "provider": "mock",
                "model": "deterministic",
                "candidate_count": len(candidates),
                "batch_size": len(candidates),
                "total_batches": 1,
                "completed_batches": 1,
                "local_calls": 0,
                "cloud_calls": 0,
                "fallback_calls": 0,
            }
        else:
            if batch_size < 1:
                raise ValueError("SOURCE_EVALUATION_BATCH_SIZE must be at least 1.")

            model_candidates, deterministic_rejections = (
                _partition_candidates_by_preview(evaluator_input)
            )
            logger.info(
                "Evaluating %d preview-success candidates; deterministically "
                "rejecting %d preview failures.",
                len(model_candidates),
                len(deterministic_rejections),
            )

            total_batches = (
                (len(model_candidates) + batch_size - 1) // batch_size
                if model_candidates
                else 0
            )
            evaluated_by_url = {
                _canonical_key(item.url): item
                for item in deterministic_rejections
            }

            if model_candidates:
                provider = get_source_evaluation_provider()
                minimum_confidence = state.get("config", {}).get("quality", {}).get(
                    "minimum_confidence", settings.minimum_confidence
                )
                formatted_system_prompt = SOURCE_EVALUATOR_SYSTEM_PROMPT.format(
                    minimum_confidence=minimum_confidence
                )
                for batch_index, start in enumerate(
                    range(0, len(model_candidates), batch_size),
                    start=1,
                ):
                    batch_candidates = model_candidates[start:start + batch_size]
                    batch_input = _batched_evaluator_input(
                        evaluator_input,
                        batch_candidates,
                    )
                    end = start + len(batch_candidates)
                    user_payload = build_evaluation_user_payload(
                        batch_input,
                        batch_number=batch_index,
                        total_batches=total_batches,
                        candidate_start_position=start + 1,
                        candidate_end_position=end,
                        total_candidates=len(model_candidates),
                    )
                    logger.info(
                        "Evaluating source batch %d/%d "
                        "(preview-success candidate positions %d-%d).",
                        batch_index,
                        total_batches,
                        start + 1,
                        end,
                    )
                    batch_evaluations = generate_evaluated_batch(
                        provider,
                        batch_input,
                        user_payload,
                        task_name=f"source_evaluation_batch_{batch_index}",
                        max_retries=settings.source_evaluator_max_retries,
                        system_prompt=formatted_system_prompt,
                    )
                    for item in batch_evaluations:
                        evaluated_by_url[_canonical_key(item.url)] = item
                    completed_batches += 1

            evaluated = [
                evaluated_by_url[
                    _canonical_key(candidate.get("canonical_url") or candidate["url"])
                ]
                for candidate in candidates
            ]
            max_sources = state.get("config", {}).get("research", {}).get(
                "max_sources",
                len(evaluated),
            )
            evaluation = _compatibility_result(evaluated, max_sources=max_sources)
            source_evaluation_metrics = {
                **_evaluation_provider_metrics(
                    provider,
                    candidate_count=len(candidates),
                    batch_size=batch_size,
                    total_batches=total_batches,
                    completed_batches=completed_batches,
                ),
                "model_evaluated_candidates": len(model_candidates),
                "deterministic_preview_rejections": len(
                    deterministic_rejections
                ),
                "generation_identity_rejections": sum(
                    GENERATION_IDENTITY_REJECTION_REASON in item.reasons
                    for item in evaluated
                ),
            }

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
        for item in serialized_evaluations:
            emit("policy_applied", source_url=item["url"],
                 status="rejected" if item.get("decision") == "reject" else "completed", details=item)
        registry.record_policy_evaluations(serialized_evaluations)
        registry.record_evaluation(
            selected_sources=selected_sources,
            rejected_sources=rejected,
        )
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": registry.active_pipeline_candidates(),
            "source_evaluations": serialized_evaluations,
            "source_evaluation_metrics": source_evaluation_metrics,
            "selected_sources": selected_sources,
            "rejected_sources": rejected,
            "status": "sources_evaluated",
            "pipeline_status": "sources_evaluated",
        }
    except Exception as error:
        return {
            "source_evaluation_metrics": _evaluation_provider_metrics(
                provider,
                candidate_count=len(state.get("candidate_sources", [])),
                batch_size=batch_size,
                total_batches=total_batches,
                completed_batches=completed_batches,
            ),
            "errors": state.get("errors", []) + [{
                "node": "source_evaluator",
                "error": str(error),
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
