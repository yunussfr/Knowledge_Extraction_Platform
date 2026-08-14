"""Deterministic helpers for binding extracted facts to supplied chunk text."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.schemas.models import DocumentChunk, EvidenceRef


def has_value(value: Any) -> bool:
    """Return whether a dynamic-schema value contains a factual candidate."""
    return value is not None and value != "" and value != [] and value != {}


def evidence_atoms(value: Any) -> list[str]:
    """Flatten a field value into scalar strings that can be located in source text."""
    if isinstance(value, list):
        return [atom for item in value for atom in evidence_atoms(item)]
    if isinstance(value, dict):
        return [atom for item in value.values() for atom in evidence_atoms(item)]
    if not has_value(value):
        return []
    return [str(value).strip()]


def source_evidence_slice(content: str, candidate: str) -> str | None:
    """Return the exact supplied-content slice matching a candidate evidence string."""
    candidate = candidate.strip()
    if not candidate:
        return None
    direct_start = content.find(candidate)
    if direct_start >= 0:
        return content[direct_start:direct_start + len(candidate)]

    parts = candidate.split()
    if not parts:
        return None
    pattern = r"\s+".join(re.escape(part) for part in parts)
    match = re.search(pattern, content, flags=re.IGNORECASE)
    return match.group(0) if match else None


def locate_evidence(
    candidate: str,
    chunks: Iterable[DocumentChunk],
    *,
    source_url: str,
    preferred_chunk_id: str = "",
) -> EvidenceRef | None:
    """Locate a candidate in supplied same-source chunks and return canonical provenance."""
    ordered = [chunk for chunk in chunks if chunk.source_url == source_url]
    if preferred_chunk_id:
        ordered.sort(key=lambda chunk: chunk.chunk_id != preferred_chunk_id)
    for chunk in ordered:
        evidence_text = source_evidence_slice(chunk.content, candidate)
        if evidence_text is not None:
            return EvidenceRef(
                source_url=chunk.source_url,
                chunk_id=chunk.chunk_id,
                evidence_text=evidence_text,
            )
    return None
