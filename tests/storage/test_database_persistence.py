from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import StatementError
import pytest
from sqlalchemy.orm import Session

from src.storage.database import Base
from src.storage.models import Chunk, DatasetRecord, Evidence, ResearchRun, Source
from src.storage.repositories import persist_pipeline_state
from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.settings import settings
from src.state.state import create_initial_state


def _state(tmp_path: Path) -> dict:
    url = f"sqlite:///{tmp_path / 'knowledge.db'}"
    return {
        "config": {"storage": {"enabled": True, "database_url": url}},
        "domain": "coffee",
        "dataset_name": "coffee_records",
        "dataset_topic": "Traditional coffee",
        "dataset_purpose": "Evidence-backed records",
        "approved_dataset_schema": {"name": "coffee", "schema_version": 1, "fields": []},
        "status": "completed",
        "candidate_sources": [{"url": "https://example.test/coffee", "domain": "example.test", "title": "Coffee"}],
        "selected_sources": [{"url": "https://example.test/coffee", "title": "Coffee"}],
        "acquired_documents": [{"source_url": "https://example.test/coffee", "raw_markdown": "Raw coffee text", "content_hash": "raw-hash", "retrieved_at": "2026-08-31T00:00:00Z", "success": True}],
        "processed_documents": [{"source": "https://example.test/coffee", "content": "Processed coffee text", "word_count": 3, "metadata": {"content_hash": "processed-hash"}}],
        "document_chunks": [{"source_url": "https://example.test/coffee", "chunk_id": "coffee:0", "chunk_index": 0, "content": "Coffee evidence", "token_count": 2, "heading": "Coffee"}],
        "accepted_records": [{"local_record_id": "coffee:0:record:0001", "data": {"name": "Coffee"}, "_metadata": {"resolution_key": "coffee", "evidence_quality_score": 0.9, "field_evidence": {"name": [{"source_url": "https://example.test/coffee", "chunk_id": "coffee:0", "evidence_text": "Coffee evidence"}]}}}],
        "run_manifest": {"created_at": "2026-08-31T00:00:00+00:00"},
        "run_metrics": {"sources": {"discovered": 1}},
    }


def test_pipeline_artifacts_persist_and_repeat_is_idempotent(tmp_path):
    state = _state(tmp_path)
    first = persist_pipeline_state(state)
    second = persist_pipeline_state(state)
    assert first["sources"] == 1
    assert first["documents"] == 1
    assert first["chunks"] == 1
    assert first["records_inserted"] == 1
    assert first["evidence_inserted"] == 1
    assert second["records_inserted"] == 0
    assert second["evidence_inserted"] == 0

    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchRun)) == 1
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Chunk)) == 1
        assert session.scalar(select(func.count()).select_from(DatasetRecord)) == 1
        assert session.scalar(select(func.count()).select_from(Evidence)) == 1


def test_models_can_bootstrap_clean_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    assert set(Base.metadata.tables) == {"datasets", "research_runs", "sources", "documents", "document_chunks", "dataset_records", "field_evidence"}


def test_persistence_transaction_rolls_back_on_serialization_failure(tmp_path):
    state = _state(tmp_path)
    state["run_metrics"] = {"not_json": object()}
    try:
        persist_pipeline_state(state)
    except (TypeError, StatementError):
        pass
    else:
        raise AssertionError("Expected JSON serialization failure")

    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchRun)) == 0
        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_enabled_storage_is_reached_by_mock_pipeline(tmp_path):
    original = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        config = {
            "dataset": {"name": "stored_records", "topic": "Coffee", "purpose": "Test"},
            "research": {"queries": ["coffee"], "max_sources": 1},
            "sources": [{"url": "https://example.test/coffee", "title": "Coffee", "enabled": True}],
            "storage": {"enabled": True, "database_url": f"sqlite:///{tmp_path / 'pipeline.db'}"},
            "output": {"format": "json", "directory": str(tmp_path / "output")},
        }
        pending = build_phase2_pipeline().invoke(create_initial_state("coffee", config))
        completed = build_phase2_pipeline().approve_schema(pending)
        assert completed["status"] == "completed"
        assert completed["storage_metrics"]["enabled"] is True
        assert completed["storage_metrics"]["sources"] == 1
        assert completed["run_metrics"]["storage"]["records_inserted"] >= 1
        assert (tmp_path / "output" / "stored_records.json").is_file()
    finally:
        object.__setattr__(settings, "data_source_provider", original)
