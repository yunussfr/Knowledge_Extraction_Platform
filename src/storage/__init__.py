"""Persistent storage boundary for evidence-backed pipeline artifacts."""

from src.storage.database import Base, create_session_factory, initialize_database

__all__ = ["Base", "create_session_factory", "initialize_database"]
