"""HTTP server of cell_live: JSON API, Server-Sent Events, MJPEG camera stream, the web console.
Standard library only. Routes for the JSON endpoints are in api_routes.py.

GET  /                           the operator console (web/index.html); /web/* its files
GET  /api/stream                 Server-Sent Events: status, run, trace, heartbeat
GET  /api/camera.mjpg            annotated camera frames, or 503 with the reason
Run, config and vision-start POSTs are accepted from this PC only (127.0.0.1 / ::1), unless the
backend was started with an explicit --host (then a warning is printed at start-up).
"""

from __future__ import annotations

import json
import mimetypes
import queue
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

from . import api_routes
from .poller import Poller
from .status import now_s

HEARTBEAT_S = 5.0
WEB_DIR = Path(__file__).with_name("web")
LOCAL_CLIENTS = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
CONTROL_PREFIXES = ("/api/run/", "/api/config", "/api/vision/start")
RUN_ACTIONS = api_routes.RUN_ACTIONS
MIME = {".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml", ".md": "text/plain", ".woff2": "font/woff2"}


def is_control_request(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in CONTROL_PREFIXES)


def control_allowed(client_ip: str, allow_remote_control: bool) -> bool:
    return allow_remote_control or client_ip in LOCAL_CLIENTS


def make_handler(context: Any) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "cell_live/0.3"

        def log_message(self, format: str, *args: Any) -> None:  # quiet console
            pass

        def _send_json(self, body: Any, code: int = HTTPStatus.OK) -> None:
            payload = json.dumps(body, indent=2, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/stream":
                self._stream()
            elif path == "/api/camera.mjpg":
                self._camera()
            elif path == "/" or path.startswith("/web/"):
                self._static(path)
            else:
                self._reply(api_routes.handle_get(context, path))

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if is_control_request(path) and not control_allowed(self.client_address[0], context.allow_remote_control):
                self._send_json({"error": "control requests are accepted from this PC only (127.0.0.1); "
                                          "start the backend with --host to allow others"}, HTTPStatus.FORBIDDEN)
                return
            body = self._read_json()
            if body is None:
                self._send_json({"error": "the request body must be a JSON object"}, HTTPStatus.BAD_REQUEST)
                return
            self._reply(api_routes.handle_post(context, path, body))

        def _reply(self, routed: tuple[int, Any] | None) -> None:
            if routed is None:
                self._send_json({"error": f"unknown path {self.path}"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(routed[1], routed[0])

        def _read_json(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
            return body if isinstance(body, dict) else None

        def _static(self, path: str) -> None:
            relative = "index.html" if path == "/" else path[len("/web/"):]
            target = (WEB_DIR / relative).resolve()
            if WEB_DIR.resolve() not in target.parents or not target.is_file():
                self._send_json({"error": f"no such file {path}"}, HTTPStatus.NOT_FOUND)
                return
            payload = target.read_bytes()
            mime = MIME.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _stream(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            poller = context.poller
            subscriber = poller.hub.subscribe()
            try:
                for status in poller.snapshot():  # the full picture first
                    self._event("status", status)
                while True:
                    try:
                        kind, event = subscriber.get(timeout=HEARTBEAT_S)
                        self._event(kind, event)
                    except queue.Empty:
                        self._event("heartbeat", {"server_time": now_s()})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                poller.hub.unsubscribe(subscriber)

        def _event(self, kind: str, data: dict[str, Any]) -> None:
            self.wfile.write(f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8"))
            self.wfile.flush()

        def _camera(self) -> None:
            vision = getattr(context, "vision", None)
            first = vision.jpeg() if vision is not None else None
            if first is None:
                reason = vision.summary().get("reason") if vision is not None else "no vision service in this backend"
                self._send_json({"error": f"no camera picture: {reason}"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            frame, period_s = first, 1.0 / max(0.5, vision.stream_max_fps)
            try:
                while frame is not None:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n")
                    self.wfile.write(frame + b"\r\n")
                    self.wfile.flush()
                    time.sleep(period_s)
                    frame = vision.jpeg()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

    return Handler


def make_server(poller: Poller, host: str, port: int, unknowns: list[str] | None = None,
                run_service: Any = None, context: Any = None) -> ThreadingHTTPServer:
    """context: a LiveApp (the console). Without it, a minimal context is built (checks, control, tests)."""
    if context is None:
        context = SimpleNamespace(poller=poller, run=run_service, vision=None, config_store=None, logs_dir=None,
                                  ports=None, unknowns=lambda: list(unknowns or []), allow_remote_control=False, reload=None)
    server = ThreadingHTTPServer((host, port), make_handler(context))
    server.daemon_threads = True
    return server
