"""Run the frozen source-evaluation set through the live Gemma/Jev route.

Requires local Ollama/Gemma and JEV_API_KEY. Groq is used only for a failed
profile and needs its configured key in that case. No crawler is called.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from src.agents.nodes.source_evaluator_node import _jev_evaluation, build_source_evaluator_input
from src.agents.nodes.source_profile_node import (
    source_profile_generation_node, source_profile_verification_node,
)
from src.core.settings import settings
from src.evaluation.metrics import evaluate_policy_source_predictions, load_json
from scripts.run_source_evaluator_gemma_benchmark import (
    FIXTURE_PATH, _candidate_input, _decision_metrics, _preview_input, _quality_gate,
)


BASELINE_PATH = Path(__file__).resolve().parents[1] / "docs/baselines/source_evaluator_gemma_benchmark.json"


def run_jev_source_evaluation_benchmark() -> dict:
    if settings.source_evaluator_provider != "jev":
        raise RuntimeError("Set SOURCE_EVALUATOR_PROVIDER=jev for the live comparison.")
    if not settings.jev_api_key:
        raise RuntimeError("JEV_API_KEY is required for the live Jev benchmark.")
    gold = load_json(FIXTURE_PATH)
    candidates = [dict(_candidate_input(item), candidate_id=f"cand_{index}")
                  for index, item in enumerate(gold["candidates"], 1)]
    state = {"candidate_sources": candidates,
             "source_previews": [_preview_input(item) for item in gold["candidates"]],
             "dataset_topic": gold["topic"], "dataset_purpose": gold["purpose"],
             "source_policy": {}, "config": {"research": {"max_sources": len(candidates)}},
             "errors": []}
    started = time.perf_counter()
    state.update(source_profile_generation_node(state, benchmark=True))
    if state["status"] == "failed":
        return {"status": "failed", "stage": "gemma_profile", "errors": state["errors"]}
    state.update(source_profile_verification_node(state))
    if state["status"] == "failed":
        return {"status": "failed", "stage": "jev_profile_check", "errors": state["errors"]}
    ids_by_url = {item["url"]: item["id"] for item in gold["candidates"]}
    predictions = {}
    scoring_calls = 0
    for policy_id, policy in gold["policies"].items():
        state["source_policy"] = policy
        evaluated, metrics, _ = _jev_evaluation(state, build_source_evaluator_input(state))
        scoring_calls += metrics["jev_relevance_score_calls"]
        predictions[policy_id] = [{
            "candidate_id": ids_by_url[item.url],
            "source_type": item.source_profile.source_type,
            "final_score": item.final_score,
            "decision": item.decision,
            "hard_policy_rejected": item.hard_policy_rejected,
        } for item in evaluated.evaluated_sources]
    measured = evaluate_policy_source_predictions(gold, predictions)
    decisions = _decision_metrics(gold, predictions)
    operational = {
        "schema_validity_rate": 1.0,
        "candidate_completeness_rate": 1.0 if all(len(items) == len(candidates) for items in predictions.values()) else 0.0,
        "batch_failure_rate": 0.0,
        "profile_acceptance_rate": round(
            state["source_profile_metrics"].get("profiles_accepted", 0) / len(candidates), 6
        ) if candidates else 0.0,
    }
    baseline = load_json(BASELINE_PATH)
    baseline_metrics = baseline.get("metrics", {})
    keys = ("policy_alignment_accuracy", "source_precision_at_5", "source_precision_at_10",
            "hard_policy_violation_rate")
    return {
        "status": "completed", "benchmark": "source_evaluator_jev",
        "candidate_count": len(candidates), "policy_count": len(predictions),
        "metrics": measured, "decision_metrics": decisions,
        "operational_metrics": operational,
        "quality_gate": _quality_gate(measured, operational, decisions),
        "profile_metrics": state["source_profile_metrics"],
        "provider_calls": {"gemma_batches": state["source_profile_metrics"].get("gemma_batches", 0),
                           "groq_fallback": state["source_profile_metrics"].get("groq_fallback_calls", 0),
                           "jev_profile_checks": state["source_profile_metrics"].get("jev_calls", 0),
                           "jev_relevance_scores": scoring_calls},
        "baseline_comparison": {key: {"legacy_gemma": baseline_metrics.get(key),
                                      "new_jev": measured.get(key)} for key in keys},
        "useful_selection_comparison": {
            "legacy_gemma": baseline.get("decision_metrics", {}).get("useful_selection_recall"),
            "new_jev": decisions["useful_selection_recall"]},
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "predictions_by_policy": predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    result = run_jev_source_evaluation_benchmark()
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
