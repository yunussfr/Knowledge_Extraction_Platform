"""Frozen Phase 19 cross-source resolution acceptance tests."""

from pathlib import Path

from scripts.run_phase19_record_resolution import run_resolution_benchmark
from src.evaluation import load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_resolved_record_preserves_support_from_multiple_sources():
    result = run_resolution_benchmark()

    assert result["metrics"] == {
        "input_records": 3,
        "resolved_records": 2,
        "cross_source_records": 1,
        "contributors": 3,
        "conflicts": 1,
        "method_counts": {
            "explicit_identity": 2,
            "normalized_identity": 0,
            "composite_identity": 0,
            "local_record": 0,
        },
    }
    record = result["multi_source_record"]
    assert record["source_urls"] == [
        "https://fixtures.example/resolution/source-a",
        "https://fixtures.example/resolution/source-b",
    ]
    assert record["item_name_evidence_sources"] == record["source_urls"]
    assert record["contributors"] == 2
    assert record["conflicts"] == 1
    assert record["kept_description"] == "fault-tolerant retrieval service"
    assert record["conflicting_description"] == "resilient retrieval platform"


def test_phase19_benchmark_matches_saved_artifact():
    saved = load_json(
        PROJECT_ROOT / "docs" / "baselines" / "phase19_record_resolution.json"
    )
    assert run_resolution_benchmark() == saved
