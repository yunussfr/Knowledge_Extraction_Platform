"""Read-only loopback HTTP/SSE server backed exclusively by an EventJournal."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import BoundedSemaphore, Event, Thread
from urllib.parse import parse_qs, urlsplit

from src.observability.events import EventJournal


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args):
        self.slots = BoundedSemaphore(16)
        super().__init__(*args)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(2)
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class WatchServer:
    def __init__(self, journal: EventJournal, port=0):
        self.journal = journal
        self.stopped = Event()
        self.stream_slots = BoundedSemaphore(8)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def send_headers(self, code, content_type):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()

            def send_json(self, code, value):
                self.send_headers(code, "application/json; charset=utf-8")
                self.wfile.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))

            def do_GET(self):
                # Reject browser cross-origin requests and DNS rebinding.
                if self.headers.get("Host") != owner.address.removeprefix("http://"):
                    self.send_error(403)
                    return
                if self.headers.get("Origin") not in {None, owner.address}:
                    self.send_error(403)
                    return
                target = urlsplit(self.path)
                try:
                    if target.path == "/api/events":
                        after = max(0, int(self.headers.get("Last-Event-ID") or parse_qs(target.query).get("after", ["0"])[0]))
                        if not owner.stream_slots.acquire(blocking=False):
                            self.send_error(503)
                            return
                        try:
                            self.send_headers(200, "text/event-stream; charset=utf-8")
                            while not owner.stopped.is_set():
                                batch = journal.snapshot(after)
                                if batch["gap"]:
                                    self.wfile.write(b"event: gap\ndata: {}\n\n")
                                    after = batch["first_sequence"] - 1
                                for event in batch["events"]:
                                    after = event["sequence"]
                                    payload = json.dumps(event, ensure_ascii=False)
                                    self.wfile.write(f"id: {after}\ndata: {payload}\n\n".encode("utf-8"))
                                self.wfile.write(b": keepalive\n\n")
                                self.wfile.flush()
                                owner.stopped.wait(0.25)
                        finally:
                            owner.stream_slots.release()
                    elif target.path == "/api/snapshot":
                        after = max(0, int(parse_qs(target.query).get("after", ["0"])[0]))
                        self.send_json(200, journal.snapshot(after))
                    elif target.path.startswith("/api/details/"):
                        detail = journal.detail(int(target.path.rsplit("/", 1)[-1]))
                        self.send_json(200 if detail["available"] else 410, detail)
                    else:
                        files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/styles.css": ("styles.css", "text/css")}
                        if target.path not in files:
                            self.send_error(404)
                            return
                        filename, mime = files[target.path]
                        content = (Path(__file__).parent / "static" / filename).read_bytes()
                        self.send_headers(200, mime + "; charset=utf-8")
                        self.wfile.write(content)
                except (ValueError, TypeError):
                    self.send_error(400)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass

        self.httpd = _Server(("127.0.0.1", port), Handler)
        self.address = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = Thread(target=self.httpd.serve_forever, name="watch-web", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.stopped.set()
        if self.thread.is_alive():
            self.httpd.shutdown()
            self.thread.join(timeout=3)
        self.httpd.server_close()
        self.journal.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()
