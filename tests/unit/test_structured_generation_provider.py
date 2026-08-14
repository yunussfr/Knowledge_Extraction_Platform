"""Phase 16 provider-neutral structured-generation boundary tests."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from src.schemas.models import ExtractionBatch
from src.tools.structured_generation import (
    GroqStructuredProvider,
    StructuredGenerationProvider,
    get_structured_generation_provider,
)


class ExampleOutput(BaseModel):
    value: str


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def complete_json(
        self, system_prompt, user_prompt, output_model, *, response_format=None
    ):
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "output_model": output_model,
            "response_format": response_format,
        })
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return output_model.model_validate(outcome)


def test_factory_and_protocol_expose_a_provider_neutral_contract():
    provider = get_structured_generation_provider()

    assert isinstance(provider, StructuredGenerationProvider)
    assert provider.provider_name == "groq"


def test_strict_mode_sends_pydantic_json_schema_and_returns_validated_model():
    client = FakeClient([{"value": "validated"}])
    provider = GroqStructuredProvider(client=client, output_mode="json_schema")

    result = provider.generate(
        system_prompt="system",
        user_prompt="user",
        output_model=ExampleOutput,
        task_name="example task",
    )

    assert result == ExampleOutput(value="validated")
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "example_task"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["value"]


def test_auto_mode_falls_back_only_for_explicit_unsupported_schema_format():
    client = FakeClient([
        RuntimeError("response_format json_schema is unsupported by this model"),
        {"value": "fallback"},
    ])
    provider = GroqStructuredProvider(client=client, output_mode="auto")

    result = provider.generate(
        system_prompt="system",
        user_prompt="user",
        output_model=ExampleOutput,
        task_name="example",
    )

    assert result.value == "fallback"
    assert [call["response_format"]["type"] for call in client.calls] == [
        "json_schema", "json_object"
    ]


@pytest.mark.parametrize("message", [
    "invalid schema: property definition is malformed",
    "authentication failed",
    "temporary provider timeout",
])
def test_auto_mode_does_not_hide_non_capability_failures(message):
    client = FakeClient([RuntimeError(message)])
    provider = GroqStructuredProvider(client=client, output_mode="auto")

    with pytest.raises(RuntimeError, match=message):
        provider.generate(
            system_prompt="system",
            user_prompt="user",
            output_model=ExampleOutput,
            task_name="example",
        )

    assert len(client.calls) == 1


def test_required_strict_mode_never_falls_back_when_model_is_unsupported():
    client = FakeClient([
        RuntimeError("response_format json_schema is unsupported by this model")
    ])
    provider = GroqStructuredProvider(client=client, output_mode="json_schema")

    with pytest.raises(RuntimeError, match="unsupported"):
        provider.generate(
            system_prompt="system",
            user_prompt="user",
            output_model=ExampleOutput,
            task_name="example",
        )

    assert len(client.calls) == 1


def test_json_object_mode_skips_strict_attempt_but_keeps_pydantic_validation():
    client = FakeClient([{"value": 123}])
    provider = GroqStructuredProvider(client=client, output_mode="json_object")

    with pytest.raises(Exception):
        provider.generate(
            system_prompt="system",
            user_prompt="user",
            output_model=ExampleOutput,
            task_name="example",
        )

    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_invalid_provider_mode_fails_deterministically():
    with pytest.raises(ValueError, match="GROQ_STRUCTURED_OUTPUT_MODE"):
        GroqStructuredProvider(client=FakeClient([]), output_mode="guess")


def test_semantic_extraction_node_has_no_direct_groq_dependency():
    project_root = Path(__file__).resolve().parents[2]
    source = (
        project_root / "src" / "agents" / "nodes" / "structured_extraction_node.py"
    ).read_text(encoding="utf-8")

    assert "GroqClient" not in source
    assert "src.tools.groq" not in source
    assert "get_structured_generation_provider" in source


def test_extraction_batch_schema_can_cross_the_provider_boundary():
    client = FakeClient([{"records": [], "warnings": []}])
    result = GroqStructuredProvider(
        client=client, output_mode="json_schema"
    ).generate(
        system_prompt="system",
        user_prompt="user",
        output_model=ExtractionBatch,
        task_name="structured_extraction",
    )

    assert isinstance(result, ExtractionBatch)
    assert result.records == []
