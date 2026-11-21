"""Load hardware.json. Every entry carries value, unit, source and status."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HARDWARE_PATH = Path(__file__).with_name("hardware.json")
ALLOWED_STATUS: tuple[str, ...] = ("VERIFIED", "FROM PHOTO", "ASSUMED", "CONFIRM", "SETTING")
REQUIRED_ROBODK_TARGETS: tuple[str, ...] = ("home", "pick", "place_box")
# Taught approach points replace approach_dz_mm; lid targets are needed only for the lid step.
OPTIONAL_ROBODK_TARGETS: tuple[str, ...] = (
    "pick_approach", "place_approach", "lid", "lid_on_box", "lid_approach", "lid_box_approach",
)


class HardwareConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RoboDKSettings:
    host: str
    port: int
    robot_name: str | None
    robot_name_keywords: tuple[str, ...]
    target_names: dict[str, str]  # cell target name -> RoboDK target item name
    approach_dz_mm: float
    simulation_speed: float
    attach_object_keyword: str | None
    attach_tolerance_mm: float


def load_hardware_raw(path: str | Path | None = None) -> dict[str, Any]:
    hardware_path = Path(path) if path is not None else DEFAULT_HARDWARE_PATH
    try:
        with open(hardware_path, encoding="utf-8") as hardware_file:
            raw = json.load(hardware_file)
    except (OSError, json.JSONDecodeError) as error:
        raise HardwareConfigError(f"cannot read {hardware_path}: {error}") from error
    check_entries(raw)
    return raw


def check_entries(raw: dict[str, Any]) -> None:
    """Every section entry must be {value, unit, source, status} with a known status."""
    for section_name, section in raw.items():
        if section_name.startswith("_"):
            continue
        if not isinstance(section, dict):
            raise HardwareConfigError(f"section {section_name} must be an object")
        for key, entry in section.items():
            where = f"{section_name}.{key}"
            if not isinstance(entry, dict) or set(entry) != {"value", "unit", "source", "status"}:
                raise HardwareConfigError(f"{where} must have exactly value, unit, source and status")
            if entry["status"] not in ALLOWED_STATUS:
                raise HardwareConfigError(f"{where} status {entry['status']!r} not in {ALLOWED_STATUS}")
            if not entry["source"]:
                raise HardwareConfigError(f"{where} has no source")


def robodk_settings(raw: dict[str, Any]) -> RoboDKSettings:
    section = raw.get("robodk")
    if not isinstance(section, dict):
        raise HardwareConfigError("hardware.json has no robodk section")

    def value(key: str) -> Any:
        if key not in section:
            raise HardwareConfigError(f"robodk.{key} is missing")
        return section[key]["value"]

    targets = value("target_names")
    allowed = set(REQUIRED_ROBODK_TARGETS) | set(OPTIONAL_ROBODK_TARGETS)
    if not isinstance(targets, dict) or not set(REQUIRED_ROBODK_TARGETS) <= set(targets) <= allowed:
        raise HardwareConfigError(
            f"robodk.target_names must name {list(REQUIRED_ROBODK_TARGETS)}, "
            f"optionally also {list(OPTIONAL_ROBODK_TARGETS)}"
        )
    if not all(isinstance(name, str) and name for name in targets.values()):
        raise HardwareConfigError("robodk.target_names values must be non-empty strings")
    keywords = value("robot_name_keywords")
    if not isinstance(keywords, list) or not all(isinstance(k, str) and k for k in keywords):
        raise HardwareConfigError("robodk.robot_name_keywords must be a list of strings")
    speed = value("simulation_speed")
    if not _is_number(speed) or speed <= 0:
        raise HardwareConfigError("robodk.simulation_speed must be a positive number")
    dz = value("approach_dz_mm")
    if not _is_number(dz) or dz <= 0:
        raise HardwareConfigError("robodk.approach_dz_mm must be a positive number")
    port = value("port")
    if not isinstance(port, int) or isinstance(port, bool):
        raise HardwareConfigError("robodk.port must be an integer")
    return RoboDKSettings(
        host=str(value("host")),
        port=port,
        robot_name=value("robot_name"),
        robot_name_keywords=tuple(keywords),
        target_names=dict(targets),
        approach_dz_mm=float(dz),
        simulation_speed=float(speed),
        attach_object_keyword=value("attach_object_keyword"),
        attach_tolerance_mm=float(value("attach_tolerance_mm")),
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


DOBOT_TARGETS: tuple[str, ...] = ("home", "pick_approach", "pick", "place_approach", "place_box")
DOBOT_LID_TARGETS: tuple[str, ...] = ("lid_approach", "lid", "lid_box_approach", "lid_on_box")  # optional
POSE_KEYS: tuple[str, ...] = ("x_mm", "y_mm", "z_mm", "r_deg")


@dataclass(frozen=True)
class DobotSettings:
    api_path: Path
    robot_ip: str
    dashboard_port: int
    move_port: int
    feedback_port: int
    connect_timeout_s: float
    speed_factor_percent: int | None
    vacuum_do: int | None
    targets: dict[str, tuple[float, float, float, float] | None]  # x_mm, y_mm, z_mm, r_deg
    statuses: dict[str, str]  # hardware.json key -> status
    blow_off_do: int | None = None
    blow_off_s: float = 0.0
    vacuum_on_wait_s: float = 0.0
    vacuum_off_wait_s: float = 0.0
    arm_orientation_code: int | None = None
    object_conveyor_do: int | None = None
    pick_z_by_type_mm: dict[str, float] = field(default_factory=dict)

    def missing_for_dry_run(self) -> list[str]:
        missing = [f"dobot.target_{name}" for name in DOBOT_TARGETS if self.targets.get(name) is None]
        if self.speed_factor_percent is None:
            missing.append("dobot.speed_factor_percent")
        if self.vacuum_do is None:
            missing.append("dobot.vacuum_do")
        return missing


def dobot_section(raw: dict[str, Any]) -> dict[str, Any]:
    section = raw.get("dobot")
    if not isinstance(section, dict):
        raise HardwareConfigError("hardware.json has no dobot section")
    return section


def dobot_settings(raw: dict[str, Any], hardware_path: str | Path | None = None) -> DobotSettings:
    section = dobot_section(raw)

    def value(key: str) -> Any:
        if key not in section:
            raise HardwareConfigError(f"dobot.{key} is missing")
        return section[key]["value"]

    base_dir = Path(hardware_path).resolve().parent if hardware_path else DEFAULT_HARDWARE_PATH.parent
    targets = {name: _pose(value(f"target_{name}"), f"dobot.target_{name}") for name in DOBOT_TARGETS}
    for name in DOBOT_LID_TARGETS:  # not taught yet: null or missing means the lid moves are skipped
        targets[name] = _pose(section.get(f"target_{name}", {}).get("value"), f"dobot.target_{name}")
    for key in ("dashboard_port", "move_port", "feedback_port"):
        if not isinstance(value(key), int) or isinstance(value(key), bool):
            raise HardwareConfigError(f"dobot.{key} must be an integer")
    for key in ("speed_factor_percent", "vacuum_do"):
        if value(key) is not None and (not isinstance(value(key), int) or isinstance(value(key), bool)):
            raise HardwareConfigError(f"dobot.{key} must be an integer or null")
    if not _is_number(value("connect_timeout_s")) or value("connect_timeout_s") <= 0:
        raise HardwareConfigError("dobot.connect_timeout_s must be a positive number")
    return DobotSettings(
        api_path=(base_dir / str(value("api_path"))).resolve(),
        robot_ip=str(value("robot_ip")),
        dashboard_port=value("dashboard_port"),
        move_port=value("move_port"),
        feedback_port=value("feedback_port"),
        connect_timeout_s=float(value("connect_timeout_s")),
        speed_factor_percent=value("speed_factor_percent"),
        vacuum_do=value("vacuum_do"),
        targets=targets,
        statuses={key: entry["status"] for key, entry in section.items()},
        blow_off_do=_optional_int(section, "blow_off_do"),
        blow_off_s=_optional_seconds(section, "blow_off_s"),
        vacuum_on_wait_s=_optional_seconds(section, "vacuum_on_wait_s"),
        vacuum_off_wait_s=_optional_seconds(section, "vacuum_off_wait_s"),
        arm_orientation_code=_optional_int(section, "arm_orientation_code"),
        object_conveyor_do=_optional_int(section, "object_conveyor_do"),
        pick_z_by_type_mm=_pick_heights(section),
    )


def _optional_int(section: dict[str, Any], key: str) -> int | None:
    value = section.get(key, {}).get("value")
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise HardwareConfigError(f"dobot.{key} must be an integer or null")
    return value


def _optional_seconds(section: dict[str, Any], key: str) -> float:
    value = section.get(key, {}).get("value")
    if value is None:
        return 0.0
    if not _is_number(value) or value < 0:
        raise HardwareConfigError(f"dobot.{key} must be a number of seconds >= 0 or null")
    return float(value)


def _pick_heights(section: dict[str, Any]) -> dict[str, float]:
    heights = section.get("pick_z_by_type_mm", {}).get("value") or {}
    if not isinstance(heights, dict) or not all(_is_number(z) for z in heights.values()):
        raise HardwareConfigError("dobot.pick_z_by_type_mm must map item types to heights in mm")
    return {str(kind): float(z) for kind, z in heights.items()}


def _pose(pose: Any, where: str) -> tuple[float, float, float, float] | None:
    if pose is None:
        return None
    if not isinstance(pose, dict) or set(pose) != set(POSE_KEYS):
        raise HardwareConfigError(f"{where} must be null or have exactly {list(POSE_KEYS)}")
    if any(pose[key] is None for key in POSE_KEYS):
        return None
    if not all(_is_number(pose[key]) for key in POSE_KEYS):
        raise HardwareConfigError(f"{where} values must be numbers or null")
    return tuple(float(pose[key]) for key in POSE_KEYS)  # type: ignore[return-value]
