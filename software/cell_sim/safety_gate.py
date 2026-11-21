"""Safety gate for --mode dobot-real. Standard library only; it never talks to the robot.

The real robot may start only if hardware.json has every safety value set, none of them is
ASSUMED or CONFIRM, every target lies inside the workspace limits, and the teacher approval is
recorded both in hardware.json and on the command line (--teacher-approved).
"""

from __future__ import annotations

from typing import Any

from .hardware_config import DOBOT_LID_TARGETS, DOBOT_TARGETS, POSE_KEYS

MAX_SPEED_PERCENT = 20  # team decision (integration plan); raising it needs a code change
DO_INDEX_RANGE = (1, 24)  # dobot_api.py DO() docstring: "Value range:1~24"
NOT_ALLOWED_FOR_REAL = ("ASSUMED", "CONFIRM")
LIMIT_AXES = (("x", "mm"), ("y", "mm"), ("z", "mm"), ("r", "deg"))


class SafetyGateRefused(RuntimeError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"dobot-real refused to start ({len(problems)} problem(s)):\n{lines}")


def check_real_robot_allowed(section: dict[str, Any], teacher_flag: bool) -> list[str]:
    """Return every reason the real robot must not start. An empty list means allowed."""
    problems: list[str] = []

    def entry(key: str) -> dict[str, Any] | None:
        found = section.get(key)
        if not isinstance(found, dict) or "value" not in found:
            problems.append(f"dobot.{key} is missing from hardware.json")
            return None
        if found.get("status") in NOT_ALLOWED_FOR_REAL:
            problems.append(f"dobot.{key} has status {found.get('status')}: measure or confirm it first")
        return found

    for key in ("robot_ip", "dashboard_port", "move_port"):
        found = entry(key)
        if found is not None and found["value"] in (None, ""):
            problems.append(f"dobot.{key} is null")

    _check_int(entry("speed_factor_percent"), "speed_factor_percent", (1, MAX_SPEED_PERCENT), problems)
    _check_int(entry("vacuum_do"), "vacuum_do", DO_INDEX_RANGE, problems)
    _check_int(entry("arm_orientation_code"), "arm_orientation_code", (0, 1), problems)
    for optional_output in ("blow_off_do", "object_conveyor_do"):  # checked only if hardware.json has them
        if optional_output in section:
            _check_int(entry(optional_output), optional_output, DO_INDEX_RANGE, problems)
    _check_distinct_outputs(section, problems)
    limits = _check_limits(entry("workspace_limits"), problems)
    for name in DOBOT_TARGETS + DOBOT_LID_TARGETS:  # the cycle closes the box, so the lid targets count
        _check_target(entry(f"target_{name}"), name, limits, problems)

    approval = entry("teacher_approval")
    if approval is not None and not (isinstance(approval["value"], str) and approval["value"].strip()):
        problems.append("dobot.teacher_approval is null: record the teacher's name and the date")
    if not teacher_flag:
        problems.append("the --teacher-approved flag is missing")
    return problems


def require_real_robot_allowed(section: dict[str, Any], teacher_flag: bool) -> None:
    problems = check_real_robot_allowed(section, teacher_flag)
    if problems:
        raise SafetyGateRefused(problems)


def _check_int(found: dict[str, Any] | None, key: str, allowed: tuple[int, int], problems: list[str]) -> None:
    if found is None:
        return
    value = found["value"]
    if value is None:
        problems.append(f"dobot.{key} is null")
    elif not isinstance(value, int) or isinstance(value, bool) or not allowed[0] <= value <= allowed[1]:
        problems.append(f"dobot.{key} is {value!r}; it must be an integer from {allowed[0]} to {allowed[1]}")


def _check_distinct_outputs(section: dict[str, Any], problems: list[str]) -> None:
    used: dict[int, str] = {}
    for key in ("vacuum_do", "blow_off_do", "object_conveyor_do"):
        value = section.get(key, {}).get("value") if isinstance(section.get(key), dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            if value in used:
                problems.append(f"dobot.{key} and dobot.{used[value]} use the same output DO{value}")
            used[value] = key


def _check_limits(found: dict[str, Any] | None, problems: list[str]) -> dict[str, tuple[float, float]] | None:
    if found is None:
        return None
    value = found["value"]
    if not isinstance(value, dict):
        problems.append("dobot.workspace_limits is null")
        return None
    limits: dict[str, tuple[float, float]] = {}
    for axis, unit in LIMIT_AXES:
        low, high = value.get(f"{axis}_min_{unit}"), value.get(f"{axis}_max_{unit}")
        if not _is_number(low) or not _is_number(high):
            problems.append(f"dobot.workspace_limits.{axis}_min_{unit}/{axis}_max_{unit} is null or not a number")
        elif low >= high:
            problems.append(f"dobot.workspace_limits {axis}: min {low} is not below max {high}")
        else:
            limits[f"{axis}_{unit}"] = (float(low), float(high))
    return limits if len(limits) == len(LIMIT_AXES) else None


def _check_target(
    found: dict[str, Any] | None, name: str, limits: dict[str, tuple[float, float]] | None, problems: list[str]
) -> None:
    if found is None:
        return
    pose = found["value"]
    if not isinstance(pose, dict) or any(not _is_number(pose.get(key)) for key in POSE_KEYS):
        problems.append(f"dobot.target_{name} is null or incomplete")
        return
    if limits is None:
        return
    for key in POSE_KEYS:
        low, high = limits[key]
        if not low <= pose[key] <= high:
            problems.append(f"dobot.target_{name}.{key} = {pose[key]} is outside the workspace limits [{low}, {high}]")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
