"""Prefer reliable zero-LLM extraction and expose every routing decision."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from src.core.field_evidence import evidence_atoms, locate_evidence
from src.schemas.models import (
    ApprovedDatasetSchema,
    DatasetSchemaField,
    DeterministicExtractionRule,
    DocumentChunk,
    EvidenceRef,
    ExtractedRecord,
    ExtractionBatch,
    ExtractionResult,
    ExtractionRoute,
    ProcessedDocument,
)
from src.tools.web.deterministic_extractor import Crawl4AIDeterministicExtractor
from src.tools.web.models import AcquiredDocument


_TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _normalize_label(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip().replace(r"\|", "|") for cell in stripped.split("|")]


def _schema_field_map(schema: ApprovedDatasetSchema) -> dict[str, DatasetSchemaField]:
    return {field.field_name: field for field in schema.fields}


def _header_mapping(
    headers: list[str], schema: ApprovedDatasetSchema
) -> dict[int, str] | None:
    fields = _schema_field_map(schema)
    available = set(fields)
    mapping: dict[int, str] = {}
    for index, header in enumerate(headers):
        normalized_header = _normalize_label(header)
        header_tokens = set(normalized_header.split())
        candidates: list[tuple[int, str]] = []
        for field_name in available:
            normalized_field = _normalize_label(field_name.replace("_", " "))
            field_tokens = set(normalized_field.split())
            if normalized_header == normalized_field:
                candidates.append((2, field_name))
            elif header_tokens and (
                header_tokens < field_tokens or field_tokens < header_tokens
            ):
                candidates.append((1, field_name))
        if not candidates:
            continue
        best_score = max(score for score, _ in candidates)
        best = [name for score, name in candidates if score == best_score]
        if len(best) != 1:
            return None
        mapping[index] = best[0]
        available.remove(best[0])
    required = {field.field_name for field in schema.fields if field.required}
    return mapping if required <= set(mapping.values()) else None


def _iter_markdown_tables(content: str) -> Iterable[tuple[list[str], list[list[str]]]]:
    lines = content.splitlines()
    index = 0
    while index + 2 < len(lines):
        if "|" not in lines[index] or "|" not in lines[index + 1]:
            index += 1
            continue
        headers = _split_table_row(lines[index])
        separators = _split_table_row(lines[index + 1])
        if len(headers) < 2 or len(separators) != len(headers) or not all(
            _TABLE_SEPARATOR.fullmatch(cell.replace(" ", "")) for cell in separators
        ):
            index += 1
            continue
        rows: list[list[str]] = []
        cursor = index + 2
        while cursor < len(lines) and "|" in lines[cursor]:
            row = _split_table_row(lines[cursor])
            if len(row) != len(headers):
                break
            rows.append(row)
            cursor += 1
        if rows:
            yield headers, rows
        index = max(cursor, index + 1)


def _content_outside_tables(content: str) -> str:
    lines = content.splitlines()
    kept: list[str] = []
    in_table = False
    for index, line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        starts_table = "|" in line and "|" in next_line and all(
            _TABLE_SEPARATOR.fullmatch(cell.replace(" ", ""))
            for cell in _split_table_row(next_line)
        )
        if starts_table:
            in_table = True
            continue
        if in_table and "|" in line:
            continue
        in_table = False
        kept.append(line)
    return "\n".join(kept)


def _coerce_scalar(value: Any, field_type: str) -> Any:
    if field_type == "string":
        return str(value).strip()
    if field_type == "integer":
        if isinstance(value, bool):
            raise ValueError("Boolean is not an integer value.")
        text = str(value).strip().replace(",", "")
        if not re.fullmatch(r"[-+]?\d+", text):
            raise ValueError("Value is not an integer.")
        return int(text)
    if field_type == "number":
        if isinstance(value, bool):
            raise ValueError("Boolean is not a numeric value.")
        return float(str(value).strip().replace(",", ""))
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().casefold()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
        raise ValueError("Value is not a boolean.")
    if field_type == "object":
        if not isinstance(value, dict):
            raise ValueError("Value is not an object.")
        return value
    return value


def _coerce_value(value: Any, field: DatasetSchemaField) -> Any:
    if field.type == "array" or field.type.startswith("array["):
        item_type = field.type[6:-1] if field.type.startswith("array[") else "string"
        values = value if isinstance(value, list) else [value]
        return [_coerce_scalar(item, item_type) for item in values if _has_value(item)]
    return _coerce_scalar(value, field.type)


def _value_is_evidenced(value: Any, evidence: str) -> bool:
    if isinstance(value, list):
        return bool(value) and all(_value_is_evidenced(item, evidence) for item in value)
    if isinstance(value, dict):
        return all(_value_is_evidenced(item, evidence) for item in value.values())
    if isinstance(value, bool):
        candidates = {str(value).casefold(), "yes" if value else "no", "1" if value else "0"}
        return any(candidate in evidence.casefold() for candidate in candidates)
    return str(value).strip().casefold() in evidence.casefold()


def _validated_records(
    raw_records: list[dict[str, Any]],
    schema: ApprovedDatasetSchema,
    evidence: str,
) -> list[dict[str, Any]] | None:
    fields = _schema_field_map(schema)
    required = {field.field_name for field in schema.fields if field.required}
    validated: list[dict[str, Any]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or set(raw_record) - set(fields):
            return None
        record: dict[str, Any] = {}
        try:
            for field_name, value in raw_record.items():
                if _has_value(value):
                    record[field_name] = _coerce_value(value, fields[field_name])
        except (TypeError, ValueError):
            return None
        if not required <= {name for name, value in record.items() if _has_value(value)}:
            return None
        if not all(_value_is_evidenced(value, evidence) for value in record.values()):
            return None
        validated.append(record)
    return validated or None


def _table_records(content: str, schema: ApprovedDatasetSchema) -> list[dict[str, Any]] | None:
    # A table is treated as the complete record structure only when surrounding
    # prose is small; otherwise semantic extraction may need to find extra records.
    if len(re.findall(r"\w+", _content_outside_tables(content), flags=re.UNICODE)) > 50:
        return None
    records: list[dict[str, Any]] = []
    for headers, rows in _iter_markdown_tables(content):
        mapping = _header_mapping(headers, schema)
        if mapping is None:
            continue
        records.extend({field_name: row[column] for column, field_name in mapping.items()}
                       for row in rows)
    return _validated_records(records, schema, content) if records else None


def _configured_rules(state: Dict[str, Any]) -> tuple[bool, bool, list[DeterministicExtractionRule]]:
    extraction = state.get("config", {}).get("extraction", {})
    if not isinstance(extraction, dict):
        extraction = {}
    router = extraction.get("router", {})
    if not isinstance(router, dict):
        raise ValueError("extraction.router must be an object.")
    enabled = bool(router.get("enabled", True))
    auto_table = bool(router.get("auto_table", True))
    raw_rules = router.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("extraction.router.rules must be a list.")
    rules = [DeterministicExtractionRule.model_validate(item) for item in raw_rules]
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Deterministic extraction rule IDs must be unique.")
    return enabled, auto_table, rules


def _rule_field_names(rule: DeterministicExtractionRule) -> set[str]:
    if rule.method == "regex":
        return set(rule.patterns)
    return {
        str(field.get("name", ""))
        for key in ("baseFields", "fields")
        for field in rule.schema_config.get(key, [])
        if isinstance(field, dict)
    }


def _raw_rule_records(
    rule: DeterministicExtractionRule,
    *,
    source_url: str,
    content: str,
    html: str,
    schema: ApprovedDatasetSchema,
    extractor: Crawl4AIDeterministicExtractor,
) -> list[dict[str, Any]] | None:
    approved_names = {field.field_name for field in schema.fields}
    configured_names = _rule_field_names(rule)
    if not configured_names or not configured_names <= approved_names:
        raise ValueError(
            f"Rule {rule.rule_id!r} fields must be non-empty approved schema fields."
        )
    evidence = f"{content}\n{html}"
    if rule.method in {"css", "xpath"}:
        if not html.strip():
            return None
        raw_records = extractor.extract_dom(
            method=rule.method,
            source_url=source_url,
            html=html,
            schema=rule.schema_config,
        )
        return _validated_records(raw_records, schema, evidence)

    grouped = extractor.extract_regex(
        source_url=source_url,
        content=content,
        patterns=rule.patterns,
    )
    fields = _schema_field_map(schema)
    record: dict[str, Any] = {}
    for field_name, values in grouped.items():
        if not values:
            continue
        field = fields[field_name]
        is_array = field.type == "array" or field.type.startswith("array[")
        if not is_array and len(values) != 1:
            return None
        record[field_name] = values if is_array else values[0]
    return _validated_records([record], schema, evidence)


def _field_evidence(
    record: dict[str, Any], *, source_url: str, chunks: list[DocumentChunk]
) -> dict[str, list[EvidenceRef]]:
    return {
        field_name: [
            evidence
            for evidence_text in evidence_atoms(value)
            if (evidence := locate_evidence(
                evidence_text,
                chunks,
                source_url=source_url,
                preferred_chunk_id=chunks[0].chunk_id,
            )) is not None
        ]
        for field_name, value in record.items()
        if _has_value(value)
    }


def _extraction_batch(
    records: list[dict[str, Any]],
    *,
    source_url: str,
    chunks: list[DocumentChunk],
    method: str,
) -> ExtractionBatch:
    anchor = chunks[0]
    extracted_records = [ExtractedRecord(
        local_record_id=f"{anchor.chunk_id}:record:{index:04d}",
        source_url=source_url,
        segment_id=anchor.chunk_id,
        chunk_id=anchor.chunk_id,
        source_chunk_id=anchor.chunk_id,
        data=record,
        confidence=1.0,
        field_confidence={field: 1.0 for field, value in record.items() if _has_value(value)},
        field_evidence=_field_evidence(
            record, source_url=source_url, chunks=chunks
        ),
        chunk_index=anchor.chunk_index,
        total_chunks=anchor.total_chunks,
        extraction_method=method,
    ) for index, record in enumerate(records, start=1)]
    return ExtractionBatch(
        source_url=source_url,
        segment_id=anchor.chunk_id,
        chunk_id=anchor.chunk_id,
        records=extracted_records,
    )


def extraction_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Route each processed source once and precompute reliable deterministic records."""
    try:
        approved = state.get("approved_dataset_schema")
        if not approved:
            raise ValueError("An approved dataset schema is required before extraction routing.")
        schema = ApprovedDatasetSchema.model_validate(approved)
        enabled, auto_table, rules = _configured_rules(state)
        chunks_by_url: dict[str, list[DocumentChunk]] = {}
        for raw_chunk in state.get("document_chunks", []):
            chunk = DocumentChunk.model_validate(raw_chunk)
            chunks_by_url.setdefault(chunk.source_url, []).append(chunk)
        processed_by_url = {
            item.source_url: item
            for item in (
                ProcessedDocument.model_validate(raw)
                for raw in state.get("processed_documents", [])
            )
            if item.content_status != "empty"
        }
        bronze_by_url: dict[str, AcquiredDocument] = {}
        for raw in state.get("acquired_documents", []):
            item = AcquiredDocument.model_validate(raw)
            if item.success:
                bronze_by_url[item.source_url] = item
                if item.canonical_url:
                    bronze_by_url[item.canonical_url] = item

        routes: list[ExtractionRoute] = []
        deterministic_results: list[dict[str, Any]] = []
        deterministic_batches: list[dict[str, Any]] = []
        errors = list(state.get("errors", []))
        extractor = Crawl4AIDeterministicExtractor()
        for source_url, chunks in chunks_by_url.items():
            processed = processed_by_url.get(source_url)
            content = processed.processed_content if processed else "\n\n".join(
                chunk.content for chunk in chunks
            )
            bronze = bronze_by_url.get(source_url)
            html = bronze.html or "" if bronze else ""
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            if not enabled:
                routes.append(ExtractionRoute(
                    source_url=source_url, chunk_ids=chunk_ids, method="semantic",
                    reason="Deterministic extraction router is disabled.",
                    model_call_required=True,
                ))
                continue

            rule = next((item for item in rules if re.search(item.url_pattern, source_url)), None)
            fallback_from = None
            fallback_reason = ""
            records: list[dict[str, Any]] | None = None
            method = "semantic"
            if rule is not None:
                fallback_from = rule.method
                try:
                    records = _raw_rule_records(
                        rule,
                        source_url=source_url,
                        content=content,
                        html=html,
                        schema=schema,
                        extractor=extractor,
                    )
                    fallback_reason = (
                        f"Explicit {rule.method} rule returned no complete, typed, evidenced record."
                    )
                except Exception as error:
                    fallback_reason = f"Explicit {rule.method} rule was unreliable: {error}"
                    errors.append({
                        "node": "extraction_router",
                        "source_url": source_url,
                        "rule_id": rule.rule_id,
                        "error": str(error),
                    })
                if records:
                    method = rule.method
            elif auto_table:
                records = _table_records(content, schema)
                if records:
                    method = "table"

            if records:
                batch = _extraction_batch(
                    records, source_url=source_url, chunks=chunks, method=method
                )
                extracted = [
                    ExtractionResult(
                        source_url=record.source_url,
                        data=record.data,
                        confidence=record.confidence,
                        field_confidence=record.field_confidence,
                        source_chunk_id=record.chunk_id,
                        chunk_index=record.chunk_index,
                        total_chunks=record.total_chunks,
                        extraction_method=record.extraction_method,
                    ).model_dump(mode="json")
                    for record in batch.records
                ]
                deterministic_results.extend(extracted)
                deterministic_batches.append(batch.model_dump(mode="json"))
                routes.append(ExtractionRoute(
                    source_url=source_url,
                    chunk_ids=chunk_ids,
                    method=method,
                    rule_id=rule.rule_id if rule else None,
                    reason=(
                        "Explicit selector/pattern produced complete typed records with exact source evidence."
                        if rule else
                        "Markdown table headers uniquely cover required approved-schema fields."
                    ),
                    result_count=len(extracted),
                    model_call_required=False,
                ))
            else:
                routes.append(ExtractionRoute(
                    source_url=source_url,
                    chunk_ids=chunk_ids,
                    method="semantic",
                    rule_id=rule.rule_id if rule else None,
                    fallback_from=fallback_from,
                    reason=fallback_reason or (
                        "No explicit reliable rule or complete low-prose table matches this source."
                    ),
                    model_call_required=True,
                ))

        method_counts = {
            method: sum(route.method == method for route in routes)
            for method in ("css", "xpath", "regex", "table", "semantic")
        }
        metrics = {
            "routed_sources": len(routes),
            "deterministic_sources": sum(not route.model_call_required for route in routes),
            "semantic_sources": sum(route.model_call_required for route in routes),
            "fallback_sources": sum(route.fallback_from is not None for route in routes),
            "deterministic_records": len(deterministic_results),
            "avoided_model_calls": sum(
                len(route.chunk_ids) for route in routes if not route.model_call_required
            ),
            "method_counts": method_counts,
        }
        return {
            "extraction_routes": [route.model_dump(mode="json") for route in routes],
            "deterministic_extraction_results": deterministic_results,
            "deterministic_extraction_batches": deterministic_batches,
            "extraction_routing_metrics": metrics,
            "errors": errors,
            "status": "routing_extraction",
            "pipeline_status": "routing_extraction",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{
                "node": "extraction_router", "error": str(error)
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
