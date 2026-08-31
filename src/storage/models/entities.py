"""SQLAlchemy tables; JSON payloads preserve the richer typed pipeline data."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.database import Base


JSON_PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    topic: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    schema_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(128), default="")
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id"), index=True)
    raw_markdown: Mapped[str] = mapped_column(Text, default="")
    processed_markdown: Mapped[str] = mapped_column(Text, default="")
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(32), default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    retrieved_at: Mapped[str] = mapped_column(String(64), default="")


class Chunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(128), default="")


class DatasetRecord(Base):
    __tablename__ = "dataset_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id"), index=True)
    local_record_id: Mapped[str] = mapped_column(String(255), index=True)
    identity_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    data_json: Mapped[dict] = mapped_column(JSON_PAYLOAD, default=dict)
    completeness_score: Mapped[float] = mapped_column(default=0.0)
    quality_score: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(64), default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Evidence(Base):
    __tablename__ = "field_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("dataset_records.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    chunk_id: Mapped[str] = mapped_column(String(255), default="")
    evidence_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
