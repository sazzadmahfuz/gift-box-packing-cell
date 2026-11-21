"""JSON endpoints of cell_live. Standard library only. Each returns (HTTP code, body) or None.

GET  /api/components             every component status, the CONFIRM list and the server time
GET  /api/components/<id>        one component with its history and raw reply (UI drawer)
POST /api/components/<id>/check  run that check now
GET  /api/run                    the real run
POST /api/run/gate               the gate checklist item by item, never a token
POST /api/run/arm | start | pause | resume | skip | abort | estop | belt-stop | clear-alarm
GET  /api/vision                 counts, detections, the "ready" flag (or NOT_OBSERVABLE)
POST /api/vision/start           start the camera and the model
GET  /api/logs, /api/logs/<file> the HARDWARE RUN logs in testing/live_runs
GET  /api/config, POST /api/config   the lab fields of live_config.json, validated saves
GET  /api/ports                  camera indexes and serial ports on this PC
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from .status import now_s

RUN_ACTIONS = ("arm", "start", "gate", "pause", "resume", "skip", "abort", "estop", "belt-stop", "clear-alarm")
BODY_ACTIONS = ("arm", "start", "gate")
NOT_AVAILABLE = "this backend was started without it"


def _parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def handle_get(context: Any, path: str) -> tuple[int, Any] | None:
    parts = _parts(path)
    poller = context.poller
    if parts == ["api", "components"]:
        return HTTPStatus.OK, {"components": poller.snapshot(), "unconfirmed_config": context.unknowns(), "server_time": now_s()}
    if len(parts) == 3 and parts[:2] == ["api", "components"]:
        if parts[2] not in poller.checks:
            return HTTPStatus.NOT_FOUND, {"error": f"unknown component {parts[2]}"}
        return HTTPStatus.OK, poller.detail(parts[2])
    if parts == ["api", "run"] and context.run is not None:
        return HTTPStatus.OK, context.run.status()
    if parts == ["api", "vision"]:
        vision = getattr(context, "vision", None)
        if vision is None:
            return HTTPStatus.OK, {"state": "NOT_OBSERVABLE", "reason": NOT_AVAILABLE, "counts": {}, "detections": []}
        return HTTPStatus.OK, vision.summary()
    if parts[:2] == ["api", "logs"] and getattr(context, "logs_dir", None) is not None:
        return _logs(context, parts)
    if parts == ["api", "config"] and getattr(context, "config_store", None) is not None:
        return HTTPStatus.OK, context.config_store.describe()
    if parts == ["api", "ports"] and getattr(context, "ports", None) is not None:
        return HTTPStatus.OK, context.ports()
    return None


def _logs(context: Any, parts: list[str]) -> tuple[int, Any]:
    from .logs_api import LogNotFound, list_logs, read_log

    if len(parts) == 2:
        return HTTPStatus.OK, {"folder": str(context.logs_dir), "logs": list_logs(context.logs_dir)}
    try:
        return HTTPStatus.OK, read_log(context.logs_dir, parts[2])
    except LogNotFound as error:
        return HTTPStatus.NOT_FOUND, {"error": str(error)}


def handle_post(context: Any, path: str, body: dict[str, Any]) -> tuple[int, Any] | None:
    parts = _parts(path)
    poller = context.poller
    if len(parts) == 4 and parts[:2] == ["api", "components"] and parts[3] == "check":
        if parts[2] not in poller.checks:
            return HTTPStatus.NOT_FOUND, {"error": f"unknown component {parts[2]}"}
        poller.check_now(parts[2])
        return HTTPStatus.OK, poller.detail(parts[2])
    if len(parts) == 3 and parts[:2] == ["api", "run"] and parts[2] in RUN_ACTIONS and context.run is not None:
        method = getattr(context.run, parts[2].replace("-", "_"))
        return HTTPStatus.OK, method(body) if parts[2] in BODY_ACTIONS else method()
    if parts == ["api", "vision", "start"] and getattr(context, "vision", None) is not None:
        return HTTPStatus.OK, context.vision.start_async()
    if parts == ["api", "config"] and getattr(context, "config_store", None) is not None:
        return _save_config(context, body)
    return None


def _save_config(context: Any, body: dict[str, Any]) -> tuple[int, Any]:
    if context.run is not None and context.run.active:
        return HTTPStatus.CONFLICT, {"saved": False, "problems": ["a run is active: settings cannot change now"]}
    result = context.config_store.save(body)
    if not result["saved"]:
        return HTTPStatus.BAD_REQUEST, result
    if getattr(context, "reload", None) is not None:
        result["reloaded"] = context.reload()
    return HTTPStatus.OK, result
