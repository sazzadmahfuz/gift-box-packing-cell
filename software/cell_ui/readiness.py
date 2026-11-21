"""Offline readiness checks for each mode (no tkinter, no hardware contact).

The one network touch is a TCP connect to RoboDK on this PC (localhost), closed at once.
Modes the UI does not know yet get a neutral "no offline check" note instead of an error.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from cell_sim.config import load_config, load_raw_config
from cell_sim.hardware_config import dobot_section, dobot_settings, load_hardware_raw, robodk_settings
from cell_sim.safety_gate import check_real_robot_allowed

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"


@dataclass
class Check:
    name: str
    level: str
    messages: list[str] = field(default_factory=list)


def _attempt(name: str, action: Callable[[], list[str] | None]) -> Check:
    try:
        notes = action() or []
    except Exception as error:  # loaders raise ConfigError / HardwareConfigError / OSError
        return Check(name, FAIL, [f"{type(error).__name__}: {error}"])
    return Check(name, WARN if notes else OK, notes or ["OK"])


def config_checks(config_path: Path | None) -> list[Check]:
    def assumed_notes() -> list[str]:
        load_config(config_path)
        raw = load_raw_config(config_path)
        assumed = [key for key, entry in raw.items() if isinstance(entry, dict) and "ASSUMED" in str(entry.get("note", ""))]
        return [f"{len(assumed)} values are ASSUMED placeholders: results are SIMULATION only"] if assumed else []

    return [_attempt("config.json loads", assumed_notes)]


def localhost_port_open(port: int, host: str = "localhost", timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def robodk_checks(hardware_path: Path | None, port_open: Callable[[int, str], bool]) -> list[Check]:
    checks = [_attempt("hardware.json robodk section", lambda: robodk_settings(load_hardware_raw(hardware_path)) and None)]
    if checks[0].level == FAIL:
        return checks
    settings = robodk_settings(load_hardware_raw(hardware_path))
    if port_open(settings.port, settings.host):
        checks.append(Check("RoboDK API answers", OK, [f"{settings.host}:{settings.port} is open"]))
    else:
        checks.append(Check("RoboDK API answers", FAIL, [
            f"nothing answers at {settings.host}:{settings.port}",
            "Open RoboDK with the cell station; if it is open, its API server is off (see README, RoboDK).",
        ]))
    return checks


def dobot_dry_checks(hardware_path: Path | None) -> list[Check]:
    def needed() -> list[str]:
        settings = dobot_settings(load_hardware_raw(hardware_path), hardware_path)
        missing = settings.missing_for_dry_run()
        if missing:
            raise ValueError(f"null values: {missing}")
        if not settings.api_path.is_file():
            raise FileNotFoundError(f"dobot_api.py not found at {settings.api_path}")
        assumed = sorted(key for key, status in settings.statuses.items() if status in ("ASSUMED", "CONFIRM"))
        return [f"command values still ASSUMED/CONFIRM (fine for a dry run): {', '.join(assumed)}"] if assumed else []

    return [_attempt("dobot-dry values present", needed)]


def dobot_real_checks(hardware_path: Path | None) -> list[Check]:
    try:
        problems = check_real_robot_allowed(dobot_section(load_hardware_raw(hardware_path)), teacher_flag=True)
    except Exception as error:
        return [Check("dobot-real safety gate", FAIL, [f"{type(error).__name__}: {error}"])]
    if problems:
        return [Check("dobot-real safety gate", FAIL, problems + ["(the --teacher-approved flag is also required)"])]
    return [Check("dobot-real safety gate", WARN, [
        "hardware.json passes the gate; the run also needs --teacher-approved.",
        "The CLI decides what happens next (the real motion path may not be implemented yet).",
    ])]


def mode_checks(
    mode: str,
    config_path: Path | None = None,
    hardware_path: Path | None = None,
    port_open: Callable[[int, str], bool] = lambda port, host: localhost_port_open(port, host),
) -> list[Check]:
    checks = config_checks(config_path)
    per_mode: dict[str, Callable[[], list[Check]]] = {
        "sim": lambda: [],
        "robodk": lambda: robodk_checks(hardware_path, port_open),
        "dobot-dry": lambda: dobot_dry_checks(hardware_path),
        "dobot-real": lambda: dobot_real_checks(hardware_path),
    }
    if mode in per_mode:
        return checks + per_mode[mode]()
    return checks + [Check(f"{mode}", INFO, ["no offline check defined for this mode; run it to see"])]


def overall_level(checks: list[Check]) -> str:
    levels = [check.level for check in checks]
    for level in (FAIL, WARN, INFO):
        if level in levels:
            return level
    return OK
