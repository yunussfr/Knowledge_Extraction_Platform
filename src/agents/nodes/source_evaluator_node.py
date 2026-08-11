"""Select source candidates without creating or changing URLs."""

from typing import Any, Dict

from src.agents.prompts import SOURCE_EVALUATOR_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import SourceEvaluation, SourceEvaluationResult
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def _mock_evaluation(state: Dict[str, Any]) -> SourceEvaluationResult:
    candidates = state.get("candidate_sources", [])
    limit = state.get("config", {}).get("research", {}).get("max_sources", len(candidates))
    selected = [
        SourceEvaluation(url=item["url"], selected=True, reason="Mock source accepted for deterministic testing.", priority=index)
        for index, item in enumerate(candidates[:limit], start=1)
    ]
    rejected = [
        SourceEvaluation(url=item["url"], selected=False, reason="Excluded by the configured source limit.", priority=index)
        for index, item in enumerate(candidates[limit:], start=limit + 1)
    ]
    return SourceEvaluationResult(selected_sources=selected, rejected_sources=rejected)


def _apply_evaluation(candidates: list[dict[str, Any]], evaluation: SourceEvaluationResult) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map decisions back to candidates and honor explicit user-reference fallback."""
    candidate_urls = {candidate.get("url") for candidate in candidates}
    selected_by_url = {item.url: item for item in evaluation.selected_sources if item.url in candidate_urls}
    rejected = [item.model_dump() for item in evaluation.rejected_sources if item.url in candidate_urls]
    selected_sources = []
    for candidate in candidates:
        decision = selected_by_url.get(candidate.get("url"))
        if decision:
            selected_sources.append({**candidate, "reason": decision.reason, "priority": decision.priority})

    if not selected_sources:
        for priority, candidate in enumerate(
            (item for item in candidates if item.get("user_supplied_reference")), start=1
        ):
            selected_sources.append({
                **candidate,
                "reason": "Selected as a user-supplied source because no source was selected automatically.",
                "priority": priority,
                "selection_origin": "manual_override",
            })
    selected_sources.sort(key=lambda item: item["priority"])
    return selected_sources, rejected


def source_evaluator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates only the candidate URLs already found by the source-search node."""
    try:
        candidates = state.get("candidate_sources", [])
        logger.info("Evaluating %d candidate sources.", len(candidates))
        if not candidates:
            raise ValueError("No candidate sources were found for evaluation.")
        if settings.data_source_provider == "mock":
            evaluation = _mock_evaluation(state)
        else:
            user_prompt = (
                f"Dataset topic: {state.get('dataset_topic', '')}\n"
                f"Research plan: {state.get('research_plan', {})}\n"
                f"User research constraints: {state.get('config', {}).get('research', {}).get('constraints', '')}\n"
                f"Candidate sources: {candidates}"
            )
            evaluation = GroqClient().complete_json(
                SOURCE_EVALUATOR_SYSTEM_PROMPT, user_prompt, SourceEvaluationResult
            )

        selected_sources, rejected = _apply_evaluation(candidates, evaluation)
        if not selected_sources:
            raise ValueError("Source evaluation selected no usable sources. Add a reference URL or broaden the research constraints.")
        logger.info("Selected %d sources and rejected %d sources.", len(selected_sources), len(rejected))
        return {
            "selected_sources": selected_sources,
            "rejected_sources": rejected,
            "status": "sources_selected",
            "pipeline_status": "sources_selected",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "source_evaluator", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
