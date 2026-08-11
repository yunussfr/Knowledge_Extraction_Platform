"""Merge compatible chunk-level extraction results without losing provenance."""

import json
import re
from typing import Any, Dict, Iterable, List

from src.schemas.models import ApprovedDatasetSchema, ExtractionResult, MergedRecord


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _normalized_value(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _primary_identity_field(schema: ApprovedDatasetSchema) -> str | None:
    for field in schema.fields:
        name = field.field_name.casefold()
        if field.type == "string" and (name == "id" or name.endswith("_id") or name == "name" or name.endswith("_name") or name == "title" or name.endswith("_title")):
            return field.field_name
    return None


def _record_key(result: ExtractionResult, identity_field: str | None) -> tuple[str, str]:
    source_url = result.source_url
    if identity_field and _has_value(result.data.get(identity_field)):
        return source_url, f"identity:{_normalized_value(result.data[identity_field])}"
    # Without a deterministic identity, preserve separate records rather than
    # risking an incorrect same-source merge.
    return source_url, f"chunk:{result.source_chunk_id or result.chunk_index}"


def _unique_array(values: Iterable[Any]) -> List[Any]:
    unique: List[Any] = []
    seen = set()
    for value in values:
        fingerprint = _normalized_value(value)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(value)
    return unique


def _field_confidence(result: ExtractionResult, field_name: str) -> float:
    return float(result.field_confidence.get(field_name, result.confidence))


def _merge_group(results: List[ExtractionResult]) -> MergedRecord:
    merged_data: Dict[str, Any] = {}
    merged_field_confidence: Dict[str, float] = {}
    conflicts: List[Dict[str, Any]] = []
    contributing_chunk_ids: List[str] = []
    contributing_confidences: List[float] = []

    for result in results:
        factual_fields = [field for field, value in result.data.items() if _has_value(value)]
        if factual_fields:
            contributing_confidences.append(result.confidence)
        if result.source_chunk_id and result.source_chunk_id not in contributing_chunk_ids:
            contributing_chunk_ids.append(result.source_chunk_id)
        for field_name, incoming in result.data.items():
            if not _has_value(incoming):
                continue
            incoming_confidence = _field_confidence(result, field_name)
            existing = merged_data.get(field_name)
            if not _has_value(existing):
                merged_data[field_name] = incoming
                merged_field_confidence[field_name] = incoming_confidence
                continue
            if isinstance(existing, list) and isinstance(incoming, list):
                merged_data[field_name] = _unique_array([*existing, *incoming])
                merged_field_confidence[field_name] = min(merged_field_confidence[field_name], incoming_confidence)
                continue
            if _normalized_value(existing) == _normalized_value(incoming):
                merged_field_confidence[field_name] = min(merged_field_confidence[field_name], incoming_confidence)
                continue
            existing_confidence = merged_field_confidence[field_name]
            keep_incoming = incoming_confidence > existing_confidence
            conflicts.append({
                "field_name": field_name,
                "kept": "incoming" if keep_incoming else "existing",
                "existing_confidence": existing_confidence,
                "incoming_confidence": incoming_confidence,
                "source_chunk_id": result.source_chunk_id,
            })
            if keep_incoming:
                merged_data[field_name] = incoming
                merged_field_confidence[field_name] = incoming_confidence

    first = results[0]
    return MergedRecord(
        data=merged_data,
        confidence=min(contributing_confidences, default=0.0),
        field_confidence=merged_field_confidence,
        source_url=first.source_url,
        source_title="",
        contributing_chunk_ids=contributing_chunk_ids,
        merge_conflicts=conflicts,
    )


def record_merge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Merge same-entity chunk records and keep unrelated records separate."""
    try:
        approved = state.get("approved_dataset_schema")
        if not approved:
            raise ValueError("An approved dataset schema is required before chunk records can be merged.")
        schema = ApprovedDatasetSchema.model_validate(approved)
        identity_field = _primary_identity_field(schema)
        grouped: Dict[tuple[str, str], List[ExtractionResult]] = {}
        errors = list(state.get("errors", []))
        for raw_result in state.get("chunk_extraction_results", []):
            try:
                result = ExtractionResult.model_validate(raw_result)
                grouped.setdefault(_record_key(result, identity_field), []).append(result)
            except Exception as error:
                errors.append({
                    "node": "record_merge",
                    "source_url": raw_result.get("source_url", ""),
                    "chunk_id": raw_result.get("source_chunk_id"),
                    "error": str(error),
                })
        merged_records = []
        for results in grouped.values():
            merged = _merge_group(results)
            source_chunk = next((
                chunk for chunk in state.get("document_chunks", [])
                if chunk.get("chunk_id") in merged.contributing_chunk_ids
            ), {})
            merged.source_title = source_chunk.get("source_title", "")
            merged.source_metadata = source_chunk.get("source_metadata", {})
            merged_records.append(merged.model_dump())
        if state.get("chunk_extraction_results") and not merged_records:
            return {"errors": errors, "status": "failed", "pipeline_status": "failed"}
        return {
            "merged_records": merged_records,
            "errors": errors,
            "status": "merging",
            "pipeline_status": "merging",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "record_merge", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
