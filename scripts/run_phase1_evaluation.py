"""Run the frozen Phase 1 source-policy and extraction baseline offline."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation import evaluate_extraction, evaluate_sources, load_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "evaluation" / "fixtures"


def run_baseline() -> dict:
    gold_sources = load_json(FIXTURE_ROOT / "source_evaluation_gold.json")
    gold_extraction = load_json(FIXTURE_ROOT / "extraction_gold.json")
    predictions = load_json(FIXTURE_ROOT / "legacy_baseline_predictions.json")
    return {
        "benchmark_version": "1.0",
        "baseline": "legacy_deterministic",
        "source_evaluation": evaluate_sources(gold_sources, predictions),
        "extraction": evaluate_extraction(gold_extraction, predictions),
    }


def main() -> None:
    print(json.dumps(run_baseline(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
