"""Opt-in live-provider smoke test; excluded from normal unit-test runs."""

import pytest

from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.config_loader import load_domain_config
from src.core.settings import settings
from src.state.state import create_initial_state


pytestmark = pytest.mark.skipif(
    not settings.run_integration_tests,
    reason="Set RUN_INTEGRATION_TESTS=true to run live Firecrawl and Groq integration tests.",
)


def test_live_pipeline_reaches_schema_approval_checkpoint():
    """Verify live planning, search, evaluation, and schema design without scraping."""
    if settings.data_source_provider != "firecrawl":
        pytest.skip("DATA_SOURCE_PROVIDER must be firecrawl for the live integration test.")
    if not settings.firecrawl_api_key or not settings.groq_api_key:
        pytest.skip("Both FIRECRAWL_API_KEY and GROQ_API_KEY are required for the live integration test.")

    config = load_domain_config("turkish_culture")
    state = create_initial_state("turkish_culture", config)
    result = build_phase2_pipeline().invoke(state)

    assert result["status"] == "waiting_for_schema_approval", result.get("errors")
    assert result["selected_sources"]
    assert result["draft_dataset_schema"]
