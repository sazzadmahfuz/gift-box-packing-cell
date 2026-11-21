"""USB camera check (opencv imported lazily here). Grabs frames; saves and shows nothing."""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable

from ..status import FAIL, NOT_OBSERVABLE, OK, UNKNOWN, WARN, CheckResult, missing_package

OPENCV_INSTALL = "python -m pip install opencv-python"
# One opener of the USB camera at a time: this check or the camera scan while they hold it open, or a
# vision session while it opens it. Two readers of one USB camera get no frames (17 Nov: at start-up
# the first check opened camera 1 while the session opened it, and the session lost the camera).
CAMERA_LOCK = threading.Lock()


def load_cv2() -> Any:
    import cv2  # optional package, only for the camera check

    return cv2


def _open(cv2: Any, index: int) -> Any:
    backend = getattr(cv2, "CAP_DSHOW", 0) if sys.platform == "win32" else getattr(cv2, "CAP_ANY", 0)
    return cv2.VideoCapture(index, backend)


class CameraCheck:
    id = "camera"
    name = "USB camera"

    def __init__(self, index: int | None, width_px: int, height_px: int, sample_frames: int, interval_s: float,
                 cv2_loader: Callable[[], Any] = load_cv2, session_provider: Callable[[], Any] | None = None) -> None:
        self.session_provider = session_provider  # the vision session holds the camera during a run
        self.index = index
        self.width_px = width_px
        self.height_px = height_px
        self.sample_frames = max(2, sample_frames)
        self.interval_s = interval_s
        self.cv2_loader = cv2_loader

    def run(self) -> CheckResult:
        session = self.session_provider() if self.session_provider is not None else None
        if session is not None:
            return self._from_session(session.status())
        if self.index is None:
            return CheckResult(NOT_OBSERVABLE, "camera.index is not set (CONFIRM). Run: python -m cell_live find-camera")
        try:
            cv2 = self.cv2_loader()
        except ImportError:
            return missing_package("opencv-python", OPENCV_INSTALL)
        with CAMERA_LOCK:
            session = self.session_provider() if self.session_provider is not None else None
            if session is not None:  # a session started while this check waited: never a second reader
                return self._from_session(session.status())
            return self._grab(cv2)

    def _grab(self, cv2: Any) -> CheckResult:
        start_s = time.perf_counter()
        capture = _open(cv2, self.index)
        try:
            if not capture.isOpened():
                return CheckResult(FAIL, f"cannot open camera {self.index}: not connected, wrong index, or held by another program (Choton's script?)")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width_px)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height_px)
            ok, frame = capture.read()
            open_ms = (time.perf_counter() - start_s) * 1000.0
            if not ok or frame is None:
                return CheckResult(FAIL, f"camera {self.index} opened but gave no frame")
            frames_start_s = time.perf_counter()
            grabbed = sum(1 for _ in range(self.sample_frames - 1) if capture.read()[0])
            elapsed_s = time.perf_counter() - frames_start_s
            last_frame_s = time.perf_counter()
        finally:
            capture.release()
        height_px, width_px = frame.shape[:2]
        fps = grabbed / elapsed_s if elapsed_s > 0 else 0.0
        data = {
            "width_px": width_px,
            "height_px": height_px,
            "expected": f"{self.width_px}x{self.height_px}",
            "fps_measured": round(fps, 1),
            "frame_age_s": round(time.perf_counter() - last_frame_s, 3),
        }
        if (width_px, height_px) != (self.width_px, self.height_px):
            return CheckResult(WARN, f"camera {self.index} gives {width_px}x{height_px}, expected {self.width_px}x{self.height_px}", open_ms, data)
        return CheckResult(OK, f"camera {self.index}: {width_px}x{height_px}, {fps:.1f} frames/s", open_ms, data)


    def _from_session(self, status: dict[str, Any]) -> CheckResult:
        """The camera is held by the run's vision session: report what it sees, do not open it."""
        data = {key: status.get(key) for key in ("width_px", "height_px", "fps", "frame_age_s", "camera_error")}
        data["in_use_by_run"] = True
        if status.get("starting"):
            return CheckResult(UNKNOWN, "the vision session is opening the camera (model, warm-up frames): not opened by this check", data=data)
        if not status.get("running"):
            return CheckResult(FAIL, f"vision session stopped: {status.get('camera_error') or 'no frames'}", data=data)
        return CheckResult(OK, f"camera in use by the vision session: {data['width_px']}x{data['height_px']}, "
                               f"{data['fps']} frames/s, last frame {data['frame_age_s']} s ago", data=data)


def find_cameras(max_index: int = 4, cv2_loader: Callable[[], Any] = load_cv2,
                 width_px: int = 1280, height_px: int = 720) -> list[dict[str, Any]]:
    """Which camera indexes open on this computer, and the frame size each gives when asked for
    width_px x height_px, as the camera check asks (lab row 5). Without the request DirectShow gives 640x480."""
    cv2 = cv2_loader()
    found = []
    for index in range(max_index):
        with CAMERA_LOCK:
            capture = _open(cv2, index)
            try:
                if capture.isOpened():
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width_px)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height_px)
                ok, frame = capture.read() if capture.isOpened() else (False, None)
                size = f"{frame.shape[1]}x{frame.shape[0]}" if ok and frame is not None else ""
                found.append({"index": index, "opens": bool(capture.isOpened()), "frame": size})
            finally:
                capture.release()
    return found
