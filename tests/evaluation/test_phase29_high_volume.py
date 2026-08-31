import json
from pathlib import Path

from src.agents.nodes.manifest_node import manifest_node
from src.agents.nodes.evidence_validation_node import evidence_validation_node
from src.agents.nodes.field_evidence_node import field_evidence_node
from src.agents.nodes.quality_gate_node import quality_gate_node
from src.schemas.models import ExtractedRecord, ExtractionBatch
from src.storage.repositories import persist_pipeline_state
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from src.storage.models import DatasetRecord, Evidence


FIXTURE = Path(__file__).parent / "fixtures" / "phase29_high_volume.json"


def test_25_record_gold_fixture_has_no_truncation_and_metrics_are_observable(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_url = fixture["source_url"]
    chunk_id = "high-volume:chunk:0001"
    records = [ExtractedRecord(
        local_record_id=record_id,
        source_url=source_url,
        source_chunk_id=chunk_id,
        chunk_id=chunk_id,
        data={"item_name": record_id, "description": f"Evidence for {record_id}"},
        confidence=0.95,
        extraction_method="semantic",
    ) for record_id in fixture["expected_record_ids"]]
    batch = ExtractionBatch(
        source_url=source_url,
        segment_id=chunk_id,
        chunk_id=chunk_id,
        records=records,
    )
    assert len(batch.records) == fixture["expected_record_count"]

    accepted = [{
        "local_record_id": record.local_record_id,
        "source_url": source_url,
        "data": record.data,
        "_metadata": {"source_url": source_url},
    } for record in batch.records]
    result = manifest_node({
        "domain": "fixtures",
        "dataset_name": "phase29_high_volume",
        "dataset_topic": "High-volume fixture",
        "dataset_purpose": "Acceptance",
        "config": {"output": {"directory": str(tmp_path)}},
        "research_plan": {"search_queries": []},
        "candidate_sources": [],
        "source_previews": [],
        "selected_sources": [],
        "source_evaluations": [],
        "source_selections": [],
        "source_policy": {},
        "extraction_routes": [{"model_call_required": True, "chunk_ids": [chunk_id]}],
        "extraction_batches": [batch.model_dump(mode="json")],
        "verified_records": [{
            "record": {"source_url": source_url},
            "field_validations": {
                "item_name": {"status": "SUPPORTED"},
                "description": {"status": "SUPPORTED"},
            },
        } for _ in batch.records],
        "accepted_records": accepted,
        "validated_data": accepted,
        "processed_data": [{"source": source_url, "word_count": fixture["source_word_count"]}],
        "document_chunks": [{"source_url": source_url, "chunk_id": chunk_id, "token_count": 150}],
        "evidence_validation_metrics": {"supported_fields": 50},
        "quality_gate_metrics": {"accepted_records": 25, "rejected_records": 0},
        "deduplication_metrics": {"duplicates_removed": 0},
        "storage_metrics": {},
        "output_profiles": [],
        "output_paths": {},
        "errors": [],
        "status": "completed",
        "pipeline_status": "completed",
    })
    metrics = result["run_metrics"]["extraction_validation"]
    assert metrics["records_extracted"] == 25
    assert metrics["records_per_source"] == {source_url: 25}
    assert metrics["records_per_chunk"] == [25]
    assert metrics["knowledge_yield"][source_url] == {
        "source_word_count": 125,
        "records_extracted": 25,
        "fields_populated": 50,
        "supported_fields": 50,
        "accepted_records": 25,
    }


def test_25_record_gold_fixture_preserves_evidence_through_quality_gate():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_url = fixture["source_url"]
    chunk_id = "high-volume:chunk:0001"
    records = [{
        "local_record_id": record_id,
        "source_url": source_url,
        "source_chunk_id": chunk_id,
        "chunk_id": chunk_id,
        "data": {"item_name": record_id, "description": f"Evidence for {record_id}"},
        "confidence": 0.95,
        "field_confidence": {"item_name": 0.95, "description": 0.95},
        "extraction_method": "semantic",
    } for record_id in fixture["expected_record_ids"]]
    content = " ".join(
        f"{record['data']['item_name']} {record['data']['description']}."
        for record in records
    )
    state = {
        "approved_dataset_schema": {
            "name": "phase29_high_volume",
            "description": "25-record acceptance schema",
            "fields": [
                {"field_name": "item_name", "type": "string", "required": True, "description": "Item", "extraction_instruction": "Extract item."},
                {"field_name": "description", "type": "string", "required": True, "description": "Description", "extraction_instruction": "Extract description."},
            ],
            "schema_version": 1,
            "approved_at": "2026-08-31T00:00:00+00:00",
            "approved_by": "phase29",
        },
        "document_chunks": [{"chunk_id": chunk_id, "source_url": source_url, "source_title": "High volume", "chunk_index": 0, "total_chunks": 1, "content": content, "token_count": len(content.split()), "source_metadata": {"source_provider": "fixture"}}],
        "extraction_batches": [ExtractionBatch(source_url=source_url, segment_id=chunk_id, chunk_id=chunk_id, records=records).model_dump(mode="json")],
        "source_evaluations": [{"url": source_url, "final_score": 0.9}],
        "config": {"quality": {"minimum_evidence_quality": 0.7}},
        "rejected_records": [],
        "errors": [],
    }
    evidenced = field_evidence_node(state)
    verified = evidence_validation_node({**state, **evidenced})
    gated = quality_gate_node({**state, **evidenced, **verified})
    assert gated["quality_gate_metrics"]["accepted_records"] == 25
    assert gated["quality_gate_metrics"]["rejected_records"] == 0
    assert gated["quality_gate_metrics"]["unsupported_accepted_field_rate"] == 0.0
    assert len(gated["quality_approved_extraction_batches"][0]["records"]) == 25


def test_25_record_gold_fixture_is_persisted_with_traceable_evidence(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_url = fixture["source_url"]
    state = {
        "config": {"storage": {"enabled": True, "database_url": f"sqlite:///{tmp_path / 'phase29.db'}"}},
        "domain": "fixtures", "dataset_name": "phase29_db", "dataset_topic": "High volume", "dataset_purpose": "Acceptance",
        "approved_dataset_schema": {"name": "phase29", "schema_version": 1, "fields": []},
        "status": "completed", "run_manifest": {"created_at": "2026-08-31T00:00:00+00:00"}, "run_metrics": {},
        "candidate_sources": [{"url": source_url, "title": "High volume", "domain": "fixtures.example"}],
        "selected_sources": [{"url": source_url, "title": "High volume"}],
        "acquired_documents": [{"source_url": source_url, "raw_markdown": "raw", "content_hash": "raw", "retrieved_at": "2026-08-31T00:00:00Z"}],
        "processed_documents": [{"source": source_url, "content": "processed", "word_count": 125, "metadata": {"content_hash": "processed"}}],
        "document_chunks": [{"source_url": source_url, "chunk_id": "high-volume:chunk:0001", "chunk_index": 0, "content": "evidence", "token_count": 150}],
        "accepted_records": [{"local_record_id": record_id, "data": {"item_name": record_id}, "_metadata": {"source_url": source_url, "field_evidence": {"item_name": [{"source_url": source_url, "chunk_id": "high-volume:chunk:0001", "evidence_text": record_id}]}}} for record_id in fixture["expected_record_ids"]],
    }
    metrics = persist_pipeline_state(state)
    assert metrics["records_inserted"] == 25
    assert metrics["evidence_inserted"] == 25
    engine = create_engine(f"sqlite:///{tmp_path / 'phase29.db'}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DatasetRecord)) == 25
        assert session.scalar(select(func.count()).select_from(Evidence)) == 25
