"""The lid step of the real box cycle: which lid, where the cup grips it, where it is put down.

What the 17 Nov runs showed (testing/live_runs/20261117_195652.csv):
- A filled box is seen as a "lid" at the box slot. A lid nearer than control.lid_min_from_slot_mm
  to the slot is never picked.
- A lid that lies against the box on its upstream side has its centre about 390 mm from the robot,
  15 to 18 mm outside the reach (375 mm): it is not taken, and the pause says how far to move it.
- The turn uses the direction of the open box remembered at WAIT_BOX (turn.py).

Off unless control.lid_grip_offset_max_mm is above 0 (it is 0: gripping a lid off its centre is a
new way for the robot to move, so the operator sets it only with the teacher's approval): the cup
may then grip the lid up to that far from its centre, on the line towards the robot, at a point
inside the reach, and puts it down with the same offset, so the lid's centre still lands on the
box. No move leaves the reach either way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .run_context import BoxState, Limits, RunContext, robot_call
from .states import LID_NOT_FOUND, StepPause
from .turn import turn_deg

GRIP_INSIDE_REACH_MM = 2.0  # an off-centre grip point lies this far inside the reach limit, never on it
OTHER_SIDE = "lay it against the box on its downstream side (left of the box on Vision)"  # about 362 mm from the robot


@dataclass(frozen=True)
class LidRule:
    reach_min_mm: float
    reach_max_mm: float
    arm: Any  # arm_reach.ArmReach or None
    min_from_slot_mm: float
    grip_offset_max_mm: float

    @classmethod
    def of(cls, limits: Limits) -> "LidRule":
        return cls(limits.reach_min_mm, limits.reach_max_mm, limits.arm, limits.lid_min_from_slot_mm, limits.lid_grip_offset_max_mm)

    def reachable(self, x_mm: float, y_mm: float) -> bool:
        if not self.reach_min_mm <= math.hypot(x_mm, y_mm) <= self.reach_max_mm:
            return False
        return self.arm is None or self.arm.j1_beyond_limit_deg(x_mm, y_mm) is None

    def grip_point(self, x_mm: float, y_mm: float) -> tuple[float, float] | None:
        """Where the cup goes down for a lid centred at (x, y): the centre, or the nearest point towards the
        robot that is inside the reach; None when that point is further from the centre than allowed."""
        distance_mm = math.hypot(x_mm, y_mm)
        if distance_mm > self.reach_max_mm:
            grip_distance_mm = self.reach_max_mm - GRIP_INSIDE_REACH_MM
            if distance_mm - grip_distance_mm > self.grip_offset_max_mm:
                return None
            x_mm, y_mm = x_mm * grip_distance_mm / distance_mm, y_mm * grip_distance_mm / distance_mm
        grip = (round(x_mm, 1), round(y_mm, 1))
        return grip if self.reachable(*grip) else None

    def what_to_do(self, x_mm: float, y_mm: float, slot: Any) -> str:
        """For a lid that cannot be gripped: what the operator changes."""
        distance_mm = math.hypot(x_mm, y_mm)
        if distance_mm < self.reach_min_mm:
            return f"that is closer than the reach starts ({self.reach_min_mm:g} mm), move it away from the robot"
        closer_mm = distance_mm - (self.reach_max_mm - GRIP_INSIDE_REACH_MM) - self.grip_offset_max_mm
        if closer_mm > 0:  # upstream of the box (higher y) the box belt leads away from the robot: the other side is nearer
            other_side = f", or {OTHER_SIDE}" if y_mm > slot[1] else ""
            return f"move it {math.ceil(closer_mm)} mm or more towards the robot{other_side}"
        return "the arm cannot turn that far (J1), move it along the box belt, nearer the box"


@dataclass(frozen=True)
class LidChoice:
    lid: dict[str, Any] | None
    grip_mm: tuple[float, float] | None  # where the cup goes down
    off_centre_mm: float
    words: str  # what was chosen, or why nothing could be (for the log, the pause and the Vision screen)


def choose_lid(objects: list[dict[str, Any]], slot: Any, rule: LidRule) -> LidChoice:
    """The lid the robot will take from these detections, or why it cannot take one."""
    lids = sorted((found for found in objects if found.get("type") == "lid" and "x_robot" in found),
                  key=lambda found: found.get("conf", 0.0), reverse=True)
    reasons = []
    for lid in lids:
        x_mm, y_mm = lid["x_robot"], lid["y_robot"]
        distance_mm = math.hypot(x_mm, y_mm)
        if math.dist((x_mm, y_mm), slot) < rule.min_from_slot_mm:
            reasons.append(f"the lid seen at ({x_mm:.0f}, {y_mm:.0f}) is the box itself")
        elif lid.get("edge"):
            reasons.append(f"the lid at ({x_mm:.0f}, {y_mm:.0f}) is cut off by the picture edge: {OTHER_SIDE}")
        elif (grip := rule.grip_point(x_mm, y_mm)) is None:
            reasons.append(f"the lid at ({x_mm:.0f}, {y_mm:.0f}) is {distance_mm:.0f} mm from the robot: {rule.what_to_do(x_mm, y_mm, slot)}")
        else:
            off_mm = round(math.dist(grip, (x_mm, y_mm)), 1)
            where = f"lid at ({x_mm}, {y_mm})"
            if lid.get("bottom_edge"):  # detections.complete_cut_lid
                where += f" ({lid.get('hidden_mm', 0):g} mm of it below the picture, centre worked out from its size)"
            if off_mm >= 0.1:
                where += (f", gripped {off_mm:g} mm from its centre at ({grip[0]}, {grip[1]}): the centre is "
                          f"{distance_mm:.0f} mm from the robot, the reach is {rule.reach_max_mm:g} mm")
            return LidChoice(lid, grip, off_mm, where)
    limits_words = (f"no lid {rule.reach_min_mm:g}-{rule.reach_max_mm:g} mm from the robot and "
                    f"{rule.min_from_slot_mm:g} mm or more from the box slot in the last picture")
    return LidChoice(None, None, 0.0, limits_words + (f" ({'; '.join(reasons)})" if reasons else ""))


def place_point(slot: Any, lid: dict[str, Any], grip_mm: tuple[float, float], lid_turns_deg: float) -> tuple[float, float]:
    """Where the cup must be so that the lid's centre is over the box slot: the slot plus the grip offset,
    turned with the lid."""
    dx_mm, dy_mm = grip_mm[0] - lid["x_robot"], grip_mm[1] - lid["y_robot"]
    turn_rad = math.radians(lid_turns_deg)
    return (round(slot[0] + dx_mm * math.cos(turn_rad) - dy_mm * math.sin(turn_rad), 1),
            round(slot[1] + dx_mm * math.sin(turn_rad) + dy_mm * math.cos(turn_rad), 1))


def close_lid(ctx: RunContext, box: BoxState) -> None:
    if not ctx.limits.close_lid:
        box.lid = "off (control.close_lid is false)"
        return
    if ctx.robot.get("lid_pick_z") is None or ctx.robot.get("lid_place_z") is None:
        box.lid = "open: lid heights not taught (accepted at Arm)"
        ctx.log.event("box stays open: lid heights not taught")
        return
    slot, rule = ctx.robot["box_slots"][0], LidRule.of(ctx.limits)
    choice = choose_lid(box.objects, slot, rule)
    if choice.lid is None:
        raise StepPause(LID_NOT_FOUND, choice.words)
    tool_turn_deg = turn_deg(ctx, box, choice.lid, box.objects)
    place = place_point(slot, choice.lid, choice.grip_mm, tool_turn_deg * ctx.robot.get("r_sign", 1))
    if not rule.reachable(*place):
        raise StepPause(LID_NOT_FOUND, f"{choice.words}, but the put-down point ({place[0]}, {place[1]}) is outside the reach")
    ctx.log.event(f"{choice.words}, turn {tool_turn_deg:+.0f} deg, put down at ({place[0]}, {place[1]})", detections=[choice.lid])
    robot_call(ctx, lambda: ctx.session.place_lid(choice.grip_mm[0], choice.grip_mm[1], place, tool_turn_deg))
    box.lid = "on"
