"""Phase 21 Structured, RAG, and evidence-only GraphRAG output tests."""

import json
from copy import deepcopy

from src.agents.nodes.export_node import export_node


SOURCE_URL = "https://fixtures.example/output/alpha"
CHUNK_ID = "output_chunk_001"


def _schema() -> dict:
    return {
        "name": "output_profiles",
        "description": "Output profile fixtures.",
        "fields": [
            {
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "Item name.",
                "extraction_instruction": "Extract item name.",
            },
            {
                "field_name": "description",
                "type": "string",
                "required": True,
                "description": "Description.",
                "extraction_instruction": "Extract description.",
            },
            {
                "field_name": "tags",
                "type": "array[string]",
                "required": False,
                "nullable": True,
                "description": "Tags.",
                "extraction_instruction": "Extract tags.",
            },
        ],
        "identity_fields": ["item_name"],
        "schema_version": 3,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _evidence(text: str) -> dict:
    return {
        "source_url": SOURCE_URL,
        "chunk_id": CHUNK_ID,
        "evidence_text": text,
    }


def _accepted_record() -> dict:
    return {
        "data": {
            "item_name": "Alpha Engine",
            "description": "compact inference runtime",
            "tags": ["runtime", "inference"],
        },
        "relations": [{"target_entity": "Runtime"}],
        "_metadata": {
            "source_url": SOURCE_URL,
            "source_urls": [SOURCE_URL],
            "source_title": "Alpha documentation",
            "source_titles": {SOURCE_URL: "Alpha documentation"},
            "source_content_hashes": {SOURCE_URL: "content-hash-alpha"},
            "contributing_chunk_ids": [CHUNK_ID],
            "contributing_record_ids": ["alpha-record"],
            "contributors": [{
                "source_url": SOURCE_URL,
                "local_record_id": "alpha-record",
                "chunk_id": CHUNK_ID,
                "extraction_method": "semantic",
            }],
            "field_evidence": {
                "item_name": [_evidence("Alpha Engine")],
                "description": [_evidence("compact inference runtime")],
                "tags": [_evidence("runtime and inference")],
            },
            "evidence_quality_score": 0.91,
            "evidence_support_statuses": ["SUPPORTED"],
            "quality_assessments": [],
            "validation_method": "evidence_quality_gate_and_schema",
            "language": "en",
            "resolution_method": "explicit_identity",
            "resolution_key": "alpha-engine",
            "merge_conflicts": [],
            "evidence_backed_relations": [
                {
                    "subject": "Alpha Engine",
                    "predicate": "is_a",
                    "object": "runtime",
                    "evidence": [_evidence("Alpha Engine")],
                },
                {
                    "subject": "Alpha Engine",
                    "predicate": "fabricated_relation",
                    "object": "unknown",
                    "evidence": [_evidence("fabricated evidence")],
                },
            ],
        },
    }


def _state(tmp_path, profiles=None, output_format="json") -> dict:
    output = {"directory": str(tmp_path), "format": output_format}
    if profiles is not None:
        output["profiles"] = profiles
    content = (
        "Alpha Engine is a compact inference runtime with runtime and inference tags."
    )
    return {
        "domain": "profiles",
        "dataset_name": "profile_records",
        "approved_dataset_schema": _schema(),
        "accepted_records": [_accepted_record()],
        "document_chunks": [{
            "chunk_id": CHUNK_ID,
            "source_url": SOURCE_URL,
            "source_title": "Alpha documentation",
            "chunk_index": 0,
            "total_chunks": 1,
            "heading": "Runtime Overview",
            "content": content,
            "token_count": len(content.split()),
            "source_metadata": {"content_hash": "content-hash-alpha"},
        }],
        "config": {"output": output},
        "validation_report": {},
        "errors": [],
    }


def test_profiles_are_intentionally_different_and_keep_required_evidence(tmp_path):
    state = _state(tmp_path, ["structured", "rag", "graphrag"])
    original_accepted = deepcopy(state["accepted_records"])

    result = export_node(state)

    assert result["status"] == "completed"
    assert result["output_profiles"] == ["structured", "rag", "graphrag"]
    structured = json.loads((tmp_path / "profile_records.json").read_text(encoding="utf-8"))[0]
    rag = json.loads((tmp_path / "profile_records_rag.json").read_text(encoding="utf-8"))[0]
    graphrag = json.loads((tmp_path / "profile_records_graphrag.json").read_text(encoding="utf-8"))[0]

    assert set(structured) == {
        "data", "evidence", "provenance", "quality", "schema", "_metadata"
    }
    assert structured["schema"]["identity_fields"] == ["item_name"]
    assert structured["evidence"]["item_name"][0]["evidence_text"] == "Alpha Engine"
    assert "data" not in rag
    assert rag["text"] == (
        "Item Name: Alpha Engine\n"
        "Description: compact inference runtime\n"
        'Tags: ["runtime", "inference"]'
    )
    assert rag["section_path"] == "Runtime Overview"
    assert rag["content_hash"] == "content-hash-alpha"
    assert rag["quality_score"] == 0.91
    assert graphrag["entities"][0]["name"] == "Alpha Engine"
    assert len(graphrag["claims"]) == 3
    assert graphrag["relations"] == [{
        "subject": "Alpha Engine",
        "predicate": "is_a",
        "object": "runtime",
        "evidence": [_evidence("Alpha Engine")],
    }]
    assert all(claim["evidence"] for claim in graphrag["claims"])
    assert state["accepted_records"] == original_accepted


def test_default_profile_preserves_existing_structured_filename(tmp_path):
    result = export_node(_state(tmp_path))

    assert result["output_profiles"] == ["structured"]
    assert (tmp_path / "profile_records.json").is_file()
    assert result["validation_report"]["output_path"].endswith(
        "profile_records.json"
    )


def test_multiple_jsonl_profiles_each_write_valid_records(tmp_path):
    result = export_node(_state(tmp_path, ["structured", "rag"], "jsonl"))

    assert result["status"] == "completed"
    structured = json.loads(
        (tmp_path / "profile_records.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    rag = json.loads(
        (tmp_path / "profile_records_rag.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert "data" in structured
    assert "text" in rag and "data" not in rag


def test_invalid_output_profile_fails_clearly(tmp_path):
    result = export_node(_state(tmp_path, ["vector_database"]))

    assert result["status"] == "failed"
    assert "Unsupported output profile" in result["errors"][-1]["error"]
