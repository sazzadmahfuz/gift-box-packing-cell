"""Clock interface and the wall clock. The simulated clock is in drivers/sim_devices.py."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now_s(self) -> float: ...

    def sleep_s(self, duration_s: float) -> None: ...


class WallClock:
    """Real time in seconds since the clock was created."""

    def __init__(self) -> None:
        self._start_s = time.monotonic()

    def now_s(self) -> float:
        return time.monotonic() - self._start_s

    def sleep_s(self, duration_s: float) -> None:
        if duration_s > 0:
            time.sleep(duration_s)
