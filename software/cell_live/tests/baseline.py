"""Fixed test values: the cell as it was before the 17 Nov lab, so no test depends on what the lab
writes into live_config.json or Choton's settings.json and homography.json later."""

from __future__ import annotations

import copy
from pathlib import Path

from cell_live.adapters.choton import load_choton_modules
from cell_live.live_config import LiveConfig, load_live_config

CALIBRATION_12_NOV = Path(__file__).parent / "data" / "homography_2026-11-12.json"  # Choton's 12 Nov file (copy)
BEFORE_LAB = ("dobot.teacher_approval", "dobot.belt_on_value", "dobot.belt_dir_forward_value", "dobot.belt_enable_on_value",
              "control.box_wait_timeout_s", "control.box_leave_timeout_s", "dobot.feedback_readable_while_held")
CHOTON_12_NOV = {  # vision/config/settings.json robot section as committed on 12 Nov
    "home": [291.5, 151.0, 135.7, -13.5], "travel_z": 104.7, "pick_z": 63.7, "place_z": 131.7, "r_angle": -73.8,
    "box_slots": [[369.6, 17.1]], "pick_z_by_type": {"card": 63.7, "candy": 72.1}, "min_radius_mm": 150, "belt_on": 1,
}


def baseline_config() -> LiveConfig:
    live = load_live_config()
    raw = copy.deepcopy(live.raw)
    for name in BEFORE_LAB:
        section, key = name.split(".")
        raw[section][key]["value"], raw[section][key]["status"] = None, "CONFIRM"
    raw["calibration"]["file"]["value"] = str(CALIBRATION_12_NOV)
    return LiveConfig(raw, live.path)


CONFIG = baseline_config()
CHOTON = load_choton_modules(CONFIG.path_value("choton", "folder"))


def choton_settings(lid=True):
    """Choton's settings.json (copy) with his 12 Nov robot values. lid=True adds test lid heights, lid=False removes them."""
    settings = copy.deepcopy(CHOTON.vision_lib.load_settings())
    robot = settings["robot"]
    robot.update(copy.deepcopy(CHOTON_12_NOV))
    robot.pop("lid_pick_z", None), robot.pop("lid_place_z", None)
    if lid:
        robot["lid_pick_z"], robot["lid_place_z"] = 90.0, 140.0  # test values
    return settings
