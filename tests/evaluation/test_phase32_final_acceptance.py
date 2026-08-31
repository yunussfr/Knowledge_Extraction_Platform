from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.settings import settings
from src.state.state import create_initial_state


def test_final_mock_flow_reaches_knowledge_coverage_and_export(tmp_path):
    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    try:
        config = {
            "dataset": {"name": "phase32_final", "topic": "Coffee", "purpose": "Acceptance"},
            "research": {"queries": ["coffee"], "max_sources": 2},
            "mock_sources": [{"url": "https://fixture.example/coffee", "title": "Coffee", "enabled": True}],
            "storage": {"enabled": True, "database_url": f"sqlite:///{tmp_path / 'phase32.db'}"},
            "research_loop": {"enabled": True, "max_rounds": 2, "max_tasks_per_round": 5},
            "output": {"format": "json", "directory": str(tmp_path / "output")},
        }
        pipeline = build_phase2_pipeline()
        pending = pipeline.invoke(create_initial_state("phase32", config))
        assert pending["status"] == "waiting_for_schema_approval"
        completed = pipeline.approve_schema(pending)
        assert completed["status"] == "completed"
        assert completed["storage_metrics"]["enabled"] is True
        assert completed["coverage_metrics"]["enabled"] is True
        assert completed["coverage_metrics"]["entities"] >= 1
        assert (tmp_path / "output" / "phase32_final.json").is_file()
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)
