"""Build the diagnosable, serializable run manifest."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from src.core.settings import settings
from src.state.state import AgentState


def _domain(value: Any) -> str:
    return str(value or "").lower().removeprefix("www.")


def _source_policy_metrics(state: AgentState) -> dict[str, Any]:
    evaluations = state.get("source_evaluations", [])
    profiles = [item.get("source_profile") or {} for item in evaluations]
    scores = [
        float(item.get("policy_alignment_score", 0.0))
        for item in evaluations
        if item.get("policy_alignment_score") is not None
    ]
    selected = state.get("source_selections", [])
    selected_types = Counter(
        str(item.get("source_type", "unknown"))
        for item in selected
    )
    desired = set(str(item).casefold() for item in (state.get("source_policy", {}) or {}).get("desired_content", []))
    matched_desired = sum(
        bool(desired & {str(label).casefold() for label in profile.get("content_characteristics", [])})
        for profile in profiles
    )
    return {
        "source_types_observed": dict(sorted(Counter(str(profile.get("source_type", "unknown")) for profile in profiles).items())),
        "content_characteristics_observed": dict(sorted(Counter(
            str(label)
            for profile in profiles
            for label in profile.get("content_characteristics", [])
        ).items())),
        "policy_alignment_score_distribution": {
            "count": len(scores),
            "minimum": min(scores) if scores else 0.0,
            "maximum": max(scores) if scores else 0.0,
            "average": sum(scores) / len(scores) if scores else 0.0,
        },
        "hard_policy_rejections": sum(bool(item.get("hard_policy_rejected")) for item in evaluations),
        "preferred_type_selection_rate": (
            sum(str(item.get("source_type", "")).casefold() in {
                str(value).casefold() for value in (state.get("source_policy", {}) or {}).get("preferred_source_types", [])
            } for item in selected) / len(selected)
            if selected else 0.0
        ),
        "desired_content_match_rate": matched_desired / len(profiles) if profiles else 0.0,
        "selected_sources_by_type": dict(sorted(selected_types.items())),
    }


def _source_metrics(state: AgentState) -> dict[str, Any]:
    candidates = state.get("candidate_sources", [])
    previews = state.get("source_previews", [])
    selected = state.get("selected_sources", [])
    return {
        "queries_generated": len(state.get("research_plan", {}).get("search_queries", [])),
        "raw_search_results": sum(
            len(item.get("origin_history", [])) for item in candidates
        ),
        "unique_candidates": len(candidates),
        "unique_candidate_domains": len({_domain(item.get("domain")) for item in candidates if item.get("domain")}),
        "preview_successes": sum(bool(item.get("fetch_success")) for item in previews),
        "preview_failures": sum(not bool(item.get("fetch_success")) for item in previews),
        "selected_sources": len(selected),
        "unique_selected_domains": len({_domain(item.get("domain")) for item in selected if item.get("domain")}),
        "site_exploration_pages": len(state.get("site_exploration_results", [])),
    }


def _extraction_metrics(state: AgentState) -> dict[str, Any]:
    routes = state.get("extraction_routes", [])
    batches = state.get("extraction_batches", [])
    records_per_chunk = [
        len(batch.get("records", [])) for batch in batches
    ]
    evidence = state.get("evidence_validation_metrics", {})
    quality = state.get("quality_gate_metrics", {})
    dedup = state.get("deduplication_metrics", {})
    stage_counts = dedup.get("stage_counts", {})
    return {
        "deterministic_extractions": sum(not bool(route.get("model_call_required")) for route in routes),
        "semantic_extractions": sum(bool(route.get("model_call_required")) for route in routes),
        "records_extracted": sum(records_per_chunk),
        "records_per_chunk": records_per_chunk,
        "schema_valid_records": len(state.get("validated_data", [])),
        "supported_fields": evidence.get("supported_fields", evidence.get("evidenced_fields", 0)),
        "unsupported_fields": evidence.get("unsupported_fields", 0),
        "accepted_records": quality.get("accepted_records", len(state.get("accepted_records", []))),
        "rejected_records": quality.get("rejected_records", len(state.get("rejected_records", []))),
        "duplicate_records": dedup.get("duplicates_removed", sum(stage_counts.values()) if stage_counts else 0),
    }


def _cost_metrics(state: AgentState) -> dict[str, Any]:
    routes = state.get("extraction_routes", [])
    semantic_routes = [route for route in routes if route.get("model_call_required")]
    chunks_by_id = {
        chunk.get("chunk_id"): int(chunk.get("token_count", 0) or 0)
        for chunk in state.get("document_chunks", [])
    }
    semantic_chunk_ids = {
        chunk_id
        for route in semantic_routes
        for chunk_id in route.get("chunk_ids", [])
    }
    input_tokens = sum(chunks_by_id.get(chunk_id, 0) for chunk_id in semantic_chunk_ids)
    accepted = len(state.get("accepted_records", []))
    previews = state.get("source_previews", [])
    preview_sizes = [
        len(str(item.get("relevant_text", "")).split())
        for item in previews
        if item.get("relevant_text")
    ]
    model = dict(state.get("model_metrics", {}))
    model_calls = int(model.get("model_calls", len(semantic_routes)))
    input_tokens = int(model.get("input_tokens", input_tokens))
    estimated_cost = float(model.get("estimated_cost", 0.0))
    return {
        "model_calls": model_calls,
        "input_tokens": input_tokens,
        "output_tokens": int(model.get("output_tokens", 0)),
        "latency_seconds": float(model.get("latency_seconds", 0.0)),
        "estimated_cost": estimated_cost,
        "average_preview_size_words": sum(preview_sizes) / len(preview_sizes) if preview_sizes else 0.0,
        "average_extraction_input_tokens": input_tokens / model_calls if model_calls else 0.0,
        "llm_calls_per_source": model_calls / len(state.get("selected_sources", [])) if state.get("selected_sources") else 0.0,
        "accepted_records_per_llm_call": accepted / model_calls if model_calls else 0.0,
        "cost_per_accepted_record": estimated_cost / accepted if accepted else 0.0,
    }


def build_run_metrics(state: AgentState) -> dict[str, Any]:
    acquisition = dict(state.get("acquisition_metrics", {}))
    chunks = state.get("document_chunks", [])
    processed = state.get("processed_data", [])
    acquisition.setdefault("requested_urls", len(state.get("selected_sources", [])))
    acquisition.setdefault("successful_urls", len(processed))
    acquisition.setdefault("failed_urls", max(0, acquisition["requested_urls"] - acquisition["successful_urls"]))
    acquisition.setdefault("cache_hits", 0)
    acquisition["total_words"] = sum(int(item.get("word_count", 0) or item.get("metadata", {}).get("word_count", 0) or 0) for item in processed)
    acquisition["total_content_tokens"] = sum(int(item.get("token_count", 0)) for item in chunks)
    return {
        "source_policy": _source_policy_metrics(state),
        "sources": _source_metrics(state),
        "acquisition": acquisition,
        "extraction_validation": _extraction_metrics(state),
        "cost_performance": _cost_metrics(state),
        "storage": dict(state.get("storage_metrics", {})),
    }


def manifest_node(state: AgentState) -> Dict[str, Any]:
    try:
        metrics = build_run_metrics(state)
        manifest = {
            "manifest_version": "1.0",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": state.get("status", "unknown"),
            "pipeline_status": state.get("pipeline_status", "unknown"),
            "domain": state.get("domain", ""),
            "dataset_name": state.get("dataset_name", ""),
            "output_profiles": state.get("output_profiles", []),
            "output_paths": state.get("output_paths", {}),
            "errors": state.get("errors", []),
            "metrics": metrics,
        }
        output_config = state.get("config", {}).get("output", {})
        output_dir = Path(output_config.get("directory", settings.output_directory))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{state.get('dataset_name') or state.get('domain', 'run')}_manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "run_metrics": metrics,
            "run_manifest": manifest,
            "manifest_path": str(path),
            "status": "completed" if state.get("status") != "failed" else "failed",
            "pipeline_status": "completed" if state.get("pipeline_status") != "failed" else "failed",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "manifest", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
