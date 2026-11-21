"""Two rules of ours on top of Choton's detections. Standard library only.

1. Cards and candies that touch the TOP border of the camera picture are used.
Choton's yolo_lib.detect marks every object whose box is within 3 px of a picture border as
"edge" (maybe cut off), and edge objects are never counted or picked. On the 17 Nov camera stand
the top border of the picture runs along the robot-side rail of the object belt: the belt is
about as wide as a card or a candy bar is long, so an object lying across the belt always
touches that border. In testing/live_runs/20261117_195652.csv four cards in a row rode through
the whole pick area marked AT THE EDGE, and the object belt did not stop for any of them.
Past that border there is only the rail, so little of such an object can be hidden. It is used
with the centre of what the camera sees; for a card lying across the belt that can be some
millimetres towards the box belt of its true centre. An object at the left, right or bottom
border is entering or leaving the picture and stays unused.

2. The pick area is fixed in robot X/Y (control.pick_area_mm). Choton's pick area is the area of
his calibration marks + 20 mm (yolo_lib._belt_zone), so it changes with every new calibration:
marks on both belts would make it cover the box belt, and the filled box, which the model sees
as a candy or a card, would be counted and picked as an item. Objects outside our area are marked
exactly as his rule marks them (not reachable, off the belt). The rule only refuses.

3. A box or a lid that touches only the BOTTOM border is used. Since the camera was re-aimed on
17 Nov (calibration of 21:26) the whole object belt is in the picture, and the picture ends about
10 mm short of the far wall of a box standing across the box belt at the box slot. The box is
used as it is seen: its place comes from the taught box slot, the camera only checks that it is
there. A lid is gripped at its centre, so the centre of the WHOLE lid is worked out: from the
lid's top edge in the picture, half the lid's known length further down (vision.lid_apparent_size_mm,
measured in pictures where all of the lid was seen).
"""

from __future__ import annotations

from typing import Any

import math

from .feed import FEED_KINDS

EDGE_MARGIN_PX = 3  # yolo_lib.detect: a box this close to a picture border is "at the edge"
LID_SIDE_TOLERANCE = 0.15  # the lid's visible side must be within 15 % of one of its two known sides
LID_HIDDEN_MAX = 0.30  # at most this part of the lid's length may be outside the picture


def borders_touched(box: Any, width_px: int, height_px: int) -> set[str]:
    x1, y1, x2, y2 = box
    touched = {"top": y1 < EDGE_MARGIN_PX, "left": x1 < EDGE_MARGIN_PX,
               "right": x2 > width_px - EDGE_MARGIN_PX, "bottom": y2 > height_px - EDGE_MARGIN_PX}
    return {name for name, hit in touched.items() if hit}


def use_top_edge_objects(objects: list[dict[str, Any]], frame: Any) -> list[dict[str, Any]]:
    """Clears "edge" on cards and candies that touch only the top border and marks them "top_edge".
    frame: the picture the objects were found in (its shape gives the size). Returns the objects changed."""
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return []
    height_px, width_px = shape[:2]
    changed = []
    for found in objects:
        if found.get("edge") and found.get("type") in FEED_KINDS and "box" in found \
                and borders_touched(found["box"], width_px, height_px) == {"top"}:
            found["edge"], found["top_edge"] = False, True
            changed.append(found)
    return changed


def use_bottom_edge_boxes(objects: list[dict[str, Any]], frame: Any) -> list[dict[str, Any]]:
    """Clears "edge" on boxes that touch only the bottom border and marks them "bottom_edge"."""
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return []
    changed = []
    for found in objects:
        at_bottom = "box" in found and borders_touched(found["box"], shape[1], shape[0]) == {"bottom"}
        if found.get("edge") and found.get("type") == "box" and at_bottom:
            found["edge"], found["bottom_edge"] = False, True
            changed.append(found)
    return changed


def complete_cut_lid(found: dict[str, Any], corners_px: Any, size_mm: Any, to_robot: Any) -> float | None:
    """For a lid cut by the bottom border: sets x_robot / y_robot to the centre of the whole lid, clears "edge"
    and marks "bottom_edge". corners_px: the four corners of the lid's outline in the picture (Choton's
    object_angle). size_mm: (long, short) side of the lid as the camera measures it. to_robot: pixel -> robot
    X/Y. Returns the length outside the picture in mm, or None when the outline does not look like the lid
    or too much of it is hidden (the lid then stays "edge" and is not taken)."""
    if not size_mm or corners_px is None or len(corners_px) != 4:
        return None
    long_mm, short_mm = float(size_mm[0]), float(size_mm[1])
    corners = [(float(u), float(v)) for u, v in corners_px]
    edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    top = min(range(4), key=lambda i: edges[i][0][1] + edges[i][1][1])  # the outline's edge nearest the top of the picture
    middle = lambda edge: to_robot((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2)  # noqa: E731
    top_mm, far_mm = middle(edges[top]), middle(edges[(top + 2) % 4])
    width_mm = math.dist(to_robot(*edges[top][0]), to_robot(*edges[top][1]))
    seen_mm = math.dist(top_mm, far_mm)
    full_mm = long_mm if abs(width_mm - short_mm) <= abs(width_mm - long_mm) else short_mm  # the side that is cut
    across_mm = short_mm if full_mm == long_mm else long_mm
    if abs(width_mm - across_mm) > LID_SIDE_TOLERANCE * across_mm or seen_mm <= 0:
        return None
    hidden_mm = max(0.0, full_mm - seen_mm)
    if hidden_mm > LID_HIDDEN_MAX * full_mm:
        return None
    half_mm = max(full_mm, seen_mm) / 2
    found["x_robot"] = round(top_mm[0] + (far_mm[0] - top_mm[0]) / seen_mm * half_mm, 1)
    found["y_robot"] = round(top_mm[1] + (far_mm[1] - top_mm[1]) / seen_mm * half_mm, 1)
    found["edge"], found["bottom_edge"], found["hidden_mm"] = False, True, round(hidden_mm, 1)
    return hidden_mm


def keep_to_pick_area(objects: list[dict[str, Any]], area_mm: Any) -> list[dict[str, Any]]:
    """Marks objects whose centre is outside area_mm ([x min, x max, y min, y max] in robot mm) as off the
    object belt, like Choton's own rule. None: only his rule applies. Returns the objects it marked."""
    if not area_mm:
        return []
    x_min, x_max, y_min, y_max = area_mm
    marked = []
    for found in objects:
        inside = "x_robot" in found and x_min <= found["x_robot"] <= x_max and y_min <= found["y_robot"] <= y_max
        if "x_robot" in found and not inside and not found.get("off_belt"):
            found["reachable"], found["off_belt"] = False, True
            marked.append(found)
    return marked


def effective_pick_area(his: Any, ours: Any) -> tuple[float, float, float, float] | None:
    """The area in which an object counts: inside Choton's area AND inside ours (for the drawing on Vision)."""
    areas = [tuple(area) for area in (his, ours) if area]
    if not areas:
        return None
    return (max(a[0] for a in areas), min(a[1] for a in areas), max(a[2] for a in areas), min(a[3] for a in areas))
