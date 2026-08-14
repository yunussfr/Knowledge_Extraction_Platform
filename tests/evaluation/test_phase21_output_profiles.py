"""Frozen Phase 21 downstream output-profile acceptance tests."""

from pathlib import Path

from scripts.run_phase21_output_profiles import run_output_profile_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_structured_rag_and_graphrag_outputs_are_intentionally_different():
    result = run_output_profile_benchmark()

    assert result["profiles"] == ["structured", "rag", "graphrag"]
    assert result["record_counts"] == {
        "structured": 1,
        "rag": 1,
        "graphrag": 1,
    }
    assert result["intentional_difference"] is True
    assert result["graphrag"] == {
        "entities": 1,
        "claims": 2,
        "relations": 0,
        "claims_with_evidence": 2,
    }


def test_phase21_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase21_output_profiles.json"
    )
    assert run_output_profile_benchmark() == saved
