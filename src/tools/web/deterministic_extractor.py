"""Crawl4AI deterministic strategies behind a small internal boundary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.core.settings import settings


def _prepare_crawl4ai_runtime() -> None:
    """Keep Crawl4AI's import-time database/cache inside the project runtime."""
    base_directory = Path(settings.crawl4ai_base_directory).expanduser().resolve()
    base_directory.mkdir(parents=True, exist_ok=True)
    os.environ["CRAWL4_AI_BASE_DIRECTORY"] = str(base_directory)


class Crawl4AIDeterministicExtractor:
    """Execute user-supplied selectors/patterns without generating them with an LLM."""

    def extract_dom(
        self,
        *,
        method: str,
        source_url: str,
        html: str,
        schema: dict[str, Any],
    ) -> list[dict[str, Any]]:
        _prepare_crawl4ai_runtime()
        from crawl4ai.extraction_strategy import (
            JsonCssExtractionStrategy,
            JsonXPathExtractionStrategy,
        )

        strategy_class = {
            "css": JsonCssExtractionStrategy,
            "xpath": JsonXPathExtractionStrategy,
        }.get(method)
        if strategy_class is None:
            raise ValueError(f"Unsupported DOM extraction method: {method}")
        strategy = strategy_class(schema=schema, verbose=False)
        return list(strategy.extract(source_url, html))

    def extract_regex(
        self,
        *,
        source_url: str,
        content: str,
        patterns: dict[str, str],
    ) -> dict[str, list[str]]:
        _prepare_crawl4ai_runtime()
        from crawl4ai.extraction_strategy import RegexExtractionStrategy

        strategy = RegexExtractionStrategy(
            pattern=RegexExtractionStrategy.Nothing,
            custom=patterns,
            input_format="text",
        )
        grouped: dict[str, list[str]] = {name: [] for name in patterns}
        for hit in strategy.extract(source_url, content):
            label = str(hit.get("label", ""))
            value = str(hit.get("value", "")).strip()
            if label in grouped and value and value not in grouped[label]:
                grouped[label].append(value)
        return grouped
