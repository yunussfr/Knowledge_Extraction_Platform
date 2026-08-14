"""Frozen Phase 18 evidence-validation and quality-gate acceptance tests."""

from pathlib import Path

from scripts.run_phase18_evidence_quality import run_evidence_quality_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_gold_is_supported_and_unsupported_accepted_field_rate_is_below_gate():
    result = run_evidence_quality_benchmark()

    assert result["gold"] == {
        "records": 12,
        "supported_records": 12,
        "accepted_records": 12,
    }
    assert result["status_counts"] == {
        "SUPPORTED": 12,
        "PARTIALLY_SUPPORTED": 1,
        "UNSUPPORTED": 1,
        "CONTRADICTED": 1,
    }
    assert result["quality_gate"]["accepted_records"] == 12
    assert result["quality_gate"]["rejected_records"] == 3
    assert result["quality_gate"]["unsupported_accepted_field_rate"] < 0.05
    assert result["quality_gate"]["extractor_confidence_used"] is False


def test_phase18_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase18_evidence_quality.json"
    )
    assert run_evidence_quality_benchmark() == saved
