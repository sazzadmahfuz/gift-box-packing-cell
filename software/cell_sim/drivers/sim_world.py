"""What the simulated belts carry. All times and distances come from config.json (ASSUMED).

Belt A (objects) is a moving belt: item n sits (n + 1) * item_spacing_mm behind the start of
the pick area. While belt A runs its odometer counts millimetres; an item is in the pick area
from odometer (n + 1) * spacing until (n + 1) * spacing + pick_area_length_mm, then it falls
off the far end. When the belt stops, every item stays where it is.

Belt B (boxes) is run by the Arduino Nano, not by the cell: a box arrives at the Nano's sensor
(S1) box_start_to_s1_mm after the previous one was taken away, and waits there until the
operator removes it, box_removal_time_s after the lid is on.
"""

from __future__ import annotations

import random

from ..config import CellConfig
from ..events import Event, EventKind, EventQueue


class SimWorld:
    def __init__(self, config: CellConfig, queue: EventQueue, s1_working: bool = True) -> None:
        self.config = config
        self.queue = queue
        self.s1_working = s1_working  # False only in tests: no box ever reaches S1
        self.rng = random.Random(config.random_seed)
        self.running = {"A": False, "B": False}
        self.s1_active = False
        self._item_types: list[str] = []  # item_types[n] = type of the n-th item on belt A
        self._entered = 0  # items that have entered the pick area so far
        self._in_area: dict[int, float] = {}  # item index -> time it entered the pick area
        self._odometer_mm = 0.0
        self._odometer_time_s = 0.0
        self._pending: list[Event] = []

    # Items on belt A

    def item_type(self, index: int) -> str:
        """Item types are drawn once per item, in belt order, from the seeded generator."""
        while len(self._item_types) <= index:
            self._item_types.append(self.rng.choice(self.config.items_per_box))
        return self._item_types[index]

    def items_in_area(self) -> list[tuple[int, str, float]]:
        """(item index, item type, time it entered), oldest first."""
        return [(index, self.item_type(index), entered_s) for index, entered_s in sorted(self._in_area.items())]

    def odometer_mm(self) -> float:
        if not self.running["A"]:
            return self._odometer_mm
        return self._odometer_mm + (self.queue.now_s - self._odometer_time_s) * self.config.belt_a_speed_mm_s

    def _entry_mm(self, index: int) -> float:
        return (index + 1) * self.config.item_spacing_mm

    # Belt commands

    def belt_started(self, name: str) -> None:
        if name == "A" and not self.running["A"]:
            self._odometer_time_s = self.queue.now_s
            self.running["A"] = True
            self._schedule_belt_a()
        elif name == "B":
            self.running["B"] = True

    def belt_stopped(self, name: str) -> None:
        if name == "A" and self.running["A"]:
            self._odometer_mm = self.odometer_mm()
            self._odometer_time_s = self.queue.now_s
            self.running["A"] = False
            self._cancel_pending()
        elif name == "B":
            self.running["B"] = False

    # Events

    def on_event(self, event: Event) -> None:
        kind = event.kind
        if kind is EventKind.START:
            self._bring_box()
        elif kind is EventKind.ITEM_ENTERS_AREA:
            self._in_area[event.payload["item_index"]] = event.time_s
            self._entered = event.payload["item_index"] + 1
            self._schedule_belt_a()
        elif kind is EventKind.ITEM_LEAVES_AREA:
            self._in_area.pop(event.payload["item_index"], None)
            self._schedule_belt_a()
        elif kind is EventKind.PICK_DONE and event.payload.get("item_id") is not None:
            self._in_area.pop(event.payload["item_id"], None)  # the robot took it off the belt
        elif kind is EventKind.S1_ON:
            self.s1_active = True
            self.running["B"] = False  # the Nano stops belt B at its sensor
        elif kind is EventKind.LID_DONE:
            self.queue.schedule_in(self.config.box_removal_time_s, EventKind.S1_OFF)
        elif kind is EventKind.S1_OFF:
            self.s1_active = False
            self._bring_box()

    def _bring_box(self) -> None:
        self.running["B"] = True
        if self.s1_working:
            self.queue.schedule_in(self.config.box_to_s1_time_s, EventKind.S1_ON)

    def _schedule_belt_a(self) -> None:
        """Schedule the next item entering and the next item leaving the pick area."""
        self._cancel_pending()
        if not self.running["A"]:
            return
        odometer_mm = self.odometer_mm()
        speed_mm_s = self.config.belt_a_speed_mm_s
        next_index = self._entered
        enter_in_s = (self._entry_mm(next_index) - odometer_mm) / speed_mm_s
        self._pending.append(self.queue.schedule_in(
            max(enter_in_s, 0.0), EventKind.ITEM_ENTERS_AREA, item_index=next_index, item_type=self.item_type(next_index)
        ))
        if self._in_area:
            oldest = min(self._in_area)
            leave_in_s = (self._entry_mm(oldest) + self.config.pick_area_length_mm - odometer_mm) / speed_mm_s
            self._pending.append(self.queue.schedule_in(
                max(leave_in_s, 0.0), EventKind.ITEM_LEAVES_AREA,
                item_index=oldest, item_type=self.item_type(oldest), entered_s=self._in_area[oldest],
            ))

    def _cancel_pending(self) -> None:
        for event in self._pending:
            self.queue.cancel(event)
        self._pending = []
