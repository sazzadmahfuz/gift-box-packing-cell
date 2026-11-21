"""Read the run logs written by cell_sim (no tkinter here).

Columns come from each file's header, so new columns or record types need no change here.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

RECORD_TYPE_COLUMN = "record_type"
CYCLE_RECORD = "cycle"
CYCLE_TIME_COLUMN = "cycle_time_s"
CYCLE_COLUMN = "cycle"


@dataclass(frozen=True)
class RunLog:
    path: Path
    banner: str  # line 1 without "# ", e.g. "SIMULATION, assumed parameters; ..."
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    @property
    def label(self) -> str:
        """The part before the first ';', e.g. 'ROBODK SIMULATION, assumed parameters'."""
        return self.banner.split(";")[0].strip() or "(no banner)"

    def cycle_times_s(self) -> list[tuple[str, float]]:
        """(cycle, cycle_time_s) for each cycle row; [] if this log has no such columns."""
        if RECORD_TYPE_COLUMN not in self.columns or CYCLE_TIME_COLUMN not in self.columns:
            return []
        times = []
        for row in self.rows:
            if row.get(RECORD_TYPE_COLUMN) == CYCLE_RECORD and row.get(CYCLE_TIME_COLUMN):
                try:
                    times.append((row.get(CYCLE_COLUMN, "?"), float(row[CYCLE_TIME_COLUMN])))
                except ValueError:
                    continue
        return times

    def mean_cycle_time_s(self) -> float | None:
        times = [time_s for _cycle, time_s in self.cycle_times_s()]
        return sum(times) / len(times) if times else None

    def count_by_record_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            kind = row.get(RECORD_TYPE_COLUMN, "")
            counts[kind] = counts.get(kind, 0) + 1
        return counts


def list_logs(folder: Path) -> list[Path]:
    """CSV files in the folder, newest first."""
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)


def read_log(path: Path) -> RunLog:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    banner = ""
    if lines and lines[0].startswith("#"):
        banner = lines[0].lstrip("#").strip()
        lines = lines[1:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    rows = tuple(dict(row) for row in reader)
    return RunLog(path, banner, tuple(reader.fieldnames or ()), rows)


def read_banner(path: Path) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as log_file:
            first = log_file.readline()
    except OSError:
        return ""
    return first.lstrip("#").strip() if first.startswith("#") else ""
