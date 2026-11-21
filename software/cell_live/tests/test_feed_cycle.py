"""The box cycle with objects that MOVE on the object belt (fakes, no hardware).

The failure of the 17 Nov runs: the objects lay further apart than the pick area is long
(Choton's area, from y = -94.9 to 183.6 mm), so the full set was never in it at once and the
belt ran until the timeout. With the stop line the belt stops for the first object, the robot
picks it, and the belt runs again for the rest."""

import dataclasses

from cell_live.control.belts import BoxRestart, ObjectBeltDO3
from cell_live.control.cycle import RunController
from cell_live.control.cycle_steps import RunContext
from cell_live.control.states import Action, CycleState
from cell_live.tests.control_fakes import CHOTON, FakeClock, FakeLog, FakeSession, FakeVision, choton_settings, full_set, item, wait_for
from cell_live.tests.test_cycle import LID, LIMITS

PICK_AREA_Y_MM = (-94.9, 183.6)
NEW_RULE = dataclasses.replace(LIMITS, feed_timeout_s=60, feed_stop_y_mm=-60.0, refeeds_max=3)
OLD_RULE = dataclasses.replace(LIMITS, feed_timeout_s=60)  # no stop line, no refeed: the 17 Nov behaviour


class MovingBelt:
    """Objects move towards lower y by mm_per_picture while DO3 is at its run level (1 in these tests),
    count as in the pick area only inside PICK_AREA_Y_MM, and leave the belt when the robot picks them."""

    def __init__(self, session, vision, items, mm_per_picture=3.0):
        self.session, self.vision, self.items, self.mm_per_picture = session, vision, items, mm_per_picture
        self.picks_seen = 0
        vision.on_read = self.step
        self.step(0)

    def step(self, _reads):
        for kind, x_mm, y_mm in self.session.picks[self.picks_seen:]:  # the belt stood still since that picture
            self.items.remove(next(o for o in self.items if (o["type"], o["x_robot"], o["y_robot"]) == (kind, x_mm, y_mm)))
        self.picks_seen = len(self.session.picks)
        for found in self.items:
            if self.session.outputs[3] == 1:
                found["y_robot"] = round(found["y_robot"] - self.mm_per_picture, 1)
                found["u"] = 400.0 + 2.4 * found["y_robot"]
            found["reachable"] = PICK_AREA_Y_MM[0] <= found["y_robot"] <= PICK_AREA_Y_MM[1]
            found["off_belt"] = not found["reachable"]
        self.vision.objects = [dict(found) for found in self.items] + [LID]


def make_run(limits, objects=None, look_objects=None):
    clock, session, log = FakeClock(), FakeSession(), FakeLog()
    vision = FakeVision(clock, objects=objects if objects is not None else full_set() + [LID], look_objects=look_objects)
    belt = ObjectBeltDO3(session, 3, 1)
    restart = BoxRestart("operator", session, None, 0.0, sleep=lambda s: None)

    def build(controller):
        return RunContext(session, vision, belt, restart, CHOTON.yolo_lib, CHOTON.pick, choton_settings(), limits, log,
                          controller.checkpoint, controller.sleep, clock)

    return RunController(build, 1, session, log), session, vision, log


def spaced_objects():
    """A card in the pick area, the candies 300 and 550 mm behind it: never all three in the area at once."""
    return [item("card", 215.0, 150.0, 760), item("candy", 215.0, 450.0, 1480), item("candy", 215.0, 700.0, 2080)]


def _entered(log, state):
    return sum(1 for row in log.rows if row["event"] == f"enter {state}")


def test_old_rule_runs_the_belt_until_the_timeout_when_the_objects_are_spaced():
    controller, session, vision, log = make_run(OLD_RULE)
    MovingBelt(session, vision, spaced_objects())
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith("not enough objects"), controller.pause_reason
    assert session.picks == []
    controller.act(Action.ABORT)
    wait_for(lambda: controller.finished)


def test_stop_line_stops_the_belt_for_each_object_and_the_box_is_filled():
    controller, session, vision, log = make_run(NEW_RULE)
    MovingBelt(session, vision, spaced_objects())
    controller.start()
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["result"] == "done", controller.box_results
    assert [kind for kind, _, _ in session.picks] == ["card", "candy", "candy"]
    assert all(PICK_AREA_Y_MM[0] <= y_mm <= PICK_AREA_Y_MM[1] for _, _, y_mm in session.picks)
    assert _entered(log, "FEED_OBJECTS") == 3 and not any(row["state"] == "PAUSED" for row in log.rows)
    stops = [row["event"] for row in log.rows if row["event"].startswith("object belt commanded off")]
    assert ["stop line (-60 mm)" in stop for stop in stops] == [True, True, False]
    assert stops[2].startswith("object belt commanded off: the full set is in the pick area (candy 1/1")  # the last one needed
    assert "the object belt runs again" in " ".join(row["event"] for row in log.rows)


def test_a_needed_item_already_past_the_stop_line_is_picked_where_it_lies():
    # 17 Nov, live: a candy was left at y = -93.5 mm; starting the belt first would carry it out of the pick area
    controller, session, vision, log = make_run(NEW_RULE)
    lying = [item("candy", 215.0, -90.0, 184), item("card", 215.0, 400.0, 1360), item("candy", 215.0, 650.0, 1960)]
    MovingBelt(session, vision, lying)
    controller.start()
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["result"] == "done" and session.picks[0] == ("candy", 215.0, -90.0)
    first_feed = next(i for i, row in enumerate(log.rows) if row["event"] == "enter FEED_OBJECTS")
    assert log.rows[first_feed + 1]["event"].startswith("objects already in place, the object belt is not started: candy at y = -90 mm")
    assert session.calls.index("pick_and_place") < session.calls.index("DO3=1")  # the belt ran only for the rest


def test_the_full_set_together_still_needs_only_one_belt_stop():
    controller, session, vision, log = make_run(NEW_RULE)
    together = [item("card", 215.0, 250.0, 1000), item("candy", 215.0, 330.0, 1190), item("candy", 215.0, 410.0, 1380)]
    MovingBelt(session, vision, together)
    controller.start()
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["result"] == "done" and _entered(log, "FEED_OBJECTS") == 1
    assert any("the full set is in the pick area" in row["event"] for row in log.rows)


def test_feed_log_rows_show_what_the_camera_counts():
    controller, session, vision, log = make_run(NEW_RULE)
    MovingBelt(session, vision, spaced_objects())
    controller.start()
    wait_for(lambda: controller.finished)
    running = [row for row in log.rows if row["event"].startswith("object belt running: ")]
    assert running[0]["event"] == "object belt running: card 1/1, candy 0/2 in the pick area"
    assert all(o["type"] in ("card", "candy") for row in running for o in row["detections"])
    assert len(running) < 60  # on a change of the counts or once a second, not every picture


def test_the_lid_on_the_box_belt_is_used_although_it_is_outside_the_object_belt_pick_area():
    # 17 Nov, live: the lid at (351.8, 95.1) is 364 mm from the robot, but Choton's pick area marks it
    # reachable False (not on the object belt); his own close_box only checks the reach
    lid = dict(LID, x_robot=351.8, y_robot=95.1, reachable=False, off_belt=True)
    controller, session, vision, log = make_run(NEW_RULE, objects=full_set() + [lid])
    controller.start()
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["lid"] == "on" and session.lids == [(351.8, 95.1)]


def test_a_lid_beyond_our_reach_is_still_refused():
    lid = dict(LID, x_robot=360.0, y_robot=120.0, reachable=False, off_belt=True)  # 379.5 mm > 375 mm
    controller, session, vision, log = make_run(NEW_RULE, objects=full_set() + [lid])
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith("lid not found or out of reach") and session.lids == []
    controller.act(Action.ABORT)
    wait_for(lambda: controller.finished)


def test_a_box_beside_the_box_slot_pauses_before_anything_is_placed_then_retry_continues():
    # 17 Nov, live: the box centre was 78 mm from the slot and the card and both candies landed beside the box
    controller, session, vision, log = make_run(dataclasses.replace(NEW_RULE, box_slot_tolerance_mm=20.0))
    vision.box_at_mm = (357.5, -49.1)
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith(
        "box not under the box slot: the open box's centre (358, -49) is 67 mm from the box slot (369.6, 17.1), allowed 20 mm")
    assert session.picks == [] and "DO3=1" not in session.calls
    vision.box_at_mm = (372.0, 20.0)  # the operator moved the box under the slot
    controller.act(Action.RETRY)
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["result"] == "done" and len(session.picks) == 3


def test_refeeds_with_nothing_to_pick_end_in_object_missing_then_retry_resets_them():
    at_line = [item("candy", 215.0, -70.0, 230), LID]
    controller, session, vision, log = make_run(NEW_RULE, objects=at_line, look_objects=[LID])
    controller.start()
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith("object missing"), controller.pause_reason
    assert _entered(log, "FEED_OBJECTS") == 1 + NEW_RULE.refeeds_max and session.picks == []
    assert (session.outputs[3], session.outputs[1], session.outputs[2]) == (0, 0, 0)
    vision.look_objects = full_set() + [LID]  # the operator put the objects in the pick area
    controller.act(Action.RETRY)
    wait_for(lambda: controller.finished)
    assert controller.box_results[0]["result"] == "done" and len(session.picks) == 3
