"""RoboDK API reachability: a TCP connect to this PC, closed at once (no data sent)."""

from __future__ import annotations

import socket
from typing import Callable

from ..status import FAIL, OK, CheckResult, timed


class RoboDKCheck:
    id = "robodk"
    name = "RoboDK API"

    def __init__(self, host: str, port: int, interval_s: float, timeout_s: float = 1.0,
                 connect: Callable[..., socket.socket] = socket.create_connection) -> None:
        self.host = host
        self.port = port
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self.connect = connect

    def run(self) -> CheckResult:
        try:
            connection, latency_ms = timed(lambda: self.connect((self.host, self.port), timeout=self.timeout_s))
        except OSError as error:
            return CheckResult(FAIL, f"nothing answers at {self.host}:{self.port} ({error}): RoboDK closed, or its API server is off")
        connection.close()
        return CheckResult(OK, f"RoboDK API answers at {self.host}:{self.port}", latency_ms)
