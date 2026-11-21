"""The dobot-real safety gate. Nothing here connects to anything."""

import copy
import json
import socket

import pytest

from cell_sim.__main__ import EXIT_CONFIG_ERROR, EXIT_SAFETY_REFUSED, main
from cell_sim.hardware_config import DOBOT_LID_TARGETS, DOBOT_TARGETS, load_hardware_raw
from cell_sim.modes import RealMotionNotImplemented, setup_dobot_real
from cell_sim.safety_gate import MAX_SPEED_PERCENT, SafetyGateRefused, check_real_robot_allowed

LIMIT_KEYS = ("x_min_mm", "x_max_mm", "y_min_mm", "y_max_mm", "z_min_mm", "z_max_mm", "r_min_deg", "r_max_deg")
TEST_LIMITS = {  # test data only, not cell limits
    "x_min_mm": -400.0, "x_max_mm": 400.0, "y_min_mm": -400.0, "y_max_mm": 400.0,
    "z_min_mm": 0.0, "z_max_mm": 250.0, "r_min_deg": -360.0, "r_max_deg": 360.0,
}


def complete_raw():
    """hardware.json as it could look after measuring and approval (statuses VERIFIED; test data)."""
    raw = copy.deepcopy(load_hardware_raw())
    section = raw["dobot"]
    for entry in section.values():
        if entry["status"] in ("ASSUMED", "CONFIRM"):
            entry["status"] = "VERIFIED"
    section["workspace_limits"]["value"] = dict(TEST_LIMITS)
    for name in DOBOT_LID_TARGETS:  # test data only: the lid points are not taught yet
        section[f"target_{name}"]["value"] = {"x_mm": 300.0, "y_mm": 0.0, "z_mm": 140.0, "r_deg": -73.8}
    section["teacher_approval"]["value"] = "Test Teacher, 2026-11-12"
    return raw


def _problems(raw, teacher_flag=True):
    return check_real_robot_allowed(raw["dobot"], teacher_flag)


@pytest.fixture
def no_sockets(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the safety gate must not open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_complete_config_with_flag_passes():
    assert _problems(complete_raw()) == []


REQUIRED = (
    [("speed_factor_percent", None), ("vacuum_do", None), ("teacher_approval", None), ("robot_ip", None)]
    + [("workspace_limits", key) for key in LIMIT_KEYS]
    + [(f"target_{name}", None) for name in DOBOT_TARGETS + DOBOT_LID_TARGETS]
    + [(f"target_{name}", "z_mm") for name in DOBOT_TARGETS + DOBOT_LID_TARGETS]
)


@pytest.mark.parametrize("key, subkey", REQUIRED)
def test_any_null_required_value_is_refused(key, subkey):
    raw = complete_raw()
    if subkey is None:
        raw["dobot"][key]["value"] = None
    else:
        raw["dobot"][key]["value"][subkey] = None
    problems = _problems(raw)
    assert problems and any(key in problem for problem in problems)


@pytest.mark.parametrize("key", ["speed_factor_percent", "vacuum_do", "workspace_limits", "target_pick", "teacher_approval"])
@pytest.mark.parametrize("status", ["ASSUMED", "CONFIRM"])
def test_assumed_or_unconfirmed_values_are_refused(key, status):
    raw = complete_raw()
    raw["dobot"][key]["status"] = status
    assert any(key in problem and status in problem for problem in _problems(raw))


def test_missing_teacher_flag_is_refused():
    assert _problems(complete_raw(), teacher_flag=False) == ["the --teacher-approved flag is missing"]


def test_missing_entry_is_refused():
    raw = complete_raw()
    del raw["dobot"]["vacuum_do"]
    assert "dobot.vacuum_do is missing from hardware.json" in _problems(raw)


@pytest.mark.parametrize("speed", [0, MAX_SPEED_PERCENT + 1, 100, 20.0])
def test_speed_outside_the_cap_is_refused(speed):
    raw = complete_raw()
    raw["dobot"]["speed_factor_percent"]["value"] = speed
    assert any("speed_factor_percent" in problem for problem in _problems(raw))


def test_outputs_must_be_valid_and_different():
    raw = complete_raw()
    raw["dobot"]["object_conveyor_do"]["value"] = 1  # same as the suction
    assert any("use the same output DO1" in problem for problem in _problems(raw))
    raw = complete_raw()
    raw["dobot"]["blow_off_do"]["value"] = 30
    assert any("blow_off_do" in problem for problem in _problems(raw))
    raw = complete_raw()
    raw["dobot"]["arm_orientation_code"]["value"] = None
    assert any("arm_orientation_code is null" in problem for problem in _problems(raw))


def test_target_outside_the_workspace_is_refused():
    raw = complete_raw()
    raw["dobot"]["target_place_box"]["value"]["z_mm"] = 300.0
    assert any("target_place_box.z_mm = 300.0 is outside" in problem for problem in _problems(raw))


def test_today_hardware_json_is_refused():
    with pytest.raises(SafetyGateRefused) as error:
        setup_dobot_real(teacher_approved=True)
    assert any("teacher_approval is null" in problem for problem in error.value.problems)


def test_gate_passing_still_does_not_start_real_motion(tmp_path, no_sockets):
    path = tmp_path / "hardware.json"
    path.write_text(json.dumps(complete_raw()), encoding="utf-8")
    with pytest.raises(RealMotionNotImplemented, match="teacher approved"):
        setup_dobot_real(path, teacher_approved=True)


def test_cli_dobot_real_exits_5_and_lists_the_problems(tmp_path, capsys, no_sockets):
    assert main(["--mode", "dobot-real", "--out-dir", str(tmp_path)]) == EXIT_SAFETY_REFUSED
    error = capsys.readouterr().err
    assert "dobot-real refused to start" in error and "the --teacher-approved flag is missing" in error
    assert list(tmp_path.glob("*.csv")) == []


def test_teacher_flag_is_rejected_in_other_modes(capsys):
    assert main(["--mode", "sim", "--teacher-approved"]) == EXIT_CONFIG_ERROR
