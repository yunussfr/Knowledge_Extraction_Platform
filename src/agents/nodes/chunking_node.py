"""Create source-traceable, token-budgeted document chunks after cleaning."""

import re
from typing import Any, Dict, Iterable, List, Tuple

from src.core.settings import settings
from src.core.tokenization import TokenCounter
from src.schemas.models import DocumentChunk


_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _chunking_config(state: Dict[str, Any]) -> tuple[bool, int, int]:
    configured = state.get("config", {}).get("extraction", {}).get("chunking", {})
    enabled = configured.get("enabled", settings.chunking_enabled)
    target_tokens = int(configured.get("target_tokens", settings.chunk_target_tokens))
    overlap_tokens = int(configured.get("overlap_tokens", settings.chunk_overlap_tokens))
    if target_tokens < 1:
        raise ValueError("Chunk target_tokens must be greater than zero.")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("Chunk overlap_tokens must be non-negative and smaller than target_tokens.")
    return bool(enabled), target_tokens, overlap_tokens


def _structural_units(content: str) -> Iterable[Tuple[str, str]]:
    """Yield paragraphs grouped under their nearest Markdown heading."""
    heading = ""
    paragraph_lines: List[str] = []

    def emit_paragraph() -> Tuple[str, str] | None:
        text = "\n".join(paragraph_lines).strip()
        return (heading, text) if text else None

    for line in content.splitlines():
        heading_match = _MARKDOWN_HEADING.match(line)
        if heading_match:
            paragraph = emit_paragraph()
            if paragraph:
                yield paragraph
            paragraph_lines = []
            heading = heading_match.group(1)
            continue
        if not line.strip():
            paragraph = emit_paragraph()
            if paragraph:
                yield paragraph
            paragraph_lines = []
            continue
        paragraph_lines.append(line)

    paragraph = emit_paragraph()
    if paragraph:
        yield paragraph


def _split_oversized_text(text: str, target_tokens: int, counter: TokenCounter) -> List[str]:
    """Split only an oversized paragraph, preferring sentences before words."""
    sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(text) if sentence.strip()]
    if not sentences:
        sentences = [text]
    fragments: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and counter.count(candidate) > target_tokens:
            fragments.append(current)
            current = sentence
        else:
            current = candidate
        if counter.count(current) > target_tokens:
            fragments.extend(_split_oversized_sentence(current, target_tokens, counter))
            current = ""
    if current:
        fragments.append(current)
    return fragments


def _split_oversized_sentence(text: str, target_tokens: int, counter: TokenCounter) -> List[str]:
    """Use word boundaries only after a paragraph and sentence are both too large."""
    words = text.split()
    fragments: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and counter.count(candidate) > target_tokens:
            fragments.append(current)
            current = word
        else:
            current = candidate
        if counter.count(current) > target_tokens:
            # A single token-like value can exceed the budget. Split only this
            # exceptional leaf fragment so the request can never be oversized.
            fragments.extend(_split_unbreakable_text(current, target_tokens, counter))
            current = ""
    if current:
        fragments.append(current)
    return fragments


def _split_unbreakable_text(text: str, target_tokens: int, counter: TokenCounter) -> List[str]:
    fragments: List[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and counter.count(candidate) > target_tokens:
            fragments.append(current)
            current = character
        else:
            current = candidate
    if current:
        fragments.append(current)
    return fragments


def _overlap_tail(content: str, budget: int, counter: TokenCounter) -> str:
    """Keep a bounded tail of prior context without exceeding the next chunk budget."""
    if budget <= 0 or not content:
        return ""
    sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(content) if sentence.strip()]
    selected: List[str] = []
    for sentence in reversed(sentences):
        candidate = " ".join([sentence, *selected])
        if counter.count(candidate) > budget:
            break
        selected.insert(0, sentence)
    return " ".join(selected)


def _build_chunks_for_document(
    document: Dict[str, Any], source_index: int, target_tokens: int, overlap_tokens: int, counter: TokenCounter
) -> List[DocumentChunk]:
    content = str(document.get("cleaned_content", "")).strip()
    if not content:
        return []
    metadata = dict(document.get("metadata", {}))
    source_url = str(document.get("source", ""))
    source_title = str(document.get("title") or metadata.get("title", ""))
    units: List[Tuple[str, str]] = []
    fragment_target = max(1, target_tokens - overlap_tokens)
    for heading, paragraph in _structural_units(content):
        if counter.count(paragraph) <= target_tokens:
            units.append((heading, paragraph))
        else:
            # Reserve overlap room when splitting one oversized structural unit;
            # otherwise its next fragment would leave no room for prior context.
            units.extend((heading, part) for part in _split_oversized_text(paragraph, fragment_target, counter))
    if not units:
        return []

    built: List[Tuple[str, str, int]] = []
    current_parts: List[str] = []
    current_heading = ""
    current_overlap_count = 0
    for heading, unit in units:
        candidate = "\n\n".join([*current_parts, unit])
        if current_parts and counter.count(candidate) > target_tokens:
            current_content = "\n\n".join(current_parts)
            built.append((current_heading, current_content, current_overlap_count))
            overlap = _overlap_tail(current_content, overlap_tokens, counter)
            available_overlap = max(0, target_tokens - counter.count(unit))
            overlap = _overlap_tail(overlap, available_overlap, counter)
            current_parts = [part for part in (overlap, unit) if part]
            current_heading = heading
            current_overlap_count = counter.count(overlap)
            continue
        if not current_parts:
            current_heading = heading
        current_parts.append(unit)
    if current_parts:
        built.append((current_heading, "\n\n".join(current_parts), current_overlap_count))

    total_chunks = len(built)
    chunks = []
    for chunk_index, (heading, chunk_content, overlap_count) in enumerate(built):
        chunks.append(DocumentChunk(
            chunk_id=f"source_{source_index:03d}_chunk_{chunk_index + 1:03d}",
            source_url=source_url,
            source_title=source_title,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            heading=heading,
            content=chunk_content,
            token_count=counter.count(chunk_content),
            overlap_token_count=overlap_count,
            source_metadata=metadata,
        ))
    return chunks


def chunking_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Split cleaned documents into safe extraction inputs while preserving provenance."""
    try:
        documents = list(state.get("processed_data", []))
        enabled, target_tokens, overlap_tokens = _chunking_config(state)
        counter = TokenCounter()
        chunks: List[Dict[str, Any]] = []
        errors = list(state.get("errors", []))
        for source_index, document in enumerate(documents, start=1):
            try:
                content = str(document.get("cleaned_content", "")).strip()
                if not content:
                    errors.append({
                        "node": "chunking",
                        "source_url": document.get("source", ""),
                        "chunk_id": None,
                        "error": "Clean source content is empty.",
                    })
                    continue
                if not enabled:
                    token_count = counter.count(content)
                    chunks.append(DocumentChunk(
                        chunk_id=f"source_{source_index:03d}_chunk_001",
                        source_url=document.get("source", ""),
                        source_title=document.get("title", ""),
                        chunk_index=0,
                        total_chunks=1,
                        content=content,
                        token_count=token_count,
                        source_metadata=dict(document.get("metadata", {})),
                    ).model_dump())
                    continue
                chunks.extend(chunk.model_dump() for chunk in _build_chunks_for_document(
                    document, source_index, target_tokens, overlap_tokens, counter
                ))
            except Exception as error:
                errors.append({
                    "node": "chunking",
                    "source_url": document.get("source", ""),
                    "chunk_id": None,
                    "error": str(error),
                })
        if documents and not chunks:
            return {"errors": errors, "status": "failed", "pipeline_status": "failed"}
        return {
            "clean_documents": documents,
            "document_chunks": chunks,
            "errors": errors,
            "status": "chunking",
            "pipeline_status": "chunking",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "chunking", "chunk_id": None, "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
