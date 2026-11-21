"""Every check against fakes: what it reports when things work, fail, or cannot be observed."""

import json

import pytest

from cell_live.adapters.choton import AlarmTexts
from cell_live.checks.arduino import ArduinoCheck
from cell_live.checks.calibration import CalibrationCheck
from cell_live.checks.camera import CameraCheck, find_cameras
from cell_live.checks.dobot import DashboardCheck, FeedbackCheck
from cell_live.checks.relay_do3 import OutputStateCheck
from cell_live.checks.robodk import RoboDKCheck
from cell_live.checks.vision import ModelCheck
from cell_live.dobot_link import DobotLink
from cell_live.live_config import load_live_config
from cell_live.status import FAIL, NOT_OBSERVABLE, OK, UNKNOWN, WARN
from cell_live.tests.fakes import (
    DOBOT_API, FakeCapture, FakeRobot, FakeSerialPort, fake_cv2, fake_serial, feedback_bytes,
)

CONFIG = load_live_config()
ALARMS = AlarmTexts(CONFIG.path_value("dobot", "alarm_files_dir"))


def _link(robot, load_api=lambda: DOBOT_API):
    return DobotLink("192.168.1.6", 29999, 30004, 0.5, load_api=load_api, connect=robot.connect)


# Dobot


def test_dashboard_reports_mode_pose_and_no_alarms():
    result = DashboardCheck(_link(FakeRobot()), ALARMS, 2.0).run()
    assert result.state == OK and "4 ROBOT_MODE_DISABLED" in result.detail
    assert result.data["pose_xyzr"] == [183.386215, 276.015349, 151.372986, -43.644684]
    assert result.latency_ms is not None


def test_dashboard_alarm_is_shown_in_words_from_dobot_alarm_list():
    robot = FakeRobot()
    robot.replies["GetErrorID()"] = "0,{[[22],[],[],[],[],[]]},GetErrorID();"
    result = DashboardCheck(_link(robot), ALARMS, 2.0).run()
    assert result.state == WARN and result.data["alarm_ids"][0] == [22]
    assert result.data["alarms"][0].startswith("controller alarm 22: ") and "no text" not in result.data["alarms"][0]


@pytest.mark.parametrize("robot, reason, lead", [
    (FakeRobot(failure="refused"), "held", "Robot is held by another program"),
    (FakeRobot(failure="timeout"), "unreachable", "Robot unreachable"),
])
def test_held_and_unreachable_are_different_messages(robot, reason, lead):
    for check in (DashboardCheck(_link(robot), ALARMS, 2.0), FeedbackCheck(_link(robot), 2.0)):
        result = check.run()
        assert result.state == FAIL and result.data["reason"] == reason and result.detail.startswith(lead)


def test_feedback_reports_pose_bits_and_status():
    result = FeedbackCheck(_link(FakeRobot(packet=feedback_bytes(outputs=0b100))), 2.0).run()
    assert result.state == OK and result.data["digital_outputs_on"] == [3]
    assert result.data["pose_xyzr"] == [183.386, 276.015, 151.373, -43.645]


def test_invalid_feedback_packet_fails_and_missing_numpy_says_how_to_install():
    assert FeedbackCheck(_link(FakeRobot(packet=feedback_bytes(valid=False))), 2.0).run().state == FAIL

    def no_numpy():
        raise ModuleNotFoundError("No module named 'numpy'")

    result = FeedbackCheck(_link(FakeRobot(), load_api=no_numpy), 2.0).run()
    assert result.state == FAIL and "pip install numpy" in result.detail


# Belt outputs: commanded state only


def _do3(link, channel=3):
    return OutputStateCheck("object_belt_do3", "Object belt relay (DO3)", link, channel, 1, 2.0, 6.0, "not set")


def test_do3_is_shown_as_commanded_state_not_as_belt_running():
    link = _link(FakeRobot(packet=feedback_bytes(outputs=0b100)))
    assert _do3(link).run().state == UNKNOWN  # no packet read yet
    link.read_feedback()
    result = _do3(link).run()
    assert result.state == OK and result.data["commanded_level"] == 1
    assert "commanded ON" in result.detail and "not proof that the belt runs" in result.detail


def test_unset_box_belt_output_is_not_observable():
    assert _do3(_link(FakeRobot()), channel=None).run().state == NOT_OBSERVABLE


def test_do3_is_not_observable_while_the_robot_feedback_cannot_be_read():
    robot = FakeRobot(failure="timeout")
    link = _link(robot)
    assert FeedbackCheck(link, 2.0).run().state == FAIL
    result = _do3(link).run()
    assert result.state == NOT_OBSERVABLE and "robot feedback not readable" in result.detail
    assert "no answer from 192.168.1.6:30004" in result.detail
    assert robot.connects == [("192.168.1.6", 30004)]  # the DO3 check itself opened nothing


def test_a_failed_read_after_a_good_packet_hides_the_old_state():
    robot = FakeRobot(packet=feedback_bytes(outputs=0b100))
    link = _link(robot)
    link.read_feedback()
    assert _do3(link).run().state == OK
    robot.failure = "no_route"  # cable pulled: the old packet is still fresh
    assert FeedbackCheck(link, 2.0).run().state == FAIL
    assert _do3(link).run().state == NOT_OBSERVABLE
    robot.failure, robot.packet = None, feedback_bytes(outputs=0)  # cable back
    assert FeedbackCheck(link, 2.0).run().state == OK
    result = _do3(link).run()
    assert result.state == OK and result.data["commanded_level"] == 0


def test_an_invalid_packet_never_becomes_the_robot_state():
    link = _link(FakeRobot(packet=feedback_bytes(valid=False, outputs=0b100)))
    assert FeedbackCheck(link, 2.0).run().state == FAIL
    assert link.last_packet is None
    result = _do3(link).run()
    assert result.state == NOT_OBSERVABLE and "invalid packet" in result.detail


# Camera


def test_camera_without_index_is_not_observable_and_missing_opencv_says_how_to_install():
    assert CameraCheck(None, 1280, 720, 5, 10.0).run().state == NOT_OBSERVABLE

    def no_cv2():
        raise ImportError("No module named 'cv2'")

    result = CameraCheck(0, 1280, 720, 5, 10.0, cv2_loader=no_cv2).run()
    assert result.state == FAIL and "pip install opencv-python" in result.detail


def test_camera_reports_size_and_fps_and_releases_the_device():
    capture = FakeCapture()
    result = CameraCheck(0, 1280, 720, 5, 10.0, cv2_loader=lambda: fake_cv2(capture)).run()
    assert result.state == OK and result.data["width_px"] == 1280 and capture.released
    assert result.data["fps_measured"] >= 0
    wrong = CameraCheck(0, 1280, 720, 5, 10.0, cv2_loader=lambda: fake_cv2(FakeCapture(size=(480, 640)))).run()
    assert wrong.state == WARN
    closed = CameraCheck(0, 1280, 720, 5, 10.0, cv2_loader=lambda: fake_cv2(FakeCapture(opens=False))).run()
    assert closed.state == FAIL and "held by another program" in closed.detail
    assert find_cameras(2, cv2_loader=lambda: fake_cv2(FakeCapture()))[0] == {"index": 0, "opens": True, "frame": "1280x720"}


# Vision model


def test_model_check(tmp_path):
    model_file = tmp_path / "best.pt"
    assert ModelCheck(model_file, ["card"], 0.45, 300.0).run().state == FAIL  # file missing
    model_file.write_bytes(b"weights")

    def no_ultralytics(path):
        raise ImportError("No module named 'ultralytics'")

    result = ModelCheck(model_file, ["card"], 0.45, 300.0, loader=no_ultralytics).run()
    assert result.state == FAIL and "pip install ultralytics" in result.detail
    model = type("Model", (), {"names": {0: "card", 1: "candy", 2: "box", 3: "lid"}})()
    good = ModelCheck(model_file, ["card", "candy", "box", "lid"], 0.45, 300.0, loader=lambda path: model).run()
    assert good.state == OK and good.data["classes"] == ["card", "candy", "box", "lid"]
    assert ModelCheck(model_file, ["card"], 0.45, 300.0, loader=lambda path: model).run().state == WARN


# Calibration, RoboDK, Arduino


def test_calibration_file_from_choton_reads(tmp_path):
    result = CalibrationCheck(CONFIG.path_value("calibration", "file"), 60.0).run()
    assert result.state == OK and result.data["points"] == 5
    broken = tmp_path / "homography.json"
    broken.write_text("{", encoding="utf-8")
    assert CalibrationCheck(broken, 60.0).run().state == FAIL
    broken.write_text(json.dumps({"H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "practice": True}), encoding="utf-8")
    assert CalibrationCheck(broken, 60.0).run().state == WARN


def test_robodk_check():
    def refuse(address, timeout=None):
        raise ConnectionRefusedError("refused")

    assert RoboDKCheck("localhost", 20500, 10.0, connect=refuse).run().state == FAIL
    assert RoboDKCheck("localhost", 20500, 10.0, connect=FakeRobot().connect).run().state == OK


def test_arduino_check():
    assert ArduinoCheck(None, None, None, 5.0).run().state == NOT_OBSERVABLE
    assert ArduinoCheck("COM5", None, None, 5.0).run().state == NOT_OBSERVABLE

    def no_pyserial():
        raise ImportError("No module named 'serial'")

    assert "pip install pyserial" in ArduinoCheck("COM5", 9600, None, 5.0, serial_loader=no_pyserial).run().detail
    port = FakeSerialPort()
    only_opens = ArduinoCheck("COM5", 9600, None, 5.0, serial_loader=lambda: fake_serial(port)).run()
    assert only_opens.state == WARN and port.written == [] and port.closed
    answered = ArduinoCheck("COM5", 9600, "STATUS", 5.0, serial_loader=lambda: fake_serial(FakeSerialPort())).run()
    assert answered.state == OK and answered.data["reply"] == "S1=1 BELT=0"
    busy = ArduinoCheck("COM5", 9600, "STATUS", 5.0, serial_loader=lambda: fake_serial(error=OSError("access denied"))).run()
    assert busy.state == FAIL
