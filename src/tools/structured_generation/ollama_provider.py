"""Small Ollama HTTP adapter kept outside the core dependency surface."""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from pydantic import BaseModel


class OllamaStructuredProvider:
    provider_name = "ollama"

    def __init__(self, *, base_url: str | None = None, model: str | None = None, timeout: int | None = None) -> None:
        self.base_url = (base_url or os.getenv("LOCAL_MODEL_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LOCAL_MODEL", "llama3.1:8b")
        self.timeout = timeout or int(os.getenv("LOCAL_MODEL_TIMEOUT", "120"))

    def generate(self, *, system_prompt: str, user_prompt: str, output_model: type[BaseModel], task_name: str) -> BaseModel:
        del task_name
        payload = {"model": self.model, "stream": False, "format": output_model.model_json_schema(), "options": {"temperature": 0}, "system": system_prompt, "prompt": user_prompt}
        request = Request(f"{self.base_url}/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        raw = body.get("response")
        if not isinstance(raw, str):
            raise RuntimeError("Local model returned no JSON response.")
        return output_model.model_validate(json.loads(raw))
