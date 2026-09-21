"""Task-specific structured provider routing for source evaluation."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from src.core.settings import settings
from src.tools.structured_generation.groq_provider import GroqStructuredProvider
from src.tools.structured_generation.ollama_provider import OllamaStructuredProvider


OutputModel = TypeVar("OutputModel", bound=BaseModel)


class SourceEvaluationRoutingProvider:
    """Route only SourceEvaluator generation without changing extraction routing."""

    SUPPORTED_PROVIDERS = {"groq", "ollama"}

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        benchmark_approved: bool | None = None,
        cloud_fallback: bool | None = None,
        local=None,
        cloud=None,
    ) -> None:
        self.configured_provider = (
            provider or settings.source_evaluator_provider
        ).strip().lower()
        if self.configured_provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                "SOURCE_EVALUATOR_PROVIDER must be groq or ollama."
            )
        self.model_name = model or (
            settings.source_evaluator_model
            if self.configured_provider == "ollama"
            else settings.groq_model
        )
        self.benchmark_approved = (
            settings.source_evaluator_benchmark_approved
            if benchmark_approved is None
            else benchmark_approved
        )
        self.cloud_fallback_enabled = (
            settings.source_evaluator_cloud_fallback
            if cloud_fallback is None
            else cloud_fallback
        )
        self.local = local or OllamaStructuredProvider(
            model=self.model_name,
            timeout=settings.source_evaluator_timeout,
            strict_schema=True,
        )
        # Source evaluation historically used JSON Object Mode. Preserve that
        # behavior when Groq is selected or explicitly used as a fallback.
        self.cloud = cloud or GroqStructuredProvider(output_mode="json_object")
        self.provider_name = self.configured_provider
        self.local_calls = 0
        self.cloud_calls = 0
        self.fallback_calls = 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[OutputModel],
        task_name: str,
    ) -> OutputModel:
        if self.configured_provider == "groq":
            self.cloud_calls += 1
            return self.cloud.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_model=output_model,
                task_name=task_name,
            )

        if not self.benchmark_approved:
            raise RuntimeError(
                "Local SourceEvaluator is configured but not benchmark-approved. "
                "Run the Gemma source-evaluation benchmark before setting "
                "SOURCE_EVALUATOR_BENCHMARK_APPROVED=true."
            )

        self.local_calls += 1
        try:
            return self.local.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_model=output_model,
                task_name=task_name,
            )
        except Exception as error:
            if not self.cloud_fallback_enabled:
                raise RuntimeError(
                    f"Local SourceEvaluator failed with {self.model_name}: {error}"
                ) from error
            self.fallback_calls += 1
            self.cloud_calls += 1
            return self.cloud.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_model=output_model,
                task_name=task_name,
            )

    def metrics(self) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "benchmark_approved": self.benchmark_approved,
            "cloud_fallback_enabled": self.cloud_fallback_enabled,
            "local_calls": self.local_calls,
            "cloud_calls": self.cloud_calls,
            "fallback_calls": self.fallback_calls,
        }


def get_source_evaluation_provider() -> SourceEvaluationRoutingProvider:
    return SourceEvaluationRoutingProvider()
