"""Helpers for the web tests: a server around a fake context, and a handler driven without sockets."""

from __future__ import annotations

import io
import json
import sys
import threading
import traceback
import urllib.error
import urllib.request
from types import SimpleNamespace

from cell_live.poller import Poller
from cell_live.server import make_handler, make_server
from cell_live.status import FAIL, CheckResult

REQUEST_TIMEOUT_S = 10.0


def thread_stacks() -> str:
    """Where every thread is now: put in the failure text if the server does not answer."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    return "\n".join(f"--- thread {names.get(ident, ident)}\n{''.join(traceback.format_stack(frame))}"
                     for ident, frame in sys._current_frames().items())


class FixedCheck:
    def __init__(self, id, result, kind="hardware"):
        self.id, self.name, self.interval_s, self.result, self.kind = id, id, 2.0, result, kind

    def run(self):
        return self.result


class FakeVisionService:
    stream_max_fps = 50.0

    def __init__(self, frames=(b"jpeg-1", b"jpeg-2"), summary=None):
        self.frames = list(frames)
        self._summary = summary or {"state": "OK", "reason": "", "counts": {"card": 1, "candy": 2, "box": 1, "lid": 1},
                                    "usable": {"card": 1, "candy": 2}, "ready": True, "detections": []}
        self.started = 0

    def jpeg(self):
        return self.frames.pop(0) if self.frames else None

    def summary(self):
        return self._summary

    def start_async(self):
        self.started += 1
        return {"ok": True, "message": "starting"}


def context(**overrides):
    poller = Poller([FixedCheck("dobot_dashboard", CheckResult(FAIL, "Robot unreachable", data={"reason": "unreachable"}))])
    base = dict(poller=poller, run=None, vision=None, config_store=None, logs_dir=None, ports=None,
                unknowns=lambda: ["camera.index"], allow_remote_control=False, reload=None)
    base.update(overrides)
    return SimpleNamespace(**base)


class Served:
    def __init__(self, ctx):
        self.ctx = ctx
        self.http = make_server(ctx.poller, "127.0.0.1", 0, context=ctx)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"

    def _send(self, request):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
        except (TimeoutError, urllib.error.URLError) as error:
            raise AssertionError(f"no answer within {REQUEST_TIMEOUT_S} s to {request.get_method()} "
                                 f"{request.full_url} ({error})\n{thread_stacks()}") from error

    def get(self, path):
        return self._send(urllib.request.Request(self.base + path))

    def get_json(self, path):
        code, _headers, body = self.get(path)
        return code, json.loads(body)

    def post(self, path, body=None, raw=None):
        data = raw if raw is not None else json.dumps(body or {}).encode()
        request = urllib.request.Request(self.base + path, data=data, method="POST", headers={"Content-Type": "application/json"})
        code, _headers, reply = self._send(request)
        return code, json.loads(reply)

    def close(self):
        self.http.shutdown()
        self.http.server_close()


def drive(ctx, method, path, client_ip, body=b"{}"):
    """Run one request through the real handler, with a chosen client address and no socket."""
    handler_class = make_handler(ctx)
    handler = handler_class.__new__(handler_class)
    handler.client_address = (client_ip, 50000)
    handler.path = path
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    getattr(handler, f"do_{method}")()
    status_line = handler.wfile.getvalue().split(b"\r\n", 1)[0].decode()
    return int(status_line.split()[1]), handler.wfile.getvalue()
