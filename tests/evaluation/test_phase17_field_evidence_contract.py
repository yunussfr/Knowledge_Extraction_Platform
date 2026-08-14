"""Frozen acceptance checks for the Phase 17 evidence contract."""

from pathlib import Path

from scripts.run_phase17_field_evidence_contract import run_contract_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_all_gold_records_keep_usable_traceable_field_evidence():
    result = run_contract_benchmark()

    assert result["input_records"] == 12
    assert result["metrics"] == {
        "emitted_records": 12,
        "rejected_records": 0,
        "merged_records": 12,
        "evidenced_fields": 35,
        "evidence_refs": 35,
        "traceable_evidence_refs": 35,
        "records_with_usable_evidence": 12,
    }


def test_phase17_contract_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase17_field_evidence_contract.json"
    )
    assert run_contract_benchmark() == saved
