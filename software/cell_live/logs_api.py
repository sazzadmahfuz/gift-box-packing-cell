"""Read the HARDWARE RUN logs (testing/live_runs/*.csv) for the Logs screen. Standard library only.

Every number the screen shows is computed here: per box the start, end, duration and result;
the failures (PAUSED and FAULT events); the mean time of the boxes that were done.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

LOG_NAME = re.compile(r"^\d{8}_\d{6}(_\d+)?\.csv$")
BOX_RESULT = re.compile(r"^box (\d+): ([^;]+);")


class LogNotFound(LookupError):
    pass


def list_logs(folder: Path) -> list[dict[str, Any]]:
    """Newest first, with the line-1 banner."""
    if not folder.is_dir():
        return []
    logs = []
    for path in sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
        if LOG_NAME.match(path.name):
            logs.append({"name": path.name, "banner": _banner(path), "size_bytes": path.stat().st_size,
                         "modified": path.stat().st_mtime})
    return logs


def read_log(folder: Path, name: str) -> dict[str, Any]:
    if not LOG_NAME.match(name or ""):
        raise LogNotFound(f"{name!r} is not a run log name (YYYYmmdd_HHMMSS.csv)")
    path = folder / name
    if not path.is_file():
        raise LogNotFound(f"no run log {name} in {folder}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    banner = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else ""
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:] if banner else lines)))
    rows = [dict(row) for row in reader]
    return {"name": name, "banner": banner, "columns": reader.fieldnames or [], "rows": rows, "summary": summarize(rows)}


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    starts: dict[int, float] = {}
    boxes = []
    failures = []
    for row in rows:
        time_s = _number(row.get("time_s"))
        event = row.get("event", "")
        box = int(row["box"]) if (row.get("box") or "").isdigit() else 0
        if event == "enter WAIT_BOX" and box and box not in starts and time_s is not None:
            starts[box] = time_s
        result = BOX_RESULT.match(event)
        if result and time_s is not None:
            number = int(result.group(1))
            start_s = starts.get(number)
            boxes.append({"box": number, "result": result.group(2), "start_s": start_s, "end_s": time_s,
                          "duration_s": round(time_s - start_s, 3) if start_s is not None else None})
        if event.startswith("PAUSED") or event.startswith("FAULT"):
            failures.append({"time_s": time_s, "box": box, "event": event, "fault": row.get("fault", "")})
    done = [box["duration_s"] for box in boxes if box["result"] == "done" and box["duration_s"] is not None]
    return {
        "boxes": boxes,
        "boxes_done": len(done),
        "mean_box_s": round(sum(done) / len(done), 3) if done else None,
        "failures": failures,
        "end_s": _number(rows[-1].get("time_s")) if rows else None,
    }


def _banner(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as log_file:
        first = log_file.readline()
    return first.lstrip("#").strip() if first.startswith("#") else ""


def _number(text: str | None) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None
