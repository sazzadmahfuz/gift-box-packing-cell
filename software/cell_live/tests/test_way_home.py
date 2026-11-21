"""The first move of a run is a straight MovL to home: Arm refuses when that line leaves the J1 range
(control/way_home.py). 17 Nov, after the calibration: the arm stood on the middle mark at (254.0, 26.7)."""

from types import SimpleNamespace

from cell_live.control.arm_reach import ArmReach
from cell_live.control.gate import GateReport
from cell_live.control.way_home import TITLE, gate_item, way_home_problem
from cell_live.dobot_link import FeedbackPacket
from cell_live.tests.control_fakes import choton_settings
from cell_live.tests.test_runlog_and_api import ROBOT_OK, lab_config, service

ARM = ArmReach(200.0, 200.0, True, 80.0)
HOME = [197.6, 302.4, 189.7, -36.9]  # taught 17 Nov


def test_from_the_calibration_mark_the_straight_move_home_leaves_the_j1_range():
    problem = way_home_problem(ARM, 85, [254.03, 26.67, 68.17, -192.9], HOME)
    assert problem.startswith("the arm stands at (254, 27): on the straight move home J1 would have to go to 85.8 deg (range +/-85 deg)")
    assert "Move the arm first" in problem and round(ARM.j1_peak_on_line_deg((254.03, 26.67), (197.6, 302.4)), 1) == 85.8


def test_from_above_the_box_slot_and_from_home_itself_the_move_is_fine():
    assert way_home_problem(ARM, 85, [349.6, 38.7, 174.1, -117.6], HOME) == ""  # the route of every pick: J1 up to 82.3 deg
    assert way_home_problem(ARM, 85, HOME, HOME) == ""
    assert round(ARM.j1_peak_on_line_deg((349.6, 38.7), (197.6, 302.4)), 1) == 82.3


def test_a_line_that_starts_where_the_links_cannot_reach_is_refused_too():
    assert "the arm cannot reach a point on it" in way_home_problem(ARM, 85, [390.0, -200.0], HOME)  # 438 mm from the base


def test_nothing_is_checked_while_a_value_is_missing():
    assert way_home_problem(None, 85, [254.0, 26.7], HOME) == "" and way_home_problem(ARM, None, [254.0, 26.7], HOME) == ""
    assert way_home_problem(ARM, 85, None, HOME) == "" and way_home_problem(ARM, 85, [254.0, 26.7], None) == ""


def test_the_check_is_one_more_gate_item():
    report = GateReport([], [], [{"number": 1, "title": "first", "ok": True, "problems": []}])
    gate_item(report, "")
    assert report.ok and report.items[-1] == {"number": 2, "title": TITLE, "ok": True, "problems": []}
    gate_item(report, "the arm stands at (254, 27): ...")
    assert not report.ok and report.items[-1]["number"] == 3 and report.items[-1]["problems"] == ["the arm stands at (254, 27): ..."]


def test_arm_is_refused_while_the_arm_stands_where_the_way_home_leaves_the_j1_range(tmp_path):
    settings = choton_settings(lid=False)
    settings["robot"]["home"] = HOME  # the test settings hold the 12 Nov home
    run = service(tmp_path, config=lab_config(), robot=ROBOT_OK, settings=settings)
    run.link = SimpleNamespace(last_packet=FeedbackPacket({"pose_xyzr": [254.03, 26.67, 68.17, -192.9]}, 0.0, 1.0))
    reply = run.gate({"hand_on_estop": True, "boxes": 1})
    item = reply["items"][-1]
    assert item["title"] == TITLE and item["ok"] is False and "J1 would have to go to" in item["problems"][0]
    assert any("J1 would have to go to" in problem for problem in run.arm({"hand_on_estop": True, "boxes": 1})["problems"])
    run.link = SimpleNamespace(last_packet=FeedbackPacket({"pose_xyzr": [349.6, 38.7, 174.1, -117.6]}, 0.0, 1.0))
    assert run.gate({"hand_on_estop": True, "boxes": 1})["items"][-1]["ok"] is True
