"""Groq adapter for provider-neutral Pydantic structured generation."""

from __future__ import annotations

import re
from typing import Any, TypeVar

from pydantic import BaseModel

from src.core.settings import settings
from src.tools.groq_client import GroqClient


OutputModel = TypeVar("OutputModel", bound=BaseModel)


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize Pydantic JSON Schema to strict object semantics recursively."""
    normalized: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"default", "title"}:
            continue
        if isinstance(value, dict):
            normalized[key] = _strict_schema(value)
        elif isinstance(value, list):
            normalized[key] = [
                _strict_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            normalized[key] = value
    if normalized.get("type") == "object" or "properties" in normalized:
        properties = normalized.get("properties", {})
        normalized["additionalProperties"] = False
        normalized["required"] = list(properties)
    return normalized


def _schema_response_format(
    output_model: type[BaseModel], task_name: str
) -> dict[str, Any]:
    schema_name = re.sub(r"[^A-Za-z0-9_-]+", "_", task_name).strip("_")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name or "structured_generation",
            "strict": True,
            "schema": _strict_schema(output_model.model_json_schema()),
        },
    }


def _strict_output_is_unsupported(error: Exception) -> bool:
    message = str(error).casefold()
    output_marker = any(marker in message for marker in (
        "json_schema", "response_format", "structured output",
    ))
    unsupported_marker = any(marker in message for marker in (
        "unsupported", "not supported", "does not support", "unavailable",
    ))
    return output_marker and unsupported_marker


class GroqStructuredProvider:
    """Attempt strict schema output first and isolate a narrow compatibility fallback."""

    provider_name = "groq"
    SUPPORTED_MODES = {"auto", "json_schema", "json_object"}

    def __init__(
        self,
        *,
        client: GroqClient | None = None,
        output_mode: str | None = None,
    ) -> None:
        self._client = client or GroqClient()
        self.output_mode = (
            output_mode or settings.groq_structured_output_mode
        ).strip().lower()
        if self.output_mode not in self.SUPPORTED_MODES:
            raise ValueError(
                "GROQ_STRUCTURED_OUTPUT_MODE must be auto, json_schema, or json_object."
            )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[OutputModel],
        task_name: str,
    ) -> OutputModel:
        if self.output_mode == "json_object":
            return self._client.complete_json(
                system_prompt, user_prompt, output_model,
                response_format={"type": "json_object"},
            )

        try:
            return self._client.complete_json(
                system_prompt,
                user_prompt,
                output_model,
                response_format=_schema_response_format(output_model, task_name),
            )
        except Exception as error:
            if self.output_mode != "auto" or not _strict_output_is_unsupported(error):
                raise
            return self._client.complete_json(
                system_prompt, user_prompt, output_model,
                response_format={"type": "json_object"},
            )
