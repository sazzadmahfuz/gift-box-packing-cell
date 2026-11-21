"""Read-only access to Choton's code and files by path. Nothing in his folder is changed.

The checks read his JSON files (settings, calibration, Dobot's alarm lists). Real control loads his
modules (robot_lib, vision_lib, yolo_lib and the helpers of 14_pick_and_place.py) by path and
calls them; his main() is never called. Loading them needs opencv and numpy.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

CHOTON_MODULES = ("robot_lib", "vision_lib", "yolo_lib")
PICK_SCRIPT = "14_pick_and_place.py"  # loaded only for straighten_turn; its main() never runs
_loaded: dict[Path, SimpleNamespace] = {}


class ChotonCodeUnavailable(RuntimeError):
    """His folder, one of his files, or a package his code needs (opencv, numpy) is missing."""


def load_choton_modules(folder: Path, names: tuple[str, ...] = CHOTON_MODULES, with_script: bool = True) -> SimpleNamespace:
    """His modules import each other by plain name (import vision_lib as vl), so his folder is
    put on sys.path. The same module objects are returned on every call."""
    folder = Path(folder).resolve()
    cached = _loaded.get(folder)
    if cached is not None and all(hasattr(cached, name) for name in names) and (not with_script or hasattr(cached, "pick")):
        return cached
    if not (folder / "robot_lib.py").is_file():
        raise ChotonCodeUnavailable(f"Choton's code not found in {folder} (choton.folder in live_config.json)")
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    modules: dict[str, ModuleType] = {}
    try:
        for name in names:
            modules[name] = importlib.import_module(name)
        if with_script:
            modules["pick"] = _load_script(folder / PICK_SCRIPT)
    except ImportError as error:  # opencv / numpy missing
        raise ChotonCodeUnavailable(f"Choton's code needs a package that is missing ({error}). "
                                    "Install it with: python -m pip install opencv-python numpy") from error
    namespace = cached or SimpleNamespace(folder=folder)
    for name, module in modules.items():
        setattr(namespace, name, module)
    _loaded[folder] = namespace
    return namespace


def _load_script(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("choton_pick_and_place", path)
    if spec is None or spec.loader is None:
        raise ChotonCodeUnavailable(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # defines functions only; main() runs only as __main__
    return module

CONTROLLER_ALARMS_FILE = "alarm_controller.json"  # Dobot's lists, as shipped in Choton's code/files
SERVO_ALARMS_FILE = "alarm_servo.json"


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as json_file:
        return json.load(json_file)


class AlarmTexts:
    """Turns Dobot alarm ids into words. GetErrorID lists controller ids first, then one list per joint."""

    def __init__(self, folder: Path | None) -> None:
        self.controller: dict[int, str] = {}
        self.servo: dict[int, str] = {}
        self.problem = ""
        if folder is None:
            self.problem = "alarm list folder not set"
            return
        try:
            self.controller = _by_id(read_json(folder / CONTROLLER_ALARMS_FILE))
            self.servo = _by_id(read_json(folder / SERVO_ALARMS_FILE))
        except (OSError, ValueError) as error:
            self.problem = f"alarm lists not readable in {folder}: {error}"

    def describe(self, alarm_lists: list[list[int]]) -> list[str]:
        words = []
        for position, ids in enumerate(alarm_lists):
            table, where = (self.controller, "controller") if position == 0 else (self.servo, f"joint {position}")
            for alarm_id in ids:
                words.append(f"{where} alarm {alarm_id}: {table.get(alarm_id, 'no text in the alarm list')}")
        return words


def parse_error_lists(inside: str) -> list[list[int]]:
    """'[[22],[],[],[],[],[]]' (the part between the braces of a GetErrorID reply) -> lists of ids."""
    text = inside.strip()
    if not text:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError(f"unexpected GetErrorID content {inside!r}")
    return [[int(alarm_id) for alarm_id in group] if isinstance(group, list) else [int(group)] for group in parsed]


def _by_id(entries: Any) -> dict[int, str]:
    table: dict[int, str] = {}
    for entry in entries:
        english = entry.get("en", {}) if isinstance(entry, dict) else {}
        if "id" in entry:
            table[int(entry["id"])] = english.get("description", "") or "(no description)"
    return table
