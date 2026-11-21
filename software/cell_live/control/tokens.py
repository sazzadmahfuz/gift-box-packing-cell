"""One-time arm tokens for the safety gate. Standard library only."""

from __future__ import annotations

import secrets
import time
from typing import Callable


class ArmTokens:
    """One-time tokens: valid for lifetime_s, only for the box count and speed they were armed with."""

    def __init__(self, lifetime_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.lifetime_s = lifetime_s
        self.clock = clock
        self._tokens: dict[str, tuple[float, int, int]] = {}

    def issue(self, boxes: int, speed_percent: int) -> str:
        token = secrets.token_hex(16)
        self._tokens[token] = (self.clock() + self.lifetime_s, boxes, speed_percent)
        return token

    def redeem(self, token: str, boxes: int, speed_percent: int) -> str:
        """'' if the token is valid for these values; otherwise why not. A token works once."""
        entry = self._tokens.pop(token, None) if isinstance(token, str) else None
        if entry is None:
            return "no valid arm token: press Arm first"
        expires_at, armed_boxes, armed_speed = entry
        if self.clock() > expires_at:
            return f"arm token expired (valid {self.lifetime_s:g} s): press Arm again"
        if (boxes, speed_percent) != (armed_boxes, armed_speed):
            return f"start values ({boxes} boxes, {speed_percent} %) differ from the armed ones ({armed_boxes}, {armed_speed} %)"
        return ""
