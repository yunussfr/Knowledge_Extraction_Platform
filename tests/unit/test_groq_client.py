"""Focused tests for the low-level Groq JSON client."""

from types import SimpleNamespace

from pydantic import BaseModel

from src.tools.groq_client import GroqClient


class ExampleOutput(BaseModel):
    value: str


def test_default_json_object_request_includes_explicit_json_instruction(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"value":"ok"}')
                    )
                ]
            )

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("groq.Groq", FakeGroq)
    monkeypatch.setattr(
        "src.tools.groq_client.settings",
        SimpleNamespace(
            groq_api_key="test-key",
            groq_request_timeout=60,
            groq_max_retries=0,
            groq_model="test-model",
            groq_temperature=0.0,
        ),
    )

    result = GroqClient().complete_json("system", "user", ExampleOutput)

    assert result == ExampleOutput(value="ok")
    assert captured["response_format"] == {"type": "json_object"}
    assert "json" in captured["messages"][1]["content"]


def test_json_schema_request_does_not_add_json_object_instruction(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"value":"ok"}')
                    )
                ]
            )

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("groq.Groq", FakeGroq)
    monkeypatch.setattr(
        "src.tools.groq_client.settings",
        SimpleNamespace(
            groq_api_key="test-key",
            groq_request_timeout=60,
            groq_max_retries=0,
            groq_model="test-model",
            groq_temperature=0.0,
        ),
    )

    GroqClient().complete_json(
        "system",
        "user",
        ExampleOutput,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "example",
                "schema": ExampleOutput.model_json_schema(),
            },
        },
    )

    assert captured["messages"][1]["content"] == "user"
