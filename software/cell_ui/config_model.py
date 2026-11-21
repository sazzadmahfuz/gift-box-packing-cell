"""Generic model of the JSON settings files (config.json, hardware.json). No tkinter here.

An "entry" is any dict with a "value" key; its other keys (unit, note, source, status...) are
edited beside it. Everything else is found by walking the file, so new keys appear by themselves.
Validation uses the program's own loaders, so the UI can never save a file the program rejects.
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cell_sim.config import DEFAULT_CONFIG_PATH, config_from_dict
from cell_sim.hardware_config import (
    ALLOWED_STATUS,
    DEFAULT_HARDWARE_PATH,
    check_entries,
    dobot_settings,
    robodk_settings,
)

VALUE_FIELD = "value"
STATUS_FIELD = "status"
PROVENANCE_FIELDS = ("status", "source", "note")  # what must change when a value is re-measured
Path_ = tuple[str, ...]


@dataclass(frozen=True)
class EntryRef:
    path: Path_  # keys from the file root, e.g. ("dobot", "vacuum_do")
    fields: tuple[str, ...]  # keys of the entry, "value" first


def _validate_config(raw: dict[str, Any], _path: Path) -> None:
    config_from_dict(raw)


def _validate_hardware(raw: dict[str, Any], path: Path) -> None:
    check_entries(raw)
    section_loaders = {"robodk": lambda: robodk_settings(raw), "dobot": lambda: dobot_settings(raw, path)}
    for section, load in section_loaders.items():
        if section in raw:
            load()


VALIDATORS: dict[str, Callable[[dict[str, Any], Path], None]] = {
    DEFAULT_CONFIG_PATH.name: _validate_config,
    DEFAULT_HARDWARE_PATH.name: _validate_hardware,
}
KNOWN_FILES = (DEFAULT_CONFIG_PATH, DEFAULT_HARDWARE_PATH)


class SettingsFile:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.reload()

    def reload(self) -> None:
        self.raw: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.original = copy.deepcopy(self.raw)

    # Reading

    def comments(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.raw.items() if key.startswith("_")}

    def entries(self) -> list[EntryRef]:
        found: list[EntryRef] = []
        _walk(self.raw, (), found)
        return found

    def sections(self) -> list[Path_]:
        """Paths of the dicts that hold entries, in file order (the root is ())."""
        seen: list[Path_] = []
        for ref in self.entries():
            if ref.path[:-1] not in seen:
                seen.append(ref.path[:-1])
        return seen

    def entry(self, path: Path_) -> dict[str, Any]:
        node: Any = self.raw
        for key in path:
            node = node[key]
        return node

    def field_text(self, path: Path_, field_name: str) -> str:
        value = self.entry(path).get(field_name)
        if field_name == VALUE_FIELD:
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else str(value)

    def status_choices(self) -> tuple[str, ...]:
        return ALLOWED_STATUS

    # Editing

    def set_field(self, path: Path_, field_name: str, text: str) -> None:
        """Value fields take JSON (50, "abc", null, [1, 2]); plain words are kept as text."""
        if field_name == VALUE_FIELD:
            try:
                parsed: Any = json.loads(text)
            except json.JSONDecodeError:
                parsed = text
        else:
            parsed = text
        self.entry(path)[field_name] = parsed

    def is_dirty(self) -> bool:
        return self.raw != self.original

    def changed_entries(self) -> list[Path_]:
        return [ref.path for ref in self.entries() if self.entry(ref.path) != _get(self.original, ref.path)]

    def provenance_warnings(self) -> list[str]:
        """Entries whose value changed while status/source/note stayed the same."""
        warnings = []
        for path in self.changed_entries():
            before, after = _get(self.original, path), self.entry(path)
            if before is None or before.get(VALUE_FIELD) == after.get(VALUE_FIELD):
                continue
            kept = [name for name in PROVENANCE_FIELDS if name in after and after[name] == before.get(name)]
            if kept and len(kept) == len([name for name in PROVENANCE_FIELDS if name in after]):
                warnings.append(f"{'.'.join(path)}: value changed but {', '.join(kept)} did not")
        return warnings

    # Checking and saving

    def validate(self) -> str:
        """Return "" if the program accepts the edited file, otherwise its error message."""
        validator = VALIDATORS.get(self.path.name)
        try:
            json.dumps(self.raw)
            if validator is not None:
                validator(copy.deepcopy(self.raw), self.path)
        except Exception as error:  # the loaders raise ConfigError / HardwareConfigError / ValueError
            return f"{type(error).__name__}: {error}"
        return ""

    def save(self) -> Path:
        """Validate, keep <name>.bak, write the file. Raises ValueError if validation fails."""
        problem = self.validate()
        if problem:
            raise ValueError(problem)
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        shutil.copy2(self.path, backup)
        self.path.write_text(json.dumps(self.raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.original = copy.deepcopy(self.raw)
        return backup

    def revert(self) -> None:
        self.raw = copy.deepcopy(self.original)


def _walk(node: dict[str, Any], prefix: Path_, found: list[EntryRef]) -> None:
    for key, child in node.items():
        if key.startswith("_") or not isinstance(child, dict):
            continue
        if VALUE_FIELD in child:
            others = tuple(name for name in child if name != VALUE_FIELD)
            found.append(EntryRef(prefix + (key,), (VALUE_FIELD, *others)))
        else:
            _walk(child, prefix + (key,), found)


def _get(node: Any, path: Path_) -> Any:
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node
