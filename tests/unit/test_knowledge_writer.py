import os

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.storage.models.knowledge import Entity, Fact, FactEvidence, Relation
from src.storage.repositories import persist_pipeline_state


def test_three_sources_upsert_one_entity_and_preserve_fact_conflicts(tmp_path):
    urls = [f"https://source-{index}.example/item" for index in range(1, 4)]
    records = []
    for index, url in enumerate(urls, start=1):
        records.append({
            "local_record_id": f"record-{index}",
            "data": {"name": "  Shared Entity  ", "description": f"Description from source {index}"},
            "_metadata": {"source_url": url, "field_evidence": {
                "name": [{"source_url": url, "chunk_id": f"chunk-{index}", "evidence_text": "Shared Entity"}],
                "description": [{"source_url": url, "chunk_id": f"chunk-{index}", "evidence_text": f"Description from source {index}"}],
            }},
        })
    db_url = os.getenv("PHASE30_DATABASE_URL", f"sqlite:///{tmp_path / 'knowledge.db'}")
    state = {
        "config": {"storage": {"enabled": True, "database_url": db_url}},
        "domain": "knowledge", "dataset_name": "knowledge_records", "dataset_topic": "Entities", "dataset_purpose": "Acceptance",
        "approved_dataset_schema": {"name": "entity", "identity_fields": ["name"], "schema_version": 1, "fields": [{"field_name": "name"}, {"field_name": "description"}]},
        "status": "completed", "run_manifest": {"created_at": "2026-08-31T00:00:00+00:00"}, "run_metrics": {},
        "candidate_sources": [{"url": url, "title": f"Source {index}", "domain": f"source-{index}.example"} for index, url in enumerate(urls, start=1)],
        "selected_sources": [{"url": url} for url in urls],
        "acquired_documents": [{"source_url": url, "raw_markdown": "raw", "content_hash": f"hash-{index}", "retrieved_at": "2026-08-31T00:00:00Z"} for index, url in enumerate(urls, start=1)],
        "processed_documents": [],
        "document_chunks": [{"source_url": url, "chunk_id": f"chunk-{index}", "chunk_index": 0, "content": f"Shared Entity Description from source {index}", "token_count": 5} for index, url in enumerate(urls, start=1)],
        "accepted_records": records,
    }
    metrics = persist_pipeline_state(state)
    assert metrics["entities_created"] == 1
    assert metrics["facts_created"] == 4
    assert metrics["knowledge_evidence_created"] == 6
    assert metrics["identity_conflicts"] == 2

    second = persist_pipeline_state(state)
    assert second["entities_created"] == 0
    assert second["facts_created"] == 0
    assert second["knowledge_evidence_created"] == 0
    engine = create_engine(db_url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Entity)) == 1
        assert session.scalar(select(func.count()).select_from(Fact)) == 4
        assert session.scalar(select(func.count()).select_from(FactEvidence)) == 6
        statuses = {fact.status for fact in session.scalars(select(Fact)).all()}
        assert statuses == {"asserted", "conflict"}


def test_only_explicit_evidence_backed_relations_are_written(tmp_path):
    url = "https://source.example/relation"
    state = {
        "config": {"storage": {"enabled": True, "database_url": f"sqlite:///{tmp_path / 'relations.db'}"}},
        "domain": "knowledge", "dataset_name": "relation_records", "dataset_topic": "Relations", "dataset_purpose": "Acceptance",
        "approved_dataset_schema": {"name": "entity", "identity_fields": ["name"], "schema_version": 1, "fields": [{"field_name": "name"}]},
        "status": "completed", "run_manifest": {"created_at": "2026-08-31T00:00:00+00:00"}, "run_metrics": {},
        "candidate_sources": [{"url": url, "title": "Relation source", "domain": "source.example"}],
        "selected_sources": [{"url": url}],
        "acquired_documents": [{"source_url": url, "raw_markdown": "Alice leads the team.", "content_hash": "relation-hash", "retrieved_at": "2026-08-31T00:00:00Z"}],
        "processed_documents": [],
        "document_chunks": [{"source_url": url, "chunk_id": "relation-chunk", "chunk_index": 0, "content": "Alice leads the team.", "token_count": 4}],
        "accepted_records": [{
            "local_record_id": "relation-record",
            "data": {"name": "Alice"},
            "_metadata": {
                "source_url": url,
                "field_evidence": {"name": [{"source_url": url, "chunk_id": "relation-chunk", "evidence_text": "Alice"}]},
                "evidence_backed_relations": [
                    {"object": "Team", "predicate": "leads", "evidence": "Alice leads the team."},
                    {"object": "Ignored", "predicate": "co_occurs_with"},
                ],
            },
        }],
    }
    metrics = persist_pipeline_state(state)
    assert metrics["relations_created"] == 1
    assert metrics["entities_created"] == 2
    engine = create_engine(state["config"]["storage"]["database_url"])
    with Session(engine) as session:
        relations = session.scalars(select(Relation)).all()
        assert len(relations) == 1
        assert relations[0].relation_type == "leads"
