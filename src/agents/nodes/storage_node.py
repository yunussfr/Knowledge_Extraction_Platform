"""Persist completed pipeline artifacts through the storage repository boundary."""

from __future__ import annotations

import os
from typing import Any, Dict

from src.storage.repositories import persist_pipeline_state


def storage_node(state: Dict[str, Any]) -> Dict[str, Any]:
    config = state.get("config", {})
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    enabled = isinstance(storage, dict) and storage.get("enabled", False)
    enabled = bool(enabled or os.getenv("STORAGE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"})
    if not enabled:
        return {"storage_metrics": {"enabled": False}, "status": state.get("status", "completed"), "pipeline_status": state.get("pipeline_status", "completed")}
    try:
        metrics = persist_pipeline_state(state)
        return {"storage_metrics": {"enabled": True, **metrics}, "status": state.get("status", "completed"), "pipeline_status": state.get("pipeline_status", "completed")}
    except Exception as error:
        return {
            "storage_metrics": {"enabled": True, "persisted": False},
            "errors": state.get("errors", []) + [{"node": "storage", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
