"""The backend's one camera and vision session, for the UI (Vision screen, MJPEG stream) and runs.

It starts in the background when camera.index is confirmed (or on POST /api/vision/start). While
the cycle takes no pictures (no run, or a run that is PAUSED or in FAULT), a live loop detects on
the newest frame via peek(), so it never takes a frame the cycle needs; while the cycle works, its
own detections are shown. Overlays are drawn with
Choton's yolo_lib.draw on a copy of his settings whose reach circle is OUR limit (375 mm).
Nothing is simulated: without a camera everything says NOT_OBSERVABLE and why.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable

from .arm_reach import arm_reach_from
from ..adapters.choton import read_json
from .belts import box_nearest_the_slot, box_off_the_slot
from .camera_view import describe as describe_view_correction
from .camera_view import view_correction
from .detections import effective_pick_area
from .feed import FeedWatch
from .gate import NOT_FOR_A_RUN
from .lid import LidRule, choose_lid
from .overlay import draw_box_slot, draw_calibration_marks, draw_feed_guides, pick_area
from .run_context import mark_reach_objects
from .vision_session import VisionSession, VisionUnavailable

KINDS = ("card", "candy", "box", "lid")


class _Opening:
    """Stands in for the session while it opens the camera (model load, warm-up frames, camera lock)."""

    @staticmethod
    def status() -> dict[str, Any]:
        return {"running": True, "starting": True, "camera_error": ""}


OPENING = _Opening()


class VisionService:
    def __init__(self, config: Any, load_choton: Callable[[Any], Any], make_vision: Callable[..., Any] = VisionSession,
                 run_active: Callable[[], bool] = lambda: False, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.load_choton = load_choton
        self.make_vision = make_vision
        self.run_active = run_active
        self.clock = clock
        self.session: Any = None
        self.choton: Any = None
        self.settings: dict[str, Any] | None = None
        self.error = ""
        self.starting = False
        self._lock = threading.Lock()
        self._running = False
        self._ready_frames = 0
        self._seen_at: float | None = None
        self._feed: FeedWatch | None = None  # the run's stop rule, applied to the detections the screen gets
        self._feed_decision: dict[str, Any] = {}
        self.stream_max_fps = float(self._value("stream_max_fps", 5.0))
        self.live_interval_s = float(self._value("live_detect_interval_s", 0.5))
        self.arm = arm_reach_from(config)  # the run's J1 check, so the screen marks what the run will not pick

    def _value(self, key: str, default: float) -> Any:
        entry = self.config.raw.get("vision", {}).get(key)
        return entry["value"] if entry and entry["value"] is not None else default

    def _view_correction_facts(self) -> tuple[Any, Any]:
        """(calibration.view_correction, the "created" stamp of the calibration file); (None, None) if not readable."""
        entry = self.config.raw.get("calibration", {}).get("view_correction")
        try:
            return (entry["value"] if entry else None), read_json(self.config.path_value("calibration", "file")).get("created")
        except (OSError, ValueError, TypeError, AttributeError):
            return None, None

    def _calibration_marks(self) -> Any:
        """The robot X/Y of the calibration marks (homography.json robot_points), for the drawing; [] if not readable."""
        try:
            return read_json(self.config.path_value("calibration", "file")).get("robot_points") or []
        except (OSError, ValueError, TypeError, AttributeError):
            return []

    def view_note(self) -> str:
        """'' or what is to be said about the camera view correction (gate note, Vision screen)."""
        return describe_view_correction(*self._view_correction_facts())

    def _our_pick_area(self) -> Any:
        entry = self.config.raw.get("control", {}).get("pick_area_mm")
        return entry["value"] if entry else None

    def camera_reason(self) -> str:
        """Why there is no camera session, or '' if the camera index allows one."""
        entry = self.config.entry("camera", "index")
        if entry["value"] is None or entry["status"] in NOT_FOR_A_RUN:
            return f"camera.index is not set ({entry['status']}): set it in Settings"
        return ""

    def camera_holder(self) -> Any:
        """For the camera check: the session, or a stand-in while one is opening the camera, or None.
        The check opens the camera itself only for None: two readers of one USB camera get no frames."""
        return OPENING if self.starting and self.session is None else self.session

    # Starting and stopping

    def ensure_started(self, choton: Any = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start the session now if needed (blocks while the model loads). Returns status()."""
        with self._lock:  # every way out clears "starting" here, also the one start_async set before its thread
            if self.session is not None and self.session.status()["running"]:
                self.starting = False
                return self.status()
            reason = self.camera_reason()
            if reason:
                self.error, self.starting = reason, False
                return self.status()
            self.starting = True
            if self.session is not None:  # a stopped session (camera lost): make sure it let go of the camera
                self.session.stop()
            try:
                self.choton = choton or self.load_choton(self.config.path_value("choton", "folder"))
                self.settings = copy.deepcopy(settings or self.choton.vision_lib.load_settings())
                session = self.make_vision(self.choton, self.settings, self.config.value("camera", "index"),
                                           float(self.config.value("control", "camera_frame_max_age_s")))
                session.top_edge_usable = bool(self._value("top_edge_objects_usable", False))
                session.pick_area_mm = self._our_pick_area()
                session.bottom_edge_usable = bool(self._value("bottom_edge_box_and_lid_usable", False))
                session.lid_size_mm = self._value("lid_apparent_size_mm", None)
                session.view_correction = view_correction(*self._view_correction_facts())
                session.start()
                self.session, self.error = session, ""  # before starting clears: the check never sees no session
            except (VisionUnavailable, RuntimeError, OSError) as error:  # ChotonCodeUnavailable is a RuntimeError
                self.error = str(error)
                return self.status()
            finally:
                self.starting = False
        self._start_live_loop()
        return self.status()

    def start_async(self) -> dict[str, Any]:
        reason = self.camera_reason()
        if reason:
            return {"ok": False, "message": reason}
        self.starting = True  # at once, so a camera check that runs before the thread leaves the camera alone
        threading.Thread(target=self.ensure_started, name="vision-start", daemon=True).start()
        return {"ok": True, "message": "starting the camera and the model (this takes a few seconds)"}

    def stop(self) -> None:
        self._running = False
        if self.session is not None:
            self.session.stop()

    def _start_live_loop(self) -> None:
        self._running = True
        threading.Thread(target=self._live_loop, name="vision-live", daemon=True).start()

    def _live_loop(self) -> None:
        last_number = 0
        while self._running and self.session is not None:
            if not self.run_active():  # while the cycle works, the cycle detects; never take its frames
                try:
                    number, frame = self.session.peek()
                    if frame is not None and number != last_number:
                        getattr(self.session, "detect_for_the_screen", self.session.detect)(frame)
                        last_number = number
                except Exception as error:  # a camera or model error must not stop the service
                    self.error = f"live detection failed: {error}"
            time.sleep(self.live_interval_s)

    # What the UI shows

    def status(self) -> dict[str, Any]:
        if self.session is None:
            return {"model_loaded": False, "model_error": self.error, "frame_age_s": None, "camera_error": self.error, "running": False}
        return self.session.status()

    def summary(self) -> dict[str, Any]:
        """Counts, detections and the ready flag, all computed here from the latest detections."""
        if self.session is None:
            state = "UNKNOWN" if self.starting else "NOT_OBSERVABLE"
            return {"state": state, "reason": "starting the camera" if self.starting else (self.error or self.camera_reason()),
                    "counts": {}, "usable": {}, "detections": [], "ready": False}
        status = self.session.status()
        latest = getattr(self.session, "latest", None)
        if not status.get("running"):
            return {"state": "FAIL", "reason": status.get("camera_error") or "camera stopped", "counts": {}, "usable": {},
                    "detections": [], "ready": False, "camera": status}
        objects = [dict(o) for o in (latest[1] if latest else [])]
        mark_reach_objects(objects, self.config.value("control", "reach_min_mm"), self.config.value("control", "reach_max_mm"), self.arm)
        usable = [o for o in objects if not o.get("edge") and o.get("reachable", True)]
        counts = {kind: sum(1 for o in objects if o.get("type") == kind and not o.get("edge")) for kind in KINDS}
        usable_counts = {kind: sum(1 for o in usable if o.get("type") == kind) for kind in ("card", "candy")}
        self._update_ready(latest, usable_counts, objects)
        return {
            "state": "OK", "reason": "", "source": "run" if self.run_active() else "live",
            "counts": counts, "usable": usable_counts, "ready": self._ready_frames >= self._ready_needed(),
            "ready_frames": self._ready_frames, "ready_needed": self._ready_needed(), "want": self._want(),
            "feed": self._feed_decision, "detections": [_row(o) for o in objects], "camera": status,
            "detections_age_s": round(self.clock() - latest[2], 2) if latest else None, **self._box_and_lid(objects),
            "view_note": self.view_note(),
        }

    def _box_and_lid(self, objects: list[dict[str, Any]]) -> dict[str, Any]:
        """What a run would do with the box and the lid in this picture, in the run's own words (belts.py, lid.py)."""
        slot = ((self.settings or {}).get("robot", {}).get("box_slots") or [None])[0]
        if not slot:
            return {}
        control = lambda key: self.config.value("control", key)  # noqa: E731 (short local helper)
        rule = LidRule(control("reach_min_mm"), control("reach_max_mm"), self.arm, float(control("lid_min_from_slot_mm")),
                       float(control("lid_grip_offset_max_mm")))
        lid = choose_lid(objects, slot, rule)
        boxes = [o for o in objects if o.get("type") == "box" and not o.get("edge") and "x_robot" in o]
        if not boxes:
            box = {"ok": False, "words": "no open box in the picture (a box with items in it is not seen as a box)"}
        else:
            problem = box_off_the_slot(box_nearest_the_slot(boxes, slot), slot, control("box_slot_tolerance_mm"))
            box = {"ok": not problem, "words": problem or "open box under the box slot"}
        return {"box": box, "lid": {"ok": lid.lid is not None, "words": lid.words}}

    def _want(self) -> dict[str, int]:
        return dict((self.settings or {}).get("box_contents", {"card": 1, "candy": 2}))

    def _ready_needed(self) -> int:
        return int(self.config.value("control", "objects_ready_frames"))

    def _update_ready(self, latest: Any, usable_counts: dict[str, int], objects: list[dict[str, Any]]) -> None:
        if not latest or latest[2] == self._seen_at:
            return
        self._seen_at = latest[2]
        ready = all(usable_counts.get(kind, 0) >= n for kind, n in self._want().items())
        self._ready_frames = self._ready_frames + 1 if ready else 0
        if self._feed is None:
            stop_y_mm = self.config.value("control", "feed_stop_y_mm")
            self._feed = FeedWatch(self._want(), self._ready_needed(), None if stop_y_mm is None else float(stop_y_mm),
                                   int(self.config.value("control", "feed_stop_line_frames")), _usable)
        decision = self._feed.see(objects)
        self._feed_decision = {"stop": decision.stop, "reason": decision.reason, "counts": decision.counts,
                               "stop_y_mm": self._feed.stop_y_mm}

    def jpeg(self) -> bytes | None:
        """The newest frame with Choton's overlay (our 375 mm reach circle), as JPEG; None without a camera."""
        if self.session is None or not self.session.status().get("running"):
            return None
        _number, frame = self.session.peek()
        if frame is None:
            return None
        latest = getattr(self.session, "latest", None)
        objects = [dict(o) for o in (latest[1] if latest else [])]
        mark_reach_objects(objects, self.config.value("control", "reach_min_mm"), self.config.value("control", "reach_max_mm"), self.arm)
        overlay_settings = copy.deepcopy(self.settings or {})
        overlay_settings.setdefault("robot", {})["reach_radius_mm"] = self.config.value("control", "reach_max_mm")
        try:
            cv2 = self.choton.vision_lib.cv2
            picture = self.choton.yolo_lib.draw(frame, objects, overlay_settings, self.session.H)
            to_pixel = getattr(self.session, "robot_pixel", None)
            if to_pixel is not None and self.session.H is not None:
                area = effective_pick_area(pick_area(self.choton.yolo_lib), self._our_pick_area())
                draw_feed_guides(cv2, picture, to_pixel, area, self.config.value("control", "feed_stop_y_mm"))
                draw_box_slot(cv2, picture, to_pixel, ((self.settings or {}).get("robot", {}).get("box_slots") or [None])[0])
                draw_calibration_marks(cv2, picture, to_pixel, self._calibration_marks())
            ok, encoded = cv2.imencode(".jpg", picture)
        except Exception as error:  # drawing must never break the stream
            self.error = f"overlay failed: {error}"
            return None
        return encoded.tobytes() if ok else None


def _usable(found: dict[str, Any]) -> bool:
    """Choton's yolo_lib.usable (not at the edge, reachable), on objects marked by mark_reach_objects."""
    return not found.get("edge") and found.get("reachable", True)


def _row(found: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": found.get("type"), "conf": found.get("conf"), "color": found.get("color"),
        "x_robot": found.get("x_robot"), "y_robot": found.get("y_robot"), "angle": found.get("angle_robot"),
        "edge": bool(found.get("edge")), "top_edge": bool(found.get("top_edge")), "reachable": bool(found.get("reachable", True)),
        "bottom_edge": bool(found.get("bottom_edge")), "hidden_mm": found.get("hidden_mm"),
        "out_of_reach_mm": found.get("out_of_reach_mm"),
        "out_of_reach_j1_deg": found.get("out_of_reach_j1_deg"),
    }
