"""--mode dobot-dry: Dobot's own command strings, printed, never sent."""

import ast
import json
import socket
from pathlib import Path

import pytest

from cell_sim.__main__ import main
from cell_sim.config import load_config
from cell_sim.drivers.dobot_tcp_robot import build_dry_robot, parse_reply
from cell_sim.hardware_config import HardwareConfigError, dobot_settings, load_hardware_raw
from cell_sim.interfaces import RobotDriver
from cell_sim.modes import setup_dobot_dry
from cell_sim.simulation import Simulation

PACKAGE_DIR = Path(__file__).resolve().parents[1]
REFERENCE_CYCLE_TIMES_S = [61.1, 58.7, 60.1, 60.1, 58.7]  # test_reference.py
TEST_VALUES = {  # fixed test values: these tests check the command strings, not the lab's taught points
    "speed_factor_percent": 20,
    "pick_z_by_type_mm": {"card": 63.7, "candy": 72.1},
    "target_pick_approach": {"x_mm": 233.62, "y_mm": -12.95, "z_mm": 104.7, "r_deg": -73.8},
    "target_pick": {"x_mm": 233.62, "y_mm": -12.95, "z_mm": 63.7, "r_deg": -73.8},
}


@pytest.fixture
def no_sockets(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("dobot-dry must not open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _dry_robot():
    raw = load_hardware_raw()
    for key, value in TEST_VALUES.items():
        raw["dobot"][key]["value"] = value
    lines = []
    return build_dry_robot(dobot_settings(raw), say=lines.append), lines


def _commands(lines):
    return [line.split(" <- ")[1].split("  #")[0] if " <- " in line else line.split("] ")[1].split("  #")[0] for line in lines]


def test_enable_and_pick_print_dobot_strings_with_port_target_and_speed(no_sockets):
    robot, lines = _dry_robot()
    assert isinstance(robot, RobotDriver)
    robot.enable()
    robot.select_item("card")
    for step in ("pick_above", "pick"):
        robot.move_to(step)
    robot.set_vacuum(True)
    assert _commands(lines) == [
        "ClearError()",
        "EnableRobot()",
        "SpeedFactor(20)",
        "SetArmOrientation(0)",
        "MovL(233.620000,-12.950000,104.700000,-73.800000)",
        "Sync()",
        "MovL(233.620000,-12.950000,63.700000,-73.800000)",
        "Sync()",
        "DO(1,1)",
        "wait 0.6 s on the PC",
    ]
    assert all(line.startswith("[DOBOT DRY, nothing sent] ") for line in lines)
    assert "port 30003 <- MovL" in lines[6] and "target pick " in lines[6] and "speed ratio 20 %" in lines[6]
    assert "port 29999 <- DO(1,1)" in lines[8] and "suction ON" in lines[8]


def test_every_move_is_movl_so_the_arm_side_never_flips(no_sockets):
    robot, lines = _dry_robot()
    for step in ("home", "pick_above", "pick", "pick_above", "place_above", "place_box", "place_above"):
        robot.move_to(step)
    moves = [command[:4] for command in _commands(lines) if command != "Sync()"]
    assert moves == ["MovL"] * 7


def test_pick_height_depends_on_the_item_type(no_sockets):
    robot, lines = _dry_robot()
    for item_type, z_text in (("candy_A", "72.100000"), ("card", "63.700000")):
        robot.select_item(item_type)
        robot.move_to("pick")
        assert _commands(lines)[-2] == f"MovL(233.620000,-12.950000,{z_text},-73.800000)"


def test_release_is_suction_off_then_a_blow_off_pulse(no_sockets):
    robot, lines = _dry_robot()
    robot.set_vacuum(False)
    assert _commands(lines) == [
        "DO(1,0)", "DO(2,1)", "wait 0.2 s on the PC", "DO(2,0)", "wait 0.3 s on the PC",
    ]


def test_object_conveyor_is_switched_with_do3_and_close_turns_every_output_off(no_sockets):
    robot, lines = _dry_robot()
    robot.set_object_conveyor(True)
    robot.set_object_conveyor(False)
    robot.close()
    assert _commands(lines) == ["DO(3,1)", "DO(3,0)", "DO(1,0)", "DO(2,0)", "DO(3,0)", "DisableRobot()"]


def test_parse_reply():
    assert parse_reply("0,{366.2,1.0},GetPose();") == (0, "366.2,1.0")
    assert parse_reply("-1,{},MovJ();")[0] == -1
    assert parse_reply("")[0] is None


def test_dry_cell_keeps_the_sim_reference_times(no_sockets):
    mode = setup_dobot_dry(say=lambda line: None)
    result = Simulation(load_config(), 5, cell_factory=mode.cell_factory).run()
    assert [round(cycle.cycle_time_s, 3) for cycle in result.cycles] == REFERENCE_CYCLE_TIMES_S


def test_cli_dobot_dry_writes_a_dry_csv(tmp_path, capsys, no_sockets):
    assert main(["--mode", "dobot-dry", "--cycles", "1", "--out-dir", str(tmp_path)]) == 0
    (csv_path,) = tmp_path.glob("*.csv")
    banner = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert banner.startswith("# SIMULATION, assumed parameters; DOBOT DRY RUN: TCP command strings printed, nothing sent")
    output = capsys.readouterr().out
    assert "[DOBOT DRY, nothing sent] port 30003 <- MovL(" in output and "<- MovJ(" not in output
    assert "port 29999 <- DisableRobot()" in output  # close at the end
    lines = output.splitlines()
    on = lines.index(next(line for line in lines if "<- DO(3,1)" in line))
    off = lines.index(next(line for line in lines if "<- DO(3,0)" in line))
    first_move = lines.index(next(line for line in lines if "<- MovL(" in line))
    assert on < off < first_move  # belt A runs and stops before the robot moves (team set-up)
    cycle_row = csv_path.read_text(encoding="utf-8").splitlines()[-1]
    assert "lid moves not sent" in cycle_row  # lid targets not taught yet: shown, not hidden


def test_robot_output_belt_switches_do3_and_moves_the_simulated_belt(no_sockets):
    from cell_sim.drivers.robot_output_belt import RobotOutputBelt

    robot, lines = _dry_robot()
    states = []
    inner = type("Belt", (), {"start": lambda s: states.append("on"), "stop": lambda s: states.append("off"),
                              "is_running": lambda s: states[-1:] == ["on"]})()
    belt = RobotOutputBelt(robot, inner=inner)
    belt.stop()  # not running: no output sent
    belt.start()
    assert belt.is_running()
    belt.stop()
    assert _commands(lines) == ["DO(3,1)", "DO(3,0)"] and states == ["off", "on", "off"]


def test_dry_run_refuses_null_command_values(tmp_path):
    raw = load_hardware_raw()
    raw["dobot"]["target_pick"]["value"] = None
    raw["dobot"]["vacuum_do"]["value"] = None
    path = tmp_path / "hardware.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(HardwareConfigError, match="target_pick.*vacuum_do"):
        setup_dobot_dry(path, say=lambda line: None)


def _calls(path, names):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in names:
                found.append(name)
    return found


def test_dobot_api_is_loaded_only_in_its_driver_file_and_numpy_is_never_imported():
    for path in PACKAGE_DIR.rglob("*.py"):
        if path.parent.name == "tests":
            continue
        loads = _calls(path, {"spec_from_file_location", "module_from_spec"})
        assert loads == ([] if path.name != "dobot_tcp_robot.py" else ["spec_from_file_location", "module_from_spec"])
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] + [getattr(node, "module", None) or ""]
                assert not any(n.split(".")[0] in ("numpy", "tkinter", "dobot_api") for n in names), path.name
