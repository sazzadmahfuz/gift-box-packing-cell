"""Load live_config.json. Same rules as cell_sim/hardware.json: value, unit, source, status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cell_sim.hardware_config import ALLOWED_STATUS, HardwareConfigError, check_entries

DEFAULT_LIVE_CONFIG_PATH = Path(__file__).with_name("live_config.json")
REPO_ROOT = Path(__file__).resolve().parents[2]
NULL_STATUS = ("CONFIRM", "SETTING")  # null: not known yet (CONFIRM) or deliberately not used (SETTING)


class LiveConfigError(ValueError):
    pass


class LiveConfig:
    def __init__(self, raw: dict[str, Any], path: Path = DEFAULT_LIVE_CONFIG_PATH, repo_root: Path = REPO_ROOT) -> None:
        try:
            check_entries(raw)
        except HardwareConfigError as error:
            raise LiveConfigError(str(error)) from error
        for section, key, entry in _entries(raw):
            if entry["value"] is None and entry["status"] not in NULL_STATUS:
                raise LiveConfigError(f"{section}.{key} is null, so its status must be CONFIRM (not known yet) "
                                      "or SETTING (deliberately not used)")
        self.raw = raw
        self.path = path
        self.repo_root = repo_root

    def entry(self, section: str, key: str) -> dict[str, Any]:
        try:
            return self.raw[section][key]
        except KeyError as error:
            raise LiveConfigError(f"{section}.{key} is missing from {self.path.name}") from error

    def value(self, section: str, key: str) -> Any:
        return self.entry(section, key)["value"]

    def status(self, section: str, key: str) -> str:
        return self.entry(section, key)["status"]

    def path_value(self, section: str, key: str) -> Path | None:
        """A path entry, resolved against the repo root when it is relative."""
        value = self.value(section, key)
        if value is None:
            return None
        path = Path(value)
        return path if path.is_absolute() else (self.repo_root / path).resolve()

    def poll_interval_s(self, section: str, default_s: float = 5.0) -> float:
        value = self.raw.get(section, {}).get("poll_interval_s", {}).get("value")
        return float(value) if isinstance(value, (int, float)) and value > 0 else default_s

    def unknowns(self) -> list[str]:
        """Every CONFIRM entry: what still has to be measured or decided."""
        return [f"{section}.{key}" for section, key, entry in _entries(self.raw) if entry["status"] == "CONFIRM"]


def load_live_config(path: str | Path | None = None) -> LiveConfig:
    config_path = Path(path) if path is not None else DEFAULT_LIVE_CONFIG_PATH
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LiveConfigError(f"cannot read {config_path}: {error}") from error
    return LiveConfig(raw, config_path)


def _entries(raw: dict[str, Any]):
    for section, entries in raw.items():
        if section.startswith("_") or not isinstance(entries, dict):
            continue
        for key, entry in entries.items():
            yield section, key, entry


__all__ = ["ALLOWED_STATUS", "DEFAULT_LIVE_CONFIG_PATH", "LiveConfig", "LiveConfigError", "REPO_ROOT", "load_live_config"]
