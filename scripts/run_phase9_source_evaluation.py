"""Run deterministic Phase 9 policy evaluation on the frozen Phase 1 source set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.source_policy_evaluator import evaluate_source_for_policy
from src.evaluation.metrics import evaluate_policy_source_predictions, load_json
from src.schemas.models import SourcePolicy, SourceProfile
from src.tools.web.models import SourcePreview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "evaluation" / "fixtures" / "source_evaluation_gold.json"
PHASE1_BASELINE = PROJECT_ROOT / "docs" / "baselines" / "phase1_baseline.json"


def _profile(candidate: dict[str, Any]) -> SourceProfile:
    cases = set(candidate.get("cases", []))
    source_type = candidate["source_type"]
    if "deep" in cases:
        depth = "deep"
    elif "shallow" in cases or "thin-page" in cases or "marketing" in cases:
        depth = "shallow"
    else:
        depth = "medium"

    characteristics: list[str] = []
    mappings = {
        "implementation-details": "implementation_details",
        "benchmark": "benchmark",
        "statistics": "statistics",
        "primary-facts": "primary_facts",
        "marketing": "marketing",
        "opinion": "opinion",
    }
    for case, label in mappings.items():
        if case in cases:
            characteristics.append(label)
    if "deep" in cases or "useful" in cases:
        characteristics.append("technical_explanation")
    if depth == "shallow":
        characteristics.append("shallow_summary")

    high_authority_types = {"government", "university", "academic", "official_documentation"}
    authority_score = 0.85 if source_type in high_authority_types else 0.45
    if source_type in {"forum", "social_media"}:
        authority_score = 0.25
    technical_score = {"deep": 0.92, "medium": 0.60, "shallow": 0.22}[depth]
    density_score = {"deep": 0.90, "medium": 0.62, "shallow": 0.25}[depth]
    extractability = 0.82 if source_type in {"dataset", "official_documentation", "academic"} else 0.70
    if "marketing" in cases or "opinion" in cases or "thin-page" in cases:
        extractability = 0.35

    return SourceProfile(
        source_type=source_type,
        content_characteristics=characteristics,
        content_depth=depth,
        authority_signals=["identified_publisher"] if source_type in high_authority_types else [],
        authority_score=authority_score,
        information_density_score=density_score,
        technical_depth_score=technical_score,
        recency_score=0.90 if "recent" in cases else 0.50,
        extractability_score=extractability,
    )


def run_evaluation() -> dict[str, Any]:
    gold = load_json(FIXTURE)
    predictions_by_policy: dict[str, list[dict[str, Any]]] = {}
    for policy_id, raw_policy in gold["policies"].items():
        policy = SourcePolicy.model_validate(raw_policy)
        predictions: list[dict[str, Any]] = []
        for candidate in gold["candidates"]:
            url = candidate["url"]
            preview = SourcePreview(
                url=url,
                title=candidate["id"],
                domain=url.split("/")[2],
                relevant_text=candidate["preview"],
                approximate_word_count=len(candidate["preview"].split()),
                preview_word_count=len(candidate["preview"].split()),
                fetch_success=True,
            )
            result = evaluate_source_for_policy(
                url=url,
                profile=_profile(candidate),
                topic_relevance_score=0.10 if "irrelevant" in candidate["cases"] else 0.90,
                preview=preview,
                policy=policy,
            )
            predictions.append({
                "candidate_id": candidate["id"],
                "final_score": result.final_score,
                "decision": result.decision,
                "hard_policy_rejected": result.hard_policy_rejected,
            })
        predictions_by_policy[policy_id] = predictions

    metrics = evaluate_policy_source_predictions(gold, predictions_by_policy)
    legacy = load_json(PHASE1_BASELINE)["source_evaluation"]
    return {
        "benchmark_version": gold["benchmark_version"],
        "implementation": "phase9_deterministic_policy_evaluator",
        "metrics": metrics,
        "legacy_baseline": legacy,
        "delta": {
            "source_precision_at_5": round(
                metrics["source_precision_at_5"] - legacy["source_precision_at_5"], 6
            ),
            "source_precision_at_10": round(
                metrics["source_precision_at_10"] - legacy["source_precision_at_10"], 6
            ),
            "policy_alignment_accuracy": round(
                metrics["policy_alignment_accuracy"] - legacy["policy_alignment_accuracy"], 6
            ),
            "hard_policy_violation_rate": round(
                metrics["hard_policy_violation_rate"] - legacy["hard_policy_violation_rate"], 6
            ),
        },
        "predictions_by_policy": predictions_by_policy,
    }


def main() -> None:
    print(json.dumps(run_evaluation(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
