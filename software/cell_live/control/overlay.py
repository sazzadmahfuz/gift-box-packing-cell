"""The pick area and the object belt's stop line, drawn on the console's camera picture.

The pick area is Choton's (yolo_lib._belt_zone: his calibration crosses + 20 mm, in robot X/Y),
read and never changed. The stop line is control.feed_stop_y_mm (feed.py). cv2 is handed in by
the caller (Choton's vision_lib), so this file imports no vision package.
"""

from __future__ import annotations

from typing import Any, Callable

AREA_BGR = (255, 160, 0)  # blue-ish, apart from Choton's class colours
LINE_BGR = (0, 0, 255)  # red
MARK_BGR = (0, 255, 255)  # yellow
LABEL_SCALE = 0.6


def pick_area(yolo_lib: Any) -> tuple[float, float, float, float] | None:
    """(x min, x max, y min, y max) in robot mm of Choton's pick area, or None without a robot calibration."""
    zone_of = getattr(yolo_lib, "_belt_zone", None)
    try:
        return zone_of() if zone_of is not None else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def draw_feed_guides(cv2: Any, picture: Any, to_pixel: Callable[[float, float], tuple[float, float]],
                     zone: tuple[float, float, float, float] | None, stop_y_mm: float | None) -> Any:
    """Draws on picture (in place) and returns it."""
    if zone is None:
        return picture
    x_min, x_max, y_min, y_max = zone

    def point(x_mm: float, y_mm: float) -> tuple[int, int]:
        u, v = to_pixel(x_mm, y_mm)
        return int(round(u)), int(round(v))

    corners = [point(x_min, y_min), point(x_min, y_max), point(x_max, y_max), point(x_max, y_min)]
    for start, end in zip(corners, corners[1:] + corners[:1]):
        cv2.line(picture, start, end, AREA_BGR, 2)
    top_left = min(corners, key=lambda p: p[0] + p[1])
    cv2.putText(picture, "pick area", (top_left[0] + 6, top_left[1] + 22), cv2.FONT_HERSHEY_SIMPLEX, LABEL_SCALE, AREA_BGR, 2)
    if stop_y_mm is not None and y_min <= stop_y_mm <= y_max:
        start, end = point(x_min, stop_y_mm), point(x_max, stop_y_mm)
        cv2.line(picture, start, end, LINE_BGR, 3)
        cv2.putText(picture, f"stop line y = {stop_y_mm:g} mm", (min(start[0], end[0]) + 6, max(start[1], end[1]) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, LABEL_SCALE, LINE_BGR, 2)
    return picture


def draw_box_slot(cv2: Any, picture: Any, to_pixel: Callable[[float, float], tuple[float, float]], slot: Any) -> Any:
    """Where the robot drops the items (Choton's taught box slot): the open box must stand with this in its middle."""
    if not slot:
        return picture
    u, v = to_pixel(float(slot[0]), float(slot[1]))
    centre = (int(round(u)), int(round(v)))
    cv2.drawMarker(picture, centre, LINE_BGR, cv2.MARKER_TILTED_CROSS, 34, 3)
    cv2.circle(picture, centre, 24, LINE_BGR, 2)
    cv2.putText(picture, "box slot", (centre[0] + 28, centre[1] + 6), cv2.FONT_HERSHEY_SIMPLEX, LABEL_SCALE, LINE_BGR, 2)
    return picture


def draw_calibration_marks(cv2: Any, picture: Any, to_pixel: Callable[[float, float], tuple[float, float]], robot_points: Any) -> Any:
    """A small circle where each calibration mark (robot X/Y in homography.json) lies in the picture. While the tape
    crosses are still where the cup touched them, every circle sits on its cross; if not, the camera has moved."""
    for number, point in enumerate(robot_points or [], start=1):
        u, v = to_pixel(float(point[0]), float(point[1]))
        centre = (int(round(u)), int(round(v)))
        cv2.circle(picture, centre, 13, MARK_BGR, 2)
        cv2.putText(picture, f"cal {number}", (centre[0] + 16, centre[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, MARK_BGR, 2)
    return picture
