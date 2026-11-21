"""Event loop: device events drive the state machine, the state machine commands the cell.

One cycle (Choton_Week3_Notebook.md, team-confirmed 2026-11-16): wait for the box at S1 and
see it with the camera -> run belt A until the camera sees the full set in the pick area for
set_confirm_time_s -> stop belt A, robot home, pictures -> pick and place every item -> lid
-> the operator removes the box. Unneeded items pass the pick area and fall off belt A.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .cell import ActionRecord, Cell
from .config import CellConfig
from .controller import EXPECTED_EVENT_TEXT, State, StateMachine, Transition
from .drivers.sim_devices import build_sim_cell
from .events import Event, EventKind, EventQueue
from .interfaces import Detection, RobotError
from .recorder import CycleRecord, ItemRecord, SkippedRecord

# Builds the cell on the simulation's own event queue (sim, robodk, dobot modes).
CellFactory = Callable[[CellConfig, EventQueue], Cell]


@dataclass
class SimResult:
    cycles_requested: int
    final_state: State
    cycles: list[CycleRecord] = field(default_factory=list)
    items: list[ItemRecord] = field(default_factory=list)
    skipped: list[SkippedRecord] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    fault_reason: str | None = None
    end_time_s: float = 0.0


def choose_items(needed: tuple[str, ...], seen: list[Detection]) -> list[Detection] | None:
    """One detection per needed item, oldest first; None if the set is not complete."""
    available = sorted(seen, key=lambda detection: detection.time_s)
    plan: list[Detection] = []
    for item_type in needed:
        match = next((d for d in available if d.item_type == item_type and d not in plan), None)
        if match is None:
            return None
        plan.append(match)
    return plan


class Simulation:
    def __init__(
        self,
        config: CellConfig,
        cycles: int,
        s1_working: bool = True,
        realtime_factor: float | None = None,
        on_cycle: Callable[[CycleRecord], None] | None = None,
        cell_factory: CellFactory | None = None,
    ) -> None:
        if cycles < 1:
            raise ValueError("cycles must be at least 1")
        self.config = config
        self.cycles_requested = cycles
        self.realtime_factor = realtime_factor
        self.on_cycle = on_cycle
        self.queue = EventQueue()
        self.cell = build_sim_cell(config, self.queue, s1_working) if cell_factory is None else cell_factory(config, self.queue)
        self.machine = StateMachine(self.queue, config.timeouts_s)
        self.items: list[ItemRecord] = []
        self.skipped: list[SkippedRecord] = []
        self.cycles: list[CycleRecord] = []
        self.fault_reason: str | None = None
        self.finished = False
        self.cycle_number = 0
        self.cycle_times: dict[str, float] = {}
        self.cycle_skipped = 0
        self.plan: list[Detection] = []  # items the robot picks this cycle, in placing order
        self.plan_index = 0
        self.pick_start_s = 0.0
        self.pick_done_s = 0.0
        self.confirm_event: Event | None = None
        self.cycle_note = ""

    def run(self) -> SimResult:
        self.queue.schedule_in(0.0, EventKind.START)
        while not self.finished:
            if not self.queue:
                self._fault("event queue empty (no expected event left)")
                break
            previous_s = self.queue.now_s
            event = self.queue.pop()
            self._wait_realtime(event.time_s - previous_s)
            self._dispatch(event)
        return SimResult(
            self.cycles_requested, self.machine.state, self.cycles, self.items, self.skipped,
            self.machine.transitions, self.cell.actions, self.fault_reason, self.queue.now_s,
        )

    def _wait_realtime(self, delta_s: float) -> None:
        if self.realtime_factor and delta_s > 0:
            time.sleep(delta_s / self.realtime_factor)

    def _dispatch(self, event: Event) -> None:
        self.cell.on_event(event)
        if event.kind is EventKind.TIMEOUT:
            if self.machine.is_current_timeout(event):
                state = self.machine.state
                self._fault(f"timeout in {state.name}: {EXPECTED_EVENT_TEXT[state]}")
            return
        handler = getattr(self, f"_on_{event.kind.name.lower()}")
        try:
            handler(event)
        except RobotError as error:
            self._fault(f"robot error: {error}")

    def _expect(self, event: Event, *states: State) -> None:
        if self.machine.state not in states:
            raise RuntimeError(f"{event.kind.name} arrived in unexpected state {self.machine.state.name}")

    def _fault(self, reason: str) -> None:
        self.cell.stop_all()
        self.fault_reason = f"FAULT in {self.machine.state.name} at t={self.queue.now_s:.3f} s: {reason}"
        self.machine.enter(State.FAULT)
        self.finished = True

    # Box arrives

    def _on_start(self, event: Event) -> None:
        self._expect(event, State.INIT)
        self.cell.start()
        self.machine.enter(State.READY)
        self._start_cycle()

    def _start_cycle(self) -> None:
        self.cycle_number += 1
        self.cycle_skipped = 0
        self.cycle_note = ""
        self.cycle_times = {"cycle_start_s": self.queue.now_s}
        self.machine.enter(State.WAIT_BOX)

    def _on_s1_on(self, event: Event) -> None:
        self._expect(event, State.WAIT_BOX)
        self.cell.look_at_box()

    def _on_box_seen(self, event: Event) -> None:
        self._expect(event, State.WAIT_BOX)
        self.cycle_times["box_seen_s"] = self.queue.now_s
        self.machine.enter(State.FEED_SET)
        self.cell.start_feed()
        self._check_set()

    # Belt A runs until the full set is in the pick area

    def _on_item_enters_area(self, event: Event) -> None:
        self._expect(event, State.FEED_SET)
        self._check_set()

    def _on_item_leaves_area(self, event: Event) -> None:
        self._expect(event, State.FEED_SET)
        payload = event.payload
        self.skipped.append(SkippedRecord(self.cycle_number, payload["item_type"], payload["entered_s"], event.time_s))
        self.cycle_skipped += 1
        self._check_set()

    def _check_set(self) -> None:
        complete = choose_items(self.config.items_per_box, self.cell.items_in_view()) is not None
        if complete and self.confirm_event is None:
            self.confirm_event = self.queue.schedule_in(self.config.set_confirm_time_s, EventKind.SET_CONFIRMED)
        elif not complete and self.confirm_event is not None:
            self.queue.cancel(self.confirm_event)  # an item left before the camera was sure
            self.confirm_event = None

    def _on_set_confirmed(self, event: Event) -> None:
        self._expect(event, State.FEED_SET)
        self.confirm_event = None
        self.cell.stop_belt_a()
        self.cycle_times["set_ready_s"] = self.queue.now_s
        self.machine.enter(State.DETECT)
        self.cell.take_pictures()

    # Robot: pictures, then pick and place each item

    def _on_pictures_done(self, event: Event) -> None:
        self._expect(event, State.DETECT)
        self.cycle_times["pictures_done_s"] = self.queue.now_s
        plan = choose_items(self.config.items_per_box, self.cell.items_in_view())
        if plan is None:
            self._fault("the pictures no longer show the full set")
            return
        self.plan, self.plan_index = plan, 0
        self._start_pick()

    def _start_pick(self) -> None:
        self.machine.enter(State.PICK)
        target = self.plan[self.plan_index]
        self.pick_start_s = self.cell.start_pick(target.item_type, target.item_id)

    def _on_pick_done(self, event: Event) -> None:
        self._expect(event, State.PICK)
        self.pick_done_s = self.queue.now_s
        self.cell.finish_pick(event.payload["item_type"])
        self.machine.enter(State.PLACE)
        self.cell.start_place()

    def _on_place_done(self, event: Event) -> None:
        self._expect(event, State.PLACE)
        item_type = self.cell.finish_place()
        target = self.plan[self.plan_index]
        self.items.append(ItemRecord(
            self.cycle_number, self.plan_index + 1, item_type, target.time_s,
            self.pick_start_s, self.pick_done_s, self.queue.now_s,
        ))
        self.plan_index += 1
        if self.plan_index < len(self.plan):
            self._start_pick()
            return
        self.machine.enter(State.CLOSE_LID)
        self.cell.close_lid()

    # Lid, then the operator removes the box

    def _on_lid_done(self, event: Event) -> None:
        self._expect(event, State.CLOSE_LID)
        self.cycle_times["lid_done_s"] = self.queue.now_s
        self.cycle_note = event.payload.get("note", "")
        self.machine.enter(State.RELEASE_BOX)

    def _on_s1_off(self, event: Event) -> None:
        self._expect(event, State.RELEASE_BOX)
        self.cycle_times["box_removed_s"] = self.queue.now_s
        self.machine.enter(State.CYCLE_DONE)
        record = CycleRecord(
            cycle=self.cycle_number,
            items=tuple(r.item_type for r in self.items if r.cycle == self.cycle_number),
            cycle_done_s=self.queue.now_s,
            skipped_count=self.cycle_skipped,
            note=self.cycle_note,
            **self.cycle_times,
        )
        self.cycles.append(record)
        if self.on_cycle is not None:
            self.on_cycle(record)
        self.machine.enter(State.READY)
        if self.cycle_number >= self.cycles_requested:
            self.finished = True
        else:
            self._start_cycle()


def run_simulation(
    config: CellConfig,
    cycles: int,
    s1_working: bool = True,
    realtime_factor: float | None = None,
    on_cycle: Callable[[CycleRecord], None] | None = None,
) -> SimResult:
    return Simulation(config, cycles, s1_working, realtime_factor, on_cycle).run()
