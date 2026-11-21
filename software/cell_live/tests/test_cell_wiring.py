"""The cell as built on 17 Nov. Object belt on DO3 (start and stop), DO4 (direction) and
DO16 (enable); the box belt runs on its own UNO and sensor, and an operator takes the closed box."""

import copy
import json
import shutil
from pathlib import Path

import pytest

from cell_live.checks import build_checks
from cell_live.checks.calibration import CalibrationCheck
from cell_live.config_store import ConfigStore
from cell_live.control.belts import ObjectBeltDO3
from cell_live.control.robot_client import ControlRefused
from cell_live.control.robot_session import RobotSession, SessionError, SessionValues
from cell_live.dobot_link import DobotLink
from cell_live.live_config import DEFAULT_LIVE_CONFIG_PATH, LiveConfig, LiveConfigError, load_live_config
from cell_live.status import FAIL, NOT_OBSERVABLE, OK, WARN
from cell_live.tests.control_fakes import (
    CHOTON, FakeClock, FakeNet, FakeSession, FakeVision, choton_settings, objects_come_with_the_belt, wait_for,
)
from cell_live.tests.fakes import DOBOT_API, FakeRobot, feedback_bytes
from cell_live.tests.test_gate import config_with, has, problems
from cell_live.tests.test_runlog_and_api import ROBOT_OK, lab_config, service

CONFIG = load_live_config()
NEW_LEVELS = ("dobot.belt_dir_forward_value", "dobot.belt_enable_on_value")


# Config


def test_the_17_nov_wiring_is_in_the_config():
    value = CONFIG.value
    assert (value("dobot", "belt_do"), value("dobot", "belt_dir_do"), value("dobot", "belt_enable_do")) == (3, 4, 16)
    assert CONFIG.status("dobot", "belt_enable_do") == "VERIFIED"  # wiring confirmed 17 Nov; its level: lab test T5
    assert value("belts", "box_restart") == "operator" and value("dobot", "box_belt_do") is None
    assert (value("belts", "object_belt_serial"), value("belts", "box_belt_serial")) == ("DTCB 25261249", "DTCB-2418-0718")
    assert value("arduino", "board") == "Arduino UNO R4 WiFi" and value("arduino", "serial_port") is None


def test_lab_values_are_null_and_confirm_until_the_lab_gives_them_then_verified_with_a_source():
    for name in ("dobot.belt_on_value", *NEW_LEVELS, "control.box_wait_timeout_s", "control.box_leave_timeout_s"):
        section, key = name.split(".")
        entry = CONFIG.entry(section, key)
        if entry["value"] is None:
            assert entry["status"] == "CONFIRM", name
        else:
            assert entry["status"] == "VERIFIED" and not entry["source"].startswith(("lab test T", "not measured")), name
    for name in ("dobot.box_belt_do", "belts.box_restart", "arduino.serial_port", "arduino.baud", "arduino.status_command"):
        assert name not in CONFIG.unknowns(), name  # decided, or deliberately not used


def test_null_may_mean_not_used_but_never_verified():
    raw = copy.deepcopy(CONFIG.raw)
    raw["dobot"]["belt_dir_do"]["value"] = None  # still marked VERIFIED
    with pytest.raises(LiveConfigError, match="CONFIRM .* or SETTING"):
        LiveConfig(raw)
    raw["dobot"]["belt_dir_do"]["status"] = "SETTING"
    assert LiveConfig(raw).value("dobot", "belt_dir_do") is None


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "live_config.json"
    shutil.copy2(DEFAULT_LIVE_CONFIG_PATH, path)
    return ConfigStore(lambda: load_live_config(path)), path


@pytest.mark.parametrize("key, value, problem", [
    ("belt_dir_do", 25, "from 1 to 24"), ("belt_enable_do", 0, "from 1 to 24"),
    ("belt_dir_forward_value", 2, "from 0 to 1"), ("belt_enable_on_value", "on", "whole number"),
])
def test_the_new_outputs_and_levels_have_type_rules(store, key, value, problem):
    result = store[0].save({"section": "dobot", "key": key, "value": value, "status": "VERIFIED", "source": "lab, 17 Nov"})
    assert result["saved"] is False and any(problem in text for text in result["problems"]), result


def test_a_lab_result_saves_and_then_loads(store):
    config_store, path = store
    result = config_store.save({"section": "dobot", "key": "belt_enable_on_value", "value": 1, "status": "VERIFIED",
                                "source": "lab test T5, 17 Nov"})
    assert result["saved"] is True, result["problems"]
    loaded = load_live_config(path)
    assert loaded.value("dobot", "belt_enable_on_value") == 1 and "dobot.belt_enable_on_value" not in loaded.unknowns()


# Checks


def with_values(**changes):
    """Our config with some entries changed, e.g. dobot__belt_enable_on_value=1 (status VERIFIED)."""
    raw = copy.deepcopy(CONFIG.raw)
    for name, value in changes.items():
        section, key = name.split("__")
        raw[section][key].update(value=value, status="VERIFIED")
    return LiveConfig(raw, CONFIG.path)


def checks_for(robot, config=CONFIG):
    link = DobotLink("192.168.1.6", 29999, 30004, 0.5, load_api=lambda: DOBOT_API, connect=robot.connect)
    return {check.id: check for check in build_checks(config, link)}


def test_the_object_belt_has_three_output_checks_and_the_box_belt_none_in_operator_mode():
    checks = checks_for(FakeRobot())
    assert [checks[i].name for i in ("object_belt_do3", "object_belt_dir", "object_belt_power")] == [
        "Object belt start and stop (DO3)", "Object belt direction (DO4)", "Object belt enable (DO16)"]
    assert "box_belt_do" not in checks
    assert {"object_belt_do3", "object_belt_dir", "object_belt_power"} <= set(checks["dobot_feedback"].triggers)
    controller = checks["box_belt_nano"]
    assert controller.name == "Box belt controller (UNO R4 WiFi) and sensor"
    result = controller.run()
    assert result.state == NOT_OBSERVABLE and "not connected to this PC" in result.detail


def test_a_dobot_output_for_the_box_belt_brings_its_check_back():
    raw = copy.deepcopy(CONFIG.raw)
    raw["belts"]["box_restart"]["value"] = "dobot_output"
    raw["dobot"]["box_belt_do"].update(value=5, status="VERIFIED")
    ids = list(checks_for(FakeRobot(), LiveConfig(raw, CONFIG.path)))
    assert ids.index("box_belt_do") == ids.index("object_belt_power") + 1


def test_do4_and_do16_come_from_the_same_feedback_packet():
    robot = FakeRobot(packet=feedback_bytes(outputs=(1 << 2) | (1 << 15)))  # DO3 and DO16 on, DO4 off
    checks = checks_for(robot, with_values(dobot__belt_enable_on_value=1))  # as if lab test T5 had given 1
    assert checks["dobot_feedback"].run().state == OK
    direction, enable = checks["object_belt_dir"].run(), checks["object_belt_power"].run()
    assert direction.state == OK and direction.data["commanded_level"] == 0
    assert "forward" not in direction.detail  # T7 not done yet: the check claims no direction
    assert enable.data["commanded_level"] == 1 and "the level that enables the belt" in enable.detail


def test_without_robot_feedback_do4_and_do16_are_not_observable():
    checks = checks_for(FakeRobot(failure="timeout"))
    assert checks["dobot_feedback"].run().state == FAIL
    for component_id in ("object_belt_dir", "object_belt_power"):
        result = checks[component_id].run()
        assert result.state == NOT_OBSERVABLE and "robot feedback not readable" in result.detail


# Run control (test values: DO3 runs the belt at 0, DO4 forward is 1, DO16 enables at 1)

VALUES = SessionValues(speed_percent=40, vacuum_do=1, blow_do=2, belt_do=3, belt_on_value=0, belt_dir_do=4,
                       belt_dir_forward_value=1, belt_enable_do=16, belt_enable_on_value=1, box_belt_do=None,
                       reach_min_mm=150, reach_max_mm=375, move_port=30003, reply_timeout_s=0.5)


@pytest.fixture
def opened(monkeypatch):
    monkeypatch.setattr(CHOTON.robot_lib.time, "sleep", lambda seconds: None)  # robot_lib's pauses
    net = FakeNet()
    link = DobotLink(CONFIG.value("dobot", "ip"), 29999, 30004, 0.5, connect=net.connect)
    session = RobotSession(link, CHOTON, choton_settings(), VALUES, lambda port, c, r: None, lambda: DOBOT_API)
    return net, link, session


def test_off_levels_switch_the_object_belt_off_first_and_leave_its_direction_alone():
    levels = VALUES.off_levels()
    assert list(levels) == [3, 16, 1, 2] and levels[3] == 1 and levels[16] == 0  # DO3 stop level, DO16 off
    assert 4 not in levels


def test_the_session_start_sets_do3_do4_do16_in_order_before_any_move(opened):
    net, link, session = opened
    set_now = session.open()
    dashboard = net.commands(29999)
    start = dashboard.index("SetArmOrientation(0)") + 1  # right after Choton's enable sequence
    assert dashboard[start:] == ["DO(3,1)", "DO(4,1)", "DO(16,1)"]
    assert net.commands(30003) == []  # no move, not even a Sync, before the start levels
    assert set_now == ["DO3 = 1 (object belt stopped)", "DO4 = 1 (object belt forward)", "DO16 = 1 (object belt enabled)"]


def test_a_refused_start_level_refuses_the_session_and_closes_it(opened):
    net, link, session = opened
    net.replies["DO"] = "-1,{},DO();"  # the robot answers every DO with an error
    with pytest.raises(SessionError, match="object belt start levels were not set"):
        session.open()
    assert link.control_session is None and session.robot is None
    assert all(connection.closed for connection in net.connections)


def test_the_belt_direction_stays_forward_and_is_never_set_after_the_estop(opened):
    net, link, session = opened
    session.open()
    with pytest.raises(ControlRefused, match="DO4 may only be set to 1"):
        session.robot.dash.DO(4, 0)
    session.software_estop()
    with pytest.raises(ControlRefused, match="not after the software e-stop"):
        session.robot.dash.DO(4, 1)
    assert "DOExecute(4" not in " ".join(net.commands(29999))  # the e-stop leaves DO4 alone


def test_every_belt_start_switches_the_enable_on_first():
    session = FakeSession(belt_on_value=0)
    belt = ObjectBeltDO3(session, 3, 0, enable=(16, 1))
    belt.start()
    belt.stop()
    belt.start()  # after a pause DO16 is off: the next start switches it on again
    assert session.calls == ["DO16=1", "DO3=0", "DO3=1", "DO16=1", "DO3=0"]


@pytest.mark.parametrize("change, words", [
    ({"dobot__belt_dir_forward_value": None}, "dobot.belt_dir_forward_value is not set"),
    ({"dobot__belt_enable_on_value": (1, "CONFIRM")}, "dobot.belt_enable_on_value = 1 is still CONFIRM"),
    ({"dobot__belt_dir_do": None}, "dobot.belt_dir_do is not set"),
    ({"dobot__belt_enable_do": (16, "ASSUMED")}, "dobot.belt_enable_do = 16 is still ASSUMED"),
    ({"dobot__belt_enable_on_value": 2}, "dobot.belt_enable_on_value = 2 must be 0 or 1"),
    ({"dobot__belt_enable_do": 1}, "use the same output DO1"),
])
def test_arm_is_refused_until_the_new_object_belt_values_are_confirmed(change, words):
    has(problems(config=config_with(**change)), words)


def test_a_run_logs_its_start_levels_and_switches_the_enable_on_before_the_belt(tmp_path):
    clock = FakeClock()
    session = FakeSession()
    session.open = lambda: ["DO3 = 0 (object belt stopped)", "DO4 = 1 (object belt forward)", "DO16 = 1 (object belt enabled)"]
    vision = FakeVision(clock)
    objects_come_with_the_belt(vision, session)  # the belt must run, so its start order can be seen
    run = service(tmp_path, config=lab_config(), robot=ROBOT_OK, session=session, vision=vision,
                  settings=choton_settings(lid=False))
    armed = run.arm({"hand_on_estop": True, "boxes": 1, "speed_percent": 40, "accept_open_box": True})
    assert armed["armed"] is True, armed["problems"]
    started = run.start({"boxes": 1, "speed_percent": 40, "token": armed["token"]})
    assert started["started"] is True, started
    wait_for(lambda: run.controller.finished)
    log = Path(started["run_log"]).read_text(encoding="utf-8")
    assert "outputs at the start: DO3 = 0 (object belt stopped); DO4 = 1 (object belt forward); DO16 = 1" in log
    assert session.calls.index("DO16=1") < session.calls.index("DO3=1")  # enabled before the belt is told to run


# Choton's lab values of 17 Nov (new worktable and camera stand)

CHOTON_17_NOV = {"home": [197.6, 302.4, 189.7, -36.9], "box_slots": [[369.8, 27.9]], "travel_z": 174.1, "place_z": 135.4,
                 "pick_z_by_type": {"card": 62.3, "candy": 71.8}, "lid_pick_z": 86.3, "lid_place_z": 105.1}


def test_a_calibration_from_before_the_new_worktable_is_refused_and_a_new_one_passes():
    config = config_with(calibration__valid_from="2026-11-17")
    old = {"frame": "robot", "practice": False, "created": "2026-11-12_16-54-12"}
    has(problems(config=config, calibration=old),
        "calibration made 2026-11-12, before the current worktable and camera stand (2026-11-17)")
    new = {**old, "created": "2026-11-17_14-30-00"}
    assert not any("worktable" in problem for problem in problems(config=config, calibration=new))


def test_the_calibration_lamp_warns_about_a_file_from_before_the_new_worktable(tmp_path):
    path = tmp_path / "homography.json"
    base = {"H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "robot_points": [[0, 0]] * 5, "mean_error_mm": 0.51,
            "frame": "robot", "practice": False}
    path.write_text(json.dumps({**base, "created": "2026-11-12_16-54-12"}), encoding="utf-8")
    old = CalibrationCheck(path, 60.0, valid_from="2026-11-17").run()
    assert old.state == WARN and "before the current worktable and camera stand (2026-11-17)" in old.detail
    path.write_text(json.dumps({**base, "created": "2026-11-17_14-30-00"}), encoding="utf-8")
    assert CalibrationCheck(path, 60.0, valid_from="2026-11-17").run().state == OK


def test_chotons_17_nov_points_are_inside_the_reach_and_the_box_needs_more_than_370_mm():
    robot = {**choton_settings()["robot"], **CHOTON_17_NOV}
    assert not [problem for problem in problems(robot=robot) if "taught point" in problem]  # 175-375 mm in the config
    has(problems(robot=robot, config=config_with(control__reach_max_mm=370)),
        "taught point box_slots[0] (369.8, 27.9) is 370.9 mm from the robot")
