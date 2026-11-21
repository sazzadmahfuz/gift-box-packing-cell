"""Settings screen: read live_config.json and save the lab fields, validated. Standard library only.

Only the lab fields can be changed (the ones that were CONFIRM when the console was built, and the
object belt outputs added with the 17 Nov wiring). A save
must bring a new source, and a status that is not CONFIRM (unless the value is null). The edited
file must pass the LiveConfig loader; the old file is kept as live_config.json.bak.
Choton's settings.json is never written: it belongs to his folder.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Callable

from .control.gate import BOX_RESTART_MODES, looks_like_approval
from .live_config import ALLOWED_STATUS, LiveConfig, LiveConfigError, load_live_config

LAB_FIELDS: dict[str, tuple] = {  # section.key -> type rule
    "dobot.speed_percent": ("int", 1, 100),
    "control.speed_percent_max": ("int", 1, 100),
    "dobot.teacher_approval": ("approval",),
    "camera.index": ("int", 0, 9),
    "dobot.belt_on_value": ("int", 0, 1),
    "dobot.box_belt_do": ("int", 1, 24),
    "dobot.belt_dir_do": ("int", 1, 24),
    "dobot.belt_dir_forward_value": ("int", 0, 1),
    "dobot.belt_enable_do": ("int", 1, 24),
    "dobot.belt_enable_on_value": ("int", 0, 1),
    "dobot.do_bit_order": ("text",),
    "dobot.feedback_readable_while_held": ("bool",),
    "control.box_wait_timeout_s": ("number", 1, 3600),
    "control.box_leave_timeout_s": ("number", 1, 3600),
    "control.feed_stop_y_mm": ("number", -400, 400),
    "belts.box_restart": ("choice", BOX_RESTART_MODES),
    "arduino.serial_port": ("text",),
    "arduino.baud": ("int", 300, 2_000_000),
    "arduino.status_command": ("text",),
    "arduino.sensor_active_level": ("int", 0, 1),
}


def check_type(rule: tuple, value: Any) -> str:
    """'' if the value fits the rule; otherwise why not. null is always allowed (status CONFIRM)."""
    if value is None:
        return ""
    kind = rule[0]
    if kind in ("int", "number"):
        whole = isinstance(value, int) and not isinstance(value, bool)
        number = whole or (kind == "number" and isinstance(value, float))
        if not number:
            return f"must be a {'whole number' if kind == 'int' else 'number'}"
        if not rule[1] <= value <= rule[2]:
            return f"must be from {rule[1]} to {rule[2]}"
    elif kind == "bool" and not isinstance(value, bool):
        return "must be true or false"
    elif kind == "text" and not (isinstance(value, str) and value.strip()):
        return "must be a non-empty text"
    elif kind == "approval" and not looks_like_approval(value):
        return "must hold the teacher's name and the date, for example 'Name, 2026-11-17'"
    elif kind == "choice" and value not in rule[1]:
        return f"must be one of {list(rule[1])}"
    return ""


def format_config(raw: dict[str, Any]) -> str:
    """The same layout as the committed file: one entry per line."""
    lines = ["{"]
    sections = list(raw.items())
    for index, (section, entries) in enumerate(sections):
        comma = "," if index < len(sections) - 1 else ""
        if section.startswith("_"):
            lines.append(f"  {json.dumps(section)}: {json.dumps(entries, ensure_ascii=False)}{comma}")
            continue
        lines.append(f"  {json.dumps(section)}: {{")
        items = list(entries.items())
        for position, (key, entry) in enumerate(items):
            inner = "," if position < len(items) - 1 else ""
            lines.append(f"    {json.dumps(key)}: {json.dumps(entry, ensure_ascii=False)}{inner}")
        lines.append(f"  }}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


class ConfigStore:
    def __init__(self, config_source: Callable[[], LiveConfig]) -> None:
        self.config_source = config_source

    def describe(self) -> dict[str, Any]:
        config = self.config_source()
        entries = []
        for section, keys in config.raw.items():
            if section.startswith("_"):
                continue
            for key, entry in keys.items():
                name = f"{section}.{key}"
                rule = LAB_FIELDS.get(name)
                entries.append({"section": section, "key": key, **entry, "editable": rule is not None,
                                "type": rule[0] if rule else None,
                                "choices": list(rule[1]) if rule and rule[0] == "choice" else None})
        return {"file": str(config.path), "entries": entries, "allowed_status": list(ALLOWED_STATUS),
                "unconfirmed": config.unknowns()}

    def save(self, body: dict[str, Any]) -> dict[str, Any]:
        """Apply one edit to the file as it is on disk now, so changes made to the file after the
        backend loaded it are kept (the backend's own copy may be older)."""
        try:
            config = load_live_config(self.config_source().path)
        except LiveConfigError as error:
            return {"saved": False, "problems": [f"live_config.json on disk does not load: {error}"]}
        section, key = body.get("section"), body.get("key")
        name = f"{section}.{key}"
        problems = []
        rule = LAB_FIELDS.get(name)
        if rule is None:
            return {"saved": False, "problems": [f"{name} is not a lab field: it cannot be changed from the UI"]}
        old = config.raw[section][key]
        value, status, source = body.get("value"), body.get("status"), (body.get("source") or "").strip()
        problem = check_type(rule, value)
        if problem:
            problems.append(f"{name} {problem}")
        if status not in ALLOWED_STATUS:
            problems.append(f"status must be one of {list(ALLOWED_STATUS)}")
        elif value is not None and status == "CONFIRM":
            problems.append("a value from the lab needs a status other than CONFIRM (for example VERIFIED)")
        if not source or source == old["source"]:
            problems.append("write where the value comes from (new source, for example 'lab 17 Nov, Rashmika')")
        if problems:
            return {"saved": False, "problems": problems}
        raw = copy.deepcopy(config.raw)
        raw[section][key] = {"value": value, "unit": old["unit"], "source": source, "status": status if value is not None else "CONFIRM"}
        try:
            LiveConfig(raw, config.path)
        except LiveConfigError as error:
            return {"saved": False, "problems": [str(error)]}
        backup = Path(str(config.path) + ".bak")
        shutil.copy2(config.path, backup)
        Path(config.path).write_text(format_config(raw), encoding="utf-8")
        return {"saved": True, "entry": name, "backup": backup.name, "problems": []}
