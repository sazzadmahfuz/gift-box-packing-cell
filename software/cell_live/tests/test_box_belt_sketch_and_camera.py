"""Rashmika's box belt sketch and the stand camera, as found on 17 Nov."""

from pathlib import Path

from cell_live.checks.arduino import ArduinoCheck
from cell_live.checks.camera import find_cameras
from cell_live.checks.ports import camera_ports
from cell_live.live_config import load_live_config
from cell_live.status import NOT_OBSERVABLE
from cell_live.tests.fakes import FakeCapture, fake_cv2

CONFIG = load_live_config()
SKETCH = "notebooks/week-03/Rashmika/ArduinoCode/ArduinoCode.ino"
REPO = Path(__file__).resolve().parents[3]


def test_the_sensor_level_comes_from_the_sketch():
    assert CONFIG.value("arduino", "sensor_active_level") == 0
    assert CONFIG.status("arduino", "sensor_active_level") == "VERIFIED"
    assert SKETCH in CONFIG.entry("arduino", "sensor_active_level")["source"]
    assert (REPO / SKETCH).is_file()


def test_the_sketch_sends_nothing_over_usb_so_the_port_stays_unused():
    for key in ("serial_port", "baud", "status_command"):
        entry = CONFIG.entry("arduino", key)
        assert entry["value"] is None and entry["status"] == "SETTING" and "sends nothing over USB" in entry["source"]
    result = ArduinoCheck(None, None, None, 2.0, 1.0).run()
    assert result.state == NOT_OBSERVABLE and "sends no status" in result.detail


def test_the_camera_is_the_usb_camera_on_the_stand():
    assert CONFIG.value("camera", "index") == 1 and CONFIG.status("camera", "index") == "VERIFIED"
    assert "17 Nov" in CONFIG.entry("camera", "index")["source"]  # test pictures 17 Nov: index 0 is the laptop webcam


def test_the_camera_scan_asks_for_the_configured_size():
    capture = FakeCapture()
    find_cameras(1, cv2_loader=lambda: fake_cv2(capture), width_px=1920, height_px=1080)
    assert capture.settings == {3: 1920, 4: 1080}  # CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT


def test_the_camera_scan_does_not_set_a_size_on_a_camera_that_did_not_open():
    capture = FakeCapture(opens=False)
    assert find_cameras(1, cv2_loader=lambda: fake_cv2(capture)) == [{"index": 0, "opens": False, "frame": ""}]
    assert capture.settings == {}


def test_the_ports_scan_passes_the_size_on():
    asked = []
    camera_ports(None, finder=lambda **size: asked.append(size) or [], size_px=(1280, 720))
    assert asked == [{"width_px": 1280, "height_px": 720}]
