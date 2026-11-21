"""Can the arm reach a point in the configuration it is in? Standard library only.

The M1 Pro is modelled as a two-link arm (dobot.link1_mm, dobot.link2_mm): with 200 + 200 mm the
model gives the robot's own J1 and J2 to 0.01 deg (q_actual read from the feedback port, 17 Nov).
MovL keeps the arm's side (dobot.arm_side), so a point whose J1 in that side is above
control.arm_j1_max_deg is never picked (17 Nov: a path that needed J1 = 90.1 deg ended in
controller alarm 23). The check only refuses picks; it never adds a move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArmReach:
    link1_mm: float
    link2_mm: float
    left: bool  # left arm: J2 below 0
    j1_max_deg: float

    def joints_deg(self, x_mm: float, y_mm: float) -> tuple[float, float] | None:
        """(J1, J2) in degrees for the point in this arm side, or None if the links cannot reach it."""
        cos_j2 = (x_mm ** 2 + y_mm ** 2 - self.link1_mm ** 2 - self.link2_mm ** 2) / (2 * self.link1_mm * self.link2_mm)
        if not -1.0 <= cos_j2 <= 1.0:
            return None
        j2 = -math.acos(cos_j2) if self.left else math.acos(cos_j2)
        j1 = math.atan2(y_mm, x_mm) - math.atan2(self.link2_mm * math.sin(j2), self.link1_mm + self.link2_mm * math.cos(j2))
        return math.degrees(j1), math.degrees(j2)

    def j1_peak_on_line_deg(self, start_mm: tuple[float, float], end_mm: tuple[float, float], steps: int = 200) -> float:
        """The largest |J1| the arm needs anywhere on the straight line (a MovL) between two points;
        inf when the links cannot reach a point of the line."""
        peak = 0.0
        for step in range(steps + 1):
            part = step / steps
            joints = self.joints_deg(start_mm[0] + part * (end_mm[0] - start_mm[0]), start_mm[1] + part * (end_mm[1] - start_mm[1]))
            if joints is None:
                return math.inf
            peak = max(peak, abs(joints[0]))
        return peak

    def j1_beyond_limit_deg(self, x_mm: float, y_mm: float) -> float | None:
        """The J1 the point needs when that is beyond the limit (inf: no pose at all), else None."""
        joints = self.joints_deg(x_mm, y_mm)
        if joints is None:
            return math.inf
        return joints[0] if abs(joints[0]) > self.j1_max_deg else None


def arm_reach_from(config: Any) -> ArmReach | None:
    """From live_config.json; None (the check is off) while a value is not set."""
    values = [config.value("dobot", "link1_mm"), config.value("dobot", "link2_mm"), config.value("dobot", "arm_side"),
              config.value("control", "arm_j1_max_deg")]
    if any(value is None for value in values):
        return None
    link1_mm, link2_mm, side, j1_max_deg = values
    return ArmReach(float(link1_mm), float(link2_mm), side == "left", float(j1_max_deg))
