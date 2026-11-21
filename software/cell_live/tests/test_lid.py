"""Which lid the robot takes and where it grips it (control/lid.py). Run 3 on 17 Nov
(testing/live_runs/20261117_195652.csv): the lid lay against the box on its upstream side at
(351.5, 175.3), 392.8 mm from the robot, 17.8 mm beyond the reach of 375 mm."""

import dataclasses
import math

from cell_live.control.arm_reach import ArmReach
from cell_live.control.lid import LidRule, choose_lid, place_point
from cell_live.control.states import Action, CycleState
from cell_live.tests.control_fakes import full_set, item, wait_for
from cell_live.tests.test_cycle import LIMITS, make_run

SLOT = (349.6, 38.7)  # taught 17 Nov
ARM = ArmReach(200.0, 200.0, True, 80.0)
LID_OF_RUN_3 = item("lid", 351.5, 175.3, 835, conf=0.89, angle=5.0)
CENTRE_ONLY = LidRule(175.0, 375.0, ARM, 80.0, 0.0)  # control.lid_grip_offset_max_mm = 0: as delivered
OFF_CENTRE = dataclasses.replace(CENTRE_ONLY, grip_offset_max_mm=30.0)  # set with the teacher's approval


def test_a_lid_inside_the_reach_is_gripped_at_its_centre():
    lid = item("lid", 350.0, -92.0, 190)  # against the box on its downstream side: 361.9 mm
    choice = choose_lid([lid], SLOT, CENTRE_ONLY)
    assert choice.lid is lid and choice.grip_mm == (350.0, -92.0) and choice.off_centre_mm == 0.0
    assert choice.words == "lid at (350.0, -92.0)"
    assert place_point(SLOT, lid, choice.grip_mm, -3.0) == SLOT


def test_the_lid_of_run_3_is_refused_at_its_centre_and_the_text_says_how_far_to_move_it():
    choice = choose_lid([LID_OF_RUN_3], SLOT, CENTRE_ONLY)
    assert choice.lid is None
    assert choice.words == ("no lid 175-375 mm from the robot and 80 mm or more from the box slot in the last picture "
                            "(the lid at (352, 175) is 393 mm from the robot: move it 20 mm or more towards the robot, "
                            "or lay it against the box on its downstream side (left of the box on Vision))")


def test_with_the_offset_allowed_the_lid_of_run_3_is_gripped_inside_the_reach_on_the_line_to_the_robot():
    choice = choose_lid([LID_OF_RUN_3], SLOT, OFF_CENTRE)
    grip = choice.grip_mm
    assert choice.lid is LID_OF_RUN_3 and math.isclose(math.hypot(*grip), 373.0, abs_tol=0.1)  # 2 mm inside the reach
    assert math.isclose(grip[1] / grip[0], 175.3 / 351.5, abs_tol=0.001) and math.isclose(choice.off_centre_mm, 19.8, abs_tol=0.1)
    assert choice.words.startswith("lid at (351.5, 175.3), gripped 19.8 mm from its centre at (333.8, 166.5)")
    place = place_point(SLOT, LID_OF_RUN_3, grip, 0.0)  # the same offset at the box: the lid's centre lands on the slot
    assert math.isclose(place[0] - SLOT[0], grip[0] - 351.5, abs_tol=0.05) and math.isclose(place[1] - SLOT[1], grip[1] - 175.3, abs_tol=0.05)
    assert OFF_CENTRE.reachable(*place)


def test_the_offset_turns_with_the_lid():
    lid = item("lid", 300.0, 100.0, 700)
    assert place_point((350.0, 40.0), lid, (290.0, 100.0), 90.0) == (350.0, 30.0)  # 10 mm towards -x becomes 10 mm towards -y
    assert place_point((350.0, 40.0), lid, (290.0, 100.0), -90.0) == (350.0, 50.0)


def test_a_lid_further_out_than_the_offset_allows_is_refused():
    far = item("lid", 351.0, 205.0, 900)  # 406.5 mm from the robot: a lid lying upstream with a gap to the box
    choice = choose_lid([far], SLOT, OFF_CENTRE)
    assert choice.lid is None and "is 406 mm from the robot: move it 4 mm or more towards the robot" in choice.words


def test_the_filled_box_and_a_cut_off_lid_are_named_and_the_usable_lid_is_taken():
    filled_box = item("lid", 358.5, 32.1, 640, conf=0.95)  # 10 mm from the slot
    cut_off = item("lid", 340.0, 150.0, 1200, conf=0.93, edge=True)
    good = item("lid", 350.0, -92.0, 190, conf=0.6)
    assert choose_lid([filled_box, cut_off, good], SLOT, CENTRE_ONLY).lid is good
    words = choose_lid([filled_box, cut_off], SLOT, CENTRE_ONLY).words
    assert "the lid seen at (358, 32) is the box itself" in words
    assert "the lid at (340, 150) is cut off by the picture edge: lay it against the box on its downstream side" in words
    assert choose_lid([], SLOT, CENTRE_ONLY).words == "no lid 175-375 mm from the robot and 80 mm or more from the box slot in the last picture"


def _run(limits, lid):
    controller, session, vision, log = make_run(vision_kwargs={"look_objects": full_set() + [lid]})
    controller.context = dataclasses.replace(controller.context, limits=limits)
    return controller, session, log


def test_in_a_run_the_out_of_reach_lid_pauses_while_the_offset_is_off():
    controller, session, log = _run(dataclasses.replace(LIMITS, lid_min_from_slot_mm=80.0), LID_OF_RUN_3)
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith("lid not found or out of reach") and "move it 20 mm or more towards the robot" in controller.pause_reason
    assert session.lids == [] and len(session.picks) == 3
    controller.act(Action.ABORT)
    wait_for(lambda: controller.finished)


def test_in_a_run_with_the_offset_allowed_the_lid_is_gripped_off_centre_and_put_down_with_the_same_offset():
    limits = dataclasses.replace(LIMITS, lid_min_from_slot_mm=80.0, lid_grip_offset_max_mm=30.0)
    controller, session, log = _run(limits, LID_OF_RUN_3)
    controller.start()
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["lid"] == "on" and session.lids == [(333.8, 166.5)]
    slot = (369.6, 17.1)  # the test settings' box slot; the open box of the fake lies at +5 deg, the lid at +5 deg: no turn
    assert session.lid_places == [(round(slot[0] + 333.8 - 351.5, 1), round(slot[1] + 166.5 - 175.3, 1))]
    row = next(row["event"] for row in log.rows if row["event"].startswith("lid at"))
    assert "gripped 19.8 mm from its centre at (333.8, 166.5)" in row and "turn +0 deg, put down at (351.9, 8.3)" in row
