"""Runs each check on its own interval in its own thread, and on demand. Standard library only.

Every status change goes to the EventHub, which feeds the Server-Sent Events stream. The hub
carries typed events: "status" (a component), "run" (the real run), "trace" (commands, replies).
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from typing import Any, Callable

from .status import FAIL, CheckResult, ComponentStatus, now_s

HISTORY_LENGTH = 50


class EventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def publish(self, event: dict[str, Any], kind: str = "status") -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait((kind, event))
            except queue.Full:  # a slow client misses updates; the next full status catches up
                pass


class Poller:
    def __init__(self, checks: list[Any], hub: EventHub | None = None, clock: Callable[[], float] = now_s) -> None:
        self.checks = {check.id: check for check in checks}
        self.statuses = {check.id: ComponentStatus(check.id, check.name) for check in checks}
        self.history = {check.id: deque(maxlen=HISTORY_LENGTH) for check in checks}
        self.hub = hub or EventHub()
        self.clock = clock
        self._locks = {check.id: threading.Lock() for check in checks}
        self._wake = {check.id: threading.Event() for check in checks}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def check_now(self, component_id: str) -> ComponentStatus:
        """Run one check at once (also used by the polling threads)."""
        check = self.checks[component_id]
        with self._locks[component_id]:
            try:
                result = check.run()
            except Exception as error:  # a bug or surprise in a check must not stop the others
                result = CheckResult(FAIL, f"check crashed: {type(error).__name__}: {error}")
            status = self.statuses[component_id]
            status.apply(result, self.clock())
            self.history[component_id].append(
                {"checked_at": status.checked_at, "state": status.state, "detail": status.detail, "latency_ms": status.latency_ms}
            )
            snapshot = self._describe(component_id)
        self.hub.publish(snapshot)
        for dependent in getattr(check, "triggers", ()):  # checks that read what this one fetched
            if dependent in self._wake:
                self._wake[dependent].set()
        return status

    def _describe(self, component_id: str) -> dict[str, Any]:
        check = self.checks[component_id]
        described = self.statuses[component_id].to_dict()
        described["interval_s"] = check.interval_s
        described["kind"] = getattr(check, "kind", "hardware")  # "file": a file on this PC, not a device
        return described

    def snapshot(self) -> list[dict[str, Any]]:
        return [self._describe(component_id) for component_id in self.statuses]

    def detail(self, component_id: str) -> dict[str, Any]:
        """One component with its last checks, newest first (for the UI drawer)."""
        return {**self._describe(component_id), "history": list(reversed(self.history[component_id]))}

    def start(self) -> None:
        for component_id, check in self.checks.items():
            thread = threading.Thread(target=self._loop, args=(component_id, check.interval_s), name=f"check-{component_id}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def request(self, component_id: str) -> None:
        """Ask the polling thread to check now instead of waiting for its interval."""
        self._wake[component_id].set()

    def stop(self) -> None:
        self._stop.set()
        for wake in self._wake.values():
            wake.set()

    def _loop(self, component_id: str, interval_s: float) -> None:
        while not self._stop.is_set():
            self.check_now(component_id)
            self._wake[component_id].wait(interval_s)
            self._wake[component_id].clear()
