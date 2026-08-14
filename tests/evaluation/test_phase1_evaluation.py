"""Acceptance tests for the frozen Phase 1 gold evaluation set."""

from pathlib import Path

from scripts.run_phase1_evaluation import FIXTURE_ROOT, run_baseline
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_source_gold_set_has_required_size_cases_and_policy_matrix():
    gold = load_json(FIXTURE_ROOT / "source_evaluation_gold.json")
    candidates = gold["candidates"]

    assert 20 <= len(candidates) <= 30
    assert set(gold["policies"]) == {"policy_a", "policy_b"}
    assert gold["policies"]["policy_a"]["allowed_source_types"] is None
    assert gold["policies"]["policy_a"]["blocked_source_types"] is None
    assert gold["policies"]["policy_b"]["allowed_source_types"] == [
        "academic", "government", "university"
    ]

    cases = [set(candidate["cases"]) for candidate in candidates]
    required_combinations = [
        {"high-authority", "deep", "relevant"},
        {"high-authority", "shallow", "relevant"},
        {"high-authority", "irrelevant"},
        {"independent", "deep", "relevant"},
        {"independent", "shallow"},
        {"university", "useful"},
        {"university", "irrelevant"},
        {"official", "useful"},
        {"official", "shallow"},
        {"thin-page"},
        {"duplicate-page"},
        {"useful-non-seed-domain"},
        {"allowed-source-type"},
        {"blocked-by-policy-b"},
    ]
    assert all(any(required <= observed for observed in cases) for required in required_combinations)
    assert all(set(candidate["expected"]) == set(gold["policies"]) for candidate in candidates)


def test_same_source_has_policy_specific_expected_outcomes():
    gold = load_json(FIXTURE_ROOT / "source_evaluation_gold.json")
    candidate = next(
        item for item in gold["candidates"] if item["id"] == "independent_deep_relevant"
    )

    assert candidate["expected"]["policy_a"] == {
        "decision": "select", "hard_policy_rejected": False
    }
    assert candidate["expected"]["policy_b"] == {
        "decision": "reject", "hard_policy_rejected": True
    }


def test_extraction_gold_set_covers_required_pages_and_traceable_evidence():
    gold = load_json(FIXTURE_ROOT / "extraction_gold.json")
    pages = gold["pages"]
    observed_scenarios = {scenario for page in pages for scenario in page["scenarios"]}

    assert 5 <= len(pages) <= 10
    assert {
        "zero-record-page",
        "single-record-page",
        "many-record-page",
        "repeated-dom-cards",
        "table",
        "long-prose",
        "missing-optional-fields",
        "duplicate-information",
    } <= observed_scenarios
    assert len(next(page for page in pages if "long-prose" in page["scenarios"])["content"].split()) >= 100

    for page in pages:
        for record in page["expected_records"]:
            assert record["data"]["item_name"]
            for field_name, evidence_values in record["field_evidence"].items():
                assert field_name in record["data"]
                assert evidence_values
                assert all(evidence in page["content"] for evidence in evidence_values)


def test_phase1_metrics_cover_every_required_measure_and_expose_legacy_gaps():
    result = run_baseline()

    assert result["source_evaluation"] == {
        "candidate_count": 24,
        "policy_count": 2,
        "source_precision_at_5": 0.4,
        "source_precision_at_10": 0.35,
        "precision_at_5_by_policy": {"policy_a": 0.4, "policy_b": 0.4},
        "precision_at_10_by_policy": {"policy_a": 0.4, "policy_b": 0.3},
        "policy_alignment_accuracy": 0.520833,
        "hard_policy_violation_rate": 0.25,
        "same_source_multi_policy_outcome_count": 9,
    }
    assert result["extraction"] == {
        "page_count": 8,
        "expected_records": 12,
        "predicted_records": 8,
        "record_precision": 0.875,
        "record_recall": 0.583333,
        "field_precision": 0.956522,
        "field_recall": 0.542857,
        "schema_valid_rate": 0.875,
        "unsupported_field_rate": 1.0,
        "duplicate_rate": 0.125,
    }


def test_phase1_baseline_is_reproducible_and_matches_saved_artifact():
    first = run_baseline()
    second = run_baseline()
    saved = load_json(PROJECT_ROOT / "docs" / "baselines" / "phase1_baseline.json")

    assert first == second == saved
