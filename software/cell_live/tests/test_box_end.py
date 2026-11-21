"""The end of a box, as run 3 on 17 Nov showed it (testing/live_runs/20261117_195652.csv): a filled box is
seen as a "lid" or as the card on top, never as a box."""

import dataclasses

from cell_live.control.vision_session import VisionSession
from cell_live.tests.control_fakes import CHOTON, FakeClock, FakeLog, FakeSession, FakeVision, choton_settings, full_set, item, wait_for
from cell_live.tests.test_cycle import LIMITS, make_run
from cell_live.control.states import Action, CycleState

SLOT = (369.6, 17.1)  # the test settings' box slot (Choton's 12 Nov values)
FILLED_BOX_AS_LID = item("lid", 378.3, 10.5, 640, conf=0.64)  # 10 mm from the slot, like run 3
REAL_LID = item("lid", 352.0, -100.0, 200)  # beside the box, inside the reach (366 mm)


def _run(look_objects):
    controller, session, vision, log = make_run(vision_kwargs={"look_objects": look_objects})
    controller.context = dataclasses.replace(controller.context, limits=dataclasses.replace(LIMITS, lid_min_from_slot_mm=80.0))
    return controller, session


def test_a_lid_seen_at_the_box_slot_is_the_filled_box_and_the_real_lid_beside_it_is_used():
    controller, session = _run(full_set() + [FILLED_BOX_AS_LID, REAL_LID])
    controller.start()
    wait_for(lambda: controller.finished)
    assert session.lids == [(352.0, -100.0)] and controller.box_results[0]["lid"] == "on"


def test_only_the_filled_box_seen_as_a_lid_pauses_instead_of_picking_from_the_box():
    controller, session = _run(full_set() + [FILLED_BOX_AS_LID])
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith("lid not found or out of reach") and "80 mm or more from the box slot" in controller.pause_reason
    assert session.lids == []
    controller.act(Action.ABORT)
    wait_for(lambda: controller.finished)


def _session_with_identity_calibration():
    session = VisionSession(CHOTON, choton_settings(), 1, 0.5, make_source=lambda settings: None, load_model=lambda settings: None)
    session.H = CHOTON.vision_lib.np.eye(3)  # picture pixel = robot mm: the slot pixel is the slot itself
    return session


def test_a_filled_box_seen_as_its_card_is_still_a_box_over_the_slot():
    session = _session_with_identity_calibration()
    card_on_top = {"type": "card", "box": (SLOT[0] - 50, SLOT[1] - 40, SLOT[0] + 50, SLOT[1] + 40)}
    elsewhere = {"type": "card", "box": (0, 0, 100, 100)}
    assert session.box_present([card_on_top], list(SLOT)) and not session.box_present([elsewhere], list(SLOT))
    assert not session.box_present([], list(SLOT))


def test_no_open_box_but_a_filled_one_at_the_slot_says_so():
    # run 205234 on 17 Nov: the filled box of the run before still stood at the slot, and the pause only said "no box"
    controller, session, vision, log = make_run(vision_kwargs={"box": False, "box_leaves": False})  # something is seen over the slot
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason == ("no box: no open box standing still within 5 s; a box with items in it stands at the box slot: "
                                       "take it away and put an empty box there")
    controller.act(Action.ABORT)
    wait_for(lambda: controller.finished)
