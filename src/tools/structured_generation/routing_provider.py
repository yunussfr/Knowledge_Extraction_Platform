"""Benchmark-gated local-first routing with controlled cloud fallback."""

from __future__ import annotations

import os
import re
from typing import TypeVar

from pydantic import BaseModel

from src.tools.structured_generation.groq_provider import GroqStructuredProvider
from src.tools.structured_generation.ollama_provider import OllamaStructuredProvider

OutputModel = TypeVar("OutputModel", bound=BaseModel)


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _evidence_quality_is_valid(result: BaseModel, user_prompt: str) -> bool:
    """Reject local batches whose populated fields are not source-traceable."""
    records = getattr(result, "records", None)
    if records is None:
        return True
    source_match = re.search(r"https?://[^\s]+", user_prompt)
    source_url = source_match.group(0).rstrip(".,)") if source_match else ""
    content = user_prompt.split("Chunk content:", 1)[-1]
    for record in records:
        data = record.get("data", {}) if isinstance(record, dict) else getattr(record, "data", {}) or {}
        evidence_by_field = record.get("field_evidence", {}) if isinstance(record, dict) else getattr(record, "field_evidence", {}) or {}
        for field_name in data:
            refs = evidence_by_field.get(field_name, [])
            if not refs:
                return False
            if not any(
                (ref.get("source_url", "") if isinstance(ref, dict) else getattr(ref, "source_url", "")) == source_url
                and bool(ref.get("evidence_text", "") if isinstance(ref, dict) else getattr(ref, "evidence_text", ""))
                and (ref.get("evidence_text", "") if isinstance(ref, dict) else getattr(ref, "evidence_text", "")) in content
                for ref in refs
            ):
                return False
    return True


class RoutingStructuredProvider:
    provider_name = "groq"

    def __init__(self, *, local=None, cloud=None) -> None:
        self.local = local or OllamaStructuredProvider()
        self.cloud = cloud or GroqStructuredProvider()
        self.local_first_enabled = _enabled("LOCAL_FIRST_ENABLED") and _enabled("LOCAL_FIRST_BENCHMARK_APPROVED")
        self.provider_name = "local-first" if self.local_first_enabled else self.cloud.provider_name
        self.local_calls = 0
        self.cloud_calls = 0
        self.fallback_calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str, output_model: type[OutputModel], task_name: str) -> OutputModel:
        if self.local_first_enabled:
            try:
                self.local_calls += 1
                result = self.local.generate(system_prompt=system_prompt, user_prompt=user_prompt, output_model=output_model, task_name=task_name)
                # ExtractionBatch deliberately isolates malformed records. Treat that
                # silent loss as a quality failure and escalate instead of accepting an
                # apparently valid but empty/partially rejected batch.
                if getattr(result, "warnings", None) or not _evidence_quality_is_valid(result, user_prompt):
                    raise ValueError("Local structured output contained rejected records.")
                return result
            except Exception:
                # Cloud escalation is intentionally narrow to this semantic boundary.
                self.fallback_calls += 1
        self.cloud_calls += 1
        return self.cloud.generate(system_prompt=system_prompt, user_prompt=user_prompt, output_model=output_model, task_name=task_name)
