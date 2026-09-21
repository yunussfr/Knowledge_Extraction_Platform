"""Small Ollama HTTP adapter kept outside the core dependency surface."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen

from pydantic import BaseModel


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every object field explicit for local constrained decoding."""
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
    if isinstance(normalized.get("properties"), dict):
        normalized["additionalProperties"] = False
        normalized["required"] = list(normalized["properties"])
    return normalized


class OllamaStructuredProvider:
    provider_name = "ollama"

    def __init__(self, *, base_url: str | None = None, model: str | None = None, timeout: int | None = None, strict_schema: bool = False) -> None:
        self.base_url = (base_url or os.getenv("LOCAL_MODEL_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LOCAL_MODEL", "llama3.1:8b")
        self.timeout = timeout or int(os.getenv("LOCAL_MODEL_TIMEOUT", "120"))
        self.strict_schema = strict_schema

    def generate(self, *, system_prompt: str, user_prompt: str, output_model: type[BaseModel], task_name: str) -> BaseModel:
        del task_name
        output_schema = output_model.model_json_schema()
        if self.strict_schema:
            output_schema = _strict_schema(output_schema)
        payload = {"model": self.model, "stream": False, "format": output_schema, "options": {"temperature": 0}, "system": system_prompt, "prompt": user_prompt}
        request = Request(f"{self.base_url}/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        raw = body.get("response")
        if not isinstance(raw, str):
            raise RuntimeError("Local model returned no JSON response.")
        return output_model.model_validate(json.loads(raw))
