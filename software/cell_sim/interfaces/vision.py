"""Vision interface: which items the camera sees on belt A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Detection:
    item_type: str  # cell item name (for example card, candy) or "unknown"
    time_s: float  # clock time the item was first seen fully in the pick area
    ready_s: float  # clock time the result is available (frame time + processing time)
    x_table_mm: float | None = None  # vision table frame, NOT the robot frame
    y_table_mm: float | None = None
    angle_deg: float | None = None
    item_id: int | None = None  # the same physical item keeps its id between frames


@runtime_checkable
class VisionSource(Protocol):
    def detections(self) -> list[Detection]:
        """Items fully inside the pick area in the latest frame, oldest first."""
        ...
