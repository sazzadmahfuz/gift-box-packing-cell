"""Item and cycle records, the CSV writer and the per-cycle summary line."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import SIMULATION_BANNER

if TYPE_CHECKING:
    from .simulation import SimResult


@dataclass(frozen=True)
class ItemRecord:
    cycle: int
    item_index: int  # 1-based position in the box
    item_type: str
    entered_area_s: float  # the item was first fully inside the pick area
    pick_start_s: float
    pick_done_s: float
    place_done_s: float

    @property
    def item_time_s(self) -> float:
        return self.place_done_s - self.entered_area_s


@dataclass(frozen=True)
class SkippedRecord:
    """An item that left the pick area unpicked (not needed, or the set was not complete yet)."""

    cycle: int
    item_type: str
    entered_area_s: float
    left_area_s: float


@dataclass(frozen=True)
class CycleRecord:
    cycle: int
    items: tuple[str, ...]
    cycle_start_s: float
    box_seen_s: float  # camera saw the open box standing at S1
    set_ready_s: float  # full set in the pick area, belt A stopped
    pictures_done_s: float
    lid_done_s: float
    box_removed_s: float
    cycle_done_s: float
    skipped_count: int
    note: str = ""

    @property
    def cycle_time_s(self) -> float:
        return self.cycle_done_s - self.cycle_start_s


CSV_COLUMNS: tuple[str, ...] = (
    "record_type",
    "cycle",
    "item_index",
    "item_type",
    "items",
    "entered_area_s",
    "left_area_s",
    "pick_start_s",
    "pick_done_s",
    "place_done_s",
    "item_time_s",
    "cycle_start_s",
    "box_seen_s",
    "set_ready_s",
    "pictures_done_s",
    "lid_done_s",
    "box_removed_s",
    "cycle_done_s",
    "cycle_time_s",
    "skipped_count",
    "note",
)


def _seconds(value_s: float) -> str:
    return f"{value_s:.3f}"


def _item_row(record: ItemRecord) -> dict[str, str]:
    return {
        "record_type": "item",
        "cycle": str(record.cycle),
        "item_index": str(record.item_index),
        "item_type": record.item_type,
        "entered_area_s": _seconds(record.entered_area_s),
        "pick_start_s": _seconds(record.pick_start_s),
        "pick_done_s": _seconds(record.pick_done_s),
        "place_done_s": _seconds(record.place_done_s),
        "item_time_s": _seconds(record.item_time_s),
    }


def _skipped_row(record: SkippedRecord) -> dict[str, str]:
    return {
        "record_type": "skipped",
        "cycle": str(record.cycle),
        "item_type": record.item_type,
        "entered_area_s": _seconds(record.entered_area_s),
        "left_area_s": _seconds(record.left_area_s),
        "note": "left the pick area unpicked; passed to the end of belt A",
    }


def _cycle_row(record: CycleRecord) -> dict[str, str]:
    return {
        "record_type": "cycle",
        "cycle": str(record.cycle),
        "items": "|".join(record.items),
        "cycle_start_s": _seconds(record.cycle_start_s),
        "box_seen_s": _seconds(record.box_seen_s),
        "set_ready_s": _seconds(record.set_ready_s),
        "pictures_done_s": _seconds(record.pictures_done_s),
        "lid_done_s": _seconds(record.lid_done_s),
        "box_removed_s": _seconds(record.box_removed_s),
        "cycle_done_s": _seconds(record.cycle_done_s),
        "cycle_time_s": _seconds(record.cycle_time_s),
        "skipped_count": str(record.skipped_count),
        "note": record.note,
    }


def csv_rows(result: SimResult) -> list[dict[str, str]]:
    """Per cycle: item and skipped rows in the order they entered the pick area, then the cycle row."""
    rows: list[dict[str, str]] = []
    last_cycle = max([0, *(r.cycle for r in result.items), *(r.cycle for r in result.skipped)])
    for cycle in range(1, last_cycle + 1):
        detections: list[tuple[float, int, dict[str, str]]] = []
        detections += [(r.entered_area_s, 0, _item_row(r)) for r in result.items if r.cycle == cycle]
        detections += [(r.entered_area_s, 1, _skipped_row(r)) for r in result.skipped if r.cycle == cycle]
        rows += [row for _, _, row in sorted(detections, key=lambda entry: entry[:2])]
        rows += [_cycle_row(r) for r in result.cycles if r.cycle == cycle]
    if result.fault_reason is not None:
        rows.append({"record_type": "fault", "cycle": str(last_cycle), "note": result.fault_reason})
    return rows


def write_csv(result: SimResult, out_dir: str | Path, banner: str = SIMULATION_BANNER) -> Path:
    """Write the run to <out_dir>/<timestamp>.csv. Line 1 is the banner (label, parameter source)."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = directory / f"{stamp}.csv"
    suffix = 2
    while path.exists():
        path = directory / f"{stamp}_{suffix}.csv"
        suffix += 1
    with open(path, "w", encoding="utf-8", newline="") as csv_file:
        csv_file.write(banner + "\n")
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows(result))
    return path


def summary_line(record: CycleRecord, cycles_requested: int, label: str = "SIMULATION") -> str:
    return (
        f"[{label}] cycle {record.cycle}/{cycles_requested}: "
        f"items={','.join(record.items)} skipped={record.skipped_count} "
        f"cycle_time_s={_seconds(record.cycle_time_s)} done_at_s={_seconds(record.cycle_done_s)}"
    )
