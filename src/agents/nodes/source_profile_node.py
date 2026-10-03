"""Generate local source profiles and verify their evidence with Jev."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.core.logging import get_logger
from src.core.settings import settings
from src.core.source_registry import normalize_candidate_url
from src.observability.events import emit
from src.schemas.models import (
    SourceProfileBatch,
    SourceProfileVerification,
)
from src.tools.structured_generation.groq_provider import GroqStructuredProvider
from src.tools.structured_generation.jev_provider import JevDecisionProvider
from src.tools.structured_generation.ollama_provider import OllamaStructuredProvider
from src.tools.web.models import SourcePreview


logger = get_logger(__name__)

PROFILE_PROMPT = (
    "Characterize only the supplied page preview and metadata. Return one profile "
    "per candidate with its exact URL and candidate_id. Do not browse, invent "
    "content, change identities, or assert facts absent from the preview. "
    "Use unknown/empty values when evidence is insufficient. Return JSON only."
)


class SourceProfileIdentityError(ValueError):
    """A generated profile batch omitted or changed a supplied candidate."""


def _key(candidate: dict[str, Any]) -> str:
    return normalize_candidate_url(candidate.get("canonical_url") or candidate["url"])


def _previews(state: dict[str, Any]) -> dict[str, SourcePreview]:
    return {normalize_candidate_url(item["url"]): SourcePreview.model_validate(item)
            for item in state.get("source_previews", [])}


def _generate_profiles(provider: Any, candidates: list[dict[str, Any]],
                       previews: dict[str, SourcePreview], *, task_name: str) -> dict[str, dict[str, Any]]:
    payload = {
        "candidates": [
            {"url": _key(candidate), "candidate_id": candidate.get("candidate_id"),
             "title": candidate.get("title", ""),
             "preview": previews[_key(candidate)].model_dump(mode="json",
                 exclude={"internal_links", "external_links"})}
            for candidate in candidates
        ],
        "required_output": SourceProfileBatch.model_json_schema(),
    }
    result = provider.generate(
        system_prompt=PROFILE_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        output_model=SourceProfileBatch,
        task_name=task_name,
    )
    expected = {_key(candidate): candidate for candidate in candidates}
    found: dict[str, dict[str, Any]] = {}
    for proposal in result.profiles:
        # Exact supplied identity is required; URL normalization must not silently
        # accept a different URL returned by a model.
        if proposal.url not in expected or proposal.url in found:
            raise SourceProfileIdentityError(f"Profile provider returned an unknown or duplicate URL: {proposal.url}")
        if proposal.candidate_id != expected[proposal.url].get("candidate_id"):
            raise SourceProfileIdentityError(f"Profile provider changed candidate identity: {proposal.url}")
        found[proposal.url] = proposal.model_dump(mode="json")
    if set(found) != set(expected):
        raise SourceProfileIdentityError("Profile provider omitted candidate URLs.")
    return found


def source_profile_generation_node(state: dict[str, Any], *, benchmark: bool = False) -> dict[str, Any]:
    """Generate Gemma proposals in the existing configured candidate batches."""
    try:
        if not settings.source_evaluator_benchmark_approved and not benchmark:
            raise RuntimeError("Jev source profiling requires SOURCE_EVALUATOR_BENCHMARK_APPROVED=true after a same-gold benchmark.")
        if settings.source_evaluation_batch_size < 1:
            raise ValueError("SOURCE_EVALUATION_BATCH_SIZE must be at least 1.")
        previews = _previews(state)
        candidates = [item for item in state.get("candidate_sources", [])
                      if (preview := previews.get(_key(item))) is not None and preview.fetch_success]
        local = OllamaStructuredProvider(
            model=settings.source_evaluator_model,
            timeout=settings.source_evaluator_timeout,
            strict_schema=True,
        )
        proposals: list[dict[str, Any]] = []
        batches = 0
        calls = 0
        retry_calls = 0
        for start in range(0, len(candidates), settings.source_evaluation_batch_size):
            batch = candidates[start:start + settings.source_evaluation_batch_size]
            batches += 1
            calls += 1
            try:
                found = _generate_profiles(local, batch, previews,
                                           task_name=f"source_profiles_{start + 1}")
                for candidate in batch:
                    proposal = {**found[_key(candidate)], "provider": "ollama"}
                    proposals.append(proposal)
                    emit("source_profile_generated", source_url=proposal["url"], details=proposal)
            except Exception as error:
                logger.warning("Gemma profile batch failed for candidate positions %d-%d: %s",
                               start + 1, start + len(batch), error)
                for candidate in batch:
                    try:
                        if not isinstance(error, (SourceProfileIdentityError, ValidationError)):
                            raise error
                        calls += 1
                        retry_calls += 1
                        found = _generate_profiles(local, [candidate], previews,
                                                   task_name=f"source_profile_retry_{_key(candidate)}")
                        proposal = {**found[_key(candidate)], "provider": "ollama"}
                    except Exception as candidate_error:
                        proposal = {"url": _key(candidate), "candidate_id": candidate.get("candidate_id"),
                                    "provider": "ollama", "error": str(candidate_error)}
                    proposals.append(proposal)
                    emit("source_profile_generated", source_url=proposal["url"],
                         status="completed" if "source_profile" in proposal else "error", details=proposal)
        return {"source_profile_proposals": proposals,
                "source_profile_metrics": {"gemma_batches": batches,
                    "gemma_model": settings.source_evaluator_model,
                    "gemma_calls": calls, "gemma_retry_calls": retry_calls,
                    "gemma_proposals":
                    sum("source_profile" in item for item in proposals)},
                "status": "sources_profiled", "pipeline_status": "sources_profiled"}
    except Exception as error:
        emit("source_profile_error", status="error", details={"stage": "generation", "error": str(error)})
        return {"errors": state.get("errors", []) + [{"node": "source_profile_generation", "error": str(error)}],
                "status": "failed", "pipeline_status": "failed"}


def source_profile_verification_node(state: dict[str, Any]) -> dict[str, Any]:
    """Accept supported Gemma profiles; retry only unsupported candidates with Groq."""
    try:
        previews = _previews(state)
        proposals: dict[str, dict[str, Any]] = {}
        candidate_urls = {_key(item) for item in state.get("candidate_sources", [])}
        for item in state.get("source_profile_proposals", []):
            url = item.get("url", "")
            if url not in candidate_urls or url in proposals:
                raise SourceProfileIdentityError(f"Profile proposal has unknown or duplicate URL: {url}")
            proposals[url] = item
        jev = JevDecisionProvider()
        cloud = None
        results: list[dict[str, Any]] = []
        groq_calls = 0
        for candidate in state.get("candidate_sources", []):
            url = _key(candidate)
            preview = previews.get(url)
            if preview is None or not preview.fetch_success:
                continue
            proposal = proposals.get(url)
            if proposal is not None and proposal.get("candidate_id") != candidate.get("candidate_id"):
                raise ValueError(f"Profile proposal changed candidate identity: {url}")
            reasons: list[str] = []
            attempts: list[dict[str, Any]] = []
            accepted: SourceProfileVerification | None = None
            attempted_provider = "ollama"
            for provider_name in ("ollama", "groq"):
                attempted_provider = provider_name
                if provider_name == "ollama":
                    item = proposal
                    if item is None or "source_profile" not in item:
                        reasons.append("Gemma did not return a valid complete profile.")
                        attempts.append({"provider": "ollama", "status": "generation_failed",
                                         "error": item.get("error") if item else "Missing profile proposal"})
                        continue
                else:
                    emit("profile_fallback", source_url=url, status="fallback",
                         details={"from_provider": "ollama", "to_provider": "groq", "reasons": reasons})
                    logger.warning("Falling back to Groq profile for %s: %s", url, "; ".join(reasons))
                    groq_calls += 1
                    try:
                        if cloud is None:
                            cloud = GroqStructuredProvider(output_mode="json_object")
                        item = _generate_profiles(cloud, [candidate], previews,
                                                  task_name="source_profile_fallback")[url]
                    except Exception as error:
                        reasons.append(f"Groq profile generation failed: {error}")
                        attempts.append({"provider": "groq", "status": "generation_failed", "error": str(error)})
                        break
                profile = SourceProfileBatch.model_validate({"profiles": [item]}).profiles[0].source_profile
                checks = jev.verify_profile(preview=preview, profile=profile)
                supported = profile.source_type != "unknown" and set(checks) == {
                    "source_type_supported", "content_supported", "scores_supported"
                } and all(
                    score >= max(0.80, settings.source_profile_min_support)
                    for score in checks.values()
                )
                attempts.append({"provider": provider_name,
                                 "status": "accepted" if supported else "unsupported",
                                 "checks": checks})
                if supported:
                    accepted = SourceProfileVerification(
                        url=url, candidate_id=candidate.get("candidate_id"),
                        source_profile=profile, status="accepted", provider=provider_name,
                        checks=checks, attempts=attempts, reasons=reasons,
                    )
                    break
                reasons.append(f"{provider_name} profile lacked preview support: {checks}")
            result = accepted or SourceProfileVerification(
                url=url, candidate_id=candidate.get("candidate_id"), status="rejected",
                provider=attempted_provider, attempts=attempts, reasons=reasons,
            )
            serialized = result.model_dump(mode="json")
            results.append(serialized)
            emit("source_profile_verified", source_url=url,
                 status="completed" if result.status == "accepted" else "rejected",
                 details=serialized)
            if result.status == "rejected":
                logger.warning("Skipping source with unsupported profiles: %s: %s", url, "; ".join(reasons))
        return {"source_profile_verifications": results,
                "source_profile_metrics": {**state.get("source_profile_metrics", {}),
                    "groq_model": settings.groq_model if groq_calls else None,
                    "groq_fallback_calls": groq_calls,
                    "profiles_accepted": sum(item["status"] == "accepted" for item in results),
                    "profiles_rejected": sum(item["status"] == "rejected" for item in results),
                    **jev.metrics()},
                "status": "source_profiles_verified", "pipeline_status": "source_profiles_verified"}
    except Exception as error:
        emit("source_profile_error", status="error", details={"stage": "verification", "error": str(error)})
        return {"errors": state.get("errors", []) + [{"node": "source_profile_verification", "error": str(error)}],
                "status": "failed", "pipeline_status": "failed"}
