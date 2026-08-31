"""Persistent knowledge objects kept separate from consumer dataset records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.database import Base
from src.storage.models.entities import now_utc

JSON_PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(128), default="record_identity")
    canonical_name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text)
    attributes_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    __table_args__ = (UniqueConstraint("entity_type", "normalized_name", name="uq_entity_type_normalized_name"),)


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(255))
    value_json: Mapped[object] = mapped_column(JSON_PAYLOAD)
    value_hash: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="asserted")
    __table_args__ = (UniqueConstraint("entity_id", "predicate", "value_hash", name="uq_fact_value"),)


class Relation(Base):
    __tablename__ = "relations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(128))
    target_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    attributes_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("source_entity_id", "relation_type", "target_entity_id", name="uq_relation_identity"),)


class FactEvidence(Base):
    __tablename__ = "fact_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    chunk_id: Mapped[str] = mapped_column(String(255), default="")
    evidence_text: Mapped[str] = mapped_column(Text)


class DatasetRecordEntity(Base):
    __tablename__ = "dataset_record_entities"
    dataset_record_id: Mapped[int] = mapped_column(ForeignKey("dataset_records.id"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), primary_key=True)
