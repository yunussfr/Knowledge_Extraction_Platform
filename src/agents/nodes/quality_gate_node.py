"""Accept or reject verified records using measurable evidence-quality components."""

from __future__ import annotations

from statistics import fmean
from typing import Any, Dict

from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import (
    EvidenceSupportStatus,
    ExtractionBatch,
    RecordQualityAssessment,
    VerifiedRecord,
)


logger = get_logger(__name__)


def _bounded_score(value: Any, default: float = 0.5) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _configured_probability(value: Any, setting_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{setting_name} must be a number from 0 to 1.") from error
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"{setting_name} must be a number from 0 to 1.")
    return parsed


def _configured_boolean(value: Any, setting_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().casefold() in {
        "true", "false", "1", "0", "yes", "no", "on", "off",
    }:
        return value.strip().casefold() in {"true", "1", "yes", "on"}
    raise ValueError(f"{setting_name} must be a boolean.")


def _source_score(state: Dict[str, Any], source_url: str) -> float:
    for collection_name in (
        "source_evaluations",
        "source_selections",
        "selected_sources",
    ):
        for item in state.get(collection_name, []):
            if item.get("url") != source_url:
                continue
            for score_name in ("final_score", "selection_score", "score"):
                if score_name in item:
                    return _bounded_score(item[score_name])
    return 0.5


def _quality_assessment(
    verified: VerifiedRecord,
    state: Dict[str, Any],
    *,
    threshold: float,
    allow_partially_supported: bool,
) -> RecordQualityAssessment:
    duplicate_scores = {
        "unique": 1.0,
        "duplicate": 0.0,
        "not_evaluated": 0.5,
    }
    components = {
        "schema_validity": 1.0 if verified.schema_valid else 0.0,
        "required_field_completeness": verified.required_field_completeness,
        "evidence_support_rate": verified.evidence_support_rate,
        "source_score": _source_score(state, verified.record.source_url),
        "provenance_completeness": verified.provenance_completeness,
        "duplicate_status": duplicate_scores[verified.duplicate_status],
    }
    final_score = round(fmean(components.values()), 6)
    permitted_statuses = {EvidenceSupportStatus.SUPPORTED}
    if allow_partially_supported:
        permitted_statuses.add(EvidenceSupportStatus.PARTIALLY_SUPPORTED)
    reasons: list[str] = []
    if verified.status not in permitted_statuses:
        reasons.append(
            f"Evidence status {verified.status.value} is not accepted by the quality gate."
        )
    if final_score < threshold:
        reasons.append(
            f"Evidence quality {final_score:.2f} is below the minimum {threshold:.2f}."
        )
    return RecordQualityAssessment(
        local_record_id=verified.record.local_record_id,
        source_url=verified.record.source_url,
        support_status=verified.status,
        components=components,
        final_quality_score=final_score,
        accepted=not reasons,
        reasons=reasons,
    )


def quality_gate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gate verified candidates without using extractor confidence as a component."""
    try:
        if "verified_records" not in state:
            raise ValueError("Evidence validation must run before the quality gate.")
        quality_config = state.get("config", {}).get("quality", {})
        threshold = _configured_probability(
            quality_config.get(
                "minimum_evidence_quality", settings.minimum_evidence_quality
            ),
            "minimum_evidence_quality",
        )
        allow_partial = _configured_boolean(
            quality_config.get(
                "allow_partially_supported", settings.allow_partially_supported
            ),
            "allow_partially_supported",
        )
        verified = [
            VerifiedRecord.model_validate(raw)
            for raw in state.get("verified_records", [])
        ]
        assessments = [
            _quality_assessment(
                item,
                state,
                threshold=threshold,
                allow_partially_supported=allow_partial,
            )
            for item in verified
        ]
        assessment_by_key = {
            (assessment.source_url, assessment.local_record_id): assessment
            for assessment in assessments
        }
        accepted_keys = {
            key for key, assessment in assessment_by_key.items() if assessment.accepted
        }
        approved_batches: list[ExtractionBatch] = []
        for raw_batch in state.get("evidenced_extraction_batches", []):
            batch = ExtractionBatch.model_validate(raw_batch)
            approved_batches.append(ExtractionBatch(
                source_url=batch.source_url,
                segment_id=batch.segment_id,
                chunk_id=batch.chunk_id,
                records=[
                    record
                    for record in batch.records
                    if (record.source_url, record.local_record_id) in accepted_keys
                ],
                warnings=list(batch.warnings),
            ))
        rejections = [
            {
                "source_url": assessment.source_url,
                "local_record_id": assessment.local_record_id,
                "status": "rejected",
                "stage": "evidence_quality_gate",
                "support_status": assessment.support_status.value,
                "quality_score": assessment.final_quality_score,
                "reasons": assessment.reasons,
            }
            for assessment in assessments
            if not assessment.accepted
        ]
        accepted_verified = [
            item
            for item, assessment in zip(verified, assessments)
            if assessment.accepted
        ]
        accepted_field_count = sum(
            len(item.field_validations) for item in accepted_verified
        )
        unsupported_accepted_fields = sum(
            field.status in {
                EvidenceSupportStatus.UNSUPPORTED,
                EvidenceSupportStatus.CONTRADICTED,
            }
            for item in accepted_verified
            for field in item.field_validations.values()
        )
        unsupported_accepted_field_rate = (
            unsupported_accepted_fields / accepted_field_count
            if accepted_field_count
            else 0.0
        )
        metrics = {
            "assessed_records": len(assessments),
            "accepted_records": sum(item.accepted for item in assessments),
            "rejected_records": sum(not item.accepted for item in assessments),
            "minimum_evidence_quality": threshold,
            "allow_partially_supported": allow_partial,
            "unsupported_accepted_fields": unsupported_accepted_fields,
            "accepted_field_count": accepted_field_count,
            "unsupported_accepted_field_rate": unsupported_accepted_field_rate,
            "extractor_confidence_used": False,
        }
        logger.info(
            "Evidence quality gate accepted %d/%d records.",
            metrics["accepted_records"],
            metrics["assessed_records"],
        )
        return {
            "quality_approved_extraction_batches": [
                batch.model_dump(mode="json") for batch in approved_batches
            ],
            "record_quality_assessments": [
                item.model_dump(mode="json") for item in assessments
            ],
            "quality_gate_metrics": metrics,
            "quality_gate_rejections": rejections,
            "rejected_records": list(state.get("rejected_records", [])) + rejections,
            "status": "quality_gating",
            "pipeline_status": "quality_gating",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "quality_gate", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
