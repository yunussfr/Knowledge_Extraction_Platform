"""Deterministic coverage analysis and bounded enrichment task generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from src.storage.database import create_session_factory, initialize_database
from src.storage.models.entities import Dataset, DatasetRecord
from src.storage.models.knowledge import DatasetRecordEntity, Entity, Fact, FactEvidence
from src.storage.models.coverage import CoverageState, ResearchTask


def analyze_coverage(state: dict[str, Any]) -> dict[str, Any]:
    """Persist field coverage and create/update a bounded queue of research tasks."""
    config = state.get("config", {})
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    enabled = bool(isinstance(storage, dict) and storage.get("enabled"))
    if not enabled:
        return {"coverage_metrics": {"enabled": False}, "coverage_states": [], "research_tasks": []}

    initialize_database(config)
    factory = create_session_factory(config)
    fields = [item.get("field_name") for item in (state.get("approved_dataset_schema", {}).get("fields", [])) if isinstance(item, dict) and item.get("field_name")]
    loop = config.get("research_loop", {}) if isinstance(config, dict) else {}
    max_tasks = int(loop.get("max_tasks_per_round", 25)) if isinstance(loop, dict) else 25
    with factory() as session:
        dataset = session.scalar(select(Dataset).where(Dataset.name == str(state.get("dataset_name", ""))))
        if dataset is None:
            return {"coverage_metrics": {"enabled": True, "entities": 0, "tasks_created": 0, "information_gain": 0}, "coverage_states": [], "research_tasks": []}
        entity_ids = session.scalars(
            select(DatasetRecordEntity.entity_id)
            .join(DatasetRecord, DatasetRecordEntity.dataset_record_id == DatasetRecord.id)
            .where(DatasetRecord.dataset_id == dataset.id)
        ).all()
        entity_ids = sorted(set(entity_ids))
        created_tasks = completed_tasks = 0
        coverage_rows: list[dict[str, Any]] = []
        pending_created = 0
        for entity_id in entity_ids:
            entity = session.get(Entity, entity_id)
            if entity is None:
                continue
            for field_name in fields:
                facts = session.scalars(select(Fact).where(Fact.entity_id == entity.id, Fact.predicate == field_name)).all()
                evidence_count = session.scalar(select(func.count()).select_from(FactEvidence).where(FactEvidence.fact_id.in_([fact.id for fact in facts]))) if facts else 0
                status = "missing" if not facts else ("conflicting" if any(fact.status == "conflict" for fact in facts) else "supported")
                row = session.scalar(select(CoverageState).where(CoverageState.dataset_id == dataset.id, CoverageState.entity_id == entity.id, CoverageState.field_name == field_name))
                if row is None:
                    row = CoverageState(dataset_id=dataset.id, entity_id=entity.id, field_name=field_name, status=status, evidence_count=int(evidence_count or 0), details_json={})
                    session.add(row)
                else:
                    row.status, row.evidence_count = status, int(evidence_count or 0)
                coverage_rows.append({"entity_id": entity.id, "field_name": field_name, "status": status, "evidence_count": int(evidence_count or 0)})
                task_type = "fill_missing_field" if status == "missing" else "resolve_conflict" if status == "conflicting" else ""
                task = session.scalar(select(ResearchTask).where(ResearchTask.dataset_id == dataset.id, ResearchTask.entity_id == entity.id, ResearchTask.field_name == field_name, ResearchTask.task_type.in_(["fill_missing_field", "resolve_conflict"])))
                if status == "supported":
                    if task is not None and task.status != "completed":
                        task.status = "completed"
                        task.completed_at = datetime.now(timezone.utc)
                        completed_tasks += 1
                elif task_type and task is None and pending_created < max_tasks:
                    session.add(ResearchTask(dataset_id=dataset.id, entity_id=entity.id, field_name=field_name, task_type=task_type, priority=100 if task_type == "fill_missing_field" else 90, status="pending", query_context_json={"entity": entity.canonical_name, "field": field_name, "query": f"{entity.canonical_name} {field_name}"}))
                    pending_created += 1
                    created_tasks += 1
        session.commit()
        tasks = session.scalars(select(ResearchTask).where(ResearchTask.dataset_id == dataset.id)).all()
        return {"coverage_metrics": {"enabled": True, "entities": len(entity_ids), "fields": len(coverage_rows), "missing_fields": sum(row["status"] == "missing" for row in coverage_rows), "conflicting_fields": sum(row["status"] == "conflicting" for row in coverage_rows), "supported_fields": sum(row["status"] == "supported" for row in coverage_rows), "tasks_created": created_tasks, "tasks_completed": completed_tasks, "information_gain": completed_tasks}, "coverage_states": coverage_rows, "research_tasks": [{"id": task.id, "entity_id": task.entity_id, "field_name": task.field_name, "task_type": task.task_type, "priority": task.priority, "status": task.status, "query_context": task.query_context_json} for task in tasks]}
