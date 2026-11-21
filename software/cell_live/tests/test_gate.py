"""The safety gate: one test (or more) per gate item, plus tokens."""

import copy

import pytest

from cell_live.adapters.choton import read_json
from cell_live.control.gate import ArmTokens, GateFacts, check
from cell_live.live_config import LiveConfig
from cell_live.tests.control_fakes import CONFIG, FakeClock, choton_settings

LAB_VALUES = {  # test data only: what the lab will fill in on 17 Nov
    "dobot.speed_percent": 40, "control.speed_percent_max": 60, "dobot.teacher_approval": "Test Teacher, 2026-11-17",
    "camera.index": 0, "dobot.belt_on_value": 1, "control.box_wait_timeout_s": 30.0,
    "control.box_leave_timeout_s": 20.0, "belts.box_restart": "operator",
    "dobot.belt_dir_forward_value": 1, "dobot.belt_enable_on_value": 1,  # lab tests T7 and T5
    "calibration.valid_from": "2026-11-12",  # the repo still holds Choton's 12 Nov homography.json
}


def config_with(**changes):
    """Our live_config.json with the lab values filled in, then the given changes (value or (value, status))."""
    raw = copy.deepcopy(CONFIG.raw)
    for name, value in {**LAB_VALUES, **{k.replace("__", "."): v for k, v in changes.items()}}.items():
        section, key = name.split(".")
        value, status = value if isinstance(value, tuple) else (value, "VERIFIED")
        raw[section][key]["value"], raw[section][key]["status"] = value, status if value is not None else "CONFIRM"
    return LiveConfig(raw, CONFIG.path)


def facts(config=None, robot=None, **overrides):
    settings = choton_settings()
    base = dict(
        config=config or config_with(),
        choton_robot=robot or settings["robot"],
        box_contents=settings["box_contents"],
        calibration=read_json(CONFIG.path_value("calibration", "file")),
        vision={"model_loaded": True, "classes": ["card", "candy", "box", "lid"], "frame_age_s": 0.2},
        robot_status={"state": "OK", "detail": "Connected", "data": {"robot_mode": 4, "robot_mode_name": "ROBOT_MODE_DISABLED"}},
        operator={"hand_on_estop": True, "boxes": 2, "speed_percent": 40, "accept_open_box": False},
    )
    base.update(overrides)
    return GateFacts(**base)


def problems(**kwargs):
    return check(facts(**kwargs)).problems


def has(found, words):
    assert any(words in problem for problem in found), found


def test_complete_facts_pass_and_only_an_unverified_turn_direction_gets_a_note():
    report = check(facts())
    assert report.ok, report.problems
    assert not any("r_sign" in note for note in report.notes)  # r_sign = 1 was verified on 17 Nov
    other_way = copy.deepcopy(facts().choton_robot)
    other_way["r_sign"] = -1
    report = check(facts(robot=other_way))
    assert report.ok and any("r_sign = -1" in note for note in report.notes)


def test_todays_config_refuses_and_lists_every_lab_value():
    found = problems(config=CONFIG)
    for name in ("dobot.teacher_approval",
                 "dobot.belt_on_value", "dobot.belt_dir_forward_value", "dobot.belt_enable_on_value",
                 "control.box_wait_timeout_s", "control.box_leave_timeout_s"):
        has(found, name)
    has(found, "calibration made 2026-11-12, before the current worktable and camera stand (2026-11-17)")
    assert not any("belts.box_restart" in problem or "speed_percent" in problem for problem in found)  # set 17 Nov


# Item 1: speed (from config, never a hard-coded limit)


def test_speed_values_must_be_set_and_confirmed():
    has(problems(config=config_with(dobot__speed_percent=None)), "dobot.speed_percent is not set")
    has(problems(config=config_with(control__speed_percent_max=(60, "CONFIRM"))), "control.speed_percent_max = 60 is still CONFIRM")


def test_speed_above_the_lab_maximum_is_refused():
    has(problems(config=config_with(dobot__speed_percent=70)), "is above control.speed_percent_max 60 %")
    has(problems(operator={"hand_on_estop": True, "boxes": 1, "speed_percent": 61}), "requested speed 61")


def test_the_limit_comes_from_config_not_from_old_code():
    config = config_with(dobot__speed_percent=85, control__speed_percent_max=90)
    assert problems(config=config, operator={"hand_on_estop": True, "boxes": 1, "speed_percent": 85}) == []


# Item 2: teacher approval


def test_teacher_approval_needs_a_name_and_date():
    has(problems(config=config_with(dobot__teacher_approval=None)), "dobot.teacher_approval is not set")
    has(problems(config=config_with(dobot__teacher_approval="  ")), "teacher's name and the date")
    for wrong in ("20", "Teacher", "2026-11-17", "17 Nov"):  # "20": a timeout typed in the wrong field (17 Nov)
        has(problems(config=config_with(dobot__teacher_approval=wrong)), "teacher's name and the date")
    for right in ("Test Teacher, 2026-11-17", "T. Teacher 17.11.2026", "Teacher, 17 Nov 2026"):
        assert not any("teacher" in problem for problem in problems(config=config_with(dobot__teacher_approval=right)))


# Item 3: reach of the taught points


def test_taught_points_outside_the_reach_are_refused():
    robot = choton_settings()["robot"]
    robot["box_slots"] = [[380.0, 0.0]]
    has(problems(robot=robot), "box_slots[0] (380.0, 0.0) is 380.0 mm from the robot")
    robot = choton_settings()["robot"]
    robot["home"] = [100.0, 0.0, 135.7, -13.5]
    has(problems(robot=robot), "taught point home")


# Item 4: calibration


def test_calibration_must_be_to_the_robot_and_not_practice():
    calibration = read_json(CONFIG.path_value("calibration", "file"))
    has(problems(calibration={**calibration, "frame": "table"}), "not to the robot frame")
    has(problems(calibration={**calibration, "practice": True}), "PRACTICE")
    has(problems(calibration=None, calibration_error="file missing"), "calibration file not readable: file missing")


# Item 5: taught heights


def test_taught_heights_must_exist():
    robot = choton_settings()["robot"]
    del robot["travel_z"]
    robot["pick_z_by_type"] = {"card": 63.7}
    found = problems(robot=robot)
    has(found, "robot.travel_z is not taught")
    has(found, "robot.pick_z_by_type.candy is not taught")


def test_missing_lid_heights_need_the_operator_to_accept_an_open_box():
    robot = choton_settings(lid=False)["robot"]  # as in Choton's settings.json today
    has(problems(robot=robot), "the box will stay open")
    report = check(facts(robot=robot, operator={"hand_on_estop": True, "boxes": 1, "speed_percent": 40, "accept_open_box": True}))
    assert report.ok and any("box will stay open" in note for note in report.notes)


# Item 6: vision


def test_vision_must_be_ready():
    has(problems(vision={"model_loaded": False, "model_error": "pip install ultralytics", "frame_age_s": 0.1}), "pip install ultralytics")
    has(problems(vision={"model_loaded": True, "classes": ["card"], "frame_age_s": 0.1}), "differ from vision.classes")
    has(problems(vision={"model_loaded": True, "classes": ["card", "candy", "box", "lid"], "frame_age_s": 3.0}), "last frame 3.0 s old")
    has(problems(config=config_with(camera__index=(0, "CONFIRM"))), "camera.index = 0 is still CONFIRM")


# Item 7: robot state from the live checks


@pytest.mark.parametrize("status, words", [
    ({"state": "FAIL", "detail": "refused", "data": {"reason": "held"}}, "held by another program"),
    ({"state": "FAIL", "detail": "no answer", "data": {"reason": "unreachable"}}, "robot not ready: FAIL"),
    ({"state": "WARN", "detail": "alarm 22", "data": {"robot_mode": 9}}, "robot not ready: WARN"),
    ({"state": "OK", "detail": "x", "data": {"robot_mode": 9, "robot_mode_name": "ROBOT_MODE_ERROR"}}, "is not disabled/enabled"),
    (None, "not checked yet"),
])
def test_robot_must_be_ok_and_not_held(status, words):
    has(problems(robot_status=status), words)


# Item 8: outputs


def test_outputs_must_differ_and_match_chotons_settings():
    found = problems(config=config_with(dobot__blow_do=1))
    has(found, "use the same output DO1")
    has(found, "Choton settings robot.blow_do = 2")


def test_box_restart_by_dobot_output_needs_its_own_channel():
    has(problems(config=config_with(belts__box_restart="dobot_output")), "dobot.box_belt_do is not set")
    has(problems(config=config_with(belts__box_restart="dobot_output", dobot__box_belt_do=3)), "use the same output DO3")
    has(problems(config=config_with(belts__box_restart="dobot_output", dobot__box_belt_do=4)), "use the same output DO4")
    assert problems(config=config_with(belts__box_restart="dobot_output", dobot__box_belt_do=5)) == []


# Item 9: object belt levels


def test_belt_polarity_must_be_confirmed_and_match_choton():
    has(problems(config=config_with(dobot__belt_on_value=(1, "CONFIRM"))), "dobot.belt_on_value = 1 is still CONFIRM")
    has(problems(config=config_with(dobot__belt_on_value=0)), "Choton settings robot.belt_on = 1")


# Item 10: operator


def test_operator_must_confirm_the_emergency_stop_and_the_box_count():
    has(problems(operator={"hand_on_estop": False, "boxes": 1, "speed_percent": 40}), "hand on the emergency stop")
    has(problems(operator={"hand_on_estop": True, "boxes": 0, "speed_percent": 40}), "number of boxes")


# State timeouts and the box restart


def test_cycle_settings_must_be_set():
    has(problems(config=config_with(control__box_wait_timeout_s=None)), "control.box_wait_timeout_s is not set")
    has(problems(config=config_with(belts__box_restart="magic")), "must be one of")
    has(problems(config=config_with(belts__box_restart=None)), "belts.box_restart is not set")


# Arm tokens: one-time, 60 s, bound to the armed values


def test_tokens_work_once_expire_and_must_match():
    clock = FakeClock()
    tokens = ArmTokens(60.0, clock)
    token = tokens.issue(2, 40)
    assert tokens.redeem(token, 2, 40) == ""
    assert "no valid arm token" in tokens.redeem(token, 2, 40)  # used already
    late = tokens.issue(2, 40)
    clock.advance(61.0)
    assert "expired" in tokens.redeem(late, 2, 40)
    other = tokens.issue(2, 40)
    assert "differ from the armed ones" in tokens.redeem(other, 3, 40)
    assert "no valid arm token" in tokens.redeem(None, 2, 40)
