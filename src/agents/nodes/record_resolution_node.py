"""Resolve approved records across sources with schema-aware identities."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict

from src.agents.nodes.record_merge_node import merge_record_group
from src.core.logging import get_logger
from src.schemas.models import (
    ApprovedDatasetSchema,
    ExtractedRecord,
    ExtractionBatch,
    RecordQualityAssessment,
)


logger = get_logger(__name__)


def _normalized_identity_value(value: Any) -> str:
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"\s+", " ", normalized).strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inferred_identity_field(schema: ApprovedDatasetSchema) -> str | None:
    scalar_fields = [
        field
        for field in schema.fields
        if field.type in {"string", "integer", "number"}
    ]
    for field in scalar_fields:
        name = field.field_name.casefold()
        if name == "id" or name.endswith("_id") or name in {"code", "sku"}:
            return field.field_name
    for field in scalar_fields:
        name = field.field_name.casefold()
        if (
            name == "name"
            or name.endswith("_name")
            or name == "title"
            or name.endswith("_title")
        ):
            return field.field_name
    return None


def _resolution_identity(
    record: ExtractedRecord,
    schema: ApprovedDatasetSchema,
) -> tuple[str, str]:
    explicit_fields = schema.identity_fields
    if explicit_fields and all(
        record.data.get(field_name) not in (None, "", [], {})
        for field_name in explicit_fields
    ):
        values = [
            _normalized_identity_value(record.data[field_name])
            for field_name in explicit_fields
        ]
        method = "composite_identity" if len(explicit_fields) > 1 else "explicit_identity"
        return method, json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    if explicit_fields:
        local_key = json.dumps(
            [record.source_url, record.local_record_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return "local_record", local_key

    inferred_field = _inferred_identity_field(schema)
    if inferred_field and record.data.get(inferred_field) not in (None, "", [], {}):
        return (
            "normalized_identity",
            _normalized_identity_value(record.data[inferred_field]),
        )
    local_key = json.dumps(
        [record.source_url, record.local_record_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "local_record", local_key


def record_resolution_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve same-identity candidates while keeping all source provenance."""
    try:
        approved = state.get("approved_dataset_schema")
        if not approved:
            raise ValueError("An approved dataset schema is required for record resolution.")
        if not state.get("quality_gate_metrics"):
            raise ValueError("The evidence quality gate must run before record resolution.")
        schema = ApprovedDatasetSchema.model_validate(approved)
        groups: dict[tuple[str, str], list[ExtractedRecord]] = {}
        input_records: list[ExtractedRecord] = []
        for raw_batch in state.get("quality_approved_extraction_batches", []):
            batch = ExtractionBatch.model_validate(raw_batch)
            input_records.extend(batch.records)
        for record in input_records:
            method, identity_key = _resolution_identity(record, schema)
            groups.setdefault((method, identity_key), []).append(record)

        chunks_by_key = {
            (chunk.get("source_url", ""), chunk.get("chunk_id", "")): chunk
            for chunk in state.get("document_chunks", [])
        }
        quality_by_key = {
            (item.source_url, item.local_record_id): item
            for item in (
                RecordQualityAssessment.model_validate(raw)
                for raw in state.get("record_quality_assessments", [])
            )
        }
        resolved = []
        for (method, identity_key), contributors in groups.items():
            merged = merge_record_group(contributors)
            merged.resolution_method = method
            merged.resolution_key = identity_key
            merged.source_titles = {}
            merged.source_content_hashes = {}
            for contributor in merged.contributors:
                chunk = chunks_by_key.get(
                    (contributor.source_url, contributor.chunk_id), {}
                )
                title = chunk.get("source_title", "")
                if title:
                    merged.source_titles[contributor.source_url] = title
                source_metadata = chunk.get("source_metadata", {})
                content_hash = source_metadata.get(
                    "content_hash", source_metadata.get("processed_content_hash", "")
                )
                if content_hash:
                    merged.source_content_hashes[contributor.source_url] = content_hash
            if merged.source_urls:
                first_source = merged.source_urls[0]
                first_chunk = next((
                    chunks_by_key.get((item.source_url, item.chunk_id), {})
                    for item in merged.contributors
                    if item.source_url == first_source
                ), {})
                merged.source_url = first_source
                merged.source_title = merged.source_titles.get(first_source, "")
                merged.source_metadata = first_chunk.get("source_metadata", {})
            merged.quality_assessments = [
                quality_by_key[(item.source_url, item.local_record_id)]
                for item in merged.contributors
                if (item.source_url, item.local_record_id) in quality_by_key
            ]
            if merged.quality_assessments:
                merged.evidence_quality_score = min(
                    item.final_quality_score for item in merged.quality_assessments
                )
                merged.evidence_support_statuses = list(dict.fromkeys(
                    item.support_status for item in merged.quality_assessments
                ))
            resolved.append(merged.model_dump(mode="json"))

        metrics = {
            "input_records": len(input_records),
            "resolved_records": len(resolved),
            "cross_source_records": sum(
                len(item["source_urls"]) > 1 for item in resolved
            ),
            "contributors": sum(len(item["contributors"]) for item in resolved),
            "conflicts": sum(len(item["merge_conflicts"]) for item in resolved),
            "method_counts": {
                method: sum(item["resolution_method"] == method for item in resolved)
                for method in (
                    "explicit_identity",
                    "normalized_identity",
                    "composite_identity",
                    "local_record",
                )
            },
        }
        logger.info(
            "Record resolution produced %d records from %d contributors.",
            metrics["resolved_records"],
            metrics["input_records"],
        )
        return {
            "resolved_records": resolved,
            "merged_records": resolved,
            "record_resolution_metrics": metrics,
            "status": "resolving_records",
            "pipeline_status": "resolving_records",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "record_resolution", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
