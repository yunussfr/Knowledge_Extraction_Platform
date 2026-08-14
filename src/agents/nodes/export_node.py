"""Write validated records in explicit Structured, RAG, or GraphRAG profiles."""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict

from src.core.field_evidence import source_evidence_slice
from src.core.settings import settings
from src.schemas.models import (
    ApprovedDatasetSchema,
    EvidenceBackedRelation,
    EvidenceRef,
    GraphRAGClaim,
    GraphRAGEntity,
    GraphRAGOutputRecord,
    KnowledgeRecord,
    MetadataSchema,
    RAGOutputRecord,
    StructuredOutputRecord,
)
from src.state.state import AgentState


PROFILE_NAMES = {"structured", "rag", "graphrag"}


def _legacy_records(state: AgentState) -> list[dict[str, Any]]:
    records = []
    for index, item in enumerate(state.get("validated_data", []), start=1):
        metadata = MetadataSchema(
            schema_version="1.0",
            source_url=item["metadata"].get("source_url", ""),
            source_type="web",
            retrieved_at=item["metadata"].get("extracted_at", ""),
            processed_at=datetime.datetime.utcnow().isoformat(),
            confidence_score=item["metadata"].get("confidence_score", 0.0),
            validation_method=item["metadata"].get("validation_method", "rule_based"),
        )
        record = KnowledgeRecord(
            id=f"{state.get('domain', 'unknown')}-{uuid.uuid4().hex[:6]}",
            domain=state.get("domain", "unknown"),
            title=f"Extracted Knowledge {index}",
            content=item.get("normalized_content", item.get("cleaned_content", "")),
            relations=[relation.get("target_entity") for relation in item.get("relations", [])],
            tags=[item.get("category", "general")],
            metadata=metadata,
            validation_status=item.get("validation_status", "validated"),
        )
        records.append(record.model_dump(mode="json"))
    return records


def _profiles(output_config: Dict[str, Any], *, approved_schema: bool) -> list[str]:
    raw_profiles = output_config.get("profiles", ["structured"])
    if isinstance(raw_profiles, str):
        raw_profiles = [raw_profiles]
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("output.profiles must contain at least one output profile.")
    profiles: list[str] = []
    aliases = {"graph_rag": "graphrag", "graph-rag": "graphrag"}
    for raw_profile in raw_profiles:
        profile = aliases.get(str(raw_profile).strip().casefold(), str(raw_profile).strip().casefold())
        if profile not in PROFILE_NAMES:
            raise ValueError(f"Unsupported output profile: {raw_profile}")
        if profile not in profiles:
            profiles.append(profile)
    if not approved_schema and profiles != ["structured"]:
        raise ValueError("RAG and GraphRAG profiles require an approved dataset schema.")
    return profiles


def _provenance(metadata: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "source_url",
        "source_urls",
        "source_title",
        "source_titles",
        "source_content_hashes",
        "contributing_chunk_ids",
        "contributing_record_ids",
        "contributors",
        "resolution_method",
        "resolution_key",
        "merge_conflicts",
        "deduplication",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def _quality(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "evidence_quality_score": metadata.get("evidence_quality_score", 0.0),
        "support_statuses": metadata.get("evidence_support_statuses", []),
        "assessments": metadata.get("quality_assessments", []),
        "validation_method": metadata.get("validation_method", ""),
    }


def _structured_records(
    records: list[Dict[str, Any]], schema: ApprovedDatasetSchema
) -> list[dict[str, Any]]:
    schema_metadata = {
        "name": schema.name,
        "description": schema.description,
        "schema_version": schema.schema_version,
        "identity_fields": schema.identity_fields,
        "fields": [field.model_dump(mode="json") for field in schema.fields],
    }
    output = []
    for record in records:
        metadata = dict(record.get("_metadata", {}))
        output.append(StructuredOutputRecord(
            data=dict(record.get("data", {})),
            evidence=metadata.get("field_evidence", {}),
            provenance=_provenance(metadata),
            quality=_quality(metadata),
            schema_metadata=schema_metadata,
            legacy_metadata=metadata,
        ).model_dump(mode="json", by_alias=True))
    return output


def _render_rag_text(data: Dict[str, Any], schema: ApprovedDatasetSchema) -> str:
    for preferred in ("text", "content"):
        value = data.get(preferred)
        if isinstance(value, str) and value.strip():
            return value.strip()
    lines = []
    for field in schema.fields:
        value = data.get(field.field_name)
        if value in (None, "", [], {}):
            continue
        rendered = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, sort_keys=True
        )
        label = field.field_name.replace("_", " ").strip().title()
        lines.append(f"{label}: {rendered}")
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("An accepted record cannot produce empty RAG text.")
    return text


def _record_title(data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    for field_name, value in data.items():
        normalized = field_name.casefold()
        if (
            normalized == "name"
            or normalized.endswith("_name")
            or normalized == "title"
            or normalized.endswith("_title")
        ) and isinstance(value, str) and value.strip():
            return value.strip()
    return str(metadata.get("source_title", ""))


def _primary_chunk(metadata: Dict[str, Any]) -> tuple[str, str]:
    contributors = metadata.get("contributors", [])
    if contributors:
        return (
            contributors[0].get("source_url", metadata.get("source_url", "")),
            contributors[0].get("chunk_id", ""),
        )
    chunks = metadata.get("contributing_chunk_ids", [])
    return metadata.get("source_url", ""), chunks[0] if chunks else ""


def _content_hash(metadata: Dict[str, Any], source_url: str) -> str:
    return str(
        metadata.get("source_content_hashes", {}).get(source_url)
        or metadata.get("processed_content_hash")
        or metadata.get("content_hash")
        or ""
    )


def _rag_records(
    records: list[Dict[str, Any]],
    schema: ApprovedDatasetSchema,
    state: AgentState,
) -> list[dict[str, Any]]:
    headings = {
        (chunk.get("source_url", ""), chunk.get("chunk_id", "")): chunk.get("heading", "")
        for chunk in state.get("document_chunks", [])
    }
    output = []
    for record in records:
        data = dict(record.get("data", {}))
        metadata = dict(record.get("_metadata", {}))
        source_url, chunk_id = _primary_chunk(metadata)
        output.append(RAGOutputRecord(
            text=_render_rag_text(data, schema),
            title=_record_title(data, metadata),
            source_url=source_url,
            source_urls=metadata.get("source_urls", [source_url] if source_url else []),
            section_path=headings.get((source_url, chunk_id), ""),
            chunk_id=chunk_id,
            language=metadata.get("language", ""),
            content_hash=_content_hash(metadata, source_url),
            quality_score=metadata.get("evidence_quality_score", 0.0),
            evidence=metadata.get("field_evidence", {}),
            record_data=data,
            schema_name=schema.name,
            schema_version=str(schema.schema_version),
        ).model_dump(mode="json"))
    return output


def _identity_fields(schema: ApprovedDatasetSchema) -> list[str]:
    if schema.identity_fields:
        return schema.identity_fields
    for field in schema.fields:
        name = field.field_name.casefold()
        if (
            name == "id"
            or name.endswith("_id")
            or name == "name"
            or name.endswith("_name")
            or name == "title"
            or name.endswith("_title")
        ):
            return [field.field_name]
    return []


def _traceable_evidence(
    raw_evidence: Any, chunks: dict[tuple[str, str], str]
) -> list[EvidenceRef]:
    traceable: list[EvidenceRef] = []
    for raw_reference in raw_evidence if isinstance(raw_evidence, list) else []:
        try:
            reference = EvidenceRef.model_validate(raw_reference)
        except Exception:
            continue
        content = chunks.get((reference.source_url, reference.chunk_id))
        if content is None or source_evidence_slice(
            content, reference.evidence_text
        ) is None:
            continue
        traceable.append(reference)
    return traceable


def _traceable_relation(
    raw_relation: Any, chunks: dict[tuple[str, str], str]
) -> EvidenceBackedRelation | None:
    try:
        relation = EvidenceBackedRelation.model_validate(raw_relation)
    except Exception:
        return None
    traceable = _traceable_evidence(relation.evidence, chunks)
    if len(traceable) != len(relation.evidence):
        return None
    relation.evidence = traceable
    return relation


def _graphrag_records(
    records: list[Dict[str, Any]],
    schema: ApprovedDatasetSchema,
    state: AgentState,
) -> list[dict[str, Any]]:
    chunks = {
        (chunk.get("source_url", ""), chunk.get("chunk_id", "")): chunk.get("content", "")
        for chunk in state.get("document_chunks", [])
    }
    identity_fields = _identity_fields(schema)
    output = []
    for record in records:
        data = dict(record.get("data", {}))
        metadata = dict(record.get("_metadata", {}))
        evidence = metadata.get("field_evidence", {})
        entities = []
        for field_name in identity_fields:
            if data.get(field_name) in (None, "", [], {}):
                continue
            traceable = _traceable_evidence(evidence.get(field_name, []), chunks)
            if traceable:
                entities.append(GraphRAGEntity(
                    name=str(data[field_name]),
                    field_name=field_name,
                    evidence=traceable,
                ))
        claims = []
        for field_name, value in data.items():
            if value in (None, "", [], {}):
                continue
            traceable = _traceable_evidence(evidence.get(field_name, []), chunks)
            if not traceable:
                continue
            claim_material = json.dumps(
                [metadata.get("resolution_key", ""), field_name, value],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            claims.append(GraphRAGClaim(
                claim_id=hashlib.sha256(claim_material.encode("utf-8")).hexdigest(),
                predicate=field_name,
                value=value,
                evidence=traceable,
            ))
        relations = [
            relation
            for raw_relation in metadata.get("evidence_backed_relations", [])
            if (relation := _traceable_relation(raw_relation, chunks)) is not None
        ]
        record_key = metadata.get("resolution_key") or hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        output.append(GraphRAGOutputRecord(
            record_key=record_key,
            entities=entities,
            claims=claims,
            relations=relations,
            provenance=_provenance(metadata),
            quality=_quality(metadata),
            schema_name=schema.name,
            schema_version=str(schema.schema_version),
        ).model_dump(mode="json"))
    return output


def _write_records(path: Path, output_format: str, records: list[dict[str, Any]]) -> None:
    if output_format == "jsonl":
        with path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return
    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)


def export_node(state: AgentState) -> Dict[str, Any]:
    """Export intentionally different downstream profiles without altering Gold state."""
    try:
        domain = state.get("domain", "unknown")
        dataset_name = state.get("dataset_name") or f"{domain}_latest"
        output_config = state.get("config", {}).get("output", {})
        output_format = output_config.get("format", settings.default_output_format).lower()
        if output_format not in {"json", "jsonl"}:
            raise ValueError(f"Unsupported output format: {output_format}")
        approved = state.get("approved_dataset_schema")
        profiles = _profiles(output_config, approved_schema=bool(approved))
        output_dir = Path(output_config.get("directory", settings.output_directory))
        output_dir.mkdir(parents=True, exist_ok=True)

        output_records: dict[str, list[dict[str, Any]]] = {}
        if approved:
            schema = ApprovedDatasetSchema.model_validate(approved)
            accepted = list(state.get("accepted_records", []))
            for profile in profiles:
                if profile == "structured":
                    output_records[profile] = _structured_records(accepted, schema)
                elif profile == "rag":
                    output_records[profile] = _rag_records(accepted, schema, state)
                else:
                    output_records[profile] = _graphrag_records(accepted, schema, state)
        else:
            output_records["structured"] = _legacy_records(state)

        output_paths: dict[str, str] = {}
        for profile, records in output_records.items():
            suffix = "" if profile == "structured" else f"_{profile}"
            output_path = output_dir / f"{dataset_name}{suffix}.{output_format}"
            _write_records(output_path, output_format, records)
            output_paths[profile] = str(output_path)

        save_raw = output_config.get("save_raw_content", settings.save_raw_content)
        save_clean = output_config.get("save_clean_content", settings.save_clean_content)
        if save_raw:
            (output_dir / f"{dataset_name}_raw.json").write_text(
                json.dumps(state.get("raw_data", []), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if save_clean:
            (output_dir / f"{dataset_name}_clean.json").write_text(
                json.dumps(state.get("processed_data", []), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        primary_profile = profiles[0]
        return {
            "output_profiles": profiles,
            "output_paths": output_paths,
            "status": "completed",
            "pipeline_status": "completed",
            "validation_report": {
                **state.get("validation_report", {}),
                "output_path": output_paths[primary_profile],
                "output_paths": output_paths,
            },
        }
    except Exception as error:
        return {
            "errors": state.get("errors", [])
            + [{"node": "export", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
