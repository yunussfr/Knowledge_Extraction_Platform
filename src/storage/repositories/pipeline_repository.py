"""Idempotent persistence mapper for a completed pipeline state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.storage.database import create_session_factory, initialize_database
from src.storage.models import Chunk, Dataset, DatasetRecord, Document, Evidence, ResearchRun, Source


def _url(item: dict[str, Any]) -> str:
    return str(item.get("canonical_url") or item.get("source_url") or item.get("source") or item.get("url") or "")


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return dict(item.get("_metadata") or item.get("metadata") or {})


def _number(item: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(item.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def persist_pipeline_state(state: dict[str, Any]) -> dict[str, Any]:
    """Persist one state atomically and return observable counts.

    The database layer receives plain JSON-safe state and never owns a crawler,
    provider client, or Pydantic model instance.
    """
    config = state.get("config", {})
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    if not isinstance(storage, dict):
        storage = {}
    initialize_database(config)
    factory = create_session_factory(config)
    dataset_name = str(state.get("dataset_name") or state.get("domain") or "dataset")
    manifest = dict(state.get("run_manifest") or {})
    prior_storage = dict(state.get("storage_metrics") or {})
    run_key = str(storage.get("run_key") or prior_storage.get("run_key") or manifest.get("created_at") or "")
    if not run_key:
        material = json.dumps({"dataset": dataset_name, "config": config}, ensure_ascii=False, sort_keys=True, default=str)
        run_key = hashlib.sha256(material.encode("utf-8")).hexdigest()

    acquired = list(state.get("acquired_documents", []))
    processed = list(state.get("processed_documents", [])) or list(state.get("processed_data", []))
    chunks = list(state.get("document_chunks", []))
    candidates = list(state.get("candidate_sources", []))
    selected = list(state.get("selected_sources", []))
    records = list(state.get("accepted_records", [])) or list(state.get("resolved_records", []))

    with factory.begin() as session:
        dataset = session.scalar(select(Dataset).where(Dataset.name == dataset_name))
        if dataset is None:
            dataset = Dataset(name=dataset_name, topic=str(state.get("dataset_topic", "")), purpose=str(state.get("dataset_purpose", "")))
            session.add(dataset)
            session.flush()
        else:
            dataset.topic = str(state.get("dataset_topic", dataset.topic))
            dataset.purpose = str(state.get("dataset_purpose", dataset.purpose))
        schema = dict(state.get("approved_dataset_schema") or {})
        dataset.schema_json = schema
        dataset.schema_version = schema.get("schema_version")

        run = session.scalar(select(ResearchRun).where(ResearchRun.run_key == run_key))
        if run is None:
            run = ResearchRun(dataset_id=dataset.id, run_key=run_key, status=str(state.get("status", "unknown")))
            session.add(run)
            session.flush()
        run.status = str(state.get("status", "unknown"))
        run.completed_at = datetime.now(timezone.utc) if run.status == "completed" else None
        run.request_json = dict(config)
        run.metrics_json = dict(state.get("run_metrics") or {})

        source_by_url: dict[str, Source] = {}
        source_items = candidates + selected
        for item in source_items:
            url = _url(item)
            if not url or url in source_by_url:
                continue
            source = session.scalar(select(Source).where(Source.canonical_url == url))
            if source is None:
                source = Source(canonical_url=url)
                session.add(source)
                session.flush()
            source.domain = str(item.get("domain") or source.domain or "")
            source.title = str(item.get("title") or source.title or "")
            source.source_type = str(item.get("type") or source.source_type or "")
            source_by_url[url] = source

        document_by_url: dict[str, Document] = {}
        document_items: dict[str, dict[str, Any]] = {}
        for item in acquired + processed:
            url = _url(item)
            if not url:
                continue
            # One URL is one retrieved document for a run. Bronze content is
            # preferred; its processed projection is merged into that row.
            if url not in document_items:
                document_items[url] = dict(item)
            else:
                document_items[url].update({key: value for key, value in item.items() if value not in (None, "", {})})
        for item in document_items.values():
            url = _url(item)
            source = source_by_url.get(url)
            if source is None:
                source = session.scalar(select(Source).where(Source.canonical_url == url))
            if source is None:
                source = Source(canonical_url=url, title=str(item.get("title", "")))
                session.add(source)
                session.flush()
                source_by_url[url] = source
            meta = _metadata(item)
            content_hash = str(item.get("content_hash") or meta.get("content_hash") or "")
            document = session.scalar(select(Document).where(Document.source_id == source.id, Document.run_id == run.id, Document.content_hash == content_hash))
            if document is None:
                document = Document(source_id=source.id, run_id=run.id, content_hash=content_hash)
                session.add(document)
            document.raw_markdown = str(item.get("raw_markdown") or item.get("content") or "")
            document.processed_markdown = str(item.get("cleaned_content") or item.get("content") or "")
            document.raw_html = item.get("html")
            document.language = str(meta.get("language", ""))
            document.word_count = int(item.get("word_count") or meta.get("word_count") or 0)
            document.retrieved_at = str(item.get("retrieved_at") or meta.get("retrieved_at") or "")
            session.flush()
            document_by_url[url] = document

        chunk_by_key: dict[tuple[str, str], Chunk] = {}
        for raw in chunks:
            url = str(raw.get("source_url", ""))
            document = document_by_url.get(url)
            if document is None:
                continue
            index = int(raw.get("chunk_index", 0) or 0)
            existing = session.scalar(select(Chunk).where(Chunk.document_id == document.id, Chunk.chunk_index == index))
            chunk = existing or Chunk(document_id=document.id, chunk_index=index)
            chunk.content = str(raw.get("content", ""))
            chunk.token_count = int(raw.get("token_count", 0) or 0)
            chunk.heading = str(raw.get("heading", ""))
            chunk.content_hash = str((raw.get("source_metadata") or {}).get("processed_content_hash") or (raw.get("source_metadata") or {}).get("content_hash") or "")
            if existing is None:
                session.add(chunk)
                session.flush()
            chunk_by_key[(url, str(raw.get("chunk_id", "")))] = chunk

        persisted_records = 0
        persisted_evidence = 0
        dataset_record_by_local_id: dict[str, DatasetRecord] = {}
        for raw_record in records:
            meta = _metadata(raw_record)
            record_id = str(raw_record.get("local_record_id") or meta.get("local_record_id") or hashlib.sha256(json.dumps(raw_record.get("data", {}), sort_keys=True, default=str).encode()).hexdigest())
            existing = session.scalar(select(DatasetRecord).where(DatasetRecord.run_id == run.id, DatasetRecord.local_record_id == record_id))
            record = existing or DatasetRecord(dataset_id=dataset.id, run_id=run.id, local_record_id=record_id)
            record.identity_key = str(meta.get("resolution_key", "") or "")
            record.data_json = dict(raw_record.get("data", {}))
            record.completeness_score = _number(meta, "completeness_score")
            record.quality_score = _number(meta, "evidence_quality_score")
            record.status = "accepted"
            if existing is None:
                session.add(record)
                session.flush()
                persisted_records += 1
            dataset_record_by_local_id[record_id] = record
            for field_name, refs in (meta.get("field_evidence") or {}).items():
                for ref in refs if isinstance(refs, list) else []:
                    evidence_text = str(ref.get("evidence_text", ""))
                    source_url = str(ref.get("source_url", ""))
                    source = source_by_url.get(source_url)
                    if not source or not evidence_text:
                        continue
                    duplicate = session.scalar(select(Evidence).where(Evidence.record_id == record.id, Evidence.field_name == str(field_name), Evidence.chunk_id == str(ref.get("chunk_id", "")), Evidence.evidence_text == evidence_text))
                    if duplicate is not None:
                        continue
                    session.add(Evidence(record_id=record.id, field_name=str(field_name), source_id=source.id, document_id=document_by_url.get(source_url).id if document_by_url.get(source_url) else None, chunk_id=str(ref.get("chunk_id", "")), evidence_text=evidence_text, confidence=None))
                    persisted_evidence += 1

        knowledge_metrics = {"entities_created": 0, "facts_created": 0, "relations_created": 0, "knowledge_evidence_created": 0, "identity_conflicts": 0, "record_entity_links_created": 0}
        if records:
            from src.knowledge.knowledge_writer import write_knowledge_records
            knowledge_metrics = write_knowledge_records(
                session,
                records,
                schema,
                source_by_url,
                document_by_url,
                dataset_record_by_local_id,
            )

    return {"dataset": dataset_name, "run_key": run_key, "sources": len(source_by_url), "documents": len(document_by_url), "chunks": len(chunk_by_key), "records_inserted": persisted_records, "evidence_inserted": persisted_evidence, **knowledge_metrics}
