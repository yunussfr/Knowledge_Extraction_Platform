"""Bind extraction candidates to supplied field-level source evidence."""

from __future__ import annotations

from typing import Any, Dict

from src.core.field_evidence import evidence_atoms, has_value, locate_evidence, source_evidence_slice
from src.core.logging import get_logger
from src.schemas.models import (
    ApprovedDatasetSchema,
    DatasetSchemaField,
    DocumentChunk,
    EvidenceRef,
    ExtractedRecord,
    ExtractionBatch,
)


logger = get_logger(__name__)


def _unique_evidence(items: list[EvidenceRef]) -> list[EvidenceRef]:
    unique: list[EvidenceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        fingerprint = (item.source_url, item.chunk_id, item.evidence_text)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(item)
    return unique


def _preserved_evidence(
    record: ExtractedRecord,
    field_name: str,
    chunks_by_id: dict[str, DocumentChunk],
    metrics: dict[str, int],
) -> list[EvidenceRef]:
    preserved: list[EvidenceRef] = []
    for candidate in record.field_evidence.get(field_name, []):
        chunk = chunks_by_id.get(candidate.chunk_id)
        if (
            chunk is None
            or chunk.source_url != record.source_url
            or candidate.source_url != record.source_url
        ):
            metrics["discarded_evidence_refs"] += 1
            continue
        evidence_text = source_evidence_slice(chunk.content, candidate.evidence_text)
        if evidence_text is None:
            metrics["discarded_evidence_refs"] += 1
            continue
        preserved.append(EvidenceRef(
            source_url=chunk.source_url,
            chunk_id=chunk.chunk_id,
            evidence_text=evidence_text,
        ))
        metrics["preserved_evidence_refs"] += 1
    return _unique_evidence(preserved)


def _derived_evidence(
    record: ExtractedRecord,
    value: Any,
    chunks_by_source: dict[str, list[DocumentChunk]],
    metrics: dict[str, int],
) -> list[EvidenceRef]:
    chunks = chunks_by_source.get(record.source_url, [])
    if record.extraction_method == "semantic":
        chunks = [chunk for chunk in chunks if chunk.chunk_id == record.chunk_id]
    derived: list[EvidenceRef] = []
    for atom in evidence_atoms(value):
        evidence = locate_evidence(
            atom,
            chunks,
            source_url=record.source_url,
            preferred_chunk_id=record.chunk_id,
        )
        if evidence is None:
            return []
        derived.append(evidence)
    unique = _unique_evidence(derived)
    metrics["derived_evidence_refs"] += len(unique)
    return unique


def _unsupported_optional(
    data: dict[str, Any],
    field: DatasetSchemaField,
    metrics: dict[str, int],
) -> str:
    if field.nullable:
        data[field.field_name] = None
        metrics["nulled_optional_fields"] += 1
        return "set to null"
    data.pop(field.field_name, None)
    metrics["omitted_optional_fields"] += 1
    return "omitted"


def _bind_record(
    record: ExtractedRecord,
    schema: ApprovedDatasetSchema,
    chunks_by_source: dict[str, list[DocumentChunk]],
    chunks_by_id: dict[str, DocumentChunk],
    metrics: dict[str, int],
) -> tuple[ExtractedRecord | None, list[str], list[str]]:
    bound = ExtractedRecord.model_validate(record.model_dump(mode="json"))
    approved_names = {field.field_name for field in schema.fields}
    warnings: list[str] = []
    reasons: list[str] = []
    for field_name in list(bound.data):
        if field_name not in approved_names:
            bound.data.pop(field_name, None)
            bound.field_confidence.pop(field_name, None)
            bound.field_evidence.pop(field_name, None)
            metrics["removed_unapproved_fields"] += 1
            warnings.append(
                f"Record {bound.local_record_id} omitted unapproved field {field_name}."
            )

    bound_evidence: dict[str, list[EvidenceRef]] = {}
    for field in schema.fields:
        field_name = field.field_name
        value = bound.data.get(field_name)
        if not has_value(value):
            bound.field_confidence.pop(field_name, None)
            bound.field_evidence.pop(field_name, None)
            if field.required:
                reasons.append(f"Required field {field_name} has no source-supported value.")
            elif field_name in bound.data and not field.nullable:
                bound.data.pop(field_name, None)
            continue

        evidence = _preserved_evidence(bound, field_name, chunks_by_id, metrics)
        if not evidence:
            evidence = _derived_evidence(bound, value, chunks_by_source, metrics)
        if evidence:
            bound_evidence[field_name] = evidence
            metrics["evidenced_fields"] += 1
            continue

        bound.field_confidence.pop(field_name, None)
        if field.required:
            reasons.append(f"Required field {field_name} has no traceable evidence.")
        else:
            action = _unsupported_optional(bound.data, field, metrics)
            warnings.append(
                f"Record {bound.local_record_id} optional field {field_name} was {action} "
                "because no supplied content supports it."
            )

    if reasons:
        return None, warnings, reasons
    bound.field_evidence = bound_evidence
    return bound, warnings, []


def field_evidence_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Create the Phase-17 evidenced candidate layer without overwriting raw batches."""
    try:
        approved = state.get("approved_dataset_schema")
        if not approved:
            raise ValueError("An approved dataset schema is required before evidence binding.")
        schema = ApprovedDatasetSchema.model_validate(approved)
        chunks = [
            DocumentChunk.model_validate(raw)
            for raw in state.get("document_chunks", [])
        ]
        chunks_by_source: dict[str, list[DocumentChunk]] = {}
        chunks_by_id: dict[str, DocumentChunk] = {}
        for chunk in chunks:
            chunks_by_source.setdefault(chunk.source_url, []).append(chunk)
            chunks_by_id[chunk.chunk_id] = chunk

        metrics = {
            "input_batches": 0,
            "output_batches": 0,
            "input_records": 0,
            "emitted_records": 0,
            "rejected_records": 0,
            "evidenced_fields": 0,
            "preserved_evidence_refs": 0,
            "derived_evidence_refs": 0,
            "discarded_evidence_refs": 0,
            "nulled_optional_fields": 0,
            "omitted_optional_fields": 0,
            "removed_unapproved_fields": 0,
        }
        evidenced_batches: list[ExtractionBatch] = []
        evidence_warnings: list[str] = []
        evidence_rejections: list[dict[str, Any]] = []
        for raw_batch in state.get("extraction_batches", []):
            batch = ExtractionBatch.model_validate(raw_batch)
            metrics["input_batches"] += 1
            metrics["input_records"] += len(batch.records)
            bound_records: list[ExtractedRecord] = []
            batch_warnings = list(batch.warnings)
            for record in batch.records:
                bound, warnings, reasons = _bind_record(
                    record, schema, chunks_by_source, chunks_by_id, metrics
                )
                batch_warnings.extend(warnings)
                evidence_warnings.extend(warnings)
                if bound is not None:
                    bound_records.append(bound)
                    continue
                metrics["rejected_records"] += 1
                rejection = {
                    "source_url": record.source_url,
                    "local_record_id": record.local_record_id,
                    "status": "rejected",
                    "stage": "field_evidence_contract",
                    "reasons": reasons,
                }
                evidence_rejections.append(rejection)
                rejection_warning = (
                    f"Record {record.local_record_id} was quarantined by the field evidence "
                    f"contract: {'; '.join(reasons)}"
                )
                batch_warnings.append(rejection_warning)
                evidence_warnings.append(rejection_warning)
            evidenced_batches.append(ExtractionBatch(
                source_url=batch.source_url,
                segment_id=batch.segment_id,
                chunk_id=batch.chunk_id,
                records=bound_records,
                warnings=batch_warnings,
            ))

        metrics["output_batches"] = len(evidenced_batches)
        metrics["emitted_records"] = sum(
            len(batch.records) for batch in evidenced_batches
        )
        logger.info(
            "Field evidence binding emitted %d/%d records with %d evidenced fields.",
            metrics["emitted_records"],
            metrics["input_records"],
            metrics["evidenced_fields"],
        )
        return {
            "evidenced_extraction_batches": [
                batch.model_dump(mode="json") for batch in evidenced_batches
            ],
            "evidence_metrics": metrics,
            "evidence_warnings": evidence_warnings,
            "evidence_rejections": evidence_rejections,
            "extraction_warnings": list(state.get("extraction_warnings", []))
            + evidence_warnings,
            "rejected_records": list(state.get("rejected_records", []))
            + evidence_rejections,
            "status": "binding_evidence",
            "pipeline_status": "binding_evidence",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "field_evidence", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
