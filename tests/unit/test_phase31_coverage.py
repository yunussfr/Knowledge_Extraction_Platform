from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.knowledge.coverage import analyze_coverage
from src.storage.models.coverage import CoverageState, ResearchTask
from src.storage.repositories import persist_pipeline_state


def _state(db_url, run_key, source_url, data, evidence_text):
    return {
        "config": {"storage": {"enabled": True, "database_url": db_url}, "research_loop": {"max_tasks_per_round": 25}},
        "domain": "coverage", "dataset_name": "coverage_records", "dataset_topic": "People", "dataset_purpose": "Acceptance",
        "approved_dataset_schema": {"name": "person", "identity_fields": ["name"], "schema_version": 1, "fields": [{"field_name": "name"}, {"field_name": "education"}]},
        "status": "completed", "run_manifest": {"created_at": run_key}, "run_metrics": {},
        "candidate_sources": [{"url": source_url, "title": "Fixture source", "domain": "fixture.example"}],
        "selected_sources": [{"url": source_url}],
        "acquired_documents": [{"source_url": source_url, "raw_markdown": evidence_text, "content_hash": run_key, "retrieved_at": run_key}],
        "processed_documents": [],
        "document_chunks": [{"source_url": source_url, "chunk_id": run_key, "chunk_index": 0, "content": evidence_text, "token_count": 3}],
        "accepted_records": [{"local_record_id": f"record-{run_key}", "data": data, "_metadata": {"source_url": source_url, "field_evidence": {field: [{"source_url": source_url, "chunk_id": run_key, "evidence_text": evidence_text}] for field in data}}}],
    }


def test_missing_field_creates_task_and_second_source_completes_it(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'coverage.db'}"
    first = _state(db_url, "2026-08-31T00:00:00+00:00", "https://fixture.example/one", {"name": "Ali",}, "Ali is a researcher.")
    persist_pipeline_state(first)
    initial = analyze_coverage(first)
    assert initial["coverage_metrics"]["missing_fields"] == 1
    assert initial["research_tasks"][0]["status"] == "pending"

    second = _state(db_url, "2026-08-31T00:01:00+00:00", "https://fixture.example/two", {"name": "Ali", "education": "Ankara University"}, "Ali studied at Ankara University.")
    persist_pipeline_state(second)
    enriched = analyze_coverage(second)
    assert enriched["coverage_metrics"]["supported_fields"] == 2
    assert enriched["coverage_metrics"]["tasks_completed"] == 1
    engine = create_engine(db_url)
    with Session(engine) as session:
        assert session.scalar(select(CoverageState.status).where(CoverageState.field_name == "education")) == "supported"
        assert session.scalar(select(ResearchTask.status).where(ResearchTask.field_name == "education")) == "completed"
