"""The calibration fitted again to a camera view that has turned. Standard library only.

Choton's homography.json maps picture pixels to robot X/Y for the view the camera had when the
calibration was made. On 17 Nov the camera turned 6.3 deg in its holder half an hour after the
calibration of 21:26 (picture scale unchanged): every position was then 9 to 28 mm off. The two
calibration crosses still in view had moved exactly with the rest of the picture (0.3 px), so the
turn is a plain movement of the picture, and one matrix undoes it:

    pixel in the view of today  ->  pixel in the view of the calibration  ->  robot X/Y (Choton's matrix)

calibration.view_correction holds that matrix and the "created" stamp of the calibration it
belongs to. It is used only with that calibration: after a new calibration it is ignored.
Choton's file is never changed. Fix the camera and calibrate again when there is time.
"""

from __future__ import annotations

from typing import Any


def view_correction(entry_value: Any, calibration_created: Any) -> list[list[float]] | None:
    """The 3 x 3 matrix (pixel of today -> calibration pixel) if it belongs to this calibration, else None."""
    if not isinstance(entry_value, dict) or not calibration_created:
        return None
    matrix = entry_value.get("pixel_to_calibration_pixel")
    if entry_value.get("for_calibration") != calibration_created or not _is_3x3(matrix):
        return None
    return [[float(number) for number in row] for row in matrix]


def describe(entry_value: Any, calibration_created: Any) -> str:
    """'' (no correction set), or what the gate and the Vision screen say about it."""
    if not isinstance(entry_value, dict):
        return ""
    if view_correction(entry_value, calibration_created) is None:
        return (f"calibration.view_correction was made for the calibration of {entry_value.get('for_calibration')}, "
                f"not for this one ({calibration_created}): it is not used")
    why = entry_value.get("why", "the camera moved after the calibration")
    return (f"the calibration of {calibration_created} is used with a correction for the camera view ({why}): "
            "fix the camera and calibrate again when there is time")


def _is_3x3(matrix: Any) -> bool:
    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    return (isinstance(matrix, list) and len(matrix) == 3
            and all(isinstance(row, list) and len(row) == 3 and all(number(value) for value in row) for row in matrix))
