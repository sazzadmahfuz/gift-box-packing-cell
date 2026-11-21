"""The camera has one reader at a time: the vision session, or the camera check, never both."""

import threading

from cell_live.checks.camera import CAMERA_LOCK, CameraCheck
from cell_live.control.vision_service import VisionService
from cell_live.control.vision_session import VisionSession
from cell_live.status import FAIL, UNKNOWN
from cell_live.tests.baseline import CONFIG


class Source:
    def __init__(self, frames=0):
        self.frames, self.released = frames, False

    def read(self):
        if self.frames <= 0:
            raise RuntimeError("Camera returned no frame (cable unplugged / Wi-Fi lost?)")
        self.frames -= 1
        return object()

    def release(self):
        self.released = True


def _session(source):
    choton = type("Choton", (), {"vision_lib": type("VL", (), {"load_homography": staticmethod(lambda: None)})})
    return VisionSession(choton, {"camera_index": 0}, 1, 0.5, make_source=lambda s: source, load_model=lambda s: object())


def _no_open():
    raise AssertionError("the camera check must not open the camera while the vision session holds it")


def test_a_lost_camera_is_released_at_once():
    source = Source(frames=3)
    session = _session(source)
    session.start()
    for _ in range(100):
        if source.released:
            break
        threading.Event().wait(0.01)
    assert source.released and not session.status()["running"] and "camera lost" in session.status()["camera_error"]


def test_the_camera_check_does_not_open_the_camera_while_the_session_is_opening_it():
    # 17 Nov: the check opened camera 1 during the session's warm-up; one of the two readers then got no frames
    opened, release = threading.Event(), threading.Event()

    def slow_session(*args):
        opened.set()
        release.wait(2.0)
        return _session(Source(frames=1000))

    service = VisionService(CONFIG, load_choton=lambda folder: None, make_vision=slow_session)
    service.choton, check = object(), CameraCheck(1, 1280, 720, 5, 10.0, cv2_loader=_no_open, session_provider=service.camera_holder)
    starting = threading.Thread(target=service.ensure_started, kwargs={"choton": object(), "settings": {"camera_index": 0}})
    starting.start()
    opened.wait(2.0)
    result = check.run()
    assert result.state == UNKNOWN and "opening the camera" in result.detail
    release.set()
    starting.join(2.0)
    service.stop()


def test_a_stopped_session_is_reported_and_never_reopened_by_the_check():
    service = VisionService(CONFIG, load_choton=lambda folder: None)
    service.session = _session(Source())
    result = CameraCheck(1, 1280, 720, 5, 10.0, cv2_loader=_no_open, session_provider=service.camera_holder).run()
    assert result.state == FAIL and "vision session stopped" in result.detail


class _SlowCamera:
    """cv2 stand-in for the camera check: its first frame waits for `release`; the order is recorded."""

    CAP_PROP_FRAME_WIDTH = CAP_PROP_FRAME_HEIGHT = 0

    def __init__(self, reading, release, order):
        self.reading, self.release_frame, self.order = reading, release, order

    def VideoCapture(self, index, backend=0):  # noqa: N802 (cv2's name)
        camera = self

        class Capture:
            def isOpened(self):  # noqa: N802
                return True

            def set(self, *args):
                pass

            def read(self):
                camera.reading.set()
                camera.release_frame.wait(2.0)
                return True, type("Frame", (), {"shape": (720, 1280, 3)})()

            def release(self):
                camera.order.append("check let go")

        return Capture()


def test_a_session_waits_until_the_camera_check_has_let_go_of_the_camera():
    # 17 Nov, at start-up: the poller's first camera check had camera 1 open (4.2 frames/s) when the
    # vision session opened it too, and the session lost the camera ("Camera returned no frame")
    reading, release, order = threading.Event(), threading.Event(), []
    check = CameraCheck(1, 1280, 720, 2, 10.0, cv2_loader=lambda: _SlowCamera(reading, release, order), session_provider=lambda: None)
    checking = threading.Thread(target=check.run)
    checking.start()
    assert reading.wait(2.0)  # the check has the camera open
    source = Source(frames=10**9)
    choton = type("Choton", (), {"vision_lib": type("VL", (), {"load_homography": staticmethod(lambda: None)})})
    session = VisionSession(choton, {"camera_index": 1}, 1, 0.5, make_source=lambda s: (order.append("session opened"), source)[1],
                            load_model=lambda s: object())
    opening = threading.Thread(target=session.start)
    opening.start()
    threading.Event().wait(0.05)
    assert order == []  # the session waits for the camera
    release.set()
    checking.join(2.0), opening.join(2.0)
    assert order == ["check let go", "session opened"]
    session.stop()


def test_start_async_marks_the_camera_busy_before_its_thread_runs():
    # with start_async first in LiveApp.start, the poller's first camera check finds the session opening
    release = threading.Event()

    def slow_session(*args):
        release.wait(2.0)
        return _session(Source(frames=10**9))

    vision_lib = type("VL", (), {"load_settings": staticmethod(lambda: {"camera_index": 1})})
    service = VisionService(CONFIG, load_choton=lambda folder: type("Choton", (), {"vision_lib": vision_lib}), make_vision=slow_session)
    assert service.start_async()["ok"]
    check = CameraCheck(1, 1280, 720, 5, 10.0, cv2_loader=_no_open, session_provider=service.camera_holder)
    assert check.run().state == UNKNOWN  # straight after start_async: the check leaves the camera alone
    release.set()
    for _ in range(200):
        if service.session is not None and not service.starting:
            break
        threading.Event().wait(0.01)
    assert service.session.status()["running"] and check.run().detail.startswith("camera in use by the vision session")
    service.stop()


def test_a_check_waiting_for_the_camera_lock_never_opens_the_camera_a_session_opened():
    session, published, results = _session(Source(frames=10**9)), {}, []
    session.start()
    check = CameraCheck(1, 1280, 720, 5, 10.0, cv2_loader=lambda: object(), session_provider=lambda: published.get("session"))
    with CAMERA_LOCK:  # a session is opening the camera right now
        waiting = threading.Thread(target=lambda: results.append(check.run()))
        waiting.start()
        threading.Event().wait(0.05)
        published["session"] = session
    waiting.join(2.0)
    assert results and results[0].detail.startswith("camera in use by the vision session")  # an open would have raised
    session.stop()


def test_a_new_start_stops_the_old_session_first():
    old_source = Source(frames=10**9)
    service = VisionService(CONFIG, load_choton=lambda folder: None, make_vision=lambda *args: _session(Source(frames=10**9)))
    service.session = _session(old_source)
    service.session.start()
    service.session._running = False  # stopped without letting go of the camera (the case before the fix)
    service.ensure_started(choton=object(), settings={"camera_index": 0})
    assert old_source.released and service.session.status()["running"]
    service.stop()
