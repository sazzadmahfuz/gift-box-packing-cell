"""The camera pictures of a real run, saved next to its log. Standard library only.

testing/live_runs/<stamp>_pictures/0007_look.jpg: the picture a decision was made on (the box
standing still, the belt running and stopping, each LOOK, the closed box). The log row names the
file, so a run can be checked afterwards picture by picture. The 17 Nov runs had no pictures, and
why the belt ignored the cards could only be worked out from the numbers in the log. The raw
pictures (nothing drawn on them) are also what a model for this camera view can be trained on.

The JPEG encoder is handed in by the caller (Choton's cv2), so this file imports no vision package.
Saving never stops a run: a failed save is counted and the run goes on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

MAX_PICTURES = 400  # per run: about 50 MB at 1280 x 720; later pictures are not saved


class RunPictures:
    def __init__(self, folder: Path, encode_jpeg: Callable[[Any], bytes | None], limit: int = MAX_PICTURES) -> None:
        self.folder = folder
        self.encode_jpeg = encode_jpeg
        self.limit = limit
        self.saved = 0
        self.failed = 0

    def save(self, label: str, frame: Any) -> str | None:
        """Returns the file name, or None when nothing was saved (no frame, limit reached, encoder or disk error)."""
        if frame is None or self.saved >= self.limit:
            return None
        try:
            data = self.encode_jpeg(frame)
            if not data:
                raise ValueError("the picture could not be encoded")
            self.folder.mkdir(parents=True, exist_ok=True)
            name = f"{self.saved + 1:04d}_{label}.jpg"
            (self.folder / name).write_bytes(data)
        except Exception:  # a full disk or a broken frame must not stop the robot cycle
            self.failed += 1
            return None
        self.saved += 1
        return name


def pictures_folder(log_path: Path) -> Path:
    """testing/live_runs/20261117_195652.csv -> testing/live_runs/20261117_195652_pictures"""
    return log_path.with_name(log_path.stem + "_pictures")
