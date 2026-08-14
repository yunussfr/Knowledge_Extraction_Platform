"""Run the deterministic Phase 21 output-profile benchmark."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from src.agents.nodes.export_node import export_node


SOURCE_URL = "https://fixtures.example/output/benchmark"
CHUNK_ID = "profile_benchmark_chunk"


def _state(output_directory: str) -> dict[str, Any]:
    evidence = lambda text: {
        "source_url": SOURCE_URL,
        "chunk_id": CHUNK_ID,
        "evidence_text": text,
    }
    return {
        "domain": "profiles",
        "dataset_name": "phase21_profiles",
        "approved_dataset_schema": {
            "name": "phase21_profiles",
            "description": "Frozen output profile schema.",
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
            ],
            "identity_fields": ["item_name"],
            "schema_version": 1,
            "approved_at": "2026-08-14T00:00:00+00:00",
            "approved_by": "benchmark",
        },
        "accepted_records": [{
            "data": {
                "item_name": "Atlas Retriever",
                "description": "fault-tolerant retrieval service",
            },
            "relations": [{"target_entity": "Retriever"}],
            "_metadata": {
                "source_url": SOURCE_URL,
                "source_urls": [SOURCE_URL],
                "source_title": "Atlas source",
                "source_content_hashes": {SOURCE_URL: "atlas-content-hash"},
                "contributing_chunk_ids": [CHUNK_ID],
                "contributing_record_ids": ["atlas"],
                "contributors": [{
                    "source_url": SOURCE_URL,
                    "local_record_id": "atlas",
                    "chunk_id": CHUNK_ID,
                    "extraction_method": "semantic",
                }],
                "field_evidence": {
                    "item_name": [evidence("Atlas Retriever")],
                    "description": [evidence("fault-tolerant retrieval service")],
                },
                "evidence_quality_score": 0.9,
                "evidence_support_statuses": ["SUPPORTED"],
                "resolution_method": "explicit_identity",
                "resolution_key": "atlas",
            },
        }],
        "document_chunks": [{
            "chunk_id": CHUNK_ID,
            "source_url": SOURCE_URL,
            "source_title": "Atlas source",
            "chunk_index": 0,
            "total_chunks": 1,
            "heading": "Retriever",
            "content": "Atlas Retriever is a fault-tolerant retrieval service.",
            "token_count": 7,
        }],
        "config": {"output": {
            "directory": output_directory,
            "format": "json",
            "profiles": ["structured", "rag", "graphrag"],
        }},
        "validation_report": {},
        "errors": [],
    }


def run_output_profile_benchmark() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        state = _state(directory)
        result = export_node(state)
        paths = {profile: Path(path) for profile, path in result["output_paths"].items()}
        payloads = {
            profile: json.loads(path.read_text(encoding="utf-8"))
            for profile, path in paths.items()
        }
    structured = payloads["structured"][0]
    rag = payloads["rag"][0]
    graphrag = payloads["graphrag"][0]
    return {
        "benchmark_version": "1.0",
        "contract": "phase21_ai_output_profiles",
        "profiles": result["output_profiles"],
        "filenames": {
            profile: path.name for profile, path in paths.items()
        },
        "record_counts": {
            profile: len(records) for profile, records in payloads.items()
        },
        "top_level_fields": {
            "structured": sorted(structured),
            "rag": sorted(rag),
            "graphrag": sorted(graphrag),
        },
        "intentional_difference": (
            "data" in structured and "text" in rag and "data" not in rag
        ),
        "graphrag": {
            "entities": len(graphrag["entities"]),
            "claims": len(graphrag["claims"]),
            "relations": len(graphrag["relations"]),
            "claims_with_evidence": sum(
                bool(claim["evidence"]) for claim in graphrag["claims"]
            ),
        },
    }


def main() -> None:
    print(json.dumps(run_output_profile_benchmark(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
