"""The arm's J1 check (control/arm_reach.py) and the box slot route, with the values measured on 17 Nov."""

import math

from cell_live.control.arm_reach import ArmReach, arm_reach_from
from cell_live.control.cycle_steps import mark_reach_objects
from cell_live.control.runlog import describe_detections
from cell_live.live_config import load_live_config
from cell_live.tests.control_fakes import item

ARM = ArmReach(200.0, 200.0, True, 80.0)
HOME, SLOT = (197.6, 302.4), (369.8, 27.9)  # Choton's 17 Nov home and box slot


def _max_j1_deg(start, end, steps=200):
    points = [(start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps) for i in range(steps + 1)]
    return max(ARM.joints_deg(*point)[0] for point in points)


def test_the_model_gives_the_joint_angles_the_robot_reported():
    # q_actual from the feedback port, 17 Nov: at home, and where the arm stood after the alarm was cleared
    for (x_mm, y_mm), measured in (((197.6, 302.4), (82.27, -50.87)), ((245.28, 239.67), (75.32, -61.96))):
        j1, j2 = ARM.joints_deg(x_mm, y_mm)
        assert abs(j1 - measured[0]) < 0.05 and abs(j2 - measured[1]) < 0.05, (j1, j2)


def test_the_straight_move_from_home_needed_more_than_the_robot_allowed_and_the_slot_route_does_not():
    candy = (205.4, -93.3)  # the pick that ended in controller alarm 23 (testing/live_runs/20261117_190902.csv)
    assert _max_j1_deg(HOME, candy) > 90.0
    assert _max_j1_deg(HOME, SLOT) <= 82.3 and _max_j1_deg(SLOT, candy) < 40.0


def test_points_beyond_the_j1_limit_or_the_links_are_reported():
    assert ARM.j1_beyond_limit_deg(205.0, -63.0) is None  # where the stop line leaves an item
    assert round(ARM.j1_beyond_limit_deg(160.0, 75.0), 1) == 88.9  # upstream, robot side of the belt
    assert ARM.j1_beyond_limit_deg(500.0, 0.0) == math.inf


def test_mark_reach_marks_what_the_arm_cannot_reach_and_the_log_says_why():
    near, far, ok = item("candy", 160.0, 75.0, 300), item("candy", 390.0, 0.0, 500), item("card", 205.0, -63.0, 200)
    skipped = mark_reach_objects([near, far, ok], 175, 375, ARM)
    assert skipped == [near, far] and ok["reachable"] and not near["reachable"]
    assert near["out_of_reach_j1_deg"] == 88.9 and "out_of_reach_j1_deg" not in far  # far: the radius rule first
    assert "ARM CANNOT REACH (J1 88.9 deg)" in describe_detections([near])


def test_without_the_arm_values_only_the_radius_counts():
    found = item("candy", 160.0, 75.0, 300)
    assert mark_reach_objects([found], 175, 375) == [] and found["reachable"]


def test_the_live_config_turns_the_check_on_with_the_measured_arm():
    arm = arm_reach_from(load_live_config())
    assert arm == ArmReach(200.0, 200.0, True, 80.0)
