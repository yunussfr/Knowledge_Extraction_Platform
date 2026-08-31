"""Structured-generation provider factory and public contracts."""

from src.tools.structured_generation.base import StructuredGenerationProvider
from src.tools.structured_generation.groq_provider import GroqStructuredProvider
from src.tools.structured_generation.local_provider import LocalStructuredProvider
from src.tools.structured_generation.ollama_provider import OllamaStructuredProvider
from src.tools.structured_generation.routing_provider import RoutingStructuredProvider


def get_structured_generation_provider() -> StructuredGenerationProvider:
    return RoutingStructuredProvider()


__all__ = [
    "GroqStructuredProvider",
    "LocalStructuredProvider",
    "OllamaStructuredProvider",
    "RoutingStructuredProvider",
    "StructuredGenerationProvider",
    "get_structured_generation_provider",
]
