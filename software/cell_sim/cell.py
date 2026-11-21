"""The cell as the state machine sees it: belt A, box sensor S1, camera and robot behind interfaces.

The cell only talks to the device interfaces. Which devices sit behind them (simulated,
RoboDK, Dobot, Arduino, bench) is decided by whoever builds the cell. Belt B (boxes) is run
by the Arduino Nano on its own, so the cell never commands it; it only sees S1 and the camera.
It enforces the safety rules: no pick while belt A moves, no place or lid unless a box is at S1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .config import CellConfig
from .events import Event, EventKind, EventQueue
from .interfaces import BeltDriver, Detection, RobotDriver, SensorS1, VisionSource


class SafetyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class ActionRecord:
    time_s: float
    action: str  # "pick", "place" or "lid"
    item_type: str
    belt_a_running: bool
    s1_active: bool


class RobotSequencer(Protocol):
    robot: RobotDriver

    def start_pictures(self) -> None:
        """Robot out of the camera view, pictures taken; PICTURES_DONE follows."""
        ...

    def start_pick(self, item_type: str, item_id: int | None = None) -> float:
        """Start the pick; PICK_DONE follows. Returns the time the pick motion starts."""
        ...

    def start_place(self, item_type: str) -> None:
        """Start the place; PLACE_DONE follows."""
        ...

    def place_finished(self) -> None: ...

    def start_close_lid(self) -> None:
        """Put the lid on the box; LID_DONE follows."""
        ...


@dataclass
class CellDevices:
    belt_a: BeltDriver
    s1: SensorS1
    vision: VisionSource
    sequencer: RobotSequencer
    # Simulated devices react to their own events here; hardware devices leave it None.
    on_event: Callable[[Event], None] | None = None


class Cell:
    def __init__(self, config: CellConfig, queue: EventQueue, devices: CellDevices) -> None:
        self.config = config
        self.queue = queue
        self.devices = devices
        self.robot_holding: str | None = None
        self.actions: list[ActionRecord] = []

    @property
    def box_at_s1(self) -> bool:
        return self.devices.s1.is_active()

    def start(self) -> None:
        self.devices.sequencer.robot.enable()

    def on_event(self, event: Event) -> None:
        if self.devices.on_event is not None:
            self.devices.on_event(event)

    # Box (belt B is the Nano's; the camera confirms the box)

    def look_at_box(self) -> None:
        """The camera checks that the open box stands still at S1; BOX_SEEN follows."""
        self.queue.schedule_in(self.config.detection_time_s, EventKind.BOX_SEEN)

    # Belt A and camera

    def start_feed(self) -> None:
        self.devices.belt_a.start()

    def stop_belt_a(self) -> None:
        self.devices.belt_a.stop()

    def items_in_view(self) -> list[Detection]:
        return self.devices.vision.detections()

    # Robot

    def take_pictures(self) -> None:
        if self.devices.belt_a.is_running():
            raise SafetyViolation("pictures requested while belt A is running")
        self.devices.sequencer.start_pictures()

    def start_pick(self, item_type: str, item_id: int | None = None) -> float:
        if self.devices.belt_a.is_running():
            raise SafetyViolation("pick requested while belt A is running")
        pick_start_s = self.devices.sequencer.start_pick(item_type, item_id)
        self._log(pick_start_s, "pick", item_type)
        return pick_start_s

    def finish_pick(self, item_type: str) -> None:
        self.robot_holding = item_type

    def start_place(self) -> None:
        if not self.devices.s1.is_active():
            raise SafetyViolation("place requested while no box is at S1")
        if self.robot_holding is None:
            raise SafetyViolation("place requested while the robot holds no item")
        self.devices.sequencer.start_place(self.robot_holding)

    def finish_place(self) -> str:
        if not self.devices.s1.is_active() or self.robot_holding is None:
            raise SafetyViolation("item released without a box at S1 or without an item")
        item_type = self.robot_holding
        self._log(self.queue.now_s, "place", item_type)
        self.robot_holding = None
        self.devices.sequencer.place_finished()
        return item_type

    def close_lid(self) -> None:
        if not self.devices.s1.is_active():
            raise SafetyViolation("lid requested while no box is at S1")
        self._log(self.queue.now_s, "lid", "lid")
        self.devices.sequencer.start_close_lid()

    def stop_all(self) -> None:
        self.devices.belt_a.stop()
        self.devices.sequencer.robot.stop()

    def _log(self, time_s: float, action: str, item_type: str) -> None:
        self.actions.append(
            ActionRecord(time_s, action, item_type, self.devices.belt_a.is_running(), self.devices.s1.is_active())
        )
