"""Can the first move of a run, straight from where the arm stands to home, be made? Standard library only.

Every run begins with a MovL to home. On 17 Nov the arm was left on a calibration mark at
(254.0, 26.7): the straight line from there to home (197.6, 302.4) needs J1 = 85.8 deg at
(210.5, 239.4), outside the M1 Pro's J1 range of +/-85 deg (dobot.j1_range_deg), and such a line
ends in controller alarm 23 before the robot moves (testing/live_runs/20261117_190902.csv). This
check only refuses Arm and says where to put the arm; it sends nothing.
"""

from __future__ import annotations

from typing import Any

MARGIN_DEG = 0.5  # the line must stay this far inside the J1 range
TITLE = "The arm can move straight home from where it stands"


def way_home_problem(arm: Any, j1_range_deg: Any, pose_xy: Any, home: Any) -> str:
    """'' when the straight line pose -> home stays inside the J1 range (or a value is missing: not checked)."""
    if arm is None or j1_range_deg is None or not pose_xy or not home or len(home) < 2:
        return ""
    peak = arm.j1_peak_on_line_deg((float(pose_xy[0]), float(pose_xy[1])), (float(home[0]), float(home[1])))
    if peak is None or peak <= float(j1_range_deg) - MARGIN_DEG:
        return ""
    need = "the arm cannot reach a point on it" if peak == float("inf") else f"J1 would have to go to {peak:.1f} deg"
    return (f"the arm stands at ({pose_xy[0]:.0f}, {pose_xy[1]:.0f}): on the straight move home {need} "
            f"(range +/-{float(j1_range_deg):g} deg), and the robot would stop with an alarm. Move the arm first, for example "
            "with Choton's 15_robot_setup.py (key x, then click on the box belt where the box stands: the cup goes above it)")


def gate_item(report: Any, problem: str) -> None:
    """Adds the check to the gate report as one more item (gate.py itself checks only values and files)."""
    report.items.append({"number": len(report.items) + 1, "title": TITLE, "ok": not problem, "problems": [problem] if problem else []})
    if problem:
        report.problems.append(problem)
