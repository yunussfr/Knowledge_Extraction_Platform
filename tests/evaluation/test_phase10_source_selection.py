"""Frozen benchmark regression gates for Phase 10 source selection."""

import json
from pathlib import Path

from scripts.run_phase10_source_selection import run_evaluation


SAVED_BASELINE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "baselines"
    / "phase10_source_selection.json"
)


def test_phase10_selection_is_reproducible_and_improves_diversity_safely():
    first = run_evaluation()
    second = run_evaluation()

    assert first == second
    assert first["after"]["hard_policy_violation_rate"] == 0.0
    assert first["after"]["precision"] >= first["before"]["precision"]
    assert first["after"]["unique_domain_count"] >= first["before"]["unique_domain_count"]
    assert first["after"]["duplicate_selection_rate"] == 0.0
    assert first["after"]["max_domain_share"] <= first["before"]["max_domain_share"]
    saved = json.loads(SAVED_BASELINE.read_text(encoding="utf-8"))
    assert saved == {
        key: first[key]
        for key in [
            "after",
            "before",
            "benchmark_version",
            "delta",
            "implementation",
            "selection_limit",
        ]
    }


def test_phase10_every_policy_stays_within_the_selection_limit():
    result = run_evaluation()

    assert all(
        metrics["selected_count"] <= result["selection_limit"]
        for metrics in result["after_by_policy"].values()
    )
