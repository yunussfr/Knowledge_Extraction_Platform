"""Merge compatible chunk-level extraction results without losing provenance."""

import json
import re
from typing import Any, Dict, Iterable, List

from src.schemas.models import (
    ApprovedDatasetSchema,
    EvidenceRef,
    ExtractedRecord,
    ExtractionBatch,
    MergedRecord,
    RecordContributor,
    RecordQualityAssessment,
)


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


def _record_key(result: ExtractedRecord, identity_field: str | None) -> tuple[str, str]:
    source_url = result.source_url
    if identity_field and _has_value(result.data.get(identity_field)):
        return source_url, f"identity:{_normalized_value(result.data[identity_field])}"
    # Without a deterministic identity, preserve separate records rather than
    # risking an incorrect same-source merge.
    return source_url, f"record:{result.local_record_id}"


def _unique_array(values: Iterable[Any]) -> List[Any]:
    unique: List[Any] = []
    seen = set()
    for value in values:
        fingerprint = _normalized_value(value)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(value)
    return unique


def _field_confidence(result: ExtractedRecord, field_name: str) -> float:
    return float(result.field_confidence.get(field_name, result.confidence))


def _extend_evidence(
    destination: List[EvidenceRef], incoming: List[EvidenceRef]
) -> List[EvidenceRef]:
    seen = {
        (item.source_url, item.chunk_id, item.evidence_text)
        for item in destination
    }
    for item in incoming:
        fingerprint = (item.source_url, item.chunk_id, item.evidence_text)
        if fingerprint not in seen:
            seen.add(fingerprint)
            destination.append(item)
    return destination


def merge_record_group(results: List[ExtractedRecord]) -> MergedRecord:
    merged_data: Dict[str, Any] = {}
    merged_field_confidence: Dict[str, float] = {}
    conflicts: List[Dict[str, Any]] = []
    contributing_chunk_ids: List[str] = []
    contributing_record_ids: List[str] = []
    source_urls: List[str] = []
    contributors: List[RecordContributor] = []
    merged_field_evidence: Dict[str, List[EvidenceRef]] = {}
    contributing_confidences: List[float] = []
    extraction_methods: List[str] = []

    for result in results:
        if result.source_url and result.source_url not in source_urls:
            source_urls.append(result.source_url)
        contributor = RecordContributor(
            source_url=result.source_url,
            local_record_id=result.local_record_id,
            chunk_id=result.chunk_id,
            extraction_method=result.extraction_method,
        )
        if contributor not in contributors:
            contributors.append(contributor)
        if result.extraction_method not in extraction_methods:
            extraction_methods.append(result.extraction_method)
        if result.local_record_id not in contributing_record_ids:
            contributing_record_ids.append(result.local_record_id)
        factual_fields = [field for field, value in result.data.items() if _has_value(value)]
        if factual_fields:
            contributing_confidences.append(result.confidence)
        if result.chunk_id and result.chunk_id not in contributing_chunk_ids:
            contributing_chunk_ids.append(result.chunk_id)
        for field_name, incoming in result.data.items():
            if not _has_value(incoming):
                continue
            incoming_confidence = _field_confidence(result, field_name)
            incoming_evidence = list(result.field_evidence.get(field_name, []))
            existing = merged_data.get(field_name)
            if not _has_value(existing):
                merged_data[field_name] = incoming
                merged_field_confidence[field_name] = incoming_confidence
                merged_field_evidence[field_name] = _extend_evidence([], incoming_evidence)
                continue
            if isinstance(existing, list) and isinstance(incoming, list):
                merged_data[field_name] = _unique_array([*existing, *incoming])
                merged_field_confidence[field_name] = min(merged_field_confidence[field_name], incoming_confidence)
                merged_field_evidence[field_name] = _extend_evidence(
                    merged_field_evidence.get(field_name, []), incoming_evidence
                )
                continue
            if _normalized_value(existing) == _normalized_value(incoming):
                merged_field_confidence[field_name] = min(merged_field_confidence[field_name], incoming_confidence)
                merged_field_evidence[field_name] = _extend_evidence(
                    merged_field_evidence.get(field_name, []), incoming_evidence
                )
                continue
            existing_confidence = merged_field_confidence[field_name]
            keep_incoming = incoming_confidence > existing_confidence
            conflicts.append({
                "field_name": field_name,
                "kept": "incoming" if keep_incoming else "existing",
                "existing_confidence": existing_confidence,
                "incoming_confidence": incoming_confidence,
                "incoming_source_url": result.source_url,
                "source_chunk_id": result.chunk_id,
                "existing_value": existing,
                "incoming_value": incoming,
            })
            if keep_incoming:
                merged_data[field_name] = incoming
                merged_field_confidence[field_name] = incoming_confidence
                merged_field_evidence[field_name] = _extend_evidence([], incoming_evidence)

    first = results[0]
    return MergedRecord(
        data=merged_data,
        confidence=min(contributing_confidences, default=0.0),
        field_confidence=merged_field_confidence,
        source_url=first.source_url,
        source_urls=source_urls,
        source_title="",
        contributing_chunk_ids=contributing_chunk_ids,
        contributing_record_ids=contributing_record_ids,
        contributors=contributors,
        field_evidence=merged_field_evidence,
        extraction_methods=extraction_methods,
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
        grouped: Dict[tuple[str, str], List[ExtractedRecord]] = {}
        errors = list(state.get("errors", []))
        input_records: List[ExtractedRecord] = []
        if state.get("quality_gate_metrics"):
            for raw_batch in state.get("quality_approved_extraction_batches", []):
                batch = ExtractionBatch.model_validate(raw_batch)
                input_records.extend(batch.records)
        elif state.get("evidence_metrics"):
            for raw_batch in state.get("evidenced_extraction_batches", []):
                batch = ExtractionBatch.model_validate(raw_batch)
                input_records.extend(batch.records)
        elif state.get("extraction_batches"):
            for raw_batch in state.get("extraction_batches", []):
                batch = ExtractionBatch.model_validate(raw_batch)
                input_records.extend(batch.records)
        else:
            for index, raw_result in enumerate(
                state.get("chunk_extraction_results", []), start=1
            ):
                legacy = ExtractedRecord.model_validate(raw_result)
                legacy.local_record_id = legacy.local_record_id or (
                    f"{legacy.chunk_id or legacy.source_chunk_id or 'legacy'}:record:{index:04d}"
                )
                input_records.append(legacy)
        for result in input_records:
            try:
                grouped.setdefault(_record_key(result, identity_field), []).append(result)
            except Exception as error:
                errors.append({
                    "node": "record_merge",
                    "source_url": result.source_url,
                    "chunk_id": result.chunk_id,
                    "error": str(error),
                })
        merged_records = []
        quality_by_key = {
            (item.source_url, item.local_record_id): item
            for item in (
                RecordQualityAssessment.model_validate(raw)
                for raw in state.get("record_quality_assessments", [])
            )
        }
        for results in grouped.values():
            merged = merge_record_group(results)
            source_chunk = next((
                chunk for chunk in state.get("document_chunks", [])
                if chunk.get("chunk_id") in merged.contributing_chunk_ids
            ), {})
            merged.source_title = source_chunk.get("source_title", "")
            merged.source_metadata = source_chunk.get("source_metadata", {})
            merged.quality_assessments = [
                quality_by_key[(merged.source_url, record_id)]
                for record_id in merged.contributing_record_ids
                if (merged.source_url, record_id) in quality_by_key
            ]
            if merged.quality_assessments:
                merged.evidence_quality_score = min(
                    item.final_quality_score for item in merged.quality_assessments
                )
                merged.evidence_support_statuses = list(dict.fromkeys(
                    item.support_status for item in merged.quality_assessments
                ))
            merged_records.append(merged.model_dump())
        if input_records and not merged_records:
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
