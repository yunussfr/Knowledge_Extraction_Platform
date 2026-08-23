import json

import pytest

from src.agents.nodes.structured_extraction_node import structured_extraction_node
from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.checkpoint import load_checkpoint, write_checkpoint
from src.core.settings import settings
from src.schemas.models import ExtractionBatch


def test_checkpoint_is_atomic_json_and_resumes_at_next_stage(tmp_path):
    state = {
        "domain": "reliability",
        "dataset_name": "checkpoint_dataset",
        "config": {"output": {"directory": str(tmp_path)}},
        "status": "processing",
        "pipeline_status": "processing",
        "errors": [],
        "checkpoint_history": [],
    }

    update = write_checkpoint(state, "acquisition")
    loaded = load_checkpoint(state)

    path = tmp_path / "checkpoint_dataset_checkpoint.json"
    assert update["checkpoint_stage"] == "acquisition"
    assert path.is_file()
    assert not (tmp_path / "checkpoint_dataset_checkpoint.json.tmp").exists()
    assert loaded["resume_from"] == "processing"
    assert json.loads(path.read_text(encoding="utf-8"))["checkpoint_stage"] == "acquisition"


def test_terminal_checkpoint_cannot_be_resumed(tmp_path):
    state = {
        "domain": "reliability",
        "dataset_name": "done",
        "config": {"output": {"directory": str(tmp_path)}},
        "status": "completed",
        "pipeline_status": "completed",
        "errors": [],
        "checkpoint_history": [],
    }
    write_checkpoint(state, "export")
    path = tmp_path / "done_checkpoint.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "completed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="terminal"):
        load_checkpoint(state)


def test_pipeline_loader_uses_stage_checkpoint_for_custom_output_directory(tmp_path):
    state = {
        "domain": "checkpoint-loader",
        "dataset_name": "custom_dataset",
        "config": {"output": {"directory": str(tmp_path)}},
        "status": "processing",
        "pipeline_status": "processing",
        "errors": [],
        "checkpoint_history": [],
    }
    write_checkpoint(state, "acquisition")

    resumed = build_phase2_pipeline().load_pending_review_state(
        "checkpoint-loader", "custom_dataset", config=state["config"]
    )

    assert resumed["resume_from"] == "processing"


def test_structured_extraction_retries_one_transient_chunk_failure(monkeypatch):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")

    class FlakyProvider:
        provider_name = "flaky"

        def __init__(self):
            self.calls = 0

        def generate(self, **_):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary provider timeout")
            return ExtractionBatch(records=[])

    provider = FlakyProvider()
    monkeypatch.setattr(
        "src.agents.nodes.structured_extraction_node.get_structured_generation_provider",
        lambda: provider,
    )
    state = {
        "approved_dataset_schema": {
            "name": "retry",
            "description": "retry",
            "fields": [{
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "name",
                "extraction_instruction": "name",
            }],
            "identity_fields": ["item_name"],
            "schema_version": 1,
            "approved_at": "2026-08-22T00:00:00+00:00",
        },
        "document_chunks": [{
            "chunk_id": "retry-chunk",
            "source_url": "https://fixture.test/retry",
            "chunk_index": 0,
            "total_chunks": 1,
            "content": "Retryable source content.",
            "token_count": 3,
        }],
        "extraction_routes": [{
            "source_url": "https://fixture.test/retry",
            "method": "semantic",
            "model_call_required": True,
        }],
        "deterministic_extraction_batches": [],
        "errors": [],
        "extraction_warnings": [],
    }

    try:
        result = structured_extraction_node(state)
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert provider.calls == 2
    assert result["status"] == "extracting_data"
    assert result["errors"] == []
