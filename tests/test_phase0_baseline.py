"""Phase 0 reproducibility tests for the existing mock baseline."""

from scripts.capture_phase0_baseline import capture_baseline


def test_mock_baseline_is_reproducible_without_user_dataset_writes():
    metrics = capture_baseline("turkish_culture")

    assert metrics == {
        "domain": "turkish_culture",
        "provider": "mock",
        "status": "completed",
        "queries": 1,
        "candidate_urls": 1,
        "selected_urls": 1,
        "unique_domains": 1,
        "scraped_sources": 1,
        "chunks": 1,
        "extraction_results": 1,
        "accepted_records": 1,
        "rejected_records": 0,
        "errors": 0,
        "runtime_seconds": metrics["runtime_seconds"],
        "model_calls": 0,
        "output_created_in_temporary_directory": True,
    }
    assert metrics["runtime_seconds"] >= 0
