"""DobotLink: read-only allowlist, held vs unreachable, feedback decoding. Fake sockets only."""

import ast
from pathlib import Path

import pytest

from cell_live.dobot_link import DobotLink, ReadOnlyViolation, RobotHeld, RobotUnreachable
from cell_live.tests.fakes import DOBOT_API, FakeRobot, feedback_bytes

PACKAGE_DIR = Path(__file__).resolve().parents[1]
MOTION_AND_OUTPUT_COMMANDS = (
    "EnableRobot()", "DisableRobot()", "MovJ(1.0,2.0,3.0,4.0)", "MovL(1.0,2.0,3.0,4.0)", "JointMovJ(0,0,0,0)",
    "MoveJog(J1+)", "DO(3,1)", "DOExecute(1,1)", "ToolDO(1,1)", "SpeedFactor(50)", "ClearError()", "ResetRobot()",
)


def _link(robot):
    return DobotLink("192.168.1.6", 29999, 30004, 0.5, load_api=lambda: DOBOT_API, connect=robot.connect)


@pytest.mark.parametrize("command", MOTION_AND_OUTPUT_COMMANDS)
def test_motion_and_output_commands_are_refused_before_any_socket_opens(command):
    robot = FakeRobot()
    link = _link(robot)
    with pytest.raises(ReadOnlyViolation):
        link.query(command)
    with pytest.raises(ReadOnlyViolation):
        link.query_all(("RobotMode()", command))
    assert robot.connects == [] and robot.sent == []


def test_read_only_commands_go_to_the_dashboard_port_only():
    robot = FakeRobot()
    replies = _link(robot).query_all(("RobotMode()", "GetErrorID()", "GetPose()"))
    assert replies["RobotMode()"].text == "0,{4},RobotMode();"
    assert robot.sent == [(29999, "RobotMode()"), (29999, "GetErrorID()"), (29999, "GetPose()")]
    assert all(reply.latency_ms >= 0 for reply in replies.values())


@pytest.mark.parametrize("failure, expected", [
    ("refused", RobotHeld), ("reset", RobotHeld), ("timeout", RobotUnreachable), ("no_route", RobotUnreachable),
])
def test_held_by_another_program_is_told_apart_from_unreachable(failure, expected):
    with pytest.raises(expected) as error:
        _link(FakeRobot(failure=failure)).query("RobotMode()")
    message = str(error.value)
    if expected is RobotHeld:
        assert "another program" in message and "CONFIRM" in message
    else:
        assert "192.168.1.x" in message


def test_a_port_that_connects_but_stays_silent_counts_as_held():
    with pytest.raises(RobotHeld, match="did not answer"):
        _link(FakeRobot(silent=True)).query("RobotMode()")
    with pytest.raises(RobotHeld, match="sent no packet"):
        _link(FakeRobot(silent=True)).read_feedback()


def test_feedback_is_decoded_with_dobot_layout_and_remembered():
    robot = FakeRobot(packet=feedback_bytes(outputs=0b101, inputs=0b10))
    link = _link(robot)
    assert link.packet_age_s() is None
    packet = link.read_feedback()
    assert packet.fields["valid"] and packet.fields["robot_mode"] == 4
    assert packet.fields["pose_xyzr"] == [183.386, 276.015, 151.373, -43.645]
    assert packet.fields["digital_outputs"] == 0b101 and packet.fields["digital_inputs"] == 0b10
    assert link.last_packet is packet and link.packet_age_s() >= 0
    assert robot.connects == [("192.168.1.6", 30004)] and robot.sent == []  # nothing is sent on 30004


def _source_files():
    return [path for path in PACKAGE_DIR.rglob("*.py") if "tests" not in path.parts]


def test_no_motion_or_output_command_appears_in_the_part1_source():
    """The live checks stay read-only. Motion lives only in control/ (behind the gate)."""
    forbidden = ("MovJ", "MovL", "JointMovJ", "MoveJog", "EnableRobot", "SpeedFactor", "DOExecute", "ToolDO", '"DO(', "'DO(")
    for path in [p for p in _source_files() if "control" not in p.parts]:
        text = path.read_text(encoding="utf-8")
        found = [word for word in forbidden if word in text]
        assert found == [], f"{path.name} mentions {found}"
        assert "move_port" not in text or path.name == "live_config.py", f"{path.name} uses the move port"


def test_core_files_use_only_the_standard_library_and_optional_packages_load_lazily():
    import sys

    allowed = set(sys.stdlib_module_names) | {"cell_sim", "cell_live"}
    optional = {"cv2", "ultralytics", "serial", "numpy", "robodk"}
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module-level imports only
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            for name in names:
                assert name.split(".")[0] in allowed, f"{path.name} imports {name} at module level"
        lazy = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))} & optional
        assert path.parent.name == "checks" or not lazy, f"{path.name} imports {lazy}"
