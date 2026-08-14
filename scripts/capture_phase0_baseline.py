"""Run the existing mock pipeline and emit reproducible Phase 0 metrics."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.config_loader import load_domain_config
from src.core.settings import settings
from src.state.state import create_initial_state


def _unique_domains(sources: list[dict[str, Any]]) -> int:
    return len({
        source.get("domain") or urlparse(source.get("url", "")).netloc
        for source in sources
        if source.get("domain") or source.get("url")
    })


def capture_baseline(domain: str) -> dict[str, Any]:
    """Run through approval in mock mode without writing into user dataset paths."""
    original_provider = settings.data_source_provider
    started = perf_counter()
    try:
        object.__setattr__(settings, "data_source_provider", "mock")
        with tempfile.TemporaryDirectory(prefix="knowledge-extraction-baseline-") as output_directory:
            config = load_domain_config(domain)
            config = {
                **config,
                "output": {
                    **config.get("output", {}),
                    "directory": output_directory,
                },
            }
            pending = build_phase2_pipeline().invoke(create_initial_state(domain, config))
            if pending.get("status") != "waiting_for_schema_approval":
                raise RuntimeError(
                    "Mock baseline did not reach schema approval: "
                    f"{pending.get('status')} {pending.get('errors', [])}"
                )
            final = build_phase2_pipeline().approve_schema(pending)
            output_path = final.get("validation_report", {}).get("output_path", "")
            output_exists = bool(output_path and Path(output_path).is_file())
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    candidates = final.get("candidate_sources", [])
    source_registry = final.get("source_registry", {})
    selected = final.get("selected_sources", [])
    return {
        "domain": domain,
        "provider": "mock",
        "status": final.get("status"),
        "queries": len(final.get("research_plan", {}).get("search_queries", [])),
        "candidate_urls": len(source_registry) if source_registry else len(candidates),
        "selected_urls": len(selected),
        "unique_domains": _unique_domains(candidates),
        "scraped_sources": len(final.get("scraped_documents", [])),
        "chunks": len(final.get("document_chunks", [])),
        "extraction_results": len(final.get("extraction_results", [])),
        "accepted_records": len(final.get("accepted_records", [])),
        "rejected_records": len(final.get("rejected_records", [])),
        "errors": len(final.get("errors", [])),
        "runtime_seconds": round(perf_counter() - started, 6),
        "model_calls": 0,
        "output_created_in_temporary_directory": output_exists,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="turkish_culture")
    args = parser.parse_args()
    print(json.dumps(capture_baseline(args.domain), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
