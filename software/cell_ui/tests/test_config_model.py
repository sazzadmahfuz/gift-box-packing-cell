import json
import shutil

import pytest

from cell_sim.config import DEFAULT_CONFIG_PATH, load_config
from cell_sim.hardware_config import DEFAULT_HARDWARE_PATH, load_hardware_raw
from cell_ui.config_model import SettingsFile


@pytest.fixture
def files(tmp_path):
    config = tmp_path / DEFAULT_CONFIG_PATH.name
    hardware = tmp_path / DEFAULT_HARDWARE_PATH.name
    shutil.copy(DEFAULT_CONFIG_PATH, config)
    shutil.copy(DEFAULT_HARDWARE_PATH, hardware)
    return SettingsFile(config), SettingsFile(hardware)


def test_entries_and_sections_are_found_by_walking_the_file(files):
    config, hardware = files
    assert ("belt_a_speed_mm_s",) in [ref.path for ref in config.entries()]
    assert config.sections() == [()]
    assert {("robodk",), ("dobot",)} <= set(hardware.sections())
    vacuum = next(ref for ref in hardware.entries() if ref.path == ("dobot", "vacuum_do"))
    assert vacuum.fields == ("value", "unit", "source", "status")
    assert all(not ref.path[-1].startswith("_") for ref in config.entries())


def test_a_new_key_or_section_appears_without_ui_changes(files):
    _config, hardware = files
    raw = json.loads(hardware.path.read_text(encoding="utf-8"))
    raw["belts"] = {"belt_a_port": {"value": "COM3", "unit": "serial port", "source": "test", "status": "CONFIRM"}}
    hardware.path.write_text(json.dumps(raw), encoding="utf-8")
    hardware.reload()
    assert ("belts", "belt_a_port") in [ref.path for ref in hardware.entries()]
    assert hardware.validate() == ""


def test_value_text_is_json_and_plain_words_stay_text(files):
    config, hardware = files
    config.set_field(("belt_a_speed_mm_s",), "value", "60")
    assert config.entry(("belt_a_speed_mm_s",))["value"] == 60
    hardware.set_field(("dobot", "robot_ip"), "value", "192.168.1.7")
    assert hardware.entry(("dobot", "robot_ip"))["value"] == "192.168.1.7"
    hardware.set_field(("dobot", "vacuum_do"), "value", "null")
    assert hardware.entry(("dobot", "vacuum_do"))["value"] is None


def test_the_programs_own_loaders_reject_bad_edits(files):
    config, hardware = files
    config.set_field(("belt_a_speed_mm_s",), "value", "-5")
    assert "belt_a_speed_mm_s" in config.validate()
    with pytest.raises(ValueError):
        config.save()
    hardware.set_field(("dobot", "vacuum_do"), "status", "MAYBE")
    assert "status" in hardware.validate()


def test_save_keeps_a_backup_and_the_program_loads_the_result(files):
    config, hardware = files
    before = config.path.read_text(encoding="utf-8")
    config.set_field(("belt_a_speed_mm_s",), "value", "60")
    config.set_field(("belt_a_speed_mm_s",), "note", "MEASURED 2026-11-12 (test)")
    backup = config.save()
    assert backup.read_text(encoding="utf-8") == before
    assert load_config(config.path).belt_a_speed_mm_s == 60
    hardware.set_field(("dobot", "speed_factor_percent"), "value", "15")
    hardware.save()
    assert load_hardware_raw(hardware.path)["dobot"]["speed_factor_percent"]["value"] == 15
    assert list(json.loads(config.path.read_text(encoding="utf-8")))[0] == "_comment"  # key order kept


def test_changed_value_without_new_status_or_source_is_flagged(files):
    _config, hardware = files
    hardware.set_field(("dobot", "vacuum_do"), "value", "4")
    assert hardware.provenance_warnings() == ["dobot.vacuum_do: value changed but status, source did not"]
    hardware.set_field(("dobot", "vacuum_do"), "status", "CONFIRM")
    assert hardware.provenance_warnings() == []


def test_revert_and_dirty(files):
    config, _hardware = files
    assert not config.is_dirty()
    config.set_field(("random_seed",), "value", "7")
    assert config.is_dirty() and config.changed_entries() == [("random_seed",)]
    config.revert()
    assert not config.is_dirty()
