"""Run log, the run service (arm and start) and the HTTP run endpoints. Fakes only."""

import copy
import json
import threading
import urllib.error
import urllib.request

import pytest

from cell_live.control.runlog import RunLog
from cell_live.control.service import RunService
from cell_live.control.vision_session import VisionUnavailable
from cell_live.live_config import LiveConfig
from cell_live.poller import Poller
from cell_live.server import make_server
from cell_live.status import FAIL, OK, CheckResult
from cell_live.tests.control_fakes import CHOTON, CONFIG, FakeClock, FakeSession, FakeVision, choton_settings, wait_for
from cell_live.tests.test_gate import LAB_VALUES


class FixedCheck:
    def __init__(self, id, result):
        self.id, self.name, self.interval_s, self.result = id, id, 60.0, result

    def run(self):
        return self.result


ROBOT_ABSENT = CheckResult(FAIL, "Robot unreachable: no answer", data={"reason": "unreachable"})
ROBOT_OK = CheckResult(OK, "Connected", data={"robot_mode": 4, "robot_mode_name": "ROBOT_MODE_DISABLED"})
NO_YOLO = CheckResult(FAIL, "Python package 'ultralytics' is not installed. Install it with: python -m pip install ultralytics")


def lab_config():
    raw = copy.deepcopy(CONFIG.raw)
    for name, value in LAB_VALUES.items():
        section, key = name.split(".")
        raw[section][key]["value"], raw[section][key]["status"] = value, "VERIFIED"
    return LiveConfig(raw, CONFIG.path)


def _no_camera(*args):
    raise VisionUnavailable("camera absent (test: no hardware)")


def service(tmp_path, config=CONFIG, robot=ROBOT_ABSENT, session=None, vision=None, settings=None):
    poller = Poller([FixedCheck("dobot_dashboard", robot), FixedCheck("vision_model", NO_YOLO)])
    settings = choton_settings(lid=False) if settings is None else settings  # the fixed test values, not today's file
    loaded = type("Choton", (), {**vars(CHOTON), "vision_lib": type("VL", (), {"load_settings": staticmethod(lambda: settings)})})
    return RunService(config, link=None, poller=poller, load_choton=lambda folder: loaded,
                      make_vision=(lambda *args: vision) if vision is not None else _no_camera, make_session=lambda *args: session, out_dir=tmp_path)


def test_run_log_banner_says_hardware_run_with_speed_approval_and_hashes(tmp_path):
    log = RunLog(tmp_path, 40, "Test Teacher, 2026-11-17", 2, {"live_config": CONFIG.path, "missing": None})
    log.state, log.box = "PICK_PLACE", 1
    log.command(29999, "DO(1,1)", "0,{},DO(1,1);")
    log.event("pick card 1/1", detections=[{"type": "card", "conf": 0.91, "x_robot": 250.0, "y_robot": 0.0, "angle_robot": 12.0}])
    log.close()
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# HARDWARE RUN; speed 40 %; boxes requested 2; teacher approval: Test Teacher, 2026-11-17; sha256 live_config=")
    assert "missing=missing" in lines[0] and "SIMULATION" not in log.path.read_text(encoding="utf-8")
    assert lines[1] == "time_s,box,state,event,command,reply,detections,fault"
    assert "DO(1,1)" in lines[2] and "card 0.91 (250.0, 0.0) +12deg" in lines[3]


def test_arm_with_todays_config_and_no_hardware_lists_every_missing_value(tmp_path):
    result = service(tmp_path).arm({})
    assert result["armed"] is False and "token" not in result
    text = "\n".join(result["problems"])
    for words in ("calibration made 2026-11-12", "dobot.teacher_approval", "camera absent",
                  "dobot.belt_on_value", "dobot.belt_dir_forward_value", "dobot.belt_enable_on_value",
                  "control.box_wait_timeout_s", "control.box_leave_timeout_s", "lid heights not taught", "vision model not loaded", "robot not ready", "hand on the emergency stop",
                  "number of boxes"):
        assert words in text, words


def test_start_needs_a_valid_token(tmp_path):
    run = service(tmp_path)
    assert run.start({"boxes": 1, "speed_percent": 40})["started"] is False
    assert "no valid arm token" in run.start({"boxes": 1, "speed_percent": 40, "token": "forged"})["problems"][0]


def test_arm_then_start_runs_a_box_through_the_service(tmp_path):
    clock = FakeClock()
    session, vision = FakeSession(), FakeVision(clock)
    run = service(tmp_path, config=lab_config(), robot=ROBOT_OK, session=session, vision=vision,
                  settings=choton_settings(lid=False))
    session.open = lambda: None
    armed = run.arm({"hand_on_estop": True, "boxes": 1, "speed_percent": 40, "accept_open_box": True})
    assert armed["armed"] is True, armed["problems"]
    started = run.start({"boxes": 1, "speed_percent": 40, "token": armed["token"]})
    assert started["started"] is True and started["run_log"].endswith(".csv")
    wait_for(lambda: run.controller.finished)
    assert run.status()["box_results"][0]["result"] == "done" and session.closed
    assert run.start({"boxes": 1, "speed_percent": 40, "token": armed["token"]})["started"] is False  # token used


def test_while_a_run_is_paused_the_live_view_detects_again_and_the_gate_reply_carries_the_box_and_lid_lines(tmp_path):
    clock = FakeClock()
    session, vision = FakeSession(), FakeVision(clock)
    vision.box_at_mm = (300.0, -60.0)  # the open box stands beside the box slot: the run pauses in WAIT_BOX
    run = service(tmp_path, config=lab_config(), robot=ROBOT_OK, session=session, vision=vision, settings=choton_settings(lid=False))
    session.open = lambda: None
    assert not run.detecting  # no run: the live view detects
    armed = run.arm({"hand_on_estop": True, "boxes": 1, "speed_percent": 40, "accept_open_box": True})
    assert run.start({"boxes": 1, "speed_percent": 40, "token": armed["token"]})["started"] is True
    wait_for(lambda: run.status()["state"] == "PAUSED")
    assert run.active and not run.detecting  # paused: the cycle takes no pictures, the live view may
    reply = run.gate({})
    assert reply["active"] is True and [part["name"] for part in reply["cell"]] == ["Box", "Lid"]
    assert reply["cell"][0]["words"].startswith("the open box's centre (300, -60) is") and reply["cell"][1]["ok"] is False
    run.abort()
    wait_for(lambda: run.controller.finished)
    assert [part["name"] for part in run.gate({})["cell"]] == ["Box", "Lid"]  # with no run active, too


@pytest.fixture
def api(tmp_path):
    poller = Poller([FixedCheck("dobot_dashboard", ROBOT_ABSENT)])
    run = service(tmp_path)
    http = make_server(poller, "127.0.0.1", 0, [], run)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


def _post(url, body):
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_http_arm_refuses_and_run_status_is_idle(api):
    armed = _post(f"{api}/api/run/arm", json.dumps({"hand_on_estop": True, "boxes": 1}).encode())
    assert armed["armed"] is False and any("dobot.teacher_approval" in p for p in armed["problems"])
    with urllib.request.urlopen(f"{api}/api/run", timeout=10) as response:
        assert json.loads(response.read())["state"] == "IDLE"
    assert _post(f"{api}/api/run/estop", b"{}")["ok"] is False  # no run: says the physical button always works
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(f"{api}/api/run/arm", b"not json")
    assert error.value.code == 400
