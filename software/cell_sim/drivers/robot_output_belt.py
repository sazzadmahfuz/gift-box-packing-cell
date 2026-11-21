"""Belt A (objects) switched by a robot output: DO3 -> relay -> Arduino Nano -> conveyor motor.

Source: vision/config/settings.json (belt_do = 3, belt_on = 1) and the
team's confirmation on 2026-11-16. The robot driver sends the output; an optional inner belt
(the simulated belt) keeps the simulated world moving in dry runs.
"""

from __future__ import annotations

from typing import Protocol

from ..interfaces import BeltDriver


class ConveyorOutput(Protocol):
    def set_object_conveyor(self, running: bool) -> None: ...


class RobotOutputBelt:
    def __init__(self, robot: ConveyorOutput, inner: BeltDriver | None = None, name: str = "A") -> None:
        self.robot = robot
        self.inner = inner
        self.name = name
        self._running = False

    def start(self) -> None:
        self.robot.set_object_conveyor(True)
        self._running = True
        if self.inner is not None:
            self.inner.start()

    def stop(self) -> None:
        if self._running:
            self.robot.set_object_conveyor(False)
        self._running = False
        if self.inner is not None:
            self.inner.stop()

    def is_running(self) -> bool:
        return self.inner.is_running() if self.inner is not None else self._running
