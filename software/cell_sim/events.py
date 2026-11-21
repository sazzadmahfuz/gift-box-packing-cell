"""Simulated clock and event queue. Time only jumps from event to event; nothing sleeps."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventKind(Enum):
    START = "START"
    S1_ON = "S1_ON"  # the Nano's box sensor stopped a box at the robot
    BOX_SEEN = "BOX_SEEN"  # the camera sees the open box standing still
    ITEM_ENTERS_AREA = "ITEM_ENTERS_AREA"  # an item is fully inside the camera's pick area
    ITEM_LEAVES_AREA = "ITEM_LEAVES_AREA"  # an item left the pick area at the far end of belt A
    SET_CONFIRMED = "SET_CONFIRMED"  # the full set was seen in several pictures in a row
    PICTURES_DONE = "PICTURES_DONE"  # robot out of view, pictures taken, objects located
    PICK_DONE = "PICK_DONE"
    PLACE_DONE = "PLACE_DONE"
    LID_DONE = "LID_DONE"
    S1_OFF = "S1_OFF"  # the operator took the closed box away
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class Event:
    time_s: float
    seq: int
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)


class EventQueue:
    """Events come out in time order; events at the same time come out in scheduling order."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, Event]] = []
        self._pending_seqs: set[int] = set()
        self._next_seq = 0
        self.now_s = 0.0

    def schedule_at(self, time_s: float, kind: EventKind, **payload: Any) -> Event:
        if time_s < self.now_s:
            raise ValueError(f"cannot schedule {kind.name} in the past ({time_s} < {self.now_s})")
        event = Event(time_s, self._next_seq, kind, payload)
        self._next_seq += 1
        heapq.heappush(self._heap, (time_s, event.seq, event))
        self._pending_seqs.add(event.seq)
        return event

    def schedule_in(self, delay_s: float, kind: EventKind, **payload: Any) -> Event:
        return self.schedule_at(self.now_s + delay_s, kind, **payload)

    def cancel(self, event: Event) -> None:
        """A cancelled event never comes out of the queue. Cancelling a popped event does nothing."""
        self._pending_seqs.discard(event.seq)

    def pop(self) -> Event:
        while True:
            _, _, event = heapq.heappop(self._heap)
            if event.seq in self._pending_seqs:
                self._pending_seqs.discard(event.seq)
                self.now_s = event.time_s
                return event

    def __len__(self) -> int:
        return len(self._pending_seqs)
