"""Load and check the cell parameters in config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .controller import TIMEOUT_STATES, State

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")

POSITIVE_NUMBER_KEYS: tuple[str, ...] = (
    "belt_a_speed_mm_s",
    "item_spacing_mm",
    "pick_area_length_mm",
    "set_confirm_time_s",
    "detection_time_s",
    "pictures_time_s",
    "pick_time_s",
    "move_to_box_time_s",
    "place_time_s",
    "lid_time_s",
    "belt_b_speed_mm_s",
    "box_start_to_s1_mm",
    "box_removal_time_s",
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CellConfig:
    items_per_box: tuple[str, ...]
    random_seed: int
    belt_a_speed_mm_s: float
    item_spacing_mm: float
    pick_area_length_mm: float
    set_confirm_time_s: float
    detection_time_s: float
    pictures_time_s: float
    pick_time_s: float
    move_to_box_time_s: float
    place_time_s: float
    lid_time_s: float
    belt_b_speed_mm_s: float
    box_start_to_s1_mm: float
    box_removal_time_s: float
    timeouts_s: dict[State, float]

    @property
    def item_spacing_time_s(self) -> float:
        return self.item_spacing_mm / self.belt_a_speed_mm_s

    @property
    def time_in_pick_area_s(self) -> float:
        """How long a moving item stays fully inside the pick area."""
        return self.pick_area_length_mm / self.belt_a_speed_mm_s

    @property
    def box_to_s1_time_s(self) -> float:
        return self.box_start_to_s1_mm / self.belt_b_speed_mm_s

    def nominal_time_s(self, state: State) -> float:
        """Shortest time each waiting state needs in normal operation."""
        return {
            State.WAIT_BOX: self.box_to_s1_time_s + self.detection_time_s,
            State.FEED_SET: len(self.items_per_box) * self.item_spacing_time_s + self.set_confirm_time_s,
            State.DETECT: self.move_to_box_time_s + self.pictures_time_s,  # worst case: robot still returning
            State.PICK: self.move_to_box_time_s + self.pick_time_s,
            State.PLACE: self.move_to_box_time_s + self.place_time_s,
            State.CLOSE_LID: self.move_to_box_time_s + self.lid_time_s,
            State.RELEASE_BOX: self.box_removal_time_s,
        }[state]


def load_raw_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with open(config_path, encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read config {config_path}: {error}") from error


def load_config(path: str | Path | None = None) -> CellConfig:
    return config_from_dict(load_raw_config(path))


def config_from_dict(raw: dict[str, Any]) -> CellConfig:
    items = _value(raw, "items_per_box")
    if not isinstance(items, list) or not items:
        raise ConfigError("items_per_box must be a non-empty list")
    if not all(isinstance(item, str) and item for item in items):
        raise ConfigError("items_per_box entries must be non-empty strings")

    seed = _value(raw, "random_seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ConfigError("random_seed must be an integer")

    numbers = {key: _positive_number(raw, key) for key in POSITIVE_NUMBER_KEYS}
    config = CellConfig(
        items_per_box=tuple(items),
        random_seed=seed,
        timeouts_s=_timeouts(raw),
        **numbers,
    )
    _check_timing(config)
    return config


def _value(raw: dict[str, Any], key: str) -> Any:
    entry = raw.get(key)
    if not isinstance(entry, dict) or not {"value", "unit", "note"} <= entry.keys():
        raise ConfigError(f"{key} must be an object with 'value', 'unit' and 'note'")
    return entry["value"]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_number(raw: dict[str, Any], key: str) -> float:
    value = _value(raw, key)
    if not _is_number(value) or value <= 0:
        raise ConfigError(f"{key} must be a positive number, got {value!r}")
    return float(value)


def _timeouts(raw: dict[str, Any]) -> dict[State, float]:
    values = _value(raw, "timeouts_s")
    if not isinstance(values, dict):
        raise ConfigError("timeouts_s value must be an object keyed by state name")
    timeouts: dict[State, float] = {}
    for state in TIMEOUT_STATES:
        timeout_s = values.get(state.name)
        if not _is_number(timeout_s) or timeout_s <= 0:
            raise ConfigError(f"timeouts_s.{state.name} must be a positive number")
        timeouts[state] = float(timeout_s)
    unknown = set(values) - {state.name for state in TIMEOUT_STATES}
    if unknown:
        raise ConfigError(f"unknown timeout states: {sorted(unknown)}")
    return timeouts


def _check_timing(config: CellConfig) -> None:
    if config.set_confirm_time_s >= config.time_in_pick_area_s:
        raise ConfigError(
            "set_confirm_time_s must be shorter than the time an item stays in the pick area "
            f"(pick_area_length_mm / belt_a_speed_mm_s = {config.time_in_pick_area_s:.3f} s)"
        )
    set_length_mm = config.item_spacing_mm * (len(config.items_per_box) - 1)
    confirm_travel_mm = config.set_confirm_time_s * config.belt_a_speed_mm_s
    if config.pick_area_length_mm <= set_length_mm + confirm_travel_mm:
        raise ConfigError(
            "pick_area_length_mm is too short: a full set at item_spacing_mm must stay in the pick area "
            f"while the camera confirms it (needs more than {set_length_mm + confirm_travel_mm:.1f} mm)"
        )
    for state, timeout_s in config.timeouts_s.items():
        nominal_s = config.nominal_time_s(state)
        if timeout_s <= nominal_s:
            raise ConfigError(
                f"timeouts_s.{state.name} = {timeout_s} s must exceed the nominal {nominal_s:.3f} s"
            )
