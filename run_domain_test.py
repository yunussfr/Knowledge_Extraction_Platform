"""Terminal entry point for the dataset-generation pipeline."""

import argparse
import json
import sys
from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
from src.core.config_loader import load_domain_config
from src.state.state import create_initial_state
from src.observability.events import emit


def _prompt_for_schema_approval(pipeline, state, review_path):
    print("\nDraft dataset schema created.")
    print(f"Review file: {review_path}")
    print(json.dumps(state["draft_dataset_schema"], ensure_ascii=False, indent=2))
    print("Edit this JSON file if needed, then choose an option below.")
    while True:
        print("\n1 - Approve the current draft")
        print("2 - Reload the edited schema file and approve it")
        print("3 - Cancel the run")
        choice = input("Selection: ").strip()
        if choice == "3":
            return pipeline.cancel(state)
        try:
            if choice == "1":
                return pipeline.approve_schema(state)
            if choice == "2":
                edited_schema = json.loads(review_path.read_text(encoding="utf-8"))
                return pipeline.approve_schema(state, edited_schema)
            print("Invalid selection. Choose 1, 2, or 3.")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"Schema validation failed: {error}")
            print("Edit the review file and try again.")


def run_domain_extraction(domain: str, approve_schema: bool = False, resume: bool = False):
    """Load one domain request, pause for approval, and complete the same graph."""
    print(f"--- Starting dataset pipeline for domain: {domain} ---")
    pipeline = build_phase2_pipeline()
    config = load_domain_config(domain)
    state = create_initial_state(domain=domain, config=config)
    if state["dataset_name"]:
        print(f"Dataset name: {state['dataset_name']}")
    if resume:
        final_state = pipeline.load_pending_review_state(
            domain, state["dataset_name"], config=config
        )
        print("Resumed saved pipeline state without repeating completed stages.")
        if final_state.get("resume_from"):
            final_state = pipeline.invoke(final_state)
    else:
        final_state = pipeline.invoke(state)

    if final_state["status"] == "waiting_for_schema_approval":
        emit("run_status", status="waiting_for_schema_approval", topic=final_state.get("dataset_topic", domain),
             message="Şema onayı bekleniyor; terminalden yanıt verin")
        review_path = pipeline.review_schema_path(final_state)
        if not resume:
            review_path = pipeline.write_draft_review_file(final_state)
        if approve_schema:
            final_state = pipeline.approve_schema(final_state)
        elif sys.stdin.isatty():
            final_state = _prompt_for_schema_approval(pipeline, final_state, review_path)
        else:
            print(f"Pipeline is waiting for schema approval. Review: {review_path}")
            print(f"Resume later with: python run_domain_test.py --domain {domain} --resume")
            return final_state

    if final_state["status"] == "completed":
        print(f"SUCCESS: {domain} pipeline completed. Errors: {len(final_state['errors'])}")
        output_path = final_state.get("validation_report", {}).get("output_path")
        if output_path:
            print(f"Dataset generated at {output_path}")
        accepted = len(final_state.get("accepted_records", []))
        rejected = len(final_state.get("rejected_records", []))
        print(f"Accepted records: {accepted}; rejected or review records: {rejected}")
        if not accepted and final_state.get("approved_dataset_schema"):
            print("No records were exported. In mock mode this is expected when the approved schema requires fields that mock content cannot support.")
        if final_state["errors"]:
            print("Recorded pipeline errors:")
            print(json.dumps(final_state["errors"], ensure_ascii=False, indent=2))
    else:
        print(f"Pipeline stopped with status: {final_state['status']}")
        if final_state["errors"]:
            print(json.dumps(final_state["errors"], ensure_ascii=False, indent=2))
    emit("run_status", status=final_state["status"])
    return final_state


def _wait_for_watch_close():
    from threading import Event
    stopped = Event()
    print("Live panel remains available for inspection. Press Ctrl+C to close it.", flush=True)
    try:
        while not stopped.wait(1):
            pass
    except KeyboardInterrupt:
        pass


def run_watched_domain(domain, *, approve_schema=False, resume=False):
    """Keep terminal input on the main thread and serve the panel independently."""
    import webbrowser
    from src.core.settings import settings
    from src.observability.events import EventJournal, observe
    from src.observability.web_server import WatchServer

    journal = EventJournal(secrets=(settings.groq_api_key, settings.firecrawl_api_key))
    with WatchServer(journal) as server, observe(journal):
        print(f"Live pipeline panel: {server.address}", flush=True)
        try:
            webbrowser.open(server.address)
        except Exception:
            pass  # The printed URL is usable even without a default browser.
        try:
            result = run_domain_extraction(domain, approve_schema=approve_schema, resume=resume)
        except KeyboardInterrupt:
            emit("run_status", status="cancelled", message="Terminalden durduruldu")
            return None
        except Exception as error:
            emit("run_status", status="error", details={"error": str(error)})
            print(f"Pipeline failed: {type(error).__name__}. Inspect the panel for details.", flush=True)
            _wait_for_watch_close()
            raise
        _wait_for_watch_close()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a domain dataset-generation pipeline.")
    parser.add_argument("--domain", default="turkish_culture", help="Directory name under configs/domains")
    parser.add_argument("--approve-schema", action="store_true", help="Approve the generated draft without interactive review")
    parser.add_argument("--resume", action="store_true", help="Resume a saved pipeline waiting for schema approval")
    parser.add_argument("--watch-web", action="store_true", help="Open a local live panel; keep it available until Ctrl+C")
    args = parser.parse_args()
    runner = run_watched_domain if args.watch_web else run_domain_extraction
    runner(args.domain, approve_schema=args.approve_schema, resume=args.resume)


if __name__ == "__main__":
    main()
