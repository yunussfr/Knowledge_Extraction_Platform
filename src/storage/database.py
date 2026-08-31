"""SQLAlchemy engine and session lifecycle kept outside LangGraph state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base for persistence models; Pydantic models remain the pipeline contract."""


def database_url(config: dict[str, Any] | None = None) -> str:
    storage = (config or {}).get("storage", {})
    if isinstance(storage, dict) and storage.get("database_url"):
        return str(storage["database_url"])
    return os.getenv("DATABASE_URL", "sqlite:///knowledge/knowledge.db")


def create_session_factory(config: dict[str, Any] | None = None) -> sessionmaker[Session]:
    url = database_url(config)
    if url.startswith("sqlite:///"):
        sqlite_path = url.removeprefix("sqlite:///")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database(config: dict[str, Any] | None = None) -> None:
    """Create tables for local bootstrap/tests; production uses Alembic migrations."""
    from src.storage.models import (  # noqa: F401
        Chunk,
        Dataset,
        DatasetRecord,
        Document,
        Evidence,
        ResearchRun,
        Source,
    )
    from src.storage.models.knowledge import (  # noqa: F401
        DatasetRecordEntity,
        Entity,
        Fact,
        FactEvidence,
        Relation,
    )
    from src.storage.models.coverage import CoverageState, ResearchTask  # noqa: F401

    factory = create_session_factory(config)
    Base.metadata.create_all(factory.kw["bind"])
