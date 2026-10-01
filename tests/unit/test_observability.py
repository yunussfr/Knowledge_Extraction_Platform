"""Offline acceptance for bounded live observation and unchanged business flow."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from src.observability.events import (
    EventJournal, emit, model_exchange, observe, observed_node, operation,
    publish_node_update,
)
from src.observability.web_server import WatchServer
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("STORAGE_ENABLED", "false")
    from src.core.settings import settings
    original = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "mock")
    yield
    object.__setattr__(settings, "data_source_provider", original)


def all_events(journal):
    return journal.snapshot(limit=10000)["events"]


def test_limits_eviction_replay_and_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    journal = EventJournal(max_events=3, max_detail_bytes=110, max_event_bytes=100)
    with observe(journal):
        for number in range(8):
            emit("sample", details={"content": "x" * 50, "number": number})
    snapshot = journal.snapshot()
    assert len(snapshot["events"]) == 3
    assert snapshot["gap"] and snapshot["first_sequence"] == 6
    assert snapshot["detail_bytes"] <= 110
    assert journal.detail(6)["available"] is False
    assert journal.detail(8)["available"] is True
    assert [e["sequence"] for e in journal.snapshot(7)["events"]] == [8]
    assert list(tmp_path.iterdir()) == []
    journal.close()
    assert journal.snapshot()["events"] == []
    assert journal.snapshot()["detail_bytes"] == 0
    assert not journal.detail(8)["available"]


def test_large_unicode_payload_is_bounded_and_explicitly_truncated():
    journal = EventJournal(max_event_bytes=1000, max_detail_bytes=2000)
    journal.publish("large", details={"text": "ğ" * 1000000})
    assert all_events(journal)[0]["details_truncated"]
    assert journal.snapshot()["detail_bytes"] <= 1000


def test_secrets_redacted_in_headers_nested_payloads_and_text(monkeypatch):
    monkeypatch.setenv("EXAMPLE_API_KEY", "environment-secret")
    journal = EventJournal(secrets=["settings-secret"])
    journal.publish("sample", message="settings-secret", source_url="https://user:pass@fixture.test/?token=private",
                    details={"authorization": "Bearer hidden", "nested": {"api_key": "abc"},
                             "text": 'environment-secret settings-secret Authorization: Bearer xyz password=hunter2'})
    dumped = json.dumps([journal.snapshot(), journal.detail(1)])
    for secret in ["environment-secret", "settings-secret", "hidden", "abc", "xyz", "hunter2", "private", "user:pass"]:
        assert secret not in dumped


def test_parallel_sequence_and_disabled_sink():
    assert emit("disabled", details=object()) is None
    journal = EventJournal(max_events=500)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: journal.publish("item", details=i), range(400)))
    assert [e["sequence"] for e in all_events(journal)] == list(range(1, 401))


def test_node_repeat_identity_failed_return_and_observation_failure():
    journal = EventJournal()
    node = observed_node("example", lambda state: {"status": "failed", "errors": ["failure"]})
    with observe(journal):
        for _ in range(2):
            result = node({})
            publish_node_update("example", result)
    events = all_events(journal)
    assert events[0]["operation_id"] == events[1]["operation_id"]
    assert events[2]["operation_id"] != events[0]["operation_id"]
    assert events[1]["status"] == events[3]["status"] == "error"
    journal.publish = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken observer"))
    with observe(journal):
        assert node({}) == result
        publish_node_update("example", result)


def test_model_exchange_correlates_exact_input_output_and_validation_error():
    journal = EventJournal()
    with observe(journal), operation(node="source_evaluator", batch_id="batch_1"):
        with model_exchange(model="fixture", provider="offline", request={"prompt": "exact evidence"}) as response:
            response["raw_response"] = '{"accepted":true}'
        with pytest.raises(ValueError), model_exchange(model="fixture", provider="offline", request={}):
            raise ValueError("invalid JSON")
    events = all_events(journal)
    assert events[0]["operation_id"] == events[1]["operation_id"]
    assert events[0]["batch_id"] == "batch_1"
    assert events[2]["operation_id"] != events[0]["operation_id"]
    assert events[3]["status"] == "error"
    assert journal.detail(1)["details"]["prompt"] == "exact evidence"
    assert journal.detail(4)["details"]["validation"] == "failed"


def fake_page(url):
    return SimpleNamespace(url=url, success=True, markdown="Evidence for " + url, metadata={}, links={})


def test_crawl_publishes_first_page_before_last_and_preserves_order():
    journal = EventJournal()
    first_done, release_last = Event(), Event()
    calls, documents = [], []

    async def loader(url):
        calls.append(url)
        if url.endswith("slow"):
            assert await asyncio.to_thread(release_last.wait, 5)
        return fake_page(url)

    original = journal.publish
    def publish(kind, **kwargs):
        result = original(kind, **kwargs)
        if kind == "page_completed":
            first_done.set()
        return result
    journal.publish = publish
    urls = ["https://fixture.test/slow", "https://fixture.test/fast"]
    def run():
        with observe(journal), operation(node="acquisition"):
            documents.extend(Crawl4AIAcquisitionProvider(result_loader=loader, batch_delay_seconds=0).acquire_many(urls))
    thread = Thread(target=run)
    thread.start()
    try:
        assert first_done.wait(5)
        assert thread.is_alive() and not documents
        assert all_events(journal)[0]["source_url"] == urls[1]
    finally:
        release_last.set()
        thread.join(5)
    assert not thread.is_alive()
    assert [d.source_url for d in documents] == urls
    assert sorted(calls) == sorted(urls)
    assert len(all_events(journal)) == 2


@pytest.mark.asyncio
async def test_crawl_context_survives_already_async_callers():
    journal = EventJournal()
    with observe(journal), operation(node="source_preview"):
        document = Crawl4AIAcquisitionProvider(result_loader=fake_page).acquire("https://fixture.test/a")
    assert document.success
    assert all_events(journal)[0]["node"] == "source_preview"


def read_sse(response):
    while True:
        line = response.readline().decode()
        if line.startswith("data: "):
            return json.loads(line[6:])
        assert line, "SSE disconnected before delivering the event"


def test_http_sse_reconnect_second_tab_readonly_and_shutdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    journal = EventJournal()
    with WatchServer(journal) as server:
        assert server.httpd.server_address[0] == "127.0.0.1"
        with observe(journal):
            emit("before", details={"html": "<script>alert(1)</script>"})
        with urlopen(server.address + "/api/events", timeout=3) as stream:
            assert read_sse(stream)["kind"] == "before"
        with observe(journal):
            emit("after_disconnect")
        request = Request(server.address + "/api/events", headers={"Last-Event-ID": "1"})
        with urlopen(request, timeout=3) as stream:
            assert read_sse(stream)["sequence"] == 2
        for _ in range(2):
            with urlopen(server.address + "/api/snapshot", timeout=3) as response:
                assert len(json.load(response)["events"]) == 2
        with urlopen(server.address, timeout=3) as response:
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
            assert b"app.js" in response.read()
        with pytest.raises(HTTPError) as failure:
            urlopen(Request(server.address + "/api/snapshot", headers={"Origin": "https://untrusted.test"}), timeout=3)
        assert failure.value.code == 403
        with pytest.raises(HTTPError) as failure:
            urlopen(server.address + "/api/details/999", timeout=3)
        assert failure.value.code == 410
    assert journal.snapshot()["events"] == []
    assert list(tmp_path.iterdir()) == []


def request_config(directory):
    return {"dataset": {"name": "watch_fixture", "topic": "Evidence", "purpose": "Offline acceptance"},
            "research": {"queries": 1, "max_sources": 2}, "schema": {"require_user_approval": True},
            "quality": {"minimum_confidence": 0.7}, "output": {"format": "json", "directory": str(directory)},
            "sources": [{"url": "https://fixture.test/evidence", "title": "Evidence", "enabled": True}]}


def test_real_graph_equivalent_with_watch_and_approval_continues(tmp_path, monkeypatch):
    from src.agents.graphs.phase2_pipeline import build_phase2_pipeline
    from src.core.settings import settings
    from src.state.state import create_initial_state
    monkeypatch.chdir(tmp_path)
    state = create_initial_state("fixture", request_config(tmp_path))
    plain = build_phase2_pipeline()
    pending_plain = plain.invoke(state)
    completed_plain = plain.approve_schema(pending_plain)
    watched = build_phase2_pipeline()
    journal = EventJournal()
    with observe(journal):
        pending = watched.invoke(state)
        boundary = journal.snapshot()["last_sequence"]
        assert all_events(journal)[-1]["status"] == "waiting_for_schema_approval"
        completed = watched.approve_schema(pending)
    for key in ["research_plan", "selected_sources", "source_evaluations", "source_selections", "draft_dataset_schema"]:
        assert pending[key] == pending_plain[key]
    assert completed["status"] == completed_plain["status"] == "completed"
    assert [r["data"] for r in completed["accepted_records"]] == [r["data"] for r in completed_plain["accepted_records"]]
    resumed = journal.snapshot(boundary)["events"]
    assert any(e.get("node") == "acquisition" for e in resumed)
    assert not any(e.get("node") == "research_planner" for e in resumed)
    assert all_events(journal)[-1]["status"] == "completed"
    json.dumps(completed)  # No journal, callbacks, locks, or provider objects in state.


def test_node_output_arrives_at_browser_before_next_node_finishes(tmp_path, monkeypatch):
    import src.agents.graphs.phase2_pipeline as module
    from src.core.settings import settings
    from src.state.state import create_initial_state
    release, entered = Event(), Event()
    original = module.source_search_node
    def blocked(state):
        entered.set()
        assert release.wait(5)
        return original(state)
    monkeypatch.setattr(module, "source_search_node", blocked)
    pipeline = module.build_phase2_pipeline()
    journal = EventJournal()
    result = []
    def run():
        with observe(journal):
            result.append(pipeline.invoke(create_initial_state("fixture", request_config(tmp_path))))
    with WatchServer(journal) as server:
        thread = Thread(target=run)
        thread.start()
        try:
            assert entered.wait(5)
            with urlopen(server.address + "/api/events", timeout=3) as stream:
                while True:
                    event = read_sse(stream)
                    if event.get("node") == "research_planner" and event["kind"] == "node_completed":
                        break
            with urlopen(server.address + f'/api/details/{event["sequence"]}', timeout=3) as response:
                assert json.load(response)["details"]["research_plan"]["search_queries"]
            assert not result
        finally:
            release.set()
            thread.join(10)
    assert result[0]["status"] == "waiting_for_schema_approval"


def test_cli_watch_retains_panel_until_close_without_restarting(monkeypatch):
    import run_domain_test as cli
    import webbrowser
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        emit("run_status", status="completed")
        return {"status": "completed"}
    def inspect():
        from src.observability.events import current_journal
        assert current_journal().snapshot()["run"]["status"] == "completed"
    monkeypatch.setattr(cli, "run_domain_extraction", run)
    monkeypatch.setattr(cli, "_wait_for_watch_close", inspect)
    monkeypatch.setattr(webbrowser, "open", lambda _: True)
    assert cli.run_watched_domain("fixture", resume=True) == {"status": "completed"}
    assert len(calls) == 1 and calls[0][1]["resume"] is True
