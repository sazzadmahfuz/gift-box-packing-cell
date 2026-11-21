"""Camera and vision for a run: Choton's FrameSource, model and yolo_lib functions.

A thread keeps reading frames so the latest one is always ready. read() hands each frame out
once (detect_stable calls it several times and expects new pictures). Nothing is drawn or
shown: no windows. His settings are copied and only camera_index is replaced by ours.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable

from ..checks.camera import CAMERA_LOCK
from .detections import borders_touched, complete_cut_lid, keep_to_pick_area, use_bottom_edge_boxes, use_top_edge_objects


class VisionUnavailable(RuntimeError):
    """Model or camera could not be started."""


class CameraLost(RuntimeError):
    """No new frame in time: cable out, or the camera stopped."""


class VisionSession:
    image = None  # yolo_lib.detect_stable reads several frames when src.image is None

    def __init__(self, choton: Any, settings: dict[str, Any], camera_index: int, frame_timeout_s: float,
                 make_source: Callable[[dict[str, Any]], Any] | None = None,
                 load_model: Callable[[dict[str, Any]], Any] | None = None,
                 clock: Callable[[], float] = time.monotonic, top_edge_usable: bool = False) -> None:
        self.choton = choton
        self.top_edge_usable = top_edge_usable  # vision.top_edge_objects_usable (detections.py)
        self.pick_area_mm: Any = None  # control.pick_area_mm, set by the vision service (detections.py)
        self.bottom_edge_usable = False  # vision.bottom_edge_box_and_lid_usable
        self.lid_size_mm: Any = None  # vision.lid_apparent_size_mm: (long, short) side of the lid as the camera measures it
        self.view_correction: Any = None  # camera_view.view_correction: pixel of today -> the calibration's pixel
        self.settings = copy.deepcopy(settings)
        self.settings["camera_index"] = camera_index
        self.frame_timeout_s = frame_timeout_s
        self.make_source = make_source or (lambda s: choton.vision_lib.FrameSource(None, s))
        self.load_model = load_model or choton.yolo_lib.load_model
        self.clock = clock
        self.model: Any = None
        self.classes: list[str] = []
        self.H: Any = None
        self.error = ""
        self._source: Any = None
        self._frame: Any = None
        self._frame_number = 0
        self._handed_out = 0
        self._frame_at_s: float | None = None
        self._frame_times: list[float] = []
        self._changed = threading.Condition()
        self._running = False
        self.latest: tuple[Any, list[dict[str, Any]], float] | None = None  # (frame, detections, time) of the last detect
        self._detect_lock = threading.Lock()

    # Start and stop

    def start(self) -> None:
        try:
            self.model = self.load_model(self.settings)
        except SystemExit as error:  # yolo_lib.load_model exits when ultralytics or the model file is missing
            raise VisionUnavailable(str(error)) from error
        names = getattr(self.model, "names", {})
        self.classes = [names[key] for key in sorted(names)] if isinstance(names, dict) else list(names)
        self.H = self.choton.vision_lib.load_homography()
        if self.view_correction is not None and self.H is not None:  # the camera turned after the calibration (camera_view.py)
            self.H = self.H @ self.choton.vision_lib.np.array(self.view_correction, dtype=float)
        try:
            with CAMERA_LOCK:  # waits while the camera check or the camera scan has the camera open
                self._source = self.make_source(self.settings)
        except (RuntimeError, OSError) as error:
            raise VisionUnavailable(f"camera {self.settings['camera_index']} did not open: {error}") from error
        self._running = True
        threading.Thread(target=self._read_loop, name="vision-camera", daemon=True).start()

    def stop(self) -> None:
        self._running = False
        with self._changed:
            self._changed.notify_all()
        if self._source is not None:
            try:
                self._source.release()
            except Exception:
                pass

    def _read_loop(self) -> None:
        while self._running:
            try:
                frame = self._source.read()
            except Exception as error:  # FrameSource raises when the camera gives no frame
                self.error = f"camera lost: {error}"
                self.stop()  # release the camera now, so a new session (or a replugged camera) can open it
                return
            now_s = self.clock()
            with self._changed:
                self._frame, self._frame_number, self._frame_at_s = frame, self._frame_number + 1, now_s
                self._frame_times = (self._frame_times + [now_s])[-30:]
                self._changed.notify_all()

    # Frames and detections (used by the cycle)

    def read(self) -> Any:
        """The next frame not handed out before; CameraLost if none arrives in time."""
        deadline_s = time.monotonic() + self.frame_timeout_s
        with self._changed:
            while self._frame_number <= self._handed_out:
                remaining_s = deadline_s - time.monotonic()
                if not self._running or remaining_s <= 0:
                    raise CameraLost(self.error or f"no new camera frame within {self.frame_timeout_s:g} s")
                self._changed.wait(remaining_s)
            self._handed_out = self._frame_number
            return self._frame

    def peek(self) -> tuple[int, Any]:
        """The newest frame and its number, WITHOUT handing it out (the cycle's read() still gets it)."""
        with self._changed:
            return self._frame_number, self._frame

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        with self._detect_lock:  # the UI's live loop and the cycle never run the model at the same time
            objects = self.choton.yolo_lib.detect(frame, self.model, self.settings, self.H)
        return self._keep(frame, objects, lids=False)

    def detect_stable(self, frames: int) -> tuple[Any, list[dict[str, Any]]]:
        with self._detect_lock:
            frame, objects = self.choton.yolo_lib.detect_stable(self, self.model, self.settings, self.H, frames=frames)
        return frame, self._keep(frame, objects, lids=True)

    def detect_for_the_screen(self, frame: Any) -> list[dict[str, Any]]:
        """detect(), plus the centre of a lid cut by the bottom border, as a LOOK works it out (for the live view)."""
        with self._detect_lock:
            objects = self.choton.yolo_lib.detect(frame, self.model, self.settings, self.H)
        return self._keep(frame, objects, lids=True)

    def _keep(self, frame: Any, objects: list[dict[str, Any]], lids: bool) -> list[dict[str, Any]]:
        """Our rules on top of his detections (detections.py). lids: also work out the centre of a cut lid. That
        outlines each such lid (about 0.1 s each), so the single pictures of the running belt go without it:
        17 Nov, testing/live_runs/20261117_220813.csv: with it a picture took 0.35 s instead of 0.15 s, the belt
        stopped late and a card came to rest at y = -114 mm, outside the pick area."""
        if self.top_edge_usable:
            use_top_edge_objects(objects, frame)
        if self.bottom_edge_usable:
            use_bottom_edge_boxes(objects, frame)
            if lids:
                self._complete_cut_lids(frame, objects)
        keep_to_pick_area(objects, self.pick_area_mm)
        self.latest = (frame, objects, self.clock())
        return objects

    def _complete_cut_lids(self, frame: Any, objects: list[dict[str, Any]]) -> None:
        """A lid cut by the bottom border gets the centre of the whole lid (detections.complete_cut_lid)."""
        shape = getattr(frame, "shape", None)
        if shape is None or not self.lid_size_mm or self.H is None:
            return
        for found in objects:
            if found.get("type") == "lid" and found.get("edge") and borders_touched(found["box"], shape[1], shape[0]) == {"bottom"}:
                corners = found.get("corners")
                if corners is None:
                    outline = self.choton.yolo_lib.object_angle(frame, found["box"])
                    corners = None if outline is None else outline[1]
                complete_cut_lid(found, corners, self.lid_size_mm, self.pixel_robot)

    def pixel_robot(self, u: float, v: float) -> tuple[float, float]:
        """Picture pixel -> robot X/Y (Choton's calibration)."""
        x_table_mm, y_table_mm = self.choton.vision_lib.pixel_to_robot(self.H, u, v)
        return self.choton.vision_lib.table_to_robot(x_table_mm, y_table_mm, self.settings)

    def add_angle(self, frame: Any, found: dict[str, Any]) -> None:
        """Choton's direction of the object's long side (angle_robot), added to one detection of this picture."""
        self.choton.yolo_lib.add_angle(frame, found, self.H)

    def robot_pixel(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Robot X/Y -> picture pixel (inverse of Choton's calibration)."""
        np = self.choton.vision_lib.np
        x_table_mm, y_table_mm = self.choton.vision_lib.robot_to_table(x_mm, y_mm, self.settings)
        u, v, w = np.linalg.inv(self.H) @ np.array([x_table_mm, y_table_mm, 1.0])
        return float(u / w), float(v / w)

    def slot_pixel(self, slot: Any) -> tuple[float, float]:
        """Robot X/Y of a box slot -> picture pixel."""
        return self.robot_pixel(slot[0], slot[1])

    def box_present(self, objects: list[dict[str, Any]], slot: Any) -> bool:
        """Anything is detected over the box slot: a box, a lid, or what lies in it. A filled box is often
        seen as the card on top (17 Nov: 'the closed box has left' 0.4 s after the request, box still there)."""
        u, v = self.slot_pixel(slot)
        for found in objects:
            x1, y1, x2, y2 = found.get("box", (0, 0, -1, -1))
            if found.get("type") in ("box", "lid", "card", "candy") and x1 <= u <= x2 and y1 <= v <= y2:
                return True
        return False

    def status(self) -> dict[str, Any]:
        times = self._frame_times
        fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 and times[-1] > times[0] else None
        frame = self._frame
        height_px, width_px = (frame.shape[:2] if frame is not None and hasattr(frame, "shape") else (None, None))
        return {
            "model_loaded": self.model is not None,
            "classes": self.classes,
            "frame_age_s": None if self._frame_at_s is None else round(self.clock() - self._frame_at_s, 3),
            "fps": None if fps is None else round(fps, 1),
            "width_px": width_px,
            "height_px": height_px,
            "camera_error": self.error,
            "running": self._running,
        }
