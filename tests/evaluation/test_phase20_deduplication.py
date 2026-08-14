"""Frozen Phase 20 staged deduplication acceptance tests."""

from pathlib import Path

from scripts.run_phase20_deduplication import run_deduplication_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_staged_deduplication_reaches_zero_remaining_exact_duplicate_rate():
    result = run_deduplication_benchmark()

    assert result["metrics"] == {
        "input_records": 8,
        "output_records": 5,
        "duplicates_removed": 3,
        "remaining_exact_duplicate_rate": 0.0,
        "stage_counts": {
            "source_or_content": 1,
            "exact_normalized_record": 1,
            "schema_identity": 1,
        },
        "identity_conflicts_retained": 1,
    }
    assert result["rejection_count"] == 3
    provenance = result["source_duplicate_provenance"]
    assert provenance["contributors"] == 2
    assert provenance["evidence_refs"] == 4
    assert provenance["deduplication"]["stages"] == ["source_or_content"]


def test_phase20_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase20_deduplication.json"
    )
    assert run_deduplication_benchmark() == saved
