"""Frozen benchmark proof for the Phase 15 batch/evidence representation."""

from pathlib import Path

from scripts.run_phase15_extraction_contract import run_contract_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_phase15_batch_contract_represents_every_frozen_record_without_a_cap():
    result = run_contract_benchmark()

    assert result["batch_count"] == 8
    assert result["metrics"] == {
        "page_count": 8,
        "expected_records": 12,
        "predicted_records": 12,
        "record_precision": 1.0,
        "record_recall": 1.0,
        "field_precision": 1.0,
        "field_recall": 1.0,
        "schema_valid_rate": 1.0,
        "unsupported_field_rate": 0.0,
        "duplicate_rate": 0.0,
    }


def test_phase15_contract_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase15_extraction_contract.json"
    )
    assert run_contract_benchmark() == saved
