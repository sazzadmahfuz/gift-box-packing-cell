"""What each state of the real box cycle does. Choton's functions do the work; the waiting loops
of his 14_pick_and_place.py (wait_box_camera, feed_objects, send_box_away) are re-written here
without input() and without windows, with his rules (5 still frames <= 6 px, 3 ready frames,
60 s, 0.5 s settle, 10 px "already picked"). The object belt also stops at the stop line
(feed.py), and runs again when the box still needs objects that are not in the pictures.
The lid step is in lid.py, the turn of each object in turn.py, what the steps share in run_context.py.

Every step calls ctx.checkpoint() at safe points (never while the robot holds an item), and
raises StepPause or StepFault instead of waiting for keyboard input.
"""

from __future__ import annotations

from typing import Callable

from .belts import box_nearest_the_slot, box_off_the_slot
from .feed import FeedWatch, feed_detections, still_needed
from .lid import close_lid
from .robot_client import ControlConnectionLost
from .run_context import (  # noqa: F401 (Limits, mark_reach_objects and out_of_reach are used through this module too)
    BoxState, Limits, RunContext, mark_reach, mark_reach_objects, out_of_reach, quietly, robot_call,
)
from .states import (
    BOX_DID_NOT_LEAVE, BOX_NOT_UNDER_SLOT, NO_BOX, NOT_ENOUGH_OBJECTS, OBJECT_MISSING,
    CycleState, RefeedRequested, StepFault, StepPause,
)
from .turn import note_box_direction, remember_box_direction, turn_deg

FEED_LOG_EVERY_S = 1.0  # while the belt runs: a log row when the counts change, else at most this often
FEED_PICTURE_EVERY_S = 2.0  # while the belt runs: a saved picture at most this often (and one when it stops)


def wait_box(ctx: RunContext, box: BoxState) -> None:
    robot_call(ctx, ctx.session.home)
    deadline_s, slot = ctx.clock() + ctx.limits.box_wait_timeout_s, ctx.robot["box_slots"][0]
    last, still, objects = None, 0, []
    while still < ctx.limits.box_still_frames:
        ctx.checkpoint()
        if ctx.clock() > deadline_s:
            filled = ("; a box with items in it stands at the box slot: take it away and put an empty box there"
                      if ctx.vision.box_present(objects, slot) else "")  # 17 Nov: the filled box of the run before was still there
            raise StepPause(NO_BOX, f"no open box standing still within {ctx.limits.box_wait_timeout_s:g} s{filled}")
        frame = ctx.vision.read()
        objects = ctx.vision.detect(frame)
        boxes = [o for o in objects if o["type"] == "box" and not o.get("edge")]
        if not boxes:
            last, still = None, 0
            continue
        best = box_nearest_the_slot(boxes, slot)
        moved = last is None or abs(best["u"] - last[0]) + abs(best["v"] - last[1]) > ctx.limits.box_still_px
        still = 0 if moved else still + 1
        last = (best["u"], best["v"])
    saved = ctx.picture("box", frame)
    problem = box_off_the_slot(best, slot, ctx.limits.box_slot_tolerance_mm)
    if problem:
        raise StepPause(BOX_NOT_UNDER_SLOT, problem)
    remember_box_direction(ctx, box, frame, best)  # the box is empty now: later it is no longer seen as a box
    ctx.log.event(f"box is here and standing still{saved}", detections=[best])


def feed_objects(ctx: RunContext, box: BoxState) -> None:
    need = still_needed(ctx.settings.get("box_contents", {"card": 1, "candy": 2}), box.placed)
    limits = ctx.limits
    robot_call(ctx, ctx.session.home)  # robot out of the camera view
    already = _in_place_without_the_belt(ctx, need)
    if already:  # 17 Nov: a candy left at the end of the pick area would be carried out by a belt start
        ctx.log.event(f"objects already in place, the object belt is not started: {already}")
        return
    watch = FeedWatch(need, limits.ready_frames, limits.feed_stop_y_mm, limits.stop_line_frames, ctx.yolo.usable)
    robot_call(ctx, ctx.belt.start)
    try:
        deadline_s = ctx.clock() + limits.feed_timeout_s
        logged_s = pictured_s = None
        while True:
            ctx.checkpoint()
            if ctx.clock() > deadline_s:
                raise StepPause(NOT_ENOUGH_OBJECTS, f"the objects did not arrive within {limits.feed_timeout_s:g} s "
                                                    f"({watch.counts}): put more on the belt")
            frame = ctx.vision.read()
            objects = ctx.vision.detect(frame)
            mark_reach_objects(objects, limits.reach_min_mm, limits.reach_max_mm, limits.arm)
            decision = watch.see(objects)
            if decision.counts_changed or logged_s is None or ctx.clock() - logged_s >= FEED_LOG_EVERY_S:
                saved = ""
                if decision.stop or pictured_s is None or ctx.clock() - pictured_s >= FEED_PICTURE_EVERY_S:
                    saved, pictured_s = ctx.picture("belt", frame), ctx.clock()
                ctx.log.event(f"object belt running: {decision.counts}{saved}", detections=feed_detections(objects))
                logged_s = ctx.clock()
            if decision.stop:
                break
    finally:
        quietly(ctx.belt.stop)
    ctx.sleep(limits.settle_s)  # let the objects stop moving
    ctx.log.event(f"object belt commanded off: {decision.reason}")


def _in_place_without_the_belt(ctx: RunContext, need: dict[str, int]) -> str:
    """The belt's stop rule on pictures of the stopped belt: why it would stop at once, or ''."""
    limits = ctx.limits
    watch = FeedWatch(need, limits.ready_frames, limits.feed_stop_y_mm, limits.stop_line_frames, ctx.yolo.usable)
    for _ in range(max(limits.ready_frames, limits.stop_line_frames)):
        ctx.checkpoint()
        objects = ctx.vision.detect(ctx.vision.read())
        mark_reach_objects(objects, limits.reach_min_mm, limits.reach_max_mm, limits.arm)
        decision = watch.see(objects)
        if decision.stop:
            return decision.reason
    return ""


def look(ctx: RunContext, box: BoxState) -> None:
    ctx.checkpoint()
    robot_call(ctx, ctx.session.home)  # out of the camera view for the pictures
    frame, objects = ctx.vision.detect_stable(ctx.limits.detect_frames)
    box.objects, box.gone = mark_reach(ctx, objects), []
    note_box_direction(box, box.objects, ctx.robot["box_slots"][0])
    ctx.log.event(f"pictures taken{ctx.picture('look', frame)}", detections=box.objects)


def pick_place(ctx: RunContext, box: BoxState) -> None:
    slots = ctx.robot["box_slots"]
    while not ctx.yolo.box_complete(box.placed, ctx.settings):
        ctx.checkpoint()  # safe point: the robot holds nothing here
        gone_px = ctx.limits.gone_px
        objects = [o for o in box.objects if all(abs(o["u"] - g["u"]) + abs(o["v"] - g["v"]) > gone_px for g in box.gone)]
        target, message = ctx.yolo.next_pick(objects, box.placed, ctx.settings)
        if target is None:
            if box.refeeds < ctx.limits.refeeds_max:  # the rest may still be on the belt: run it again
                box.refeeds += 1
                raise RefeedRequested(f"{message} (object belt run {box.refeeds} of at most {ctx.limits.refeeds_max})")
            raise StepPause(OBJECT_MISSING, message)
        slot = slots[len(box.placed) % len(slots)]
        name = f"{target.get('color', '')} {target['type']}".strip()
        tool_turn_deg = turn_deg(ctx, box, target, objects)
        ctx.log.event(f"pick {message}: {name}, turn {tool_turn_deg:+.0f} deg", detections=[target])
        robot_call(ctx, lambda: ctx.session.pick_and_place(target["x_robot"], target["y_robot"], slot, name, target["type"], tool_turn_deg))
        box.placed.append(target)
        box.gone.append(target)
        box.refeeds = 0


def release_box(ctx: RunContext, box: BoxState) -> None:
    robot_call(ctx, ctx.session.home)
    slot = ctx.robot["box_slots"][0]
    started = False
    try:
        message = ctx.restart.begin()
        started = True
        ctx.log.event(message + ctx.picture("closed_box", ctx.vision.read()))  # the picture shows how the lid landed
        deadline_s = ctx.clock() + ctx.limits.box_leave_timeout_s
        gone_frames = 0
        while gone_frames < ctx.limits.box_still_frames:
            ctx.checkpoint()
            if ctx.clock() > deadline_s:
                raise StepPause(BOX_DID_NOT_LEAVE, f"the closed box is still at the robot after {ctx.limits.box_leave_timeout_s:g} s")
            objects = ctx.vision.detect(ctx.vision.read())
            gone_frames = 0 if ctx.vision.box_present(objects, slot) else gone_frames + 1
    except ControlConnectionLost as error:
        raise StepFault(f"connection to the robot lost: {error}") from error
    finally:
        if started:
            quietly(ctx.restart.finish)
    ctx.log.event("the closed box has left")


STEPS: dict[CycleState, Callable[[RunContext, BoxState], None]] = {
    CycleState.WAIT_BOX: wait_box,
    CycleState.FEED_OBJECTS: feed_objects,
    CycleState.LOOK: look,
    CycleState.PICK_PLACE: pick_place,
    CycleState.CLOSE_LID: close_lid,
    CycleState.RELEASE_BOX: release_box,
}
