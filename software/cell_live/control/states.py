"""States, pause reasons, faults and operator actions of the real box cycle. Standard library only."""

from __future__ import annotations

from enum import Enum


class CycleState(str, Enum):
    IDLE = "IDLE"
    WAIT_BOX = "WAIT_BOX"
    FEED_OBJECTS = "FEED_OBJECTS"
    LOOK = "LOOK"
    PICK_PLACE = "PICK_PLACE"
    CLOSE_LID = "CLOSE_LID"
    RELEASE_BOX = "RELEASE_BOX"
    BOX_DONE = "BOX_DONE"
    PAUSED = "PAUSED"
    FAULT = "FAULT"


# The steps of one box, in order (BOX_DONE follows the last one).
BOX_STEPS: tuple[CycleState, ...] = (
    CycleState.WAIT_BOX,
    CycleState.FEED_OBJECTS,
    CycleState.LOOK,
    CycleState.PICK_PLACE,
    CycleState.CLOSE_LID,
    CycleState.RELEASE_BOX,
)
# "Retry" after a pause in these steps starts again with a fresh picture.
RETRY_FROM_LOOK = (CycleState.PICK_PLACE, CycleState.CLOSE_LID)


class Action(str, Enum):
    RETRY = "retry"  # also "resume" after an operator pause
    SKIP_BOX = "skip_box"
    ABORT = "abort"


# Pause reasons (shown to the operator and written to the run log)
NO_BOX = "no box"
BOX_NOT_UNDER_SLOT = "box not under the box slot"
NOT_ENOUGH_OBJECTS = "not enough objects"
OBJECT_MISSING = "object missing"
LID_NOT_FOUND = "lid not found or out of reach"
BOX_DID_NOT_LEAVE = "box did not leave"
MOVE_REFUSED = "move refused"
OPERATOR_PAUSE = "paused by the operator"

SOFTWARE_ESTOP = "software e-stop (not the physical emergency stop)"


class StepPause(Exception):
    """A step cannot go on, but the robot is fine: outputs off, wait for the operator."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class StepFault(Exception):
    """Robot alarm, lost connection or lost camera: outputs off (if possible), only Abort."""


class RefeedRequested(Exception):
    """The pictures hold none of the objects the box still needs: the object belt runs again (FEED_OBJECTS)."""


class PauseRequested(Exception):
    """The operator pressed Pause; raised at the next safe point."""


class AbortRequested(Exception):
    """The operator pressed Abort; raised at the next safe point."""
