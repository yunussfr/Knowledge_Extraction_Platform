"""Atomic, JSON-only pipeline checkpoints for resumable runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


RESUME_TARGETS = {
    "sources": "dataset_schema_designer",
    "acquisition": "processing",
    "processing": "chunking",
    "chunking": "extraction_router",
    "extraction": "field_evidence",
    "validation": "deduplication",
    "export": "manifest",
}


def checkpoint_path(state: Dict[str, Any]) -> Path:
    output = state.get("config", {}).get("output", {})
    directory = Path(output.get("directory", "./knowledge/datasets"))
    dataset_name = state.get("dataset_name") or state.get("domain", "run")
    return directory / f"{dataset_name}_checkpoint.json"


def write_checkpoint(state: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """Persist a complete JSON-safe state atomically after a completed stage."""
    path = checkpoint_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **state,
        "checkpoint_stage": stage,
        "checkpoint_path": str(path),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return {
        "checkpoint_stage": stage,
        "checkpoint_path": str(path),
        "checkpoint_history": [
            *state.get("checkpoint_history", []),
            {"stage": stage, "path": str(path)},
        ],
    }


def load_checkpoint(state: Dict[str, Any]) -> Dict[str, Any]:
    path = checkpoint_path(state)
    if not path.is_file():
        raise FileNotFoundError(f"No resumable pipeline checkpoint exists at {path}.")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    stage = loaded.get("checkpoint_stage")
    target = RESUME_TARGETS.get(stage)
    if target is None:
        raise ValueError(f"Checkpoint stage cannot be resumed: {stage!r}.")
    if loaded.get("status") in {"completed", "cancelled"}:
        raise ValueError("The saved pipeline checkpoint is already terminal.")
    loaded["resume_from"] = target
    loaded["checkpoint_path"] = str(path)
    return loaded
