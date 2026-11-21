"""Component states and timing. Standard library only.

Every status says when it was checked, when it was last OK, how long the check took, and in
plain words what was seen. Nothing here is simulated: what cannot be observed says so.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

OK, WARN, FAIL, UNKNOWN, NOT_OBSERVABLE = "OK", "WARN", "FAIL", "UNKNOWN", "NOT_OBSERVABLE"
STATES = (OK, WARN, FAIL, UNKNOWN, NOT_OBSERVABLE)


def now_s() -> float:
    """Wall-clock time in seconds since the epoch (what the UI shows)."""
    return time.time()


@dataclass(frozen=True)
class CheckResult:
    """What one check saw. latency_ms is None when nothing was measured."""

    state: str
    detail: str
    latency_ms: float | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"unknown state {self.state!r}")


@dataclass
class ComponentStatus:
    id: str
    name: str
    state: str = UNKNOWN
    detail: str = "not checked yet"
    checked_at: float | None = None
    last_ok_at: float | None = None
    latency_ms: float | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def apply(self, result: CheckResult, checked_at: float) -> None:
        """Record a new check. FAIL clears the latency but keeps last_ok_at."""
        self.state = result.state
        self.detail = result.detail
        self.checked_at = checked_at
        self.data = dict(result.data)
        self.latency_ms = None if result.state == FAIL else result.latency_ms
        if result.state == OK:
            self.last_ok_at = checked_at

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def timed(action: Callable[[], Any]) -> tuple[Any, float]:
    """Run action and return (its result, elapsed time in ms)."""
    start_s = time.perf_counter()
    result = action()
    return result, (time.perf_counter() - start_s) * 1000.0


def missing_package(package: str, install: str) -> CheckResult:
    return CheckResult(FAIL, f"Python package '{package}' is not installed. Install it with: {install}")
