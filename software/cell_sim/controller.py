"""Cell states, the allowed transitions, and the timeout hook.

The cycle follows the team's working set-up (Choton_Week3_Notebook.md, confirmed 2026-11-16):
a box arrives on belt B, belt A runs until the camera sees the full set in the pick area, the
robot picks and places every item, closes the box with the lid, and the operator removes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .events import Event, EventKind, EventQueue


class State(Enum):
    INIT = "INIT"
    READY = "READY"
    WAIT_BOX = "WAIT_BOX"
    FEED_SET = "FEED_SET"
    DETECT = "DETECT"
    PICK = "PICK"
    PLACE = "PLACE"
    CLOSE_LID = "CLOSE_LID"
    RELEASE_BOX = "RELEASE_BOX"
    CYCLE_DONE = "CYCLE_DONE"
    FAULT = "FAULT"


_NORMAL_TRANSITIONS: dict[State, set[State]] = {
    State.INIT: {State.READY},
    State.READY: {State.WAIT_BOX},
    State.WAIT_BOX: {State.FEED_SET},
    State.FEED_SET: {State.DETECT},
    State.DETECT: {State.PICK},
    State.PICK: {State.PLACE},
    State.PLACE: {State.PICK, State.CLOSE_LID},
    State.CLOSE_LID: {State.RELEASE_BOX},
    State.RELEASE_BOX: {State.CYCLE_DONE},
    State.CYCLE_DONE: {State.READY},
    State.FAULT: set(),
}

# Every state except FAULT itself may go to FAULT.
TRANSITIONS: dict[State, frozenset[State]] = {
    state: frozenset(targets | ({State.FAULT} if state is not State.FAULT else set()))
    for state, targets in _NORMAL_TRANSITIONS.items()
}

# States that wait for an event and therefore have a timeout.
TIMEOUT_STATES: tuple[State, ...] = (
    State.WAIT_BOX,
    State.FEED_SET,
    State.DETECT,
    State.PICK,
    State.PLACE,
    State.CLOSE_LID,
    State.RELEASE_BOX,
)

EXPECTED_EVENT_TEXT: dict[State, str] = {
    State.WAIT_BOX: "no box reached sensor S1 (or the camera did not see it)",
    State.FEED_SET: "the camera did not see the full set of items in the pick area",
    State.DETECT: "the robot did not finish the pictures",
    State.PICK: "the pick did not finish",
    State.PLACE: "the place did not finish",
    State.CLOSE_LID: "the lid was not put on the box",
    State.RELEASE_BOX: "the operator did not remove the closed box",
}


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class Transition:
    time_s: float
    from_state: State
    to_state: State


class StateMachine:
    """Tracks the current state and arms one timeout per entry into a waiting state."""

    def __init__(self, queue: EventQueue, timeouts_s: Mapping[State, float]) -> None:
        self.queue = queue
        self.timeouts_s = dict(timeouts_s)
        self.state = State.INIT
        self.transitions: list[Transition] = []
        self._entry_token = 0

    def enter(self, new_state: State) -> None:
        if new_state not in TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.state.name} -> {new_state.name} is not allowed")
        self.transitions.append(Transition(self.queue.now_s, self.state, new_state))
        self.state = new_state
        self._entry_token += 1
        timeout_s = self.timeouts_s.get(new_state)
        if timeout_s is not None:
            self.queue.schedule_in(
                timeout_s, EventKind.TIMEOUT, token=self._entry_token, state=new_state
            )

    def is_current_timeout(self, event: Event) -> bool:
        """A timeout counts only if the state has not changed since it was armed."""
        return event.kind is EventKind.TIMEOUT and event.payload["token"] == self._entry_token
