"""Run log: testing/live_runs/<YYYYmmdd_HHMMSS>.csv, the evidence of a real run.

Line 1 says HARDWARE RUN with the speed, the teacher approval text and the hashes of the config
files. Then one row per event: robot commands and replies, detections used, pauses, faults.
Nothing from the simulation is written here.
"""

from __future__ import annotations

import csv
import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable

COLUMNS = ("time_s", "box", "state", "event", "command", "reply", "detections", "fault")


def file_sha256(path: Path | None) -> str:
    if path is None or not Path(path).is_file():
        return "missing"
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def describe_detections(objects: list[dict[str, Any]] | None) -> str:
    parts = []
    for found in objects or []:
        where = f"({found.get('x_robot')}, {found.get('y_robot')})" if "x_robot" in found else "(no robot X/Y)"
        angle = f" {found['angle_robot']:+.0f}deg" if isinstance(found.get("angle_robot"), (int, float)) else ""
        skipped = f" OUT OF REACH {found['out_of_reach_mm']} mm" if "out_of_reach_mm" in found else ""
        skipped += f" ARM CANNOT REACH (J1 {found['out_of_reach_j1_deg']} deg)" if "out_of_reach_j1_deg" in found else ""
        skipped += " NOT IN THE PICK AREA" if found.get("off_belt") else ""  # Choton's pick area (calibration crosses)
        skipped += " AT THE EDGE" if found.get("edge") else ""
        skipped += " TOUCHES THE TOP EDGE (used)" if found.get("top_edge") else ""  # detections.py
        if found.get("bottom_edge"):
            hidden = f", {found['hidden_mm']:g} mm of it outside, centre worked out" if "hidden_mm" in found else ""
            skipped += f" CUT BY THE BOTTOM EDGE (used{hidden})"
        parts.append(f"{found.get('type')} {found.get('conf')} {where}{angle}{skipped}")
    return "; ".join(parts)


class RunLog:
    def __init__(self, out_dir: Path, speed_percent: int, teacher_approval: str, boxes: int,
                 hashed_files: dict[str, Path | None], clock: Callable[[], float] = time.monotonic,
                 on_row: Callable[[dict[str, str]], None] | None = None) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"{stamp}.csv"
        suffix = 2
        while path.exists():
            path, suffix = out_dir / f"{stamp}_{suffix}.csv", suffix + 1
        self.path = path
        self.clock = clock
        self.on_row = on_row
        self._start_s = clock()
        self._lock = threading.Lock()
        self.box = 0
        self.state = ""
        self.events: list[dict[str, str]] = []
        hashes = ", ".join(f"{name}={file_sha256(file)}" for name, file in hashed_files.items())
        banner = (f"# HARDWARE RUN; speed {speed_percent} %; boxes requested {boxes}; "
                  f"teacher approval: {teacher_approval}; sha256 {hashes}")
        self._file = open(path, "w", encoding="utf-8", newline="")
        self._file.write(banner + "\n")
        self._writer = csv.DictWriter(self._file, fieldnames=COLUMNS, lineterminator="\n")
        self._writer.writeheader()
        self._file.flush()

    def event(self, event: str, command: str = "", reply: str = "", detections: list[dict[str, Any]] | None = None,
              fault: str = "", state: str | None = None) -> None:
        row = {
            "time_s": f"{self.clock() - self._start_s:.3f}",
            "box": str(self.box),
            "state": state or self.state,
            "event": event,
            "command": command,
            "reply": reply,
            "detections": describe_detections(detections),
            "fault": fault,
        }
        with self._lock:
            if self._file.closed:
                return
            self._writer.writerow(row)
            self._file.flush()
            self.events = (self.events + [row])[-50:]
        if self.on_row is not None:
            try:
                self.on_row(row)
            except Exception:  # the UI must never break the log
                pass

    def command(self, port: int, command: str, reply: str) -> None:
        """robot_client logger: every command sent to the robot and its reply."""
        self.event(f"port {port}", command=command, reply=reply)

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()
