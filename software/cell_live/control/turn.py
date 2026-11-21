"""How far the tool turns between picking and placing, so the object lies along the box.

The rule is Choton's straighten_turn (14_pick_and_place.py): box direction minus object direction,
both the direction of the long side in robot X/Y. It takes the box direction from a "box" in the
pictures. A box with items in it is no longer seen as a box (17 Nov,
testing/live_runs/20261117_195652.csv: seen as a lid, a candy or a card), so the turn was 0 and a
card lying along the object belt went into the box crosswise. The direction of the OPEN box is
therefore measured once, when the box has arrived and is empty, and kept for every turn of that box.
"""

from __future__ import annotations

from typing import Any

from .belts import box_nearest_the_slot
from .run_context import BoxState, RunContext


def remember_box_direction(ctx: RunContext, box: BoxState, frame: Any, found: dict[str, Any]) -> None:
    """The open box stands still and is empty: measure the direction of its long side on this picture."""
    if "angle_robot" not in found:
        add_angle = getattr(ctx.vision, "add_angle", None)
        if add_angle is not None:
            add_angle(frame, found)
    if isinstance(found.get("angle_robot"), (int, float)):
        box.box_angle_deg = float(found["angle_robot"])


def note_box_direction(box: BoxState, objects: list[dict[str, Any]], slot: Any) -> None:
    """From the pictures of a LOOK, only while no direction is known yet (the box is then still empty)."""
    seen = [found for found in objects if found.get("type") == "box" and isinstance(found.get("angle_robot"), (int, float))
            and not found.get("edge")]
    if box.box_angle_deg is None and seen:
        box.box_angle_deg = float(box_nearest_the_slot(seen, slot)["angle_robot"])


def turn_deg(ctx: RunContext, box: BoxState, target: dict[str, Any], objects: list[dict[str, Any]]) -> float:
    """Choton's turn, with the remembered direction of the open box in place of any box in these pictures."""
    if box.box_angle_deg is not None:
        open_box = {"type": "box", "conf": 1.0, "angle_robot": box.box_angle_deg}
        objects = [found for found in objects if found.get("type") != "box"] + [open_box]
    elif not any(found.get("type") == "box" and "angle_robot" in found for found in objects) \
            and ctx.robot.get("box_angle_deg") is None and "angle_robot" in target:
        ctx.log.event(f"the direction of the box is not known: the {target.get('type')} is not turned")
    return float(ctx.pick.straighten_turn(target, objects, ctx.robot))
