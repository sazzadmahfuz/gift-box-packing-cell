"""Objects at the top border of the picture (control/detections.py). Run 3 on 17 Nov
(testing/live_runs/20261117_195652.csv): every card lying across the object belt touched the top
border, was marked AT THE EDGE all the way through the pick area, and the belt never stopped for it."""

from types import SimpleNamespace

from cell_live.control.detections import (
    borders_touched, complete_cut_lid, effective_pick_area, keep_to_pick_area, use_bottom_edge_boxes, use_top_edge_objects,
)
from cell_live.control.feed import FeedWatch
from cell_live.control.runlog import describe_detections
from cell_live.control.vision_session import VisionSession
from cell_live.tests.control_fakes import CHOTON

FRAME = SimpleNamespace(shape=(720, 1280, 3))  # the stand camera's picture: 1280 x 720


def seen(kind, box, x_mm=203.0, y_mm=20.0):
    """A detection as Choton's yolo_lib.detect returns it: "edge" is true within 3 px of ANY border."""
    x1, y1, x2, y2 = box
    edge = x1 < 3 or y1 < 3 or x2 > 1280 - 3 or y2 > 720 - 3
    return {"type": kind, "conf": 0.92, "box": box, "u": (x1 + x2) / 2, "v": (y1 + y2) / 2, "edge": edge,
            "x_robot": x_mm, "y_robot": y_mm, "reachable": True, "color": "red"}


CARD_ACROSS = (557, 0, 815, 304)  # the card of 17 Nov lying across the belt: cut by the top border (measured on a saved picture)
CANDY_ACROSS = (111, 2, 318, 304)  # a candy bar across the belt: its end is 2 px from the top border


def test_borders_touched_uses_chotons_three_pixel_margin():
    assert borders_touched(CARD_ACROSS, 1280, 720) == {"top"}
    assert borders_touched((337, 11, 531, 291), 1280, 720) == set()
    assert borders_touched((0, 0, 100, 100), 1280, 720) == {"top", "left"}
    assert borders_touched((943, 626, 1126, 720), 1280, 720) == {"bottom"}


def test_cards_and_candies_touching_only_the_top_border_are_used():
    card, candy = seen("card", CARD_ACROSS), seen("candy", CANDY_ACROSS)
    assert card["edge"] and candy["edge"]
    changed = use_top_edge_objects([card, candy], FRAME)
    assert changed == [card, candy] and not card["edge"] and not candy["edge"] and card["top_edge"] and candy["top_edge"]
    assert CHOTON.yolo_lib.usable(card)
    assert "TOUCHES THE TOP EDGE (used)" in describe_detections([card]) and "AT THE EDGE" not in describe_detections([card])


def test_objects_at_the_other_borders_stay_unused():
    entering = seen("card", (1100, 0, 1280, 300))  # top and right: still coming into the picture
    leaving = seen("candy", (0, 40, 150, 300))  # left: leaving it
    driver = seen("candy", (943, 626, 1126, 720))  # the motor driver at the bottom border, seen as a candy
    assert use_top_edge_objects([entering, leaving, driver], FRAME) == []
    assert entering["edge"] and leaving["edge"] and driver["edge"]


def test_boxes_and_lids_are_not_touched_and_a_frame_without_a_size_changes_nothing():
    lid = seen("lid", (600, 0, 990, 300))
    assert use_top_edge_objects([lid], FRAME) == [] and lid["edge"]
    card = seen("card", CARD_ACROSS)
    assert use_top_edge_objects([card], "frame 1") == [] and card["edge"]


def test_the_object_belt_now_stops_for_a_card_lying_across_it():
    # run 3, 52-56 s: "card 0.93 (206.5, -11.9) AT THE EDGE" and the belt ran on; the box needed one card
    rule = FeedWatch({"card": 1}, 3, -30.0, 2, CHOTON.yolo_lib.usable)
    picture = [seen("card", CARD_ACROSS, 206.5, -11.9)]
    assert not rule.see([dict(picture[0])]).stop and rule.counts == "card 0/1 in the pick area"  # Choton's rule alone
    stops = []
    for _ in range(3):
        objects = [dict(picture[0])]
        use_top_edge_objects(objects, FRAME)
        stops.append(rule.see(objects).stop)
    assert stops == [False, False, True] and rule.counts == "card 1/1 in the pick area"


PICK_AREA = [156.08, 274.43, -94.88, 183.63]  # control.pick_area_mm: Choton's area of the 17 Nov calibration


def test_our_pick_area_keeps_the_box_belt_out_when_a_new_calibration_has_marks_on_both_belts():
    # with marks on both belts Choton's own area (marks + 20 mm) covers the box belt: the filled box, seen as
    # "candy 0.81 (357.3, 32.4)" in run 3, would come back reachable and be counted and picked as a candy
    filled_box = seen("candy", (360, 350, 620, 690), 357.3, 32.4)
    on_the_belt = seen("candy", (337, 11, 531, 291), 202.0, 10.5)
    assert CHOTON.yolo_lib.usable(filled_box)
    assert keep_to_pick_area([filled_box, on_the_belt], PICK_AREA) == [filled_box]
    assert filled_box["off_belt"] and not CHOTON.yolo_lib.usable(filled_box) and CHOTON.yolo_lib.usable(on_the_belt)
    assert "NOT IN THE PICK AREA" in describe_detections([filled_box])
    assert keep_to_pick_area([seen("candy", (360, 350, 620, 690), 357.3, 32.4)], None) == []  # not set: only his rule


def test_the_area_drawn_on_vision_is_inside_both_areas():
    after_a_wide_calibration = (120.0, 400.0, -150.0, 250.0)
    assert effective_pick_area(after_a_wide_calibration, PICK_AREA) == tuple(PICK_AREA)
    assert effective_pick_area((156.08, 274.43, -94.88, 183.63), None) == (156.08, 274.43, -94.88, 183.63)
    assert effective_pick_area(None, None) is None


def _session(found, top_edge_usable):
    yolo = SimpleNamespace(detect=lambda frame, model, settings, H: [dict(found)],
                           detect_stable=lambda src, model, settings, H, frames: (FRAME, [dict(found)]))
    choton = SimpleNamespace(yolo_lib=yolo, vision_lib=SimpleNamespace(load_homography=lambda: None))
    return VisionSession(choton, {"camera_index": 0}, 1, 0.5, make_source=lambda s: None, load_model=lambda s: object(),
                         top_edge_usable=top_edge_usable)


def test_the_vision_session_applies_the_rule_to_single_pictures_and_to_stable_pictures():
    on = _session(seen("card", CARD_ACROSS), True)
    assert [o["edge"] for o in on.detect(FRAME)] == [False] and on.latest[1][0]["top_edge"]
    assert [o["edge"] for o in on.detect_stable(8)[1]] == [False]
    off = _session(seen("card", CARD_ACROSS), False)  # vision.top_edge_objects_usable = false: Choton's rule
    assert [o["edge"] for o in off.detect(FRAME)] == [True] and [o["edge"] for o in off.detect_stable(8)[1]] == [True]


def test_the_vision_session_applies_our_pick_area_to_every_detection():
    session = _session(seen("candy", (360, 350, 620, 690), 357.3, 32.4), True)
    session.pick_area_mm = PICK_AREA
    assert [o["reachable"] for o in session.detect(FRAME)] == [False] and [o["off_belt"] for o in session.detect_stable(8)[1]] == [True]


# The camera view since 17 Nov 21:26: the bottom of the picture cuts a box standing across the box belt, and the lid.

LID_SIZE = (158.0, 120.0)  # vision.lid_apparent_size_mm
SCALE = 2.5  # px per mm in these tests: pixel = robot mm * 2.5


def to_robot(u, v):
    return u / SCALE, v / SCALE


def test_a_box_cut_only_by_the_bottom_border_is_used_and_a_cut_lid_is_left_to_its_own_rule():
    box, lid = seen("box", (345, 388, 620, 720)), seen("lid", (60, 360, 372, 720))
    card_at_bottom = seen("card", (400, 600, 500, 720))
    assert use_bottom_edge_boxes([box, lid, card_at_bottom], FRAME) == [box]
    assert not box["edge"] and box["bottom_edge"] and lid["edge"] and card_at_bottom["edge"]
    assert "CUT BY THE BOTTOM EDGE (used)" in describe_detections([box])
    assert use_bottom_edge_boxes([seen("box", (345, 388, 620, 720))], "frame 1") == []
    assert use_bottom_edge_boxes([seen("box", (900, 388, 1280, 720))], FRAME) == []  # right and bottom: still arriving


def test_the_centre_of_a_lid_cut_by_the_bottom_border_is_half_its_length_below_its_top_edge():
    # a lid lying across the belt, 120 mm wide (300 px) and 158 mm long (395 px): its top edge at v = 360, so its
    # true bottom is at v = 755, 35 px (14 mm) below the picture
    lid = seen("lid", (60, 360, 360, 720))
    outline = [(60, 720), (60, 360), (360, 360), (360, 720)]  # what is seen of it
    hidden_mm = complete_cut_lid(lid, outline, LID_SIZE, to_robot)
    assert round(hidden_mm, 1) == 14.0 and lid["hidden_mm"] == 14.0 and not lid["edge"] and lid["bottom_edge"]
    assert (lid["x_robot"], lid["y_robot"]) == (84.0, 223.0)  # u = 210, v = 360 + 395 / 2 = 557.5
    assert "CUT BY THE BOTTOM EDGE (used, 14 mm of it outside, centre worked out)" in describe_detections([lid])


def test_a_turned_lid_is_completed_along_its_own_long_side():
    import math
    turn = math.radians(6.0)  # the lid of 17 Nov lay at 5 to 8 degrees
    along = (-math.sin(turn), math.cos(turn))  # the long side, pointing down the picture
    across = (math.cos(turn), math.sin(turn))
    top_left = (400.0, 300.0)
    top_right = (top_left[0] + 300 * across[0], top_left[1] + 300 * across[1])
    seen_px = 350.0  # 140 mm of the 158 mm are in the picture
    outline = [(top_left[0] + seen_px * along[0], top_left[1] + seen_px * along[1]), top_left, top_right,
               (top_right[0] + seen_px * along[0], top_right[1] + seen_px * along[1])]
    lid = seen("lid", (360, 300, 700, 720))
    assert round(complete_cut_lid(lid, outline, LID_SIZE, to_robot), 1) == 18.0
    middle_of_top = ((top_left[0] + top_right[0]) / 2, (top_left[1] + top_right[1]) / 2)
    whole_centre = (middle_of_top[0] + 197.5 * along[0], middle_of_top[1] + 197.5 * along[1])
    assert math.dist((lid["x_robot"], lid["y_robot"]), to_robot(*whole_centre)) < 0.1


def test_a_lid_lying_along_the_belt_is_completed_with_its_short_side():
    lid = seen("lid", (100, 440, 495, 720))  # 158 mm (395 px) wide: the 120 mm side is the cut one
    assert round(complete_cut_lid(lid, [(100, 720), (100, 440), (495, 440), (495, 720)], LID_SIZE, to_robot), 1) == 8.0
    assert lid["y_robot"] == round((440 + 150) / SCALE, 1)


def test_a_lid_that_is_mostly_hidden_or_does_not_look_like_the_lid_stays_at_the_edge():
    mostly_hidden = seen("lid", (60, 500, 360, 720))  # 88 of 158 mm in the picture
    assert complete_cut_lid(mostly_hidden, [(60, 720), (60, 500), (360, 500), (360, 720)], LID_SIZE, to_robot) is None
    wrong_shape = seen("lid", (60, 360, 260, 720))  # 80 mm wide: neither side of the lid
    assert complete_cut_lid(wrong_shape, [(60, 720), (60, 360), (260, 360), (260, 720)], LID_SIZE, to_robot) is None
    assert mostly_hidden["edge"] and wrong_shape["edge"] and "bottom_edge" not in wrong_shape
    assert complete_cut_lid(seen("lid", (60, 360, 360, 720)), None, LID_SIZE, to_robot) is None  # no outline found
    assert complete_cut_lid(seen("lid", (60, 360, 360, 720)), [(60, 720), (60, 360), (360, 360), (360, 720)], None, to_robot) is None


def test_a_lid_whose_outline_is_whole_keeps_the_middle_of_what_is_seen():
    lid = seen("lid", (60, 322, 360, 718))  # only its box is within 3 px of the border: all 158 mm are seen
    assert complete_cut_lid(lid, [(60, 717), (60, 322), (360, 322), (360, 717)], LID_SIZE, to_robot) == 0.0
    assert lid["y_robot"] == round((322 + 717) / 2 / SCALE, 1) and not lid["edge"]


def test_the_vision_session_completes_a_cut_lid_with_chotons_outline():
    import numpy as np
    found = seen("lid", (60, 360, 360, 720))
    outline = np.array([(60, 720), (60, 360), (360, 360), (360, 720)], dtype=float)
    yolo = SimpleNamespace(detect=lambda frame, model, settings, H: [dict(found)], object_angle=lambda frame, box: (90.0, outline))
    vision_lib = SimpleNamespace(load_homography=lambda: None, pixel_to_robot=lambda H, u, v: (u / SCALE, v / SCALE),
                                 table_to_robot=lambda x, y, settings: (x, y))
    session = VisionSession(SimpleNamespace(yolo_lib=yolo, vision_lib=vision_lib), {"camera_index": 0}, 1, 0.5,
                            make_source=lambda s: None, load_model=lambda s: object())
    session.H, session.bottom_edge_usable, session.lid_size_mm = "calibration", True, LID_SIZE
    lid = session.detect_for_the_screen(FRAME)[0]
    assert (lid["x_robot"], lid["y_robot"], lid["edge"], lid["bottom_edge"]) == (84.0, 223.0, False, True)
    yolo.detect_stable = lambda src, model, settings, H, frames: (FRAME, [dict(found)])
    assert session.detect_stable(8)[1][0]["bottom_edge"] is True  # a LOOK works the centre out too
    # the single pictures of the running belt go without it: outlining a lid takes about 0.1 s per picture
    assert session.detect(FRAME)[0]["edge"] is True
    session.bottom_edge_usable = False
    assert session.detect_for_the_screen(FRAME)[0]["edge"] is True
