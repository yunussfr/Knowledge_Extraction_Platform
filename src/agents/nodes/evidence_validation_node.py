"""Deterministically validate evidenced extraction candidates before acceptance."""

from __future__ import annotations

import re
from typing import Any, Dict

from src.core.field_evidence import evidence_atoms, has_value, source_evidence_slice
from src.core.logging import get_logger
from src.schemas.models import (
    ApprovedDatasetSchema,
    DatasetSchemaField,
    DocumentChunk,
    EvidenceRef,
    EvidenceSupportStatus,
    ExtractedRecord,
    ExtractionBatch,
    FieldEvidenceValidation,
    VerifiedRecord,
)


logger = get_logger(__name__)


def _matches_type(value: Any, field_type: str) -> bool:
    if field_type.startswith("array["):
        if not isinstance(value, list):
            return False
        item_type = field_type[6:-1]
        return all(_matches_type(item, item_type) for item in value)
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    return checks[field_type](value)


def _traceable_evidence(
    record: ExtractedRecord,
    field_name: str,
    chunks_by_key: dict[tuple[str, str], DocumentChunk],
) -> tuple[list[EvidenceRef], int]:
    valid: list[EvidenceRef] = []
    invalid_count = 0
    for evidence in record.field_evidence.get(field_name, []):
        chunk = chunks_by_key.get((evidence.source_url, evidence.chunk_id))
        if (
            chunk is None
            or evidence.source_url != record.source_url
            or source_evidence_slice(chunk.content, evidence.evidence_text) is None
        ):
            invalid_count += 1
            continue
        valid.append(evidence)
    return valid, invalid_count


def _explicit_contradiction(value: Any, field: DatasetSchemaField, evidence_text: str) -> bool:
    normalized = " ".join(evidence_text.casefold().split())
    if field.type == "boolean" and isinstance(value, bool):
        true_markers = {"true", "yes", "on"}
        false_markers = {"false", "no", "off"}
        tokens = set(re.findall(r"\w+", normalized, flags=re.UNICODE))
        expected, opposite = (
            (true_markers, false_markers) if value else (false_markers, true_markers)
        )
        return bool(tokens & opposite) and not bool(tokens & expected)
    if isinstance(value, str):
        value_pattern = r"\s+".join(
            re.escape(part) for part in value.casefold().split()
        )
        return bool(re.search(rf"\b(?:not|no)\s+{value_pattern}\b", normalized))
    return False


def _validate_field(
    record: ExtractedRecord,
    field: DatasetSchemaField,
    chunks_by_key: dict[tuple[str, str], DocumentChunk],
) -> FieldEvidenceValidation:
    value = record.data[field.field_name]
    reasons: list[str] = []
    if not _matches_type(value, field.type):
        return FieldEvidenceValidation(
            field_name=field.field_name,
            status=EvidenceSupportStatus.UNSUPPORTED,
            reasons=[f"Field value does not match approved type {field.type}."],
        )

    evidence, invalid_count = _traceable_evidence(
        record, field.field_name, chunks_by_key
    )
    if not evidence:
        return FieldEvidenceValidation(
            field_name=field.field_name,
            status=EvidenceSupportStatus.UNSUPPORTED,
            reasons=["No evidence reference is traceable to supplied content."],
        )
    combined_evidence = "\n".join(item.evidence_text for item in evidence)
    if _explicit_contradiction(value, field, combined_evidence):
        return FieldEvidenceValidation(
            field_name=field.field_name,
            status=EvidenceSupportStatus.CONTRADICTED,
            evidence=evidence,
            reasons=["Field evidence explicitly contradicts the extracted value."],
        )

    atoms = evidence_atoms(value)
    literal_support = all(
        source_evidence_slice(combined_evidence, atom) is not None for atom in atoms
    )
    if literal_support and invalid_count == 0:
        return FieldEvidenceValidation(
            field_name=field.field_name,
            status=EvidenceSupportStatus.SUPPORTED,
            evidence=evidence,
        )
    if invalid_count:
        reasons.append(f"{invalid_count} evidence reference(s) were not traceable.")
    if not literal_support:
        reasons.append(
            "Evidence is traceable but literal support is incomplete; semantic review is required."
        )
    return FieldEvidenceValidation(
        field_name=field.field_name,
        status=EvidenceSupportStatus.PARTIALLY_SUPPORTED,
        evidence=evidence,
        reasons=reasons,
        semantic_review_required=not literal_support,
    )


def _record_status(
    *,
    fatal_errors: bool,
    field_validations: dict[str, FieldEvidenceValidation],
    required_names: set[str],
) -> EvidenceSupportStatus:
    statuses = {result.status for result in field_validations.values()}
    if EvidenceSupportStatus.CONTRADICTED in statuses:
        return EvidenceSupportStatus.CONTRADICTED
    if fatal_errors or any(
        result.status == EvidenceSupportStatus.UNSUPPORTED
        and field_name in required_names
        for field_name, result in field_validations.items()
    ):
        return EvidenceSupportStatus.UNSUPPORTED
    if statuses & {
        EvidenceSupportStatus.PARTIALLY_SUPPORTED,
        EvidenceSupportStatus.UNSUPPORTED,
    }:
        return EvidenceSupportStatus.PARTIALLY_SUPPORTED
    return EvidenceSupportStatus.SUPPORTED


def _verify_record(
    record: ExtractedRecord,
    schema: ApprovedDatasetSchema,
    chunks_by_key: dict[tuple[str, str], DocumentChunk],
) -> VerifiedRecord:
    fields = {field.field_name: field for field in schema.fields}
    required_names = {field.field_name for field in schema.fields if field.required}
    validation_errors: list[str] = []
    unknown_fields = sorted(set(record.data) - set(fields))
    if unknown_fields:
        validation_errors.append(
            "Unapproved fields are present: " + ", ".join(unknown_fields)
        )
    source_exists = any(
        source_url == record.source_url for source_url, _ in chunks_by_key
    )
    chunk_exists = (record.source_url, record.chunk_id) in chunks_by_key
    if not source_exists:
        validation_errors.append("Record source does not exist in supplied chunks.")
    if not chunk_exists:
        validation_errors.append("Record chunk does not exist for its source.")

    field_validations: dict[str, FieldEvidenceValidation] = {}
    complete_required = 0
    schema_valid = not unknown_fields
    for field in schema.fields:
        value = record.data.get(field.field_name)
        if not has_value(value):
            if field.required:
                validation_errors.append(
                    f"Missing required field: {field.field_name}"
                )
            continue
        field_result = _validate_field(record, field, chunks_by_key)
        field_validations[field.field_name] = field_result
        if not _matches_type(value, field.type):
            schema_valid = False
            validation_errors.append(
                f"Field {field.field_name} does not match approved type {field.type}."
            )
        elif field.required:
            complete_required += 1

    required_completeness = (
        complete_required / len(required_names) if required_names else 1.0
    )
    support_weights = {
        EvidenceSupportStatus.SUPPORTED: 1.0,
        EvidenceSupportStatus.PARTIALLY_SUPPORTED: 0.5,
        EvidenceSupportStatus.UNSUPPORTED: 0.0,
        EvidenceSupportStatus.CONTRADICTED: 0.0,
    }
    evidence_support_rate = (
        sum(support_weights[result.status] for result in field_validations.values())
        / len(field_validations)
        if field_validations
        else 0.0
    )
    populated_fields = [
        field_name
        for field_name, value in record.data.items()
        if field_name in fields and has_value(value)
    ]
    all_have_evidence = bool(populated_fields) and all(
        record.field_evidence.get(field_name) for field_name in populated_fields
    )
    all_evidence_traceable = all(
        result.status != EvidenceSupportStatus.UNSUPPORTED
        for result in field_validations.values()
    ) and len(field_validations) == len(populated_fields)
    provenance_completeness = sum([
        source_exists,
        chunk_exists,
        all_have_evidence,
        all_evidence_traceable,
    ]) / 4
    fatal_errors = (
        not schema_valid
        or not source_exists
        or not chunk_exists
        or required_completeness < 1.0
    )
    status = _record_status(
        fatal_errors=fatal_errors,
        field_validations=field_validations,
        required_names=required_names,
    )
    return VerifiedRecord(
        record=record,
        status=status,
        field_validations=field_validations,
        schema_valid=schema_valid,
        source_exists=source_exists,
        chunk_exists=chunk_exists,
        required_field_completeness=required_completeness,
        evidence_support_rate=evidence_support_rate,
        provenance_completeness=provenance_completeness,
        validation_errors=validation_errors,
    )


def evidence_validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Assign deterministic Phase-18 support statuses without accepting records."""
    try:
        approved = state.get("approved_dataset_schema")
        if not approved:
            raise ValueError("An approved dataset schema is required for evidence validation.")
        if "evidenced_extraction_batches" not in state:
            raise ValueError("Field evidence binding must run before evidence validation.")
        schema = ApprovedDatasetSchema.model_validate(approved)
        chunks = [
            DocumentChunk.model_validate(raw)
            for raw in state.get("document_chunks", [])
        ]
        chunks_by_key = {
            (chunk.source_url, chunk.chunk_id): chunk for chunk in chunks
        }
        verified: list[VerifiedRecord] = []
        for raw_batch in state.get("evidenced_extraction_batches", []):
            batch = ExtractionBatch.model_validate(raw_batch)
            verified.extend(
                _verify_record(record, schema, chunks_by_key)
                for record in batch.records
            )
        status_counts = {
            status.value: sum(item.status == status for item in verified)
            for status in EvidenceSupportStatus
        }
        metrics = {
            "verified_records": len(verified),
            "verified_fields": sum(len(item.field_validations) for item in verified),
            "semantic_review_required_fields": sum(
                field.semantic_review_required
                for item in verified
                for field in item.field_validations.values()
            ),
            "status_counts": status_counts,
        }
        logger.info(
            "Evidence validation assigned statuses to %d records.", len(verified)
        )
        return {
            "verified_records": [item.model_dump(mode="json") for item in verified],
            "evidence_validation_metrics": metrics,
            "status": "validating_evidence",
            "pipeline_status": "validating_evidence",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "evidence_validation", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
