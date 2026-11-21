"""RoboDK driver and --mode robodk, against a fake RoboDK (no RoboDK needed)."""

import ast
from pathlib import Path

import pytest

from cell_sim.__main__ import EXIT_CONNECTION_ERROR, main
from cell_sim.config import load_config
from cell_sim.drivers import robodk_robot
from cell_sim.drivers.robodk_robot import RoboDKUnavailable, connect_robodk
from cell_sim.hardware_config import load_hardware_raw, robodk_settings
from cell_sim.interfaces import RobotDriver, RobotError
from cell_sim.modes import setup_robodk
from cell_sim.sequencer import PICK_STEPS, MeasuredSequencer
from cell_sim.simulation import Simulation
from cell_sim.tests.fake_robodk import FakeMat, cell_station, fake_modules

PACKAGE_DIR = Path(__file__).resolve().parents[1]
BASE_VALUES = {  # independent of the station-specific values in hardware.json
    "robot_name": None,
    "target_names": {"home": "home", "pick": "pick", "place_box": "place_box"},
}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def now_s(self):
        return self.now

    def sleep_s(self, duration_s):
        self.now += duration_s


def _raw_with(**values):
    raw = load_hardware_raw()
    for key, value in {**BASE_VALUES, **values}.items():
        raw["robodk"][key]["value"] = value
    return raw


SETTINGS = robodk_settings(_raw_with())


def _connect(station, **overrides):
    settings = SETTINGS if not overrides else robodk_settings(_raw_with(**overrides))
    return connect_robodk(settings, fake_modules(station), api_listening=lambda h, p: True, say=lambda t: None)


# Connecting


def test_robodk_not_running_says_what_to_open_and_never_loads_robodk(monkeypatch):
    monkeypatch.setattr(robodk_robot, "load_robodk_modules", lambda: pytest.fail("must not load robodk"))
    with pytest.raises(RoboDKUnavailable) as error:
        connect_robodk(SETTINGS, api_listening=lambda h, p: False)
    message = str(error.value)
    assert "not running, or its API is off" in message and "Open RoboDK" in message
    assert "home, pick, place_box" in message and "Test-NetConnection localhost -Port 20500" in message


def test_not_running_message_names_the_configured_robot():
    settings = robodk_settings(_raw_with(robot_name="Dobot M1"))
    with pytest.raises(RoboDKUnavailable, match="robot 'Dobot M1' with the targets"):
        connect_robodk(settings, api_listening=lambda h, p: False)


def test_missing_robodk_package_says_how_to_install(monkeypatch):
    def no_robodk(name):
        raise ImportError(f"No module named {name!r}")

    monkeypatch.setattr(robodk_robot.importlib, "import_module", no_robodk)
    with pytest.raises(RoboDKUnavailable, match="pip install robodk"):
        robodk_robot.load_robodk_modules()


def test_station_without_a_dobot_robot_is_refused():
    station, _ = cell_station(robot_name="Dobot M1")  # older M1: not matched by the keywords
    with pytest.raises(RoboDKUnavailable) as error:
        _connect(station)
    assert "set robodk.robot_name to 'Dobot M1'" in str(error.value)


def test_exact_robot_name_from_hardware_json():
    station, robot = cell_station(robot_name="My cell robot")
    assert _connect(station, robot_name="My cell robot").robot is robot


def test_missing_target_is_refused_even_if_robodk_offers_a_close_match():
    station, _ = cell_station()
    station.items = [i for i in station.items if i.name != "place_box"]
    with pytest.raises(RoboDKUnavailable, match="'place_box' not found"):
        _connect(station)


# Moving


def test_driver_satisfies_the_robot_interface():
    station, _ = cell_station()
    assert isinstance(_connect(station), RobotDriver)


def test_enable_forces_simulate_mode_and_speed():
    station, _ = cell_station()
    _connect(station).enable()
    assert station.run_mode == 1  # RUNMODE_SIMULATE: never moves a connected real robot
    assert station.simulation_speed == SETTINGS.simulation_speed


def test_pick_and_place_use_movej_between_and_movel_up_and_down():
    station, robot = cell_station()
    driver = _connect(station)
    dz_mm = SETTINGS.approach_dz_mm
    for step in ("home", "pick_above", "pick", "pick_above", "place_above", "place_box", "place_above"):
        driver.move_to(step)
    above_pick = FakeMat(10.0, 0.0, 20.0 + dz_mm)
    above_box = FakeMat(0.0, 10.0, 30.0 + dz_mm)
    assert robot.moves == [
        ("MoveJ", "home"),
        ("MoveJ", above_pick),
        ("MoveL", "pick"),
        ("MoveL", above_pick),
        ("MoveJ", above_box),
        ("MoveL", "place_box"),
        ("MoveL", above_box),
    ]
    assert robot.frame is station.frame  # approach poses are offsets in the targets' frame


def test_taught_pick_approach_replaces_the_computed_offset():
    station, robot = cell_station()
    station.add_target("pick_approach", 10.0, 0.0, 120.0)
    targets = {**BASE_VALUES["target_names"], "pick_approach": "pick_approach"}
    driver = _connect(station, target_names=targets)
    for step in ("pick_above", "pick", "pick_above", "place_above"):
        driver.move_to(step)
    assert robot.moves == [
        ("MoveJ", "pick_approach"),
        ("MoveL", "pick"),
        ("MoveL", "pick_approach"),
        ("MoveJ", FakeMat(0.0, 10.0, 30.0 + SETTINGS.approach_dz_mm)),  # no place_approach taught
    ]


def test_configured_pick_approach_must_exist_in_the_station():
    station, _ = cell_station()
    targets = {**BASE_VALUES["target_names"], "pick_approach": "pick_approach"}
    with pytest.raises(RoboDKUnavailable, match="'pick_approach' not found"):
        _connect(station, target_names=targets)


def test_unreachable_target_becomes_robot_error():
    station, robot = cell_station()
    robot.unreachable.add("pick")
    driver = _connect(station)
    driver.move_to("pick_above")
    with pytest.raises(RobotError, match="TargetReachError"):
        driver.move_to("pick")


def test_vacuum_shows_a_status_message_and_carries_the_item():
    station, robot = cell_station()
    item = next(i for i in station.items if i.name == "item")
    start_pose = item.pose
    driver = _connect(station)
    driver.move_to("pick")
    driver.set_vacuum(True)
    assert robot.tool.held == [item]
    assert station.messages[-1] == ("cell_sim: vacuum ON at pick", False)  # status bar, no popup
    item.pose = FakeMat(0.0, 10.0, 30.0)  # RoboDK moves the attached item with the tool
    driver.set_vacuum(False)
    assert robot.tool.held == []
    driver.move_to("pick_above")  # next pick: the item is back at the pick point
    assert item.pose == start_pose


def test_current_pose_comes_from_robodk():
    station, _ = cell_station()
    driver = _connect(station)
    driver.move_to("pick")
    pose = driver.current_pose()
    assert (pose.x_mm, pose.y_mm, pose.z_mm, pose.r_deg) == (10.0, 0.0, 20.0, 0.0)


# Measured timing and the full mode


def test_measured_sequencer_uses_the_robot_motion_time():
    from cell_sim.events import EventKind, EventQueue

    clock = FakeClock()
    station, _ = cell_station(clock=clock, move_s=1.5)
    queue = EventQueue()
    sequencer = MeasuredSequencer(queue, _connect(station), clock, time_scale=2.0)
    assert sequencer.start_pick("card") == 0.0
    done = queue.pop()
    moves = sum(1 for step in PICK_STEPS if not step.startswith("vacuum"))
    assert done.kind is EventKind.PICK_DONE
    assert done.time_s == pytest.approx(moves * 1.5 * 2.0)


def test_robodk_cell_runs_five_cycles():
    clock = FakeClock()
    station, robot = cell_station(clock=clock, move_s=1.0)
    mode = setup_robodk(connect=lambda settings, say: _connect(station), clock=clock)
    result = Simulation(load_config(), 5, cell_factory=mode.cell_factory).run()
    assert result.fault_reason is None and len(result.cycles) == 5
    assert all(cycle.items == load_config().items_per_box for cycle in result.cycles)
    assert all("lid moves not sent" in cycle.note for cycle in result.cycles)  # the fake station has no lid targets
    assert mode.banner.startswith("# ROBODK SIMULATION, assumed parameters")
    assert sum(1 for kind, _ in robot.moves if kind == "MoveL") == 5 * 3 * 4


def test_robot_error_in_a_run_ends_in_fault():
    station, robot = cell_station(clock=FakeClock())
    robot.unreachable.add("place_box")
    mode = setup_robodk(connect=lambda settings, say: _connect(station), clock=FakeClock())
    result = Simulation(load_config(), 1, cell_factory=mode.cell_factory).run()
    assert "robot error" in result.fault_reason and "place_box" in result.fault_reason
    assert robot.stopped


def test_cli_robodk_mode_writes_a_robodk_csv(tmp_path, monkeypatch, capsys):
    station, _ = cell_station()
    monkeypatch.setattr(robodk_robot, "connect_robodk", lambda settings, say: _connect(station))
    assert main(["--mode", "robodk", "--cycles", "2", "--out-dir", str(tmp_path)]) == 0
    (csv_path,) = tmp_path.glob("*.csv")
    assert csv_path.read_text(encoding="utf-8").startswith("# ROBODK SIMULATION, assumed parameters")
    assert capsys.readouterr().out.count("[ROBODK SIMULATION] cycle ") == 2


def test_cli_without_robodk_exits_3_with_a_clear_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(robodk_robot, "robodk_api_listening", lambda host, port: False)
    assert main(["--mode", "robodk", "--out-dir", str(tmp_path)]) == EXIT_CONNECTION_ERROR
    assert "Open RoboDK" in capsys.readouterr().err
    assert list(tmp_path.glob("*.csv")) == []


# The optional robodk package is loaded in one file only


def _dynamic_imports(path):
    """Module names passed to importlib.import_module() or __import__() in one file."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            func_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if func_name in ("import_module", "__import__"):
                first = node.args[0] if node.args else None
                names.append(first.value if isinstance(first, ast.Constant) else "<dynamic>")
    return names


def test_robodk_is_loaded_only_in_its_driver_file():
    for path in PACKAGE_DIR.rglob("*.py"):
        if path.parent.name == "tests":
            continue
        loaded = _dynamic_imports(path)
        if path.name == "robodk_robot.py":
            assert loaded == ["robodk.robolink", "robodk.robomath"]
        else:
            assert loaded == [], f"{path.name} loads {loaded}"
