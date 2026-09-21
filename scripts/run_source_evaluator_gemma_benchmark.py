"""Benchmark a local Gemma SourceEvaluator on the frozen Phase 9 source set."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from src.agents.nodes.source_evaluator_node import (
    _apply_policy_to_profiles,
    _batched_evaluator_input,
    build_evaluation_user_payload,
    generate_evaluated_batch,
)
from src.core.settings import settings
from src.evaluation.metrics import evaluate_policy_source_predictions, load_json
from src.schemas.models import (
    SourceEvaluatorInput,
    SourcePolicy,
)
from src.tools.structured_generation.base import StructuredGenerationProvider
from src.tools.structured_generation.ollama_provider import OllamaStructuredProvider
from src.tools.web.models import SourcePreview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "fixtures"
    / "source_evaluation_gold.json"
)
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "baselines"
    / "source_evaluator_gemma_benchmark.json"
)


def _candidate_input(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": candidate["url"],
        "canonical_url": candidate["url"],
        "title": candidate["id"].replace("_", " "),
        "description": candidate["preview"],
        "domain": candidate["url"].split("/")[2],
        "search_query": "transformer architecture attention evidence",
    }


def _preview_input(candidate: dict[str, Any]) -> dict[str, Any]:
    text = candidate["preview"]
    return SourcePreview(
        url=candidate["url"],
        title=candidate["id"].replace("_", " "),
        domain=candidate["url"].split("/")[2],
        relevant_text=text,
        approximate_word_count=len(text.split()),
        preview_word_count=len(text.split()),
        fetch_success=True,
    ).model_dump(mode="json")


def _decision_metrics(
    gold: dict[str, Any],
    predictions_by_policy: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    expected_by_id = {item["id"]: item["expected"] for item in gold["candidates"]}
    by_policy: dict[str, dict[str, Any]] = {}
    total_expected = 0
    total_true_positive = 0
    for policy_id, predictions in predictions_by_policy.items():
        expected_selected = {
            candidate_id
            for candidate_id, expected in expected_by_id.items()
            if expected[policy_id]["decision"] == "select"
        }
        predicted_selected = {
            item["candidate_id"]
            for item in predictions
            if item["decision"] == "select"
        }
        true_positive = len(expected_selected & predicted_selected)
        total_expected += len(expected_selected)
        total_true_positive += true_positive
        by_policy[policy_id] = {
            "expected_selected": len(expected_selected),
            "predicted_selected": len(predicted_selected),
            "useful_selection_recall": round(
                true_positive / len(expected_selected), 6
            ) if expected_selected else 1.0,
        }
    return {
        "by_policy": by_policy,
        "useful_selection_recall": round(
            total_true_positive / total_expected, 6
        ) if total_expected else 1.0,
    }


def _quality_gate(
    metrics: dict[str, Any],
    operational: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "schema_validity_rate": operational["schema_validity_rate"] == 1.0,
        "candidate_completeness_rate": operational["candidate_completeness_rate"] == 1.0,
        "batch_failure_rate": operational["batch_failure_rate"] == 0.0,
        "policy_alignment_accuracy": metrics["policy_alignment_accuracy"] >= 0.70,
        "source_precision_at_5": metrics["source_precision_at_5"] >= 0.80,
        "source_precision_at_10": metrics["source_precision_at_10"] >= 0.65,
        "hard_policy_violation_rate": metrics["hard_policy_violation_rate"] == 0.0,
        "useful_selection_recall": decisions["useful_selection_recall"] >= 0.60,
        "every_policy_selects_a_source": all(
            item["predicted_selected"] > 0
            for item in decisions["by_policy"].values()
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": {
            "schema_validity_rate": 1.0,
            "candidate_completeness_rate": 1.0,
            "batch_failure_rate": 0.0,
            "policy_alignment_accuracy_minimum": 0.70,
            "source_precision_at_5_minimum": 0.80,
            "source_precision_at_10_minimum": 0.65,
            "hard_policy_violation_rate": 0.0,
            "useful_selection_recall_minimum": 0.60,
            "every_policy_selects_a_source": True,
        },
    }


def run_gemma_source_evaluation_benchmark(
    provider: StructuredGenerationProvider | None = None,
    *,
    model: str | None = None,
    batch_size: int = 2,
) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    model_name = model or settings.source_evaluator_model
    provider = provider or OllamaStructuredProvider(
        model=model_name,
        timeout=settings.source_evaluator_timeout,
        strict_schema=True,
    )
    gold = load_json(FIXTURE_PATH)
    candidates = [_candidate_input(item) for item in gold["candidates"]]
    previews = [_preview_input(item) for item in gold["candidates"]]
    predictions_by_policy: dict[str, list[dict[str, Any]]] = {}
    total_batches = 0
    successful_batches = 0
    evaluated_candidates = 0
    errors: list[dict[str, Any]] = []
    started = time.perf_counter()

    for policy_id, raw_policy in gold["policies"].items():
        evaluator_input = SourceEvaluatorInput(
            dataset_topic=gold["topic"],
            dataset_purpose=gold["purpose"],
            source_policy=SourcePolicy.model_validate(raw_policy),
            research_plan={"search_queries": ["transformer architecture attention"]},
            candidate_sources=candidates,
            source_previews=previews,
        )
        policy_predictions: list[dict[str, Any]] = []
        policy_batch_count = (len(candidates) + batch_size - 1) // batch_size
        total_batches += policy_batch_count
        for batch_index, start in enumerate(
            range(0, len(candidates), batch_size), start=1
        ):
            batch_candidates = candidates[start:start + batch_size]
            batch_input = _batched_evaluator_input(evaluator_input, batch_candidates)
            end = start + len(batch_candidates)
            payload = build_evaluation_user_payload(
                batch_input,
                batch_number=batch_index,
                total_batches=policy_batch_count,
                candidate_start_position=start + 1,
                candidate_end_position=end,
                total_candidates=len(candidates),
            )
            try:
                evaluated = generate_evaluated_batch(
                    provider,
                    batch_input,
                    payload,
                    task_name=(
                        f"gemma_source_evaluation_{policy_id}_{batch_index}"
                    ),
                    max_retries=settings.source_evaluator_max_retries,
                )
            except Exception as error:
                errors.append({
                    "policy": policy_id,
                    "batch": batch_index,
                    "candidate_start_position": start + 1,
                    "candidate_end_position": end,
                    "error": str(error),
                })
                continue
            successful_batches += 1
            evaluated_candidates += len(evaluated)
            ids_by_url = {
                item["url"]: item["id"] for item in gold["candidates"]
            }
            policy_predictions.extend({
                "candidate_id": ids_by_url[item.url],
                "source_type": item.source_profile.source_type,
                "final_score": item.final_score,
                "decision": item.decision,
                "hard_policy_rejected": item.hard_policy_rejected,
            } for item in evaluated)
        predictions_by_policy[policy_id] = policy_predictions

    elapsed = time.perf_counter() - started
    expected_candidates = len(candidates) * len(gold["policies"])
    operational = {
        "total_batches": total_batches,
        "successful_batches": successful_batches,
        "failed_batches": total_batches - successful_batches,
        "schema_validity_rate": round(
            successful_batches / total_batches, 6
        ) if total_batches else 0.0,
        "candidate_completeness_rate": round(
            evaluated_candidates / expected_candidates, 6
        ) if expected_candidates else 0.0,
        "batch_failure_rate": round(
            (total_batches - successful_batches) / total_batches, 6
        ) if total_batches else 0.0,
        "latency_seconds": round(elapsed, 6),
    }
    result: dict[str, Any] = {
        "benchmark_version": "1.0",
        "benchmark": "source_evaluator_gemma",
        "provider": provider.provider_name,
        "model": model_name,
        "batch_size": batch_size,
        "operational_metrics": operational,
        "errors": errors,
        "predictions_by_policy": predictions_by_policy,
    }
    if errors:
        result.update({
            "status": "failed",
            "quality_gate": {"passed": False, "reason": "One or more batches failed."},
        })
        return result

    metrics = evaluate_policy_source_predictions(gold, predictions_by_policy)
    decisions = _decision_metrics(gold, predictions_by_policy)
    result.update({
        "status": "completed",
        "metrics": metrics,
        "decision_metrics": decisions,
        "quality_gate": _quality_gate(metrics, operational, decisions),
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=settings.source_evaluator_model)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    result = run_gemma_source_evaluation_benchmark(
        model=args.model,
        batch_size=args.batch_size,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.save:
        DEFAULT_OUTPUT_PATH.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not result.get("quality_gate", {}).get("passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
