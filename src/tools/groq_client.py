"""Reusable Groq structured-output client."""

from __future__ import annotations

import json
from time import sleep
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from src.core.retry import is_retryable_provider_error
from src.core.settings import settings

if TYPE_CHECKING:
    from groq.types.chat.completion_create_params import ResponseFormat


OutputModel = TypeVar("OutputModel", bound=BaseModel)


class GroqClient:
    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: type[OutputModel],
        *,
        response_format: ResponseFormat | None = None,
    ) -> OutputModel:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when DATA_SOURCE_PROVIDER is firecrawl")

        from groq import Groq

        client = Groq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_request_timeout,
        )
        last_error: Exception | None = None
        for attempt in range(settings.groq_max_retries + 1):
            try:
                effective_response_format: ResponseFormat = (
                    response_format or {"type": "json_object"}
                )
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    temperature=settings.groq_temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=effective_response_format,
                )
                content = response.choices[0].message.content or "{}"
                return output_model.model_validate(json.loads(content))
            except Exception as error:
                last_error = error
                if attempt < settings.groq_max_retries and is_retryable_provider_error(error):
                    sleep(2 ** attempt)
                    continue
                break
        raise RuntimeError(f"Groq structured-output request failed: {last_error}") from last_error
