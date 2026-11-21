"""Bench fallback only: an operator starts and stops the belts by hand and reports S1.

Use this for bench debugging when the Arduino link is not available. It is never used in
sim mode. `ask` and `say` default to input() and print(); tests pass their own.
"""

from __future__ import annotations

import threading
from typing import Callable

Ask = Callable[[str], str]
Say = Callable[[str], None]


class ManualBelt:
    def __init__(self, name: str, ask: Ask = input, say: Say = print) -> None:
        if name not in ("A", "B"):
            raise ValueError(f"belt name must be 'A' or 'B', got {name!r}")
        self.name = name
        self._ask = ask
        self._say = say
        self._running = False

    def start(self) -> None:
        self._say(f"[BENCH] Start belt {self.name} by hand.")
        self._ask(f"[BENCH] Press Enter when belt {self.name} is running: ")
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._say(f"[BENCH] Stop belt {self.name} by hand now.")
        self._ask(f"[BENCH] Press Enter when belt {self.name} has stopped: ")
        self._running = False

    def is_running(self) -> bool:
        return self._running


class ManualSensor:
    """S1 reported by the operator: each Enter press toggles the state.

    A background thread waits for the presses, so the cell keeps running (and its timeouts
    keep counting) while nobody presses anything.
    """

    def __init__(self, ask: Ask = input, say: Say = print) -> None:
        self._ask = ask
        self._say = say
        self._active = False
        self._lock = threading.Lock()
        self._changed = threading.Event()
        self._thread: threading.Thread | None = None

    def start_listening(self) -> None:
        if self._thread is not None:
            return
        self._say("[BENCH] S1 by hand: press Enter when the box reaches S1, and again when it has left.")
        self._thread = threading.Thread(target=self._listen, name="manual-s1", daemon=True)
        self._thread.start()

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def wait_for_change(self, timeout_s: float) -> bool:
        """Block until the next toggle or the timeout; True if the state changed."""
        changed = self._changed.wait(timeout_s)
        self._changed.clear()
        return changed

    def _listen(self) -> None:
        while True:
            try:
                self._ask("")
            except (EOFError, KeyboardInterrupt):
                return
            with self._lock:
                self._active = not self._active
                state = "ACTIVE (box at S1)" if self._active else "inactive (box gone)"
            self._say(f"[BENCH] S1 {state}")
            self._changed.set()
