"""Bounded, sanitized event journal and context propagation for live observation."""
from __future__ import annotations

from collections import OrderedDict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import os
import re
from threading import RLock
from time import perf_counter
from uuid import uuid4


_sink = ContextVar("observation_sink", default=None)
_context = ContextVar("observation_context", default={})
_sensitive = re.compile(r"api.?key|authorization|password|secret|access.?token|refresh.?token|cookie|credential", re.I)
_inline = re.compile(r'''(?i)((?:api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token|token|cookie)\s*["']?\s*[:=]\s*["']?)([^\s"'&,}\n]+)''')


class EventJournal:
    """A bounded in-memory ring, independent of subscribers and disk storage."""

    def __init__(self, *, max_events=2000, max_detail_bytes=16 * 1024 * 1024,
                 max_event_bytes=512 * 1024, secrets=()):
        if min(max_events, max_detail_bytes, max_event_bytes) < 1:
            raise ValueError("Observation limits must be positive.")
        self.run_id = uuid4().hex
        self.max_events = max_events
        self.max_detail_bytes = max_detail_bytes
        self.max_event_bytes = max_event_bytes
        self._events = deque()
        self._details = OrderedDict()
        self._detail_bytes = 0
        self._sequence = 0
        self._lock = RLock()
        self._closed = False
        self._pending = {}
        self.started = perf_counter()
        self._run = {"status": "idle", "topic": "", "node": "", "elapsed_seconds": 0}
        self._secrets = tuple(sorted({str(v) for v in secrets if v} | {
            v for k, v in os.environ.items() if _sensitive.search(k) and v
        }, key=len, reverse=True))

    def _text(self, value):
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s\"'<>,]+", r"\1 [REDACTED]", value)
        value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return _inline.sub(r"\1[REDACTED]", value)

    def _sanitize(self, value):
        budget = [self.max_event_bytes, 20000]
        truncated = [False]

        def visit(item, depth=0):
            budget[1] -= 1
            if budget[0] <= 0 or budget[1] <= 0 or depth > 24:
                truncated[0] = True
                return "[observation limit]"
            if hasattr(item, "model_dump"):
                item = item.model_dump(mode="json")
            if isinstance(item, dict):
                result = {}
                for key, val in item.items():
                    if budget[0] <= 0 or budget[1] <= 0:
                        truncated[0] = True
                        break
                    key = self._text(str(key))[:256]
                    budget[0] -= len(key.encode("utf-8")) + 8
                    result[key] = "[REDACTED]" if _sensitive.search(key) or key.lower() == "token" else visit(val, depth + 1)
                return result
            if isinstance(item, (list, tuple)):
                result = []
                for val in item:
                    if budget[0] <= 0 or budget[1] <= 0:
                        truncated[0] = True
                        break
                    result.append(visit(val, depth + 1))
                return result
            if item is None or isinstance(item, (int, float, bool)):
                budget[0] -= 32
                return item
            # Unknown SDK objects are never introspected (may contain credentials).
            text = self._text(item if isinstance(item, str) else f"<{type(item).__name__}>")
            encoded = text.encode("utf-8")
            limit = max(0, budget[0])
            if len(encoded) > limit:
                text = encoded[:limit].decode("utf-8", errors="ignore")
                truncated[0] = True
            budget[0] -= len(encoded) + 8
            return text

        return visit(value), truncated[0]

    def publish(self, kind, *, status="completed", details=None, message="", **fields):
        safe, truncated = self._sanitize(details)
        encoded = json.dumps(safe, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > self.max_event_bytes:
            # Keep a readable preview, explicitly marked, even for oversized pages.
            safe = {"preview": encoded[:self.max_event_bytes // 8].decode("utf-8", errors="ignore"),
                    "note": "Observation detail limit; full content unavailable."}
            encoded = json.dumps(safe, ensure_ascii=False).encode("utf-8")
            truncated = True
        header, _ = self._sanitize({**_context.get(), **fields})
        # All headers are small and bounded independently of content retention.
        header = {k: v[:2048] if isinstance(v, str) else v for k, v in header.items()
                  if k in {"node", "operation_id", "parent_operation_id", "source_url", "batch_id",
                           "model", "provider", "duration_seconds", "topic"}
                  and isinstance(v, (str, int, float, bool))}
        urls = fields.get("source_urls", _context.get().get("source_urls", []))
        if isinstance(urls, (list, tuple)):
            header["source_urls"] = [self._text(url)[:2048] for url in urls[:32] if isinstance(url, str)]
        urls = fields.get("source_urls", _context.get().get("source_urls", []))
        if isinstance(urls, (list, tuple)):
            header["source_urls"] = [self._text(url)[:2048] for url in urls[:32] if isinstance(url, str)]
        with self._lock:
            if self._closed:
                return
            self._sequence += 1
            seq = self._sequence
            event = {**header, "run_id": self.run_id, "sequence": seq,
                     "kind": self._text(str(kind))[:80], "status": self._text(str(status))[:80],
                     "message": self._text(message)[:512],
                     "timestamp": datetime.now(timezone.utc).isoformat(),
                     "elapsed_seconds": round(perf_counter() - self.started, 3),
                     "details_truncated": truncated}
            self._events.append(event)
            if len(encoded) <= min(self.max_event_bytes, self.max_detail_bytes):
                self._details[seq] = encoded
                self._detail_bytes += len(encoded)
            else:
                event["details_truncated"] = True
            while len(self._events) > self.max_events:
                old = self._events.popleft()["sequence"]
                self._detail_bytes -= len(self._details.pop(old, b""))
            while self._detail_bytes > self.max_detail_bytes:
                _, old = self._details.popitem(last=False)
                self._detail_bytes -= len(old)
            if kind == "run_status":
                self._run.update(status=status, topic=header.get("topic", self._run["topic"]), node="")
            if kind == "node_started":
                self._run.update(node=header.get("node", ""), status="running")
            if kind == "run_status" or kind == "node_started":
                self._run["elapsed_seconds"] = event["elapsed_seconds"]
            return seq

    def snapshot(self, after=0, limit=100):
        with self._lock:
            first = self._events[0]["sequence"] if self._events else self._sequence + 1
            events = [{**e, "details_available": e["sequence"] in self._details}
                      for e in self._events if e["sequence"] > after][:limit]
            return {"run_id": self.run_id, "events": events, "first_sequence": first,
                    "last_sequence": self._sequence, "gap": after < first - 1,
                    "max_events": self.max_events, "detail_bytes": self._detail_bytes,
                    "run": dict(self._run)}

    def detail(self, sequence):
        with self._lock:
            raw = self._details.get(sequence)
        return {"available": raw is not None, "details": json.loads(raw) if raw is not None else None}

    def close(self):
        with self._lock:
            self._closed = True
            self._events.clear()
            self._details.clear()
            self._pending.clear()
            self._detail_bytes = 0
            self._secrets = ()
            self._run = {"status": "closed", "topic": "", "node": "", "elapsed_seconds": 0}


def current_journal():
    return _sink.get()


@contextmanager
def observe(journal):
    token = _sink.set(journal)
    try:
        yield journal
    finally:
        _sink.reset(token)


@contextmanager
def operation(**fields):
    if _sink.get() is None:
        yield ""
        return
    parent = _context.get()
    identity = uuid4().hex
    token = _context.set({**parent, "parent_operation_id": parent.get("operation_id", ""),
                          "operation_id": identity, **fields})
    try:
        yield identity
    finally:
        _context.reset(token)


def emit(kind, **kwargs):
    """Observation failures must never change the business outcome."""
    journal = _sink.get()
    if journal is not None:
        try:
            return journal.publish(kind, **kwargs)
        except Exception:
            return None


@contextmanager
def model_exchange(*, model, provider, request):
    """Observe the actual outbound payload and validation at the provider boundary."""
    response = {}
    with operation(model=model, provider=provider):
        started = perf_counter()
        emit("model_request", status="running", details=request)
        try:
            yield response
        except Exception as error:
            emit("model_response", status="error", duration_seconds=perf_counter() - started,
                 details={**response, "validation": "failed", "error": str(error)})
            raise
        else:
            emit("model_response", duration_seconds=perf_counter() - started,
                 details={**response, "validation": "schema_valid"})


def observed_node(name, function):
    @wraps(function)
    def run(state):
        journal = _sink.get()
        if journal is None:
            return function(state)
        with operation(node=name) as identity:
            started = perf_counter()
            emit("node_started", status="running", message=name)
            try:
                result = function(state)
            except BaseException as error:
                emit("node_completed", status="error", details={"error": str(error)},
                     duration_seconds=perf_counter() - started)
                raise
            status = result.get("pipeline_status") or result.get("status")
            event_status = "error" if status == "failed" else (
                "waiting_for_schema_approval" if status == "waiting_for_schema_approval" else "completed")
            with journal._lock:
                journal._pending[name] = {"node": name, "operation_id": identity,
                    "duration_seconds": perf_counter() - started, "status": event_status}
            return result
    return run


def publish_node_update(name, output):
    journal = _sink.get()
    if journal is None:
        return
    with journal._lock:
        fields = journal._pending.pop(name, {"node": name})
    emit("node_completed", details=output, message=name, **fields)
    # Source links remain filterable without duplicating whole state payloads.
    keys = {"source_search": "candidate_sources", "source_selector": "source_selections"}
    for item in (output or {}).get(keys.get(name, ""), []):
        emit("source_discovered" if name == "source_search" else "source_selected",
             node=name, operation_id=fields.get("operation_id", ""),
             source_url=item.get("url", ""), details=item)
    if name == "source_selector":
        for item in (output or {}).get("rejected_sources", []):
            emit("source_selected", status="rejected", node=name,
                 operation_id=fields.get("operation_id", ""), source_url=item.get("url", ""), details=item)
