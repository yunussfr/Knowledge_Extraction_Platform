"""Optional local structured-generation adapter.

The adapter is intentionally backend-agnostic: a local runtime can be injected
without making Ollama, llama.cpp, or another SDK part of the core dependency
surface. It is not selected automatically; Phase 24 requires benchmark proof
before local-first routing is enabled.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


class LocalStructuredProvider:
    provider_name = "local"

    def __init__(self, generator: Callable[..., Any] | None = None) -> None:
        self._generator = generator

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
        task_name: str,
    ) -> BaseModel:
        if self._generator is None:
            raise RuntimeError(
                "No local structured-generation backend is configured; "
                "run the opt-in Phase 24 benchmark before enabling local-first routing."
            )
        result = self._generator(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_model=output_model,
            task_name=task_name,
        )
        return result if isinstance(result, output_model) else output_model.model_validate(result)
