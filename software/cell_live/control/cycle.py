"""The real box cycle as a state machine, one thread per run. No input(), no windows.

A timeout, a refused move or a missing object -> PAUSED (outputs off, robot still): the operator
chooses Retry, Skip box or Abort. A robot alarm, a lost connection or a lost camera -> FAULT
(outputs off if possible): only Abort. Pause takes effect at the next safe point (never while
the robot carries an item). The software e-stop works from any state and is NOT the physical one.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from .cycle_steps import STEPS
from .run_context import BoxState, RunContext
from .states import (
    BOX_STEPS, OPERATOR_PAUSE, RETRY_FROM_LOOK, SOFTWARE_ESTOP, AbortRequested, Action, CycleState,
    PauseRequested, RefeedRequested, StepFault, StepPause,
)

ContextBuilder = Callable[["RunController"], RunContext]


class RunController:
    def __init__(self, build_context: ContextBuilder, boxes: int, session: Any, log: Any,
                 clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.boxes = boxes
        self.session = session
        self.log = log
        self.clock = clock
        self.state = CycleState.IDLE
        self.step: CycleState | None = None
        self.box_number = 0
        self.pause_reason = ""
        self.fault = ""
        self.output_reports: list[str] = []
        self.box_results: list[dict[str, Any]] = []
        self.finished = False
        self.on_change = on_change
        self._step_started_s = clock()
        self._pause = threading.Event()
        self._abort = threading.Event()
        self._estopped = False
        self._abort_given = False  # the operator's Abort was already taken (from PAUSED or FAULT)
        self._actions: "queue.Queue[Action]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self.context = build_context(self)

    # Operator actions (API threads)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="box-cycle", daemon=True)
        self._thread.start()

    def request_pause(self) -> None:
        self._pause.set()

    def act(self, action: Action) -> str:
        if self.state in (CycleState.PAUSED, CycleState.FAULT):
            if self.state is CycleState.FAULT and action is not Action.ABORT:
                return "after a FAULT only Abort is possible"
            self._actions.put(action)
            return f"{action.value} accepted"
        if action is Action.ABORT:
            self._abort.set()
            return "abort requested: the run stops at the next safe point"
        return f"{action.value} is only possible while PAUSED"

    def estop(self) -> list[str]:
        """Software e-stop (not the physical emergency stop)."""
        self._estopped = True
        self._abort.set()
        reports = self.session.software_estop()
        self._enter_fault(SOFTWARE_ESTOP, reports)  # the cycle thread then waits for the operator's Abort
        return reports

    def clear_alarm(self) -> str:
        text = self.session.clear_alarm()
        self.log.event("operator cleared the alarm", reply=text)
        return text

    def wait(self, timeout_s: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout_s)

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "step": self.step.value if self.step else None,
            "step_elapsed_s": round(self.clock() - self._step_started_s, 1) if self.step else None,
            "box": self.box_number,
            "boxes": self.boxes,
            "pause_reason": self.pause_reason,
            "fault": self.fault,
            "outputs": self.output_reports,
            "box_results": self.box_results,
            "finished": self.finished,
            "run_log": str(getattr(self.log, "path", "")),
            "events": list(getattr(self.log, "events", []))[-20:],
        }

    # Used by the steps

    def checkpoint(self) -> None:
        if self._abort.is_set():
            raise AbortRequested()
        if self._pause.is_set():
            raise PauseRequested()

    def sleep(self, duration_s: float) -> None:
        if self._abort.wait(duration_s):
            raise AbortRequested()

    # The run (cycle thread)

    def _run(self) -> None:
        try:
            for number in range(1, self.boxes + 1):
                self.box_number = number
                self.log.box = number
                if self._run_box(BoxState(number)) == "stop":
                    break
        finally:
            self._finish()

    def _run_box(self, box: BoxState) -> str:
        index = 0
        while index < len(BOX_STEPS):
            step = BOX_STEPS[index]
            try:
                self._enter(step)
                STEPS[step](self.context, box)
                index += 1
                continue
            except RefeedRequested as more:  # not a pause: the belt brings the rest of the set
                self.log.event(f"the box still needs objects: {more}; the object belt runs again")
                index = BOX_STEPS.index(CycleState.FEED_OBJECTS)
                continue
            except PauseRequested:
                decision = self._paused(step, OPERATOR_PAUSE, "")
            except StepPause as pause:
                decision = self._paused(step, pause.reason, pause.detail)
            except AbortRequested:
                return self._stopped(box, "aborted")
            except StepFault as fault:
                return self._faulted(box, str(fault))
            except Exception as error:  # camera lost, or anything unexpected: never carry on
                return self._faulted(box, f"{type(error).__name__}: {error}")
            if decision is Action.ABORT:
                return self._stopped(box, "aborted")
            if decision is Action.SKIP_BOX:
                self._box_result(box, "skipped by the operator")
                return "next"
            box.refeeds = 0  # the operator retries: the object belt may run again
            index = BOX_STEPS.index(CycleState.LOOK) if step in RETRY_FROM_LOOK else index
        try:
            self._enter(CycleState.BOX_DONE)
        except AbortRequested:
            return self._stopped(box, "aborted")
        self._box_result(box, "done")
        return "next"

    def _stopped(self, box: BoxState, result: str) -> str:
        if self._estopped:  # stay in FAULT until the operator aborts (and may clear the alarm first)
            return self._faulted(box, SOFTWARE_ESTOP)
        self._box_result(box, result)
        return "stop"

    def _enter(self, state: CycleState) -> None:
        if self._estopped:
            raise AbortRequested()
        self.state = self.step = state
        self._step_started_s = self.clock()
        self.log.state = state.value
        self.log.event(f"enter {state.value}")
        self._changed()

    def _paused(self, step: CycleState, reason: str, detail: str) -> Action:
        if self._estopped:
            return Action.ABORT
        self.output_reports = self.session.outputs_off()
        self.state, self.step, self.pause_reason = CycleState.PAUSED, step, f"{reason}: {detail}" if detail else reason
        self._pause.clear()
        self.log.event(f"PAUSED ({self.pause_reason}) in {step.value}; outputs: {'; '.join(self.output_reports)}", state="PAUSED")
        self._changed()
        action = self._actions.get()
        self._abort_given = action is Action.ABORT
        self.pause_reason = ""
        self.log.event(f"operator: {action.value}", state=self.state.value)
        return action

    def _faulted(self, box: BoxState, reason: str) -> str:
        """Stay in FAULT (session open, so the operator can clear the alarm) until Abort."""
        if not self._estopped:
            self._enter_fault(reason, self.session.outputs_off())
        self._box_result(box, f"fault: {self.fault}")
        while not self._abort_given:
            self._abort_given = self._actions.get() is Action.ABORT
        return "stop"

    def _enter_fault(self, reason: str, reports: list[str]) -> None:
        self.output_reports = reports
        self.state, self.fault = CycleState.FAULT, reason
        self.log.event(f"FAULT: {reason}; outputs: {'; '.join(reports)}", fault=reason, state="FAULT")
        self._changed()

    def _box_result(self, box: BoxState, result: str) -> None:
        placed = [f"{p.get('color', '')} {p['type']}".strip() for p in box.placed]
        self.box_results.append({"box": box.number, "result": result, "placed": placed, "lid": box.lid})
        self.log.event(f"box {box.number}: {result}; placed {placed}; lid {box.lid}")

    def _finish(self) -> None:
        reports = self.session.close()
        if self.state is not CycleState.FAULT:
            self.output_reports = reports
        self.log.event(f"run finished; outputs: {'; '.join(reports)}", state="IDLE")
        self.log.close()
        self.state, self.step, self.finished = CycleState.IDLE, None, True
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change(self.snapshot())
            except Exception:  # the UI must never break the run
                pass
