"""Remove repeated accepted records through conservative ordered stages."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, Iterable

from src.core.source_registry import normalize_candidate_url
from src.schemas.models import ApprovedDatasetSchema
from src.state.state import AgentState


def _normalized_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if isinstance(value, dict):
        return {
            str(key): _normalized_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_normalized_value(item) for item in value]
    return value


def _record_fingerprint(record: Dict[str, Any]) -> str:
    return json.dumps(
        _normalized_value(record.get("data", {})),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _populated_field_count(record: Dict[str, Any]) -> int:
    return sum(
        value not in (None, "", [], {}) for value in record.get("data", {}).values()
    )


def _evidence_ref_count(record: Dict[str, Any]) -> int:
    return sum(
        len(references)
        for references in record.get("_metadata", {}).get("field_evidence", {}).values()
    )


def _representative_score(record: Dict[str, Any]) -> tuple[float, int, int]:
    metadata = record.get("_metadata", {})
    return (
        float(metadata.get("evidence_quality_score", 0.0)),
        _populated_field_count(record),
        _evidence_ref_count(record),
    )


def _unique_extend(
    destination: list[Any], incoming: Iterable[Any], *, fingerprint
) -> list[Any]:
    seen = {fingerprint(item) for item in destination}
    for item in incoming:
        key = fingerprint(item)
        if key not in seen:
            seen.add(key)
            destination.append(item)
    return destination


def _merge_duplicate_provenance(
    retained: Dict[str, Any], duplicate: Dict[str, Any]
) -> None:
    """Retain every source/evidence/conflict contributor from an exact duplicate."""
    retained_metadata = retained.setdefault("_metadata", {})
    duplicate_metadata = duplicate.get("_metadata", {})

    source_urls = list(retained_metadata.get("source_urls", []))
    for source_url in (
        retained_metadata.get("source_url", ""),
        duplicate_metadata.get("source_url", ""),
        *duplicate_metadata.get("source_urls", []),
    ):
        if source_url and source_url not in source_urls:
            source_urls.append(source_url)
    if source_urls:
        retained_metadata["source_urls"] = source_urls

    for field_name in ("contributing_chunk_ids", "contributing_record_ids"):
        values = list(retained_metadata.get(field_name, []))
        _unique_extend(values, duplicate_metadata.get(field_name, []), fingerprint=str)
        if values:
            retained_metadata[field_name] = values

    contributors = list(retained_metadata.get("contributors", []))
    _unique_extend(
        contributors,
        duplicate_metadata.get("contributors", []),
        fingerprint=lambda item: (
            item.get("source_url", ""),
            item.get("local_record_id", ""),
            item.get("chunk_id", ""),
            item.get("extraction_method", ""),
        ),
    )
    if contributors:
        retained_metadata["contributors"] = contributors

    for mapping_name in ("source_titles", "source_content_hashes"):
        destination = retained_metadata.setdefault(mapping_name, {})
        for key, value in duplicate_metadata.get(mapping_name, {}).items():
            if key and value and key not in destination:
                destination[key] = value

    retained_evidence = retained_metadata.setdefault("field_evidence", {})
    for field_name, evidence_refs in duplicate_metadata.get("field_evidence", {}).items():
        destination = retained_evidence.setdefault(field_name, [])
        _unique_extend(
            destination,
            evidence_refs,
            fingerprint=lambda item: (
                item.get("source_url", ""),
                item.get("chunk_id", ""),
                item.get("evidence_text", ""),
            ),
        )

    for list_name in (
        "quality_assessments",
        "merge_conflicts",
        "evidence_support_statuses",
    ):
        destination = list(retained_metadata.get(list_name, []))
        _unique_extend(
            destination,
            duplicate_metadata.get(list_name, []),
            fingerprint=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
        if destination:
            retained_metadata[list_name] = destination

    quality_scores = [
        float(score)
        for score in (
            retained_metadata.get("evidence_quality_score"),
            duplicate_metadata.get("evidence_quality_score"),
        )
        if score is not None
    ]
    if quality_scores:
        retained_metadata["evidence_quality_score"] = min(quality_scores)


def _source_keys(record: Dict[str, Any]) -> list[str]:
    metadata = record.get("_metadata", {})
    keys: list[str] = []
    hashes = {
        value
        for value in (
            metadata.get("content_hash", ""),
            metadata.get("processed_content_hash", ""),
            *metadata.get("source_content_hashes", {}).values(),
        )
        if value
    }
    keys.extend(f"hash:{value}" for value in sorted(hashes))
    urls = [
        metadata.get("source_url", ""),
        *metadata.get("source_urls", []),
    ]
    for source_url in urls:
        if not source_url:
            continue
        canonical = normalize_candidate_url(source_url)
        key = f"url:{canonical}"
        if key not in keys:
            keys.append(key)
    return keys


def _identity_key(record: Dict[str, Any], schema: ApprovedDatasetSchema | None) -> str | None:
    metadata = record.get("_metadata", {})
    method = metadata.get("resolution_method")
    resolution_key = metadata.get("resolution_key")
    if method in {
        "explicit_identity",
        "normalized_identity",
        "composite_identity",
    } and resolution_key:
        return f"{method}:{resolution_key}"
    if schema is None or not schema.identity_fields:
        return None
    data = record.get("data", {})
    if not all(data.get(field_name) not in (None, "", [], {}) for field_name in schema.identity_fields):
        return None
    values = [_normalized_value(data[field_name]) for field_name in schema.identity_fields]
    return "schema:" + json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _is_subset_record(subset: Dict[str, Any], superset: Dict[str, Any]) -> bool:
    subset_data = {
        key: _normalized_value(value)
        for key, value in subset.get("data", {}).items()
        if value not in (None, "", [], {})
    }
    superset_data = {
        key: _normalized_value(value)
        for key, value in superset.get("data", {}).items()
        if value not in (None, "", [], {})
    }
    return bool(subset_data) and all(
        key in superset_data and superset_data[key] == value
        for key, value in subset_data.items()
    )


def _record_duplicate(
    *,
    retained: Dict[str, Any],
    duplicate: Dict[str, Any],
    stage: str,
    fingerprint: str,
    rejected_records: list[Dict[str, Any]],
) -> None:
    _merge_duplicate_provenance(retained, duplicate)
    metadata = retained.setdefault("_metadata", {})
    deduplication = metadata.setdefault("deduplication", {
        "stages": [],
        "duplicate_count": 0,
        "fingerprint": _record_fingerprint(retained),
    })
    if stage not in deduplication["stages"]:
        deduplication["stages"].append(stage)
    deduplication["duplicate_count"] += 1
    rejected_records.append({
        "source_url": duplicate.get("_metadata", {}).get("source_url", ""),
        "status": "rejected",
        "stage": f"deduplication:{stage}",
        "duplicate_of": fingerprint,
        "reasons": [
            "Duplicate extracted record; provenance merged into the retained record."
        ],
    })


def deduplication_node(state: AgentState) -> Dict[str, Any]:
    """Apply source/hash, exact-normalized, then schema-identity duplicate stages."""
    try:
        accepted_records = list(state.get("accepted_records", []))
        if not accepted_records:
            return {
                "deduplication_metrics": {
                    "input_records": 0,
                    "output_records": 0,
                    "duplicates_removed": 0,
                    "remaining_exact_duplicate_rate": 0.0,
                    "stage_counts": {
                        "source_or_content": 0,
                        "exact_normalized_record": 0,
                        "schema_identity": 0,
                    },
                    "identity_conflicts_retained": 0,
                },
                "status": "exporting",
                "pipeline_status": "exporting",
            }
        approved = state.get("approved_dataset_schema")
        schema = ApprovedDatasetSchema.model_validate(approved) if approved else None
        rejected_records = list(state.get("rejected_records", []))
        stage_counts = {
            "source_or_content": 0,
            "exact_normalized_record": 0,
            "schema_identity": 0,
        }

        source_seen: dict[tuple[str, str], Dict[str, Any]] = {}
        after_source: list[Dict[str, Any]] = []
        for record in accepted_records:
            fingerprint = _record_fingerprint(record)
            duplicate = next((
                source_seen[(source_key, fingerprint)]
                for source_key in _source_keys(record)
                if (source_key, fingerprint) in source_seen
            ), None)
            if duplicate is not None:
                retained, discarded = duplicate, record
                if _representative_score(record) > _representative_score(duplicate):
                    retained, discarded = record, duplicate
                    after_source[after_source.index(duplicate)] = record
                _record_duplicate(
                    retained=retained,
                    duplicate=discarded,
                    stage="source_or_content",
                    fingerprint=fingerprint,
                    rejected_records=rejected_records,
                )
                stage_counts["source_or_content"] += 1
                for source_key in _source_keys(retained):
                    source_seen[(source_key, fingerprint)] = retained
                continue
            after_source.append(record)
            for source_key in _source_keys(record):
                source_seen[(source_key, fingerprint)] = record

        exact_seen: dict[str, Dict[str, Any]] = {}
        after_exact: list[Dict[str, Any]] = []
        for record in after_source:
            fingerprint = _record_fingerprint(record)
            duplicate = exact_seen.get(fingerprint)
            if duplicate is None:
                exact_seen[fingerprint] = record
                after_exact.append(record)
                continue
            retained, discarded = duplicate, record
            if _representative_score(record) > _representative_score(duplicate):
                retained, discarded = record, duplicate
                after_exact[after_exact.index(duplicate)] = record
                exact_seen[fingerprint] = record
            _record_duplicate(
                retained=retained,
                duplicate=discarded,
                stage="exact_normalized_record",
                fingerprint=fingerprint,
                rejected_records=rejected_records,
            )
            stage_counts["exact_normalized_record"] += 1

        identity_seen: dict[str, Dict[str, Any]] = {}
        unique_records: list[Dict[str, Any]] = []
        identity_conflicts = 0
        for record in after_exact:
            identity_key = _identity_key(record, schema)
            prior = identity_seen.get(identity_key) if identity_key else None
            if prior is None:
                if identity_key:
                    identity_seen[identity_key] = record
                unique_records.append(record)
                continue
            if _is_subset_record(record, prior):
                retained, discarded = prior, record
            elif _is_subset_record(prior, record):
                retained, discarded = record, prior
                unique_records[unique_records.index(prior)] = record
                identity_seen[identity_key] = record
            else:
                identity_conflicts += 1
                unique_records.append(record)
                continue
            _record_duplicate(
                retained=retained,
                duplicate=discarded,
                stage="schema_identity",
                fingerprint=identity_key,
                rejected_records=rejected_records,
            )
            stage_counts["schema_identity"] += 1

        final_fingerprints = [_record_fingerprint(record) for record in unique_records]
        remaining_duplicate_count = len(final_fingerprints) - len(set(final_fingerprints))
        metrics = {
            "input_records": len(accepted_records),
            "output_records": len(unique_records),
            "duplicates_removed": len(accepted_records) - len(unique_records),
            "remaining_exact_duplicate_rate": (
                remaining_duplicate_count / len(unique_records) if unique_records else 0.0
            ),
            "stage_counts": stage_counts,
            "identity_conflicts_retained": identity_conflicts,
        }
        return {
            "accepted_records": unique_records,
            "rejected_records": rejected_records,
            "deduplication_metrics": metrics,
            "status": "exporting",
            "pipeline_status": "exporting",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "deduplication", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
