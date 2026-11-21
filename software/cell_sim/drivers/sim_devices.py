"""Simulated devices. They schedule the events real hardware would produce.

SimWorld (sim_world.py) holds what the belts carry. SimBelt, SimSensor and MockVision are the
device views of that world; SimRobot records the commands it receives and moves instantly.
All times come from config.json (ASSUMED).
"""

from __future__ import annotations

from typing import Callable

from ..cell import Cell, CellDevices, RobotSequencer
from ..config import CellConfig
from ..events import EventQueue
from ..interfaces import LID_TARGET_NAMES, TARGET_NAMES, BeltDriver, Detection, Pose, RobotError
from ..sequencer import TimedSequencer
from .sim_world import SimWorld

__all__ = ["MockVision", "SimBelt", "SimClock", "SimRobot", "SimSensor", "SimWorld", "build_sim_cell"]


class SimClock:
    """Simulated time: whatever the event queue says. Nothing sleeps."""

    def __init__(self, queue: EventQueue) -> None:
        self.queue = queue

    def now_s(self) -> float:
        return self.queue.now_s

    def sleep_s(self, duration_s: float) -> None:
        """Simulated time only moves from event to event."""


class SimBelt:
    def __init__(self, world: SimWorld, name: str) -> None:
        if name not in ("A", "B"):
            raise ValueError(f"belt name must be 'A' or 'B', got {name!r}")
        self.world = world
        self.name = name

    def start(self) -> None:
        self.world.belt_started(self.name)

    def stop(self) -> None:
        self.world.belt_stopped(self.name)

    def is_running(self) -> bool:
        return self.world.running[self.name]


class SimSensor:
    """The Nano's box sensor S1 on belt B: active while a box stands at the robot."""

    def __init__(self, world: SimWorld) -> None:
        self.world = world

    def is_active(self) -> bool:
        return self.world.s1_active


class MockVision:
    """Reports every item fully inside the pick area now (the camera sees them all)."""

    def __init__(self, world: SimWorld) -> None:
        self.world = world

    def detections(self) -> list[Detection]:
        now_s = self.world.queue.now_s
        return [
            Detection(item_type, entered_s, now_s, item_id=index)
            for index, item_type, entered_s in self.world.items_in_area()
        ]


class SimRobot:
    """Moves instantly and records every command. It knows target names, not coordinates."""

    def __init__(self, target_poses: dict[str, Pose] | None = None) -> None:
        self.target_poses = dict(target_poses or {})
        self.commands: list[str] = []
        self.enabled = False
        self.vacuum_on = False
        self.at_target: str | None = None

    def enable(self) -> None:
        self.enabled = True
        self.commands.append("enable")

    def move_to(self, target_name: str) -> None:
        if target_name not in TARGET_NAMES + LID_TARGET_NAMES:
            raise RobotError(f"unknown target {target_name!r}")
        self.at_target = target_name
        self.commands.append(f"move_to {target_name}")

    def set_vacuum(self, on: bool) -> None:
        self.vacuum_on = on
        self.commands.append(f"vacuum {'on' if on else 'off'}")

    def current_pose(self) -> Pose:
        if self.at_target is None or self.at_target not in self.target_poses:
            raise RobotError("no coordinates known for the current target (simulation uses names only)")
        return self.target_poses[self.at_target]

    def stop(self) -> None:
        self.commands.append("stop")

    def close(self) -> None:
        self.commands.append("close")


def build_sim_cell(
    config: CellConfig,
    queue: EventQueue,
    s1_working: bool = True,
    make_sequencer: Callable[[CellConfig, EventQueue], RobotSequencer] | None = None,
    wrap_belt_a: Callable[[BeltDriver], BeltDriver] | None = None,
) -> Cell:
    """Belts, S1 and vision simulated. The robot is SimRobot unless make_sequencer gives another.

    wrap_belt_a lets a mode add its own belt A control on top of the simulated belt (for
    example the robot output DO3 that runs the object conveyor).
    """
    world = SimWorld(config, queue, s1_working=s1_working)
    if make_sequencer is None:
        sequencer: RobotSequencer = TimedSequencer(config, queue, SimRobot())
    else:
        sequencer = make_sequencer(config, queue)
    belt_a: BeltDriver = SimBelt(world, "A")
    if wrap_belt_a is not None:
        belt_a = wrap_belt_a(belt_a)
    devices = CellDevices(
        belt_a=belt_a,
        s1=SimSensor(world),
        vision=MockVision(world),
        sequencer=sequencer,
        on_event=world.on_event,
    )
    return Cell(config, queue, devices)
