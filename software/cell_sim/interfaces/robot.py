"""Robot interface. Every robot (simulated, RoboDK, Dobot) offers these methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Named targets the cell uses. Coordinates live in the driver's own settings, never here.
TARGET_NAMES: tuple[str, ...] = ("home", "pick_above", "pick", "place_above", "place_box")
# Lid step (pick the lid, put it on the box). Drivers may lack these; see sequencer.LID_STEPS.
LID_TARGET_NAMES: tuple[str, ...] = ("lid_above", "lid", "lid_box_above", "lid_on_box")


@dataclass(frozen=True)
class Pose:
    x_mm: float
    y_mm: float
    z_mm: float
    r_deg: float


class RobotError(RuntimeError):
    """The robot refused a command or reported an error."""


@runtime_checkable
class RobotDriver(Protocol):
    def enable(self) -> None: ...

    def move_to(self, target_name: str) -> None:
        """Block until the robot is at the named target. Raise RobotError if it cannot get there."""
        ...

    def set_vacuum(self, on: bool) -> None: ...

    def current_pose(self) -> Pose: ...

    def stop(self) -> None:
        """Stop motion now. Never raises."""
        ...

    def close(self) -> None: ...
