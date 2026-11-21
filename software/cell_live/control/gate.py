"""Safety gate in front of every real run. Standard library only, no network.

check(facts) lists every reason a run must not start (items 1-10 below,
plus the state timeouts and the box restart). An empty list means the operator may get a
one-time arm token. A missing value, or one still marked CONFIRM or ASSUMED, refuses the start.
Points and heights are read from Choton's settings.json each time and compared with our config.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .tokens import ArmTokens  # noqa: F401 (re-exported: gate.ArmTokens)

NOT_FOR_A_RUN = ("CONFIRM", "ASSUMED")
BOX_RESTART_MODES = ("dobot_output", "nano_auto", "operator")
ROBOT_MODES_OK = (4, 5)  # ROBOT_MODE_DISABLED, ROBOT_MODE_ENABLE (Dobot ui.py LABEL_ROBOT_MODE)
DO_RANGE = (1, 24)  # dobot_api.py DO() docstring
OUTPUT_KEYS = (("vacuum_do", "vacuum_do"), ("blow_do", "blow_do"), ("belt_do", "belt_do"),  # ours, Choton's
               ("belt_dir_do", None), ("belt_enable_do", None))  # None: not in Choton's settings
LEVEL_KEYS = (("belt_on_value", "belt_on"), ("belt_dir_forward_value", None), ("belt_enable_on_value", None))


@dataclass
class GateFacts:
    config: Any  # cell_live LiveConfig
    choton_robot: dict[str, Any] | None  # settings.json "robot" block, read just now
    choton_error: str = ""
    box_contents: dict[str, int] | None = None
    calibration: dict[str, Any] | None = None  # homography.json, read just now
    calibration_error: str = ""
    vision: dict[str, Any] = field(default_factory=dict)  # model_loaded, model_error, classes, frame_age_s, camera_error
    robot_status: dict[str, Any] | None = None  # the dobot_dashboard check's status
    operator: dict[str, Any] = field(default_factory=dict)  # hand_on_estop, boxes, speed_percent, accept_open_box


@dataclass
class GateReport:
    problems: list[str]
    notes: list[str]
    items: list[dict[str, Any]] = field(default_factory=list)  # one per gate item, for the live checklist

    @property
    def ok(self) -> bool:
        return not self.problems


def confirmed(config: Any, section: str, key: str, problems: list[str]) -> Any:
    """The value if it is set and confirmed; otherwise None and a problem saying why."""
    entry = config.raw.get(section, {}).get(key)
    if entry is None:
        problems.append(f"{section}.{key} is missing from live_config.json")
        return None
    if entry["value"] is None:
        problems.append(f"{section}.{key} is not set ({entry['status']}): {entry['unit']}")
        return None
    if entry["status"] in NOT_FOR_A_RUN:
        problems.append(f"{section}.{key} = {entry['value']!r} is still {entry['status']}: confirm it in the lab")
        return None
    return entry["value"]


def _is_int(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def radius_mm(x_mm: float, y_mm: float) -> float:
    return math.hypot(x_mm, y_mm)


# Item 1: speed
def check_speed(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    speed = confirmed(facts.config, "dobot", "speed_percent", problems)
    top = confirmed(facts.config, "control", "speed_percent_max", problems)
    for name, value in (("dobot.speed_percent", speed), ("control.speed_percent_max", top)):
        if value is not None and not _is_int(value, 1, 100):
            problems.append(f"{name} = {value!r} must be a whole number from 1 to 100")
    requested = facts.operator.get("speed_percent", speed)
    if not _is_int(top, 1, 100):
        return
    if _is_int(speed, 1, 100) and speed > top:
        problems.append(f"dobot.speed_percent {speed} % is above control.speed_percent_max {top} %")
    if requested is not None and (not _is_int(requested, 1, 100) or requested > top):
        problems.append(f"requested speed {requested!r} % is not allowed (1 to {top} %)")


# Item 2: teacher approval
APPROVAL_DATE = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}\.(\d{2,4})?|\d{1,2} ?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)",
                           re.IGNORECASE)


def looks_like_approval(text: Any) -> bool:
    """A teacher's name (a word of letters) and a date (2026-11-17, 17.11.2026 or 17 Nov)."""
    without_date = APPROVAL_DATE.sub(" ", text) if isinstance(text, str) else ""
    return bool(without_date != text and re.search(r"[^\W\d_]{2,}", without_date))  # a date was found, and a name: 2+ letters


def check_teacher(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    approval = confirmed(facts.config, "dobot", "teacher_approval", problems)
    if approval is not None and not looks_like_approval(approval):
        problems.append(f"dobot.teacher_approval = {approval!r} must hold the teacher's name and the date (for example 'Name, 2026-11-17')")


# Item 3: reach of the taught points (objects and the lid are checked at run time)
def check_reach(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    low = confirmed(facts.config, "control", "reach_min_mm", problems)
    high = confirmed(facts.config, "control", "reach_max_mm", problems)
    robot = facts.choton_robot or {}
    if not (_is_number(low) and _is_number(high) and low < high) or not robot:
        return
    points = []
    if _point(robot.get("home"), 2):
        points.append(("home", robot["home"][0], robot["home"][1]))
    for index, slot in enumerate(robot.get("box_slots") or []):
        if _point(slot, 2):
            points.append((f"box_slots[{index}]", slot[0], slot[1]))
    for name, x_mm, y_mm in points:
        distance = radius_mm(x_mm, y_mm)
        if not low <= distance <= high:
            problems.append(f"taught point {name} ({x_mm}, {y_mm}) is {distance:.1f} mm from the robot, outside {low}-{high} mm")


# Item 4: calibration
def check_calibration(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    calibration = facts.calibration
    if calibration is None:
        problems.append(f"calibration file not readable: {facts.calibration_error or 'missing'}")
        return
    if calibration.get("frame") != "robot":
        problems.append("calibration is not to the robot frame (homography.json 'frame' must be 'robot')")
    if calibration.get("practice") or (facts.choton_robot or {}).get("_practice"):
        problems.append("calibration or robot points are from PRACTICE (--sim): redo 15_robot_setup.py on the real robot")
    valid_from = confirmed(facts.config, "calibration", "valid_from", problems)
    made = str(calibration.get("created") or "")[:10]
    if valid_from and made < str(valid_from):
        problems.append(f"calibration made {made or 'on an unknown date'}, before the current worktable and camera stand "
                        f"({valid_from}): commit Choton's new homography.json and settings.json")


# Item 5: taught heights and points
def check_heights(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    robot = facts.choton_robot
    if robot is None:
        problems.append(f"Choton's settings.json not readable: {facts.choton_error or 'missing'}")
        return
    for key in ("travel_z", "place_z"):
        if not _is_number(robot.get(key)):
            problems.append(f"Choton settings robot.{key} is not taught")
    by_type = robot.get("pick_z_by_type") or {}
    for kind in ("card", "candy"):
        if not _is_number(by_type.get(kind)):
            problems.append(f"Choton settings robot.pick_z_by_type.{kind} is not taught")
    if not robot.get("box_slots") or not all(_point(slot, 2) for slot in robot["box_slots"]):
        problems.append("Choton settings robot.box_slots is not taught")
    if not _point(robot.get("home"), 4):
        problems.append("Choton settings robot.home is not taught")
    close_lid = confirmed(facts.config, "control", "close_lid", problems)
    if close_lid and not (_is_number(robot.get("lid_pick_z")) and _is_number(robot.get("lid_place_z"))):
        if facts.operator.get("accept_open_box"):
            notes.append("lid heights not taught: the box will stay open (accepted by the operator)")
        else:
            problems.append("lid heights not taught (robot.lid_pick_z, lid_place_z): the box will stay open. "
                            "Tick 'accept open box' to run without the lid")


# Item 6: vision
def check_vision(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    vision = facts.vision
    confirmed(facts.config, "camera", "index", problems)
    if not vision.get("model_loaded"):
        problems.append(f"vision model not loaded: {vision.get('model_error') or 'unknown reason'}")
    else:
        wanted = facts.config.value("vision", "classes")
        if sorted(vision.get("classes") or []) != sorted(wanted):
            problems.append(f"model classes {vision.get('classes')} differ from vision.classes {wanted}")
    max_age_s = facts.config.value("control", "camera_frame_max_age_s")
    age_s = vision.get("frame_age_s")
    if age_s is None or age_s > max_age_s:
        reason = vision.get("camera_error") or ("no frame yet" if age_s is None else f"last frame {age_s:.1f} s old")
        problems.append(f"camera has no frame in the last {max_age_s:g} s: {reason}")


# Item 7: robot state from the live checks
def check_robot(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    status = facts.robot_status
    if status is None:
        problems.append("robot status not checked yet (robot dashboard check)")
        return
    data = status.get("data") or {}
    if data.get("reason") == "held":
        problems.append("robot is held by another program (close DobotStudio or Choton's script)")
    elif status.get("state") != "OK":
        problems.append(f"robot not ready: {status.get('state')} - {status.get('detail')}")
    elif data.get("robot_mode") not in ROBOT_MODES_OK:
        problems.append(f"robot mode {data.get('robot_mode')} {data.get('robot_mode_name', '')} is not disabled/enabled")
    robot_ip = (facts.choton_robot or {}).get("ip")
    if robot_ip and robot_ip != facts.config.value("dobot", "ip"):
        problems.append(f"Choton settings robot.ip {robot_ip} differs from dobot.ip {facts.config.value('dobot', 'ip')}")


# Item 8: outputs set, valid, different, and the same as in Choton's settings
def check_outputs(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    robot = facts.choton_robot or {}
    channels: dict[str, int] = {}
    for ours, his in OUTPUT_KEYS:
        value = confirmed(facts.config, "dobot", ours, problems)
        if value is None:
            continue
        if not _is_int(value, *DO_RANGE):
            problems.append(f"dobot.{ours} = {value!r} is not an output 1-24")
            continue
        if robot and his and robot.get(his) != value:
            problems.append(f"dobot.{ours} = {value} but Choton settings robot.{his} = {robot.get(his)}")
        channels[ours] = value
    restart = facts.config.value("belts", "box_restart")
    if restart == "dobot_output":
        value = confirmed(facts.config, "dobot", "box_belt_do", problems)
        if value is not None and _is_int(value, *DO_RANGE):
            channels["box_belt_do"] = value
    seen: dict[int, str] = {}
    for name, value in channels.items():
        if value in seen:
            problems.append(f"dobot.{name} and dobot.{seen[value]} use the same output DO{value}")
        seen[value] = name


# Item 9: object belt levels (DO3 runs, DO4 forward, DO16 enabled), each from a lab test (T4, T7, T5)
def check_belt_levels(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    robot = facts.choton_robot or {}
    for ours, his in LEVEL_KEYS:
        value = confirmed(facts.config, "dobot", ours, problems)
        if value is None:
            continue
        if value not in (0, 1):
            problems.append(f"dobot.{ours} = {value!r} must be 0 or 1")
        elif his and robot.get(his) is not None and robot.get(his) != value:
            problems.append(f"dobot.{ours} = {value} but Choton settings robot.{his} = {robot.get(his)}")


# Item 10: operator
def check_operator(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    if facts.operator.get("hand_on_estop") is not True:
        problems.append("tick 'hand on the emergency stop' (the physical button is the real stop)")
    if not _is_int(facts.operator.get("boxes"), 1, 1000):
        problems.append("type the number of boxes (1 or more)")


# State timeouts and the box restart
def check_cycle_settings(facts: GateFacts, problems: list[str], notes: list[str]) -> None:
    for key in ("box_wait_timeout_s", "box_leave_timeout_s", "object_feed_timeout_s"):
        value = confirmed(facts.config, "control", key, problems)
        if value is not None and not (_is_number(value) and value > 0):
            problems.append(f"control.{key} = {value!r} must be a positive number of seconds")
    restart = confirmed(facts.config, "belts", "box_restart", problems)
    if restart is not None and restart not in BOX_RESTART_MODES:
        problems.append(f"belts.box_restart = {restart!r} must be one of {list(BOX_RESTART_MODES)}")
    robot = facts.choton_robot or {}
    if robot.get("r_sign", 1) != 1:  # 1 is verified: 17 Nov, live_runs/20261117_220813.csv, a candy at +72 deg, turned -70 deg, lay along the box
        notes.append(f"r_sign = {robot.get('r_sign')} (which way R+ turns the tool) is not the verified value 1: watch the first turned object")
    if facts.box_contents is not None and facts.box_contents != {"card": 1, "candy": 2}:
        notes.append(f"Choton settings box_contents = {facts.box_contents}, not 1 card + 2 candies")
    if robot.get("require_different_colors"):
        notes.append("require_different_colors is on: two candies of the same colour will not both be picked")


CHECKS: tuple[Callable[[GateFacts, list[str], list[str]], None], ...] = (
    check_speed, check_teacher, check_reach, check_calibration, check_heights,
    check_vision, check_robot, check_outputs, check_belt_levels, check_operator, check_cycle_settings,
)


ITEM_TITLES = (
    "Speed set and within the maximum", "Teacher approval recorded", "Taught points inside the reach",
    "Calibration to the robot, not practice", "Taught heights (and the lid)", "Vision: model, classes, fresh frame",
    "Robot OK, not held by another program", "Outputs set, different, as in Choton's settings",
    "Object belt levels confirmed (DO3, DO4, DO16)", "Operator: hand on the e-stop, box count", "State timeouts and box restart set",
)


def check(facts: GateFacts) -> GateReport:
    problems: list[str] = []
    notes: list[str] = []
    items = []
    for number, (item, title) in enumerate(zip(CHECKS, ITEM_TITLES), start=1):
        before = len(problems)
        item(facts, problems, notes)
        items.append({"number": number, "title": title, "ok": len(problems) == before, "problems": problems[before:]})
    return GateReport(problems, notes, items)


def _point(value: Any, size: int) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= size and all(_is_number(v) for v in value[:size])
