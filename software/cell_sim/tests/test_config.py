import copy

import pytest

from cell_sim.config import ConfigError, config_from_dict, load_config, load_raw_config
from cell_sim.controller import TIMEOUT_STATES


def test_default_config_loads():
    config = load_config()
    assert config.items_per_box == ("card", "candy", "candy")  # team decision 2026-11-16
    assert set(config.timeouts_s) == set(TIMEOUT_STATES)


def test_every_parameter_has_unit_and_assumed_or_setting_note():
    raw = load_raw_config()
    parameters = {key: entry for key, entry in raw.items() if not key.startswith("_")}
    assert parameters
    for key, entry in parameters.items():
        assert entry["unit"], key
        assert entry["note"].startswith(("ASSUMED", "SETTING")), key
    measured_like = [key for key, entry in parameters.items() if key.endswith(("_s", "_mm", "_mm_s"))]
    assert all(parameters[key]["note"].startswith("ASSUMED") for key in measured_like)


def test_four_item_box_is_accepted():
    raw = load_raw_config()
    raw["items_per_box"]["value"] = ["card", "card", "candy", "candy"]
    raw["pick_area_length_mm"]["value"] = 300.0  # 4 items need a longer pick area
    assert config_from_dict(raw).items_per_box == ("card", "card", "candy", "candy")


def _with(path, value):
    raw = copy.deepcopy(load_raw_config())
    *parents, last = path
    target = raw
    for key in parents:
        target = target[key]
    target[last] = value
    return raw


@pytest.mark.parametrize(
    "path, value",
    [
        (("items_per_box", "value"), []),
        (("items_per_box", "value"), ["card", ""]),
        (("random_seed", "value"), 1.5),
        (("belt_a_speed_mm_s", "value"), 0),
        (("belt_b_speed_mm_s", "value"), -80.0),
        (("pick_time_s", "value"), "2.0"),
        (("set_confirm_time_s", "value"), 5.0),  # longer than an item stays in the pick area (4.6 s)
        (("pick_area_length_mm", "value"), 150.0),  # a full set of 3 at 70 mm cannot be confirmed
        (("timeouts_s", "value", "WAIT_BOX"), 4.0),  # nominal box travel + camera is 5.5 s
        (("timeouts_s", "value", "FEED_ITEM"), 1.0),  # old state name
        (("timeouts_s", "value", "UNKNOWN_STATE"), 1.0),
        (("place_time_s",), 1.5),  # missing value/unit/note object
    ],
)
def test_invalid_config_is_rejected(path, value):
    with pytest.raises(ConfigError):
        config_from_dict(_with(path, value))


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")
