"""Console endpoints against fakes: components, gate, tokens, vision, camera stream, guard, SSE, ports."""

import json
import urllib.request

import pytest

from cell_live.checks.ports import camera_ports, serial_ports
from cell_live.status import OK, CheckResult
from cell_live.tests.control_fakes import FakeClock, FakeSession, FakeVision
from cell_live.tests.test_runlog_and_api import ROBOT_OK, lab_config, service
from cell_live.tests.web_fakes import FakeVisionService, Served, context, drive


@pytest.fixture
def served():
    servers = []

    def start(**overrides):
        servers.append(Served(context(**overrides)))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


def test_component_detail_has_history_and_check_now_returns_it(served):
    server = served()
    code, detail = server.post("/api/components/dobot_dashboard/check")
    assert code == 200 and detail["state"] == "FAIL" and detail["interval_s"] == 2.0 and detail["kind"] == "hardware"
    code, detail = server.get_json("/api/components/dobot_dashboard")
    assert code == 200 and len(detail["history"]) == 1 and detail["history"][0]["state"] == "FAIL"
    assert server.get_json("/api/components/nope")[0] == 404
    code, listing = server.get_json("/api/components")
    assert listing["server_time"] > 0 and listing["unconfirmed_config"] == ["camera.index"]


def test_gate_checklist_comes_item_by_item_and_never_gives_a_token(served, tmp_path):
    server = served(run=service(tmp_path))
    code, gate = server.post("/api/run/gate", {"hand_on_estop": True, "boxes": 1})
    assert code == 200 and gate["ok"] is False and "token" not in gate
    assert [item["number"] for item in gate["items"]] == list(range(1, 13))  # 11 gate items and where the arm stands (way_home.py)
    teacher = next(item for item in gate["items"] if item["number"] == 2)
    assert not teacher["ok"] and "dobot.teacher_approval is not set" in teacher["problems"][0]


def test_an_expired_token_is_refused_over_http(served, tmp_path):
    clock = FakeClock()
    run = service(tmp_path, config=lab_config(), robot=ROBOT_OK, session=FakeSession(), vision=FakeVision(clock))
    run.tokens.clock = clock
    server = served(run=run)
    body = {"hand_on_estop": True, "boxes": 1, "speed_percent": 40, "accept_open_box": True}
    code, armed = server.post("/api/run/arm", body)
    assert armed["armed"] is True, armed["problems"]
    clock.advance(61.0)
    code, started = server.post("/api/run/start", {"boxes": 1, "speed_percent": 40, "token": armed["token"]})
    assert started["started"] is False and "expired" in started["problems"][0]


def test_vision_summary_and_camera_stream(served):
    vision = FakeVisionService()
    server = served(vision=vision)
    code, summary = server.get_json("/api/vision")
    assert code == 200 and summary["ready"] is True and summary["counts"]["candy"] == 2
    with urllib.request.urlopen(server.base + "/api/camera.mjpg", timeout=10) as stream:
        assert stream.headers["Content-Type"].startswith("multipart/x-mixed-replace")
        first = stream.read(200)
    assert first.startswith(b"--frame\r\nContent-Type: image/jpeg") and b"jpeg-1" in first
    code, reply = server.post("/api/vision/start")
    assert reply["ok"] and vision.started == 1


def test_no_camera_gives_503_with_the_reason(served):
    vision = FakeVisionService(frames=(), summary={"state": "NOT_OBSERVABLE", "reason": "camera.index is not set (CONFIRM)"})
    server = served(vision=vision)
    code, _headers, body = server.get("/api/camera.mjpg")
    assert code == 503 and "camera.index is not set" in json.loads(body)["error"]
    assert served().get_json("/api/vision")[1]["state"] == "NOT_OBSERVABLE"  # a backend without a vision service


@pytest.mark.parametrize("path", ["/api/run/arm", "/api/run/estop", "/api/config", "/api/vision/start"])
def test_control_requests_from_another_computer_are_refused(path):
    ctx = context(run=type("Run", (), {"arm": lambda self, b: {"armed": False}, "estop": lambda self: {"ok": True}, "active": False})(),
                  vision=FakeVisionService(), config_store=type("Store", (), {"save": lambda self, b: {"saved": False, "problems": []}})())
    code, reply = drive(ctx, "POST", path, "192.168.1.50")
    assert code == 403 and b"this PC only" in reply
    assert drive(ctx, "GET", "/api/components", "192.168.1.50")[0] == 200  # status stays readable
    assert drive(ctx, "POST", path, "127.0.0.1")[0] != 403
    ctx.allow_remote_control = True  # started with --host
    assert drive(ctx, "POST", path, "192.168.1.50")[0] != 403


def test_sse_carries_run_and_trace_events(served):
    server = served()
    with urllib.request.urlopen(server.base + "/api/stream", timeout=10) as stream:
        for _ in range(3):  # the full picture first: one status event
            stream.readline()
        server.ctx.poller.hub.publish({"state": "PAUSED", "box": 1}, "run")
        server.ctx.poller.hub.publish({"source": "check port 29999", "command": "RobotMode()", "reply": "0,{4},RobotMode();"}, "trace")
        lines = [stream.readline() for _ in range(6)]
    assert lines[0] == b"event: run\n" and json.loads(lines[1][6:])["state"] == "PAUSED"
    assert lines[3] == b"event: trace\n" and json.loads(lines[4][6:])["command"] == "RobotMode()"


def test_a_quiet_stream_sends_heartbeats_with_the_server_time(served, monkeypatch):
    import cell_live.server

    monkeypatch.setattr(cell_live.server, "HEARTBEAT_S", 0.2)
    server = served()
    with urllib.request.urlopen(server.base + "/api/stream", timeout=10) as stream:
        for _ in range(3):  # the first status event
            stream.readline()
        lines = [stream.readline() for _ in range(3)]
    assert lines[0] == b"event: heartbeat\n" and json.loads(lines[1][6:])["server_time"] > 0


def test_ports_endpoint_and_port_finders(served):
    server = served(ports=lambda: {"cameras": {"cameras": [{"index": 0, "opens": True, "frame": "1280x720"}]}, "serial": {"ports": ["COM5"]}})
    assert server.get_json("/api/ports")[1]["serial"]["ports"] == ["COM5"]
    found = camera_ports(in_use_index=1, finder=lambda: [{"index": 0, "opens": True, "frame": "1280x720"}, {"index": 1, "opens": False, "frame": ""}])
    assert found["cameras"][1] == {"index": 1, "opens": True, "frame": "in use by the vision session"}

    def no_pyserial():
        raise ImportError("No module named 'serial'")

    assert serial_ports(list_pyserial=lambda: ["COM3"])["ports"] == ["COM3"]
    fallback = serial_ports(list_pyserial=no_pyserial, list_registry=lambda: ["COM7"])
    assert fallback == {"ports": ["COM7"], "source": "Windows registry", "detail": "pyserial not installed"}


def test_static_console_files_are_served_safely(served):
    server = served()
    code, headers, body = server.get("/")
    assert code == 200 and headers["Content-Type"].startswith("text/html") and b"HARDWARE" in body
    code, headers, _ = server.get("/web/js/app.js")
    assert code == 200 and headers["Content-Type"].startswith("text/javascript")
    assert server.get("/web/../live_config.json")[0] == 404
    assert server.get("/web/%2e%2e/live_config.json")[0] == 404
    assert server.get("/web/js/missing.js")[0] == 404


def test_check_result_of_a_file_component_is_labelled_file(served):
    from cell_live.poller import Poller
    from cell_live.tests.web_fakes import FixedCheck

    server = served(poller=Poller([FixedCheck("calibration", CheckResult(OK, "created 2026-11-12"), kind="file")]))
    server.ctx.poller.check_now("calibration")
    assert server.get_json("/api/components")[1]["components"][0]["kind"] == "file"
