"""The turn of each object uses the direction of the OPEN box (control/turn.py). Run 3 on 17 Nov
(testing/live_runs/20261117_195652.csv): the card lay along the object belt (-87 deg), the box with
two candies in it was seen as "lid 0.64" and "candy 0.81", not as a box, so the turn was 0 and the
card went into the box crosswise."""

from types import SimpleNamespace

from cell_live.control.run_context import BoxState
from cell_live.control.turn import note_box_direction, remember_box_direction, turn_deg
from cell_live.tests.control_fakes import CHOTON, FakeLog, full_set, item, wait_for
from cell_live.tests.test_cycle import LID, make_run

ROBOT = {"straighten": True, "r_sign": 1, "box_angle_deg": None}
SLOT = (349.6, 38.7)  # taught 17 Nov
CARD_ALONG_THE_BELT = item("card", 205.8, 45.9, 500, conf=0.94, angle=-87.0)
FILLED_BOX_SEEN_AS = [item("lid", 358.5, 32.1, 640, conf=0.64, angle=2.0), item("candy", 357.3, 32.4, 640, conf=0.81, angle=2.0)]


def _context(vision=None):
    return SimpleNamespace(pick=CHOTON.pick, robot=dict(ROBOT), log=FakeLog(), vision=vision or SimpleNamespace())


def test_the_remembered_box_direction_turns_the_card_although_no_box_is_in_the_pictures():
    context, box = _context(), BoxState(1, box_angle_deg=2.0)
    assert turn_deg(context, box, CARD_ALONG_THE_BELT, [CARD_ALONG_THE_BELT] + FILLED_BOX_SEEN_AS) == 89.0
    assert context.log.rows == []


def test_without_a_box_direction_the_object_is_not_turned_and_the_log_says_why():
    context, box = _context(), BoxState(1)  # run 3 as it was
    assert turn_deg(context, box, CARD_ALONG_THE_BELT, [CARD_ALONG_THE_BELT] + FILLED_BOX_SEEN_AS) == 0.0
    assert context.log.rows[0]["event"] == "the direction of the box is not known: the card is not turned"


def test_a_box_seen_later_does_not_replace_the_direction_of_the_open_box():
    context, box = _context(), BoxState(1, box_angle_deg=2.0)
    wrong = item("box", 356.0, 32.0, 640, conf=0.5, angle=-60.0)  # e.g. the box with a card lying askew in it
    assert turn_deg(context, box, CARD_ALONG_THE_BELT, [CARD_ALONG_THE_BELT, wrong]) == 89.0
    note_box_direction(box, [wrong], SLOT)
    assert box.box_angle_deg == 2.0


def test_the_direction_is_measured_on_the_picture_of_the_empty_box():
    found = {"type": "box", "conf": 0.92, "u": 500.0, "v": 507.0}  # a single picture: Choton's detect gives no angle
    measured = []

    def add_angle(frame, detection):
        measured.append(frame)
        detection["angle_robot"] = 2.0

    box = BoxState(1)
    remember_box_direction(_context(SimpleNamespace(add_angle=add_angle)), box, "frame 7", found)
    assert box.box_angle_deg == 2.0 and measured == ["frame 7"]


def test_a_look_gives_the_direction_of_the_box_at_the_slot_and_only_while_none_is_known():
    box = BoxState(1)  # run 4: the real box (0.92) and a second "box" 136 mm upstream; here the wrong one even scores higher
    note_box_direction(box, [item("box", 349.0, 174.9, 835, conf=0.95, angle=-1.0), item("box", 357.0, 29.7, 640, conf=0.92, angle=4.0)], SLOT)
    assert box.box_angle_deg == 4.0
    note_box_direction(box, [item("box", 356.9, 31.7, 640, conf=0.92, angle=30.0)], SLOT)
    assert box.box_angle_deg == 4.0
    edge_only = BoxState(1)
    note_box_direction(edge_only, [item("box", 356.9, 31.7, 640, conf=0.92, angle=30.0, edge=True)], SLOT)
    assert edge_only.box_angle_deg is None


def test_in_a_run_the_card_along_the_belt_is_turned_into_the_box_direction():
    # WAIT_BOX sees the open box (the fake's box lies at +5 deg); the LOOK pictures hold no box, as in run 3
    look = [CARD_ALONG_THE_BELT, item("candy", 250.0, 40.0, 200, angle=7.0), item("candy", 250.0, -40.0, 300, angle=1.0), LID] + FILLED_BOX_SEEN_AS
    controller, session, vision, log = make_run(vision_kwargs={"objects": full_set() + [LID], "look_objects": look})
    controller.start()
    wait_for(lambda: controller.finished)
    picks = [row["event"] for row in log.rows if row["event"].startswith("pick ")]
    assert picks == ["pick card 1/1: red card, turn -88 deg", "pick candy 1/2: red candy, turn -2 deg", "pick candy 2/2: red candy, turn +4 deg"]
    assert not any("is not known" in row["event"] for row in log.rows)
