"""Evaluator-specific local Gemma benchmark harness tests."""

import json
from pathlib import Path

from src.schemas.models import EvaluatedSource, SourceEvaluationResult, SourceProfile
from scripts.run_source_evaluator_gemma_benchmark import (
    run_gemma_source_evaluation_benchmark,
)


class FixtureProvider:
    provider_name = "fixture-gemma"

    def generate(self, *, user_prompt, **_):
        payload = json.loads(user_prompt)
        evaluated = []
        for candidate in payload["evaluator_input"]["candidate_sources"]:
            evaluated.append(EvaluatedSource(
                url=candidate["url"],
                source_profile=SourceProfile(
                    source_type="independent_technical",
                    content_characteristics=["technical_explanation"],
                    content_depth="deep",
                    authority_score=0.5,
                    information_density_score=0.8,
                    technical_depth_score=0.8,
                    extractability_score=0.8,
                ),
                topic_relevance_score=0.9,
                reasons=["Fixture profile."],
            ))
        return SourceEvaluationResult(evaluated_sources=evaluated)


class FailingProvider:
    provider_name = "fixture-failing"

    def generate(self, **_):
        raise RuntimeError("fixture local failure")


def test_benchmark_scores_every_candidate_under_every_policy():
    result = run_gemma_source_evaluation_benchmark(
        FixtureProvider(), model="fixture", batch_size=10
    )

    assert result["status"] == "completed"
    assert result["operational_metrics"]["candidate_completeness_rate"] == 1.0
    assert result["operational_metrics"]["schema_validity_rate"] == 1.0
    assert result["metrics"]["candidate_count"] == 24
    assert result["metrics"]["policy_count"] == 2


def test_benchmark_keeps_local_batch_failures_visible():
    result = run_gemma_source_evaluation_benchmark(
        FailingProvider(), model="fixture", batch_size=24
    )

    assert result["status"] == "failed"
    assert result["quality_gate"]["passed"] is False
    assert result["operational_metrics"]["failed_batches"] == 2
    assert "fixture local failure" in result["errors"][0]["error"]


def test_saved_gemma_benchmark_passes_every_acceptance_gate():
    path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "baselines"
        / "source_evaluator_gemma_benchmark.json"
    )
    result = json.loads(path.read_text(encoding="utf-8"))

    assert result["model"] == "gemma4:e4b-it-qat"
    assert result["quality_gate"]["passed"] is True
    assert all(result["quality_gate"]["checks"].values())
    assert result["operational_metrics"]["candidate_completeness_rate"] == 1.0
    assert result["operational_metrics"]["schema_validity_rate"] == 1.0
