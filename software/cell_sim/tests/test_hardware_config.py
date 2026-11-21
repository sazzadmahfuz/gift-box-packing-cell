import copy

import pytest

from cell_sim.hardware_config import (
    ALLOWED_STATUS,
    HardwareConfigError,
    check_entries,
    load_hardware_raw,
    robodk_settings,
)


def test_every_entry_has_value_unit_source_and_known_status():
    raw = load_hardware_raw()
    for section, entries in raw.items():
        if section.startswith("_"):
            continue
        for key, entry in entries.items():
            assert set(entry) == {"value", "unit", "source", "status"}, f"{section}.{key}"
            assert entry["status"] in ALLOWED_STATUS and entry["source"], f"{section}.{key}"


def test_robodk_settings_load():
    settings = robodk_settings(load_hardware_raw())
    assert settings.port == 20500
    assert {"home", "pick", "place_box"} <= set(settings.target_names)


def test_unknown_status_is_rejected():
    raw = copy.deepcopy(load_hardware_raw())
    raw["robodk"]["port"]["status"] = "MEASURED?"
    with pytest.raises(HardwareConfigError, match="status"):
        check_entries(raw)


def test_optional_approach_targets_are_accepted_and_unknown_ones_rejected():
    raw = copy.deepcopy(load_hardware_raw())
    names = {"home": "home", "pick": "pick", "place_box": "place_box", "place_approach": "pa"}
    raw["robodk"]["target_names"]["value"] = names
    assert robodk_settings(raw).target_names["place_approach"] == "pa"
    raw["robodk"]["target_names"]["value"] = {**names, "drop": "drop"}
    with pytest.raises(HardwareConfigError, match="target_names"):
        robodk_settings(raw)


def test_target_names_must_be_complete():
    raw = copy.deepcopy(load_hardware_raw())
    del raw["robodk"]["target_names"]["value"]["place_box"]
    with pytest.raises(HardwareConfigError, match="target_names"):
        robodk_settings(raw)
