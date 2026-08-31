"""Persistent coverage and bounded enrichment task state."""

from __future__ import annotations

from src.storage.models.entities import JSON_PAYLOAD, now_utc
from src.storage.database import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CoverageState(Base):
    __tablename__ = "coverage_states"
    __table_args__ = (UniqueConstraint("dataset_id", "entity_id", "field_name", name="uq_coverage_dataset_entity_field"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (UniqueConstraint("dataset_id", "entity_id", "field_name", "task_type", name="uq_research_task_target"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    query_context_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
