"""Camera -> robot calibration file check (Choton's homography.json, read only)."""

from __future__ import annotations

from pathlib import Path

from ..adapters.choton import read_json
from ..status import FAIL, OK, WARN, CheckResult


class CalibrationCheck:
    id = "calibration"
    name = "Camera calibration (homography.json)"
    kind = "file"  # a file on this PC, not a device

    def __init__(self, path: Path | None, interval_s: float, valid_from: str | None = None) -> None:
        self.path = path
        self.interval_s = interval_s
        self.valid_from = valid_from  # date of the current worktable and camera stand (calibration.valid_from)

    def run(self) -> CheckResult:
        if self.path is None or not self.path.is_file():
            return CheckResult(FAIL, f"calibration file not found: {self.path} (calibration.file)")
        try:
            calibration = read_json(self.path)
        except (OSError, ValueError) as error:
            return CheckResult(FAIL, f"calibration file does not parse: {error}")
        matrix = calibration.get("H") if isinstance(calibration, dict) else None
        if not (isinstance(matrix, list) and len(matrix) == 3 and all(isinstance(row, list) and len(row) == 3 for row in matrix)):
            return CheckResult(FAIL, "calibration file has no 3x3 matrix 'H'")
        data = {
            "created": calibration.get("created"),
            "mean_error_mm": calibration.get("mean_error_mm"),
            "points": len(calibration.get("robot_points", [])),
            "frame": calibration.get("frame"),
            "practice": calibration.get("practice"),
        }
        error_text = f"{data['mean_error_mm']:.2f} mm" if isinstance(data["mean_error_mm"], (int, float)) else "not stored"
        detail = f"created {data['created']}, mean error {error_text}, {data['points']} points"
        if data["practice"]:
            return CheckResult(WARN, f"practice calibration (not from the real robot): {detail}", data=data)
        made = str(data["created"] or "")[:10]
        if self.valid_from and made < str(self.valid_from):
            return CheckResult(WARN, f"made before the current worktable and camera stand ({self.valid_from}): {detail}. "
                                     "Commit Choton's new homography.json", data=data)
        return CheckResult(OK, detail, data=data)
