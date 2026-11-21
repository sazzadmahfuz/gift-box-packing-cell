"""Live check acceptance: hardware absent -> FAIL or NOT_OBSERVABLE; one socket owner."""

import ast
from pathlib import Path

from cell_live.checks import build_checks
from cell_live.dobot_link import DobotLink
from cell_live.live_config import load_live_config
from cell_live.poller import Poller
from cell_live.status import FAIL, NOT_OBSERVABLE
from cell_live.tests.fakes import DOBOT_API, FakeCapture, FakeRobot, fake_cv2

PACKAGE_DIR = Path(__file__).resolve().parents[1]
HARDWARE_COMPONENTS = ("dobot_dashboard", "dobot_feedback", "object_belt_do3", "object_belt_dir", "object_belt_power",
                       "camera", "robodk", "box_belt_nano")
SOCKET_CALLS = {"create_connection", "socket", "connect", "_connect", "connect_ex", "socketpair"}
SOCKET_OWNERS = {"dobot_link.py", "robodk.py"}  # robodk.py: RoboDK on this PC, never the robot


def _no_robodk(address, timeout=None):
    raise ConnectionRefusedError(10061, "refused")


def test_with_the_hardware_absent_every_hardware_component_is_fail_or_not_observable():
    config = load_live_config()
    robot = FakeRobot(failure="timeout")  # robot powered off or cable out
    link = DobotLink(config.value("dobot", "ip"), 29999, 30004, 0.5, load_api=lambda: DOBOT_API, connect=robot.connect)
    checks = build_checks(config, link)
    next(check for check in checks if check.id == "robodk").connect = _no_robodk  # RoboDK closed
    next(check for check in checks if check.id == "camera").cv2_loader = lambda: fake_cv2(FakeCapture(opens=False))  # unplugged
    poller = Poller(checks)
    for component_id in poller.checks:  # the same order as python -m cell_live --once
        poller.check_now(component_id)
    statuses = {status["id"]: status for status in poller.snapshot()}
    for component_id in HARDWARE_COMPONENTS:
        status = statuses[component_id]
        assert status["state"] in (FAIL, NOT_OBSERVABLE), f"{component_id}: {status['state']} {status['detail']}"
        assert status["detail"] and status["last_ok_at"] is None and status["latency_ms"] is None
    assert statuses["dobot_dashboard"]["data"]["reason"] == "unreachable"
    assert all(address[1] in (29999, 30004) for address in robot.connects)  # never the move port 30003


def test_only_dobot_link_opens_robot_sockets():
    owners_seen = set()
    for path in PACKAGE_DIR.rglob("*.py"):
        if "tests" in path.parts:
            continue
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.Call)
        }
        opened = calls & SOCKET_CALLS
        assert not opened or path.name in SOCKET_OWNERS, f"{path.name} opens sockets: {opened}"
        if opened:
            owners_seen.add(path.name)
    assert owners_seen == SOCKET_OWNERS  # the scan really finds the socket calls it guards


def test_the_robodk_check_points_at_robodk_not_at_the_robot():
    config = load_live_config()
    robodk = next(check for check in build_checks(config) if check.id == "robodk")
    assert (robodk.host, robodk.port) == (config.value("robodk", "host"), config.value("robodk", "port"))
    assert robodk.host != config.value("dobot", "ip")
