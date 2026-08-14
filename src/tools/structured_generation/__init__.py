"""Structured-generation provider factory and public contracts."""

from src.tools.structured_generation.base import StructuredGenerationProvider
from src.tools.structured_generation.groq_provider import GroqStructuredProvider


def get_structured_generation_provider() -> StructuredGenerationProvider:
    return GroqStructuredProvider()


__all__ = [
    "GroqStructuredProvider",
    "StructuredGenerationProvider",
    "get_structured_generation_provider",
]
