from pathlib import Path

from src.agents.nodes.manifest_node import manifest_node


def test_manifest_contains_diagnosable_phase22_metrics(tmp_path):
    state = {
        "domain": "metrics",
        "dataset_name": "metrics_dataset",
        "config": {"output": {"directory": str(tmp_path)}},
        "research_plan": {"search_queries": ["one", "two"]},
        "source_policy": {
            "preferred_source_types": ["academic"],
            "desired_content": ["technical_explanation"],
        },
        "candidate_sources": [
            {
                "domain": "example.test",
                "origin_history": [{"method": "search"}, {"method": "seed"}],
            },
            {"domain": "other.test", "origin_history": [{"method": "search"}]},
        ],
        "source_previews": [{"fetch_success": True}, {"fetch_success": False}],
        "source_evaluations": [{
            "source_profile": {
                "source_type": "academic",
                "content_characteristics": ["technical_explanation"],
            },
            "policy_alignment_score": 0.8,
            "hard_policy_rejected": False,
        }],
        "source_selections": [{"source_type": "academic"}],
        "selected_sources": [{"domain": "example.test"}],
        "document_chunks": [{"token_count": 12}],
        "processed_data": [{"word_count": 8}],
        "extraction_routes": [{"model_call_required": False}],
        "extraction_batches": [{"records": [{"data": {}}]}],
        "validated_data": [{}],
        "accepted_records": [{}],
        "rejected_records": [],
        "status": "completed",
        "pipeline_status": "completed",
        "output_profiles": ["structured"],
        "output_paths": {},
        "errors": [],
    }

    result = manifest_node(state)

    assert result["status"] == "completed"
    assert result["run_metrics"]["sources"]["queries_generated"] == 2
    assert result["run_metrics"]["sources"]["raw_search_results"] == 3
    assert result["run_metrics"]["acquisition"]["total_content_tokens"] == 12
    assert result["run_metrics"]["extraction_validation"]["records_extracted"] == 1
    assert result["run_metrics"]["cost_performance"]["model_calls"] == 0
    assert result["run_metrics"]["cost_performance"]["average_preview_size_words"] == 0.0
    manifest_path = Path(result["manifest_path"])
    assert manifest_path.is_file()
