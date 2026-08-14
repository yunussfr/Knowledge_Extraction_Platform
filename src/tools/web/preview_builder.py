"""Deterministic, provider-neutral construction of bounded source previews."""

from __future__ import annotations

import re
from typing import Any

from src.tools.web.models import AcquiredDocument, SourcePreview


WORD_PATTERN = re.compile(r"\S+", re.UNICODE)
HEADING_PATTERN = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def _bounded_words(text: str, max_words: int) -> tuple[str, int]:
    if max_words < 1:
        raise ValueError("Preview max_words must be greater than zero.")
    matches = list(WORD_PATTERN.finditer(text))
    if not matches:
        return "", 0
    end = matches[min(len(matches), max_words) - 1].end()
    return text[:end].strip(), min(len(matches), max_words)


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _structure_hints(markdown: str, headings: list[str]) -> list[str]:
    hints: list[str] = []
    if headings:
        hints.append("headings")
    if re.search(r"(?m)^\s*[-+*]\s+\S", markdown):
        hints.append("unordered_list")
    if re.search(r"(?m)^\s*\d+[.)]\s+\S", markdown):
        hints.append("ordered_list")
    if re.search(r"(?m)^\s*\|.+\|\s*$", markdown):
        hints.append("table")
    if "```" in markdown:
        hints.append("code_block")
    if re.search(r"\[[^\]]+\]\([^)]+\)", markdown):
        hints.append("links")
    return hints


def build_source_preview(
    document: AcquiredDocument,
    *,
    max_words: int,
) -> SourcePreview:
    """Reduce a full internal document to bounded evidence for source decisions."""
    raw_markdown = document.raw_markdown or ""
    preferred_markdown = document.fit_markdown or raw_markdown
    relevant_text, preview_word_count = _bounded_words(preferred_markdown, max_words)
    approximate_word_count = len(WORD_PATTERN.findall(raw_markdown))
    heading_source = raw_markdown or preferred_markdown
    headings = [
        match.group(1).strip()
        for match in HEADING_PATTERN.finditer(heading_source)
        if match.group(1).strip()
    ][:50]
    metadata = document.provider_metadata

    return SourcePreview(
        url=document.canonical_url or document.source_url,
        title=document.title,
        domain=document.domain,
        headings=headings,
        relevant_text=relevant_text,
        approximate_word_count=approximate_word_count,
        preview_word_count=preview_word_count,
        internal_links=document.internal_links,
        external_links=document.external_links,
        language=_metadata_text(metadata, "language", "lang", "og:locale"),
        publication_date=_metadata_text(
            metadata,
            "publication_date",
            "published_time",
            "article:published_time",
            "datePublished",
        ),
        updated_date=_metadata_text(
            metadata,
            "updated_date",
            "modified_time",
            "article:modified_time",
            "dateModified",
        ),
        structure_hints=_structure_hints(
            raw_markdown + ("\n" + preferred_markdown if preferred_markdown != raw_markdown else ""),
            headings,
        ),
        fetch_success=document.success,
        error=document.error,
    )
