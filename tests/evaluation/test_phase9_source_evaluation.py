"""Reproducibility and regression gates for Phase 9 source evaluation."""

import json
from pathlib import Path

from scripts.run_phase9_source_evaluation import run_evaluation


SAVED_BASELINE = Path(__file__).resolve().parents[2] / "docs" / "baselines" / "phase9_source_evaluation.json"


def test_phase9_policy_evaluation_is_reproducible_and_improves_alignment():
    first = run_evaluation()
    second = run_evaluation()

    assert first == second
    assert first["metrics"]["candidate_count"] == 24
    assert first["metrics"]["policy_count"] == 2
    assert first["metrics"]["same_source_multi_policy_outcome_count"] == 9
    assert first["delta"]["policy_alignment_accuracy"] > 0
    assert first["metrics"]["hard_policy_violation_rate"] == 0.0
    assert first["delta"]["hard_policy_violation_rate"] < 0
    saved = json.loads(SAVED_BASELINE.read_text(encoding="utf-8"))
    assert saved == {
        key: first[key]
        for key in ["benchmark_version", "delta", "implementation", "metrics"]
    }


def test_phase9_predictions_are_request_specific_for_same_candidate_set():
    result = run_evaluation()
    policy_a = {
        item["candidate_id"]: item for item in result["predictions_by_policy"]["policy_a"]
    }
    policy_b = {
        item["candidate_id"]: item for item in result["predictions_by_policy"]["policy_b"]
    }

    candidate_id = "independent_deep_relevant"
    assert policy_a[candidate_id]["decision"] == "select"
    assert policy_b[candidate_id]["decision"] == "reject"
    assert policy_a[candidate_id]["hard_policy_rejected"] is False
    assert policy_b[candidate_id]["hard_policy_rejected"] is True
