"""Which devices each --mode uses, and how its log is labelled."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import SIM_DEVICES_TEXT, SIMULATION_BANNER
from .config import CellConfig
from .drivers.robot_output_belt import RobotOutputBelt
from .drivers.sim_devices import build_sim_cell
from .events import EventQueue
from .hardware_config import HardwareConfigError, dobot_section, dobot_settings, load_hardware_raw, robodk_settings
from .interfaces import Clock, WallClock
from .safety_gate import require_real_robot_allowed
from .sequencer import MeasuredSequencer, TimedSequencer
from .simulation import CellFactory

MODES: tuple[str, ...] = ("sim", "robodk", "dobot-dry", "dobot-real")
DOBOT_DRY_BANNER = (
    "# SIMULATION, assumed parameters; DOBOT DRY RUN: TCP command strings printed, nothing sent; "
    "parameters: config.json (all ASSUMED) for all times; hardware.json dobot section for the "
    "command values (pick X/Y ASSUMED, lid targets not taught); devices: DobotTcpRobot (dry), "
    f"belt A via robot DO3 (dry) on {SIM_DEVICES_TEXT}"
)


class RealMotionNotImplemented(RuntimeError):
    """The safety gate passed, but the real-robot motion path is not written yet (CLAUDE.md)."""


@dataclass
class ModeSetup:
    label: str  # printed in front of every console line
    banner: str  # line 1 of the CSV
    cell_factory: CellFactory | None  # None = the plain sim cell
    close: Callable[[], None]


def setup_sim() -> ModeSetup:
    return ModeSetup("SIMULATION", SIMULATION_BANNER, None, lambda: None)


def robodk_banner(robot_name: str, simulation_speed: float) -> str:
    return (
        "# ROBODK SIMULATION, assumed parameters; parameters: config.json (all ASSUMED) for belts, "
        f"S1, vision and timeouts; robot motion times measured in RoboDK at simulation speed "
        f"{simulation_speed:g}; hardware.json robodk section; devices: RoboDKRobot ({robot_name}), "
        f"{SIM_DEVICES_TEXT}"
    )


def setup_robodk(
    hardware_path: str | Path | None = None,
    connect: Callable[..., object] | None = None,
    clock: Clock | None = None,
    say: Callable[[str], None] = print,
) -> ModeSetup:
    """Connect to the RoboDK station. Raises RoboDKUnavailable with what to open if it is not ready."""
    from .drivers.robodk_robot import connect_robodk  # only robodk mode needs this module

    settings = robodk_settings(load_hardware_raw(hardware_path))
    robot = (connect or connect_robodk)(settings, say=say)
    timer = clock or WallClock()

    def cell_factory(config: CellConfig, queue: EventQueue):
        return build_sim_cell(
            config,
            queue,
            make_sequencer=lambda _config, _queue: MeasuredSequencer(
                _queue, robot, timer, time_scale=settings.simulation_speed, config=_config
            ),
        )

    return ModeSetup(
        "ROBODK SIMULATION",
        robodk_banner(robot.name, settings.simulation_speed),
        cell_factory,
        robot.close,
    )


def setup_dobot_dry(hardware_path: str | Path | None = None, say: Callable[[str], None] = print) -> ModeSetup:
    """Run the simulated cell with the Dobot driver on dry sockets: every command is printed, none sent."""
    from .drivers.dobot_tcp_robot import build_dry_robot  # loads dobot_api only for this mode

    settings = dobot_settings(load_hardware_raw(hardware_path), hardware_path)
    missing = settings.missing_for_dry_run()
    if missing:
        raise HardwareConfigError(f"dobot-dry needs these values in hardware.json: {missing}")
    if settings.object_conveyor_do is None:
        raise HardwareConfigError("dobot-dry needs dobot.object_conveyor_do (the output that runs belt A)")
    robot = build_dry_robot(settings, say)
    say(
        f"[DOBOT DRY] robot {settings.robot_ip}, ports {settings.dashboard_port}/{settings.move_port}, "
        f"speed ratio {settings.speed_factor_percent} %, vacuum DO {settings.vacuum_do} "
        f"({settings.statuses.get('vacuum_do')}), blow-off DO {settings.blow_off_do}, "
        f"belt A DO {settings.object_conveyor_do}"
    )
    for name, pose in settings.targets.items():
        shown = "not taught (lid moves are skipped)" if pose is None else f"{pose} mm/deg"
        say(f"[DOBOT DRY] target {name}: {shown} ({settings.statuses.get(f'target_{name}')})")

    def cell_factory(config: CellConfig, queue: EventQueue):
        return build_sim_cell(
            config,
            queue,
            make_sequencer=lambda _config, _queue: TimedSequencer(_config, _queue, robot),
            wrap_belt_a=lambda sim_belt: RobotOutputBelt(robot, inner=sim_belt),
        )

    return ModeSetup("SIMULATION, DOBOT DRY", DOBOT_DRY_BANNER, cell_factory, robot.close)


def setup_dobot_real(hardware_path: str | Path | None = None, teacher_approved: bool = False) -> ModeSetup:
    """Safety gate only. Raises SafetyGateRefused, or RealMotionNotImplemented if the gate passes."""
    require_real_robot_allowed(dobot_section(load_hardware_raw(hardware_path)), teacher_approved)
    raise RealMotionNotImplemented(
        "the safety gate passed, but the real-robot motion path is not implemented yet. "
        "Ask for it in a message that also says the teacher approved it (CLAUDE.md)."
    )
