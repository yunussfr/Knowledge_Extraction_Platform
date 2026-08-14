"""Deterministically transform immutable Bronze documents into Silver content."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Dict

from src.core.content_processing import evidence_word_count, normalize_evidence_content
from src.core.settings import settings
from src.schemas.models import ProcessedDocument
from src.state.state import AgentState
from src.tools.web.models import AcquiredDocument


def _processing_min_words(state: Dict[str, Any]) -> int:
    configured = state.get("config", {}).get("processing", {})
    if not isinstance(configured, dict):
        configured = {}
    minimum = int(configured.get("minimum_words", settings.content_min_words))
    if minimum < 1:
        raise ValueError("Content processing minimum_words must be at least 1.")
    return minimum


def _bronze_by_url(state: Dict[str, Any]) -> dict[str, AcquiredDocument]:
    bronze: dict[str, AcquiredDocument] = {}
    for item in state.get("acquired_documents", []):
        document = AcquiredDocument.model_validate(item)
        if document.success:
            bronze[document.canonical_url or document.source_url] = document
            bronze[document.source_url] = document
    return bronze


def processing_node(state: AgentState) -> Dict[str, Any]:
    try:
        raw_data = list(state.get("raw_data", []))
        errors = list(state.get("errors", []))
        minimum_words = _processing_min_words(state)
        bronze_by_url = _bronze_by_url(state)
        processed_documents: list[ProcessedDocument] = []
        pipeline_documents: list[dict[str, Any]] = []

        print("Processing data...")
        for item in raw_data:
            source_url = str(item.get("source", ""))
            bronze = bronze_by_url.get(source_url)
            input_content = str(item.get("content", ""))
            raw_content = bronze.raw_markdown if bronze is not None else input_content
            content_hash = (
                bronze.content_hash
                if bronze is not None
                else str(item.get("metadata", {}).get("content_hash", ""))
                or sha256(raw_content.encode("utf-8")).hexdigest()
            )
            processed_content, removed_lines = normalize_evidence_content(input_content)
            word_count = evidence_word_count(processed_content)
            content_status = (
                "empty"
                if not processed_content
                else "thin" if word_count < minimum_words else "usable"
            )
            processed = ProcessedDocument(
                source_url=source_url,
                title=str(item.get("title", "")),
                raw_content=raw_content,
                processed_content=processed_content,
                content_hash=content_hash,
                processed_content_hash=sha256(
                    processed_content.encode("utf-8")
                ).hexdigest(),
                word_count=word_count,
                content_status=content_status,
                removed_boilerplate_lines=removed_lines,
                source_metadata=dict(item.get("metadata", {})),
            )
            processed_documents.append(processed)
            if content_status == "empty":
                errors.append({
                    "node": "processing",
                    "source_url": source_url,
                    "error": "Source content is empty after deterministic processing.",
                })
                continue
            pipeline_documents.append(processed.to_pipeline_document())

        counts = {
            status: sum(item.content_status == status for item in processed_documents)
            for status in ("usable", "thin", "empty")
        }
        metrics = {
            "input_documents": len(raw_data),
            "processed_documents": len(processed_documents),
            "usable_documents": counts["usable"],
            "thin_documents": counts["thin"],
            "empty_documents": counts["empty"],
            "removed_boilerplate_lines": sum(
                item.removed_boilerplate_lines for item in processed_documents
            ),
        }
        if raw_data and not pipeline_documents:
            return {
                "processed_documents": [
                    item.model_dump(mode="json") for item in processed_documents
                ],
                "content_processing_metrics": metrics,
                "processed_data": [],
                "errors": errors,
                "status": "failed",
                "pipeline_status": "failed",
            }
        next_status = "processing" if state.get("dataset_topic") else "enriching"
        return {
            "processed_documents": [
                item.model_dump(mode="json") for item in processed_documents
            ],
            "content_processing_metrics": metrics,
            "processed_data": pipeline_documents,
            "errors": errors,
            "status": next_status,
            "pipeline_status": next_status,
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{
                "node": "processing", "error": str(error)
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
