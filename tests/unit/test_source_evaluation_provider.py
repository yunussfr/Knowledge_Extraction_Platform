"""SourceEvaluator-specific provider routing tests."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from src.tools.structured_generation.source_evaluation_provider import (
    SourceEvaluationRoutingProvider,
)
from src.tools.structured_generation.ollama_provider import _strict_schema


class Output(BaseModel):
    value: str


class FixtureProvider:
    def __init__(self, value: str = "ok", error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls = 0

    def generate(self, **_):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Output(value=self.value)


def _generate(provider: SourceEvaluationRoutingProvider) -> Output:
    return provider.generate(
        system_prompt="system",
        user_prompt="user",
        output_model=Output,
        task_name="source_evaluation_test",
    )


def test_ollama_evaluator_requires_separate_benchmark_approval():
    local = FixtureProvider()
    provider = SourceEvaluationRoutingProvider(
        provider="ollama",
        model="gemma-fixture",
        benchmark_approved=False,
        local=local,
        cloud=FixtureProvider("cloud"),
    )

    with pytest.raises(RuntimeError, match="not benchmark-approved"):
        _generate(provider)

    assert local.calls == 0


def test_approved_ollama_evaluator_uses_local_without_cloud():
    local = FixtureProvider("local")
    cloud = FixtureProvider("cloud")
    provider = SourceEvaluationRoutingProvider(
        provider="ollama",
        model="gemma-fixture",
        benchmark_approved=True,
        cloud_fallback=False,
        local=local,
        cloud=cloud,
    )

    assert _generate(provider).value == "local"
    assert local.calls == 1
    assert cloud.calls == 0
    assert provider.metrics()["fallback_calls"] == 0


def test_local_failure_is_visible_when_cloud_fallback_is_disabled():
    cloud = FixtureProvider("cloud")
    provider = SourceEvaluationRoutingProvider(
        provider="ollama",
        model="gemma-fixture",
        benchmark_approved=True,
        cloud_fallback=False,
        local=FixtureProvider(error=ValueError("invalid local schema")),
        cloud=cloud,
    )

    with pytest.raises(RuntimeError, match="invalid local schema"):
        _generate(provider)

    assert cloud.calls == 0
    assert provider.metrics()["local_calls"] == 1


def test_explicit_cloud_fallback_is_counted():
    cloud = FixtureProvider("cloud")
    provider = SourceEvaluationRoutingProvider(
        provider="ollama",
        model="gemma-fixture",
        benchmark_approved=True,
        cloud_fallback=True,
        local=FixtureProvider(error=ValueError("invalid local schema")),
        cloud=cloud,
    )

    assert _generate(provider).value == "cloud"
    assert provider.metrics()["fallback_calls"] == 1
    assert provider.metrics()["cloud_calls"] == 1


def test_source_evaluator_has_no_direct_groq_dependency():
    project_root = Path(__file__).resolve().parents[2]
    source = (
        project_root / "src" / "agents" / "nodes" / "source_evaluator_node.py"
    ).read_text(encoding="utf-8")

    assert "GroqClient" not in source
    assert "get_source_evaluation_provider" in source


def test_local_evaluator_schema_requires_defaulted_nested_fields():
    schema = _strict_schema({
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "source_type": {
                        "type": "string",
                        "default": "unknown",
                    }
                },
            }
        },
    })

    assert schema["required"] == ["profile"]
    assert schema["properties"]["profile"]["required"] == ["source_type"]
    assert "default" not in schema["properties"]["profile"]["properties"]["source_type"]
