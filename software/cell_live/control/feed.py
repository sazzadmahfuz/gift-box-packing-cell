"""When the object belt stops while it brings the objects. Standard library only.

The belt runs until one of these is true:
- every object the box still needs is usable in the pick area, `ready_frames` pictures in a row
  (Choton's rule from 14_pick_and_place.py feed_objects: 3 pictures, so a flicker does not count);
- an object the box still needs has reached the stop line (`control.feed_stop_y_mm`; the objects
  move towards lower robot y), `stop_line_frames` pictures in a row. The belt stops there, so the
  object is not carried out of the pick area while the belt waits for the rest of the set. The
  robot then picks what is there and the belt runs again for the rest (cycle_steps.pick_place).

Usable is Choton's yolo_lib.usable: not at the picture edge, inside his pick area (the
calibration crosses + 20 mm), and inside our reach (run_context.mark_reach_objects).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

FEED_KINDS = ("card", "candy")  # what the object belt brings


def still_needed(want: dict[str, int], placed: list[dict[str, Any]]) -> dict[str, int]:
    """What the box still needs, e.g. {"candy": 1} after a card and one candy were placed."""
    need = {kind: count - sum(1 for done in placed if done.get("type") == kind) for kind, count in want.items()}
    return {kind: count for kind, count in need.items() if count > 0}


@dataclass(frozen=True)
class FeedDecision:
    stop: bool
    reason: str  # why the belt stops; "" while it runs
    counts_changed: bool  # the pick area counts differ from the picture before: worth a log row
    counts: str  # e.g. "card 0/1, candy 1/2 in the pick area"


class FeedWatch:
    """Fed with the detections of each new picture while the belt runs; says when to stop it."""

    def __init__(self, need: dict[str, int], ready_frames: int, stop_y_mm: float | None, stop_line_frames: int,
                 usable: Callable[[dict[str, Any]], bool]) -> None:
        self.need = dict(need)
        self.ready_frames = ready_frames
        self.stop_y_mm = stop_y_mm
        self.stop_line_frames = stop_line_frames
        self.usable = usable
        self._ready = 0
        self._at_line = 0
        self._last_counts: dict[str, int] | None = None
        self.counts = self._words({kind: 0 for kind in self.need})

    def see(self, objects: list[dict[str, Any]]) -> FeedDecision:
        usable = [found for found in objects if found.get("type") in self.need and self.usable(found)]
        counts = {kind: sum(1 for found in usable if found["type"] == kind) for kind in self.need}
        full_set = all(counts[kind] >= count for kind, count in self.need.items())
        self._ready = self._ready + 1 if full_set else 0
        at_line = [found for found in usable if self._past_line(found)]
        self._at_line = self._at_line + 1 if at_line else 0
        changed, self._last_counts = counts != self._last_counts, counts
        self.counts = self._words(counts)
        reason = ""
        if self._ready >= self.ready_frames:
            reason = f"the full set is in the pick area ({self.counts}, {self._ready} pictures in a row)"
        elif at_line and self._at_line >= self.stop_line_frames:
            lead = min(at_line, key=lambda found: found["y_robot"])
            reason = (f"{lead['type']} at y = {lead['y_robot']:.0f} mm reached the stop line ({self.stop_y_mm:g} mm), "
                      f"so it stays in the pick area ({self.counts})")
        return FeedDecision(bool(reason), reason, changed, self.counts)

    def _past_line(self, found: dict[str, Any]) -> bool:
        y_mm = found.get("y_robot")
        return self.stop_y_mm is not None and isinstance(y_mm, (int, float)) and y_mm <= self.stop_y_mm

    def _words(self, counts: dict[str, int]) -> str:
        return ", ".join(f"{kind} {counts[kind]}/{count}" for kind, count in self.need.items()) + " in the pick area"


def feed_detections(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cards and candies of one picture, for the run log (the boxes and lids are not fed)."""
    return [found for found in objects if found.get("type") in FEED_KINDS]
