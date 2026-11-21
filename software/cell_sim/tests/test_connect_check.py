"""connect-check against a fake Dobot on 127.0.0.1. No robot needed."""

import dataclasses
import socket

import pytest

from cell_sim.__main__ import main
from cell_sim.drivers.dobot_connect_check import ReadOnlyViolation, connect_check, guard_read_only
from cell_sim.drivers.dobot_tcp_robot import dry_client, load_dobot_api
from cell_sim.hardware_config import dobot_settings, load_hardware_raw
from cell_sim.tests.fake_dobot_server import DASHBOARD_PORT, FEEDBACK_PORT, HOST, FakeDobot, feedback_packet

SETTINGS = dataclasses.replace(dobot_settings(load_hardware_raw()), robot_ip=HOST, connect_timeout_s=2.0)
API = load_dobot_api(SETTINGS.api_path)


def _start_fake(**packet):
    try:
        return FakeDobot(feedback_packet(API, **packet))
    except OSError:
        pytest.skip(f"port {DASHBOARD_PORT} or {FEEDBACK_PORT} is busy on this PC")


@pytest.fixture
def fake():
    server = _start_fake()
    yield server
    server.close()


def _run(settings=SETTINGS):
    lines = []
    code = connect_check(settings, API, say=lines.append)
    return code, "\n".join(lines)


def test_sends_only_the_three_read_only_commands(fake):
    code, output = _run()
    assert code == 0
    assert fake.commands == ["GetErrorID()", "RobotMode()", "GetPose()"]
    assert "5 ROBOT_MODE_ENABLE" in output
    assert "x=366.211 y=122.182 z=124.262 mm r=-7.66 deg" in output
    assert "no errors" in output and "EnableStatus=1, ErrorStatus=0" in output
    assert output.endswith("connections closed")


def test_robot_error_gives_exit_4(fake):
    fake.replies["GetErrorID()"] = "0,{[[22],[],[],[],[],[]]},GetErrorID();"
    code, output = _run()
    assert code == 4 and "errors [22]" in output


def test_invalid_feedback_packet_is_reported():
    server = _start_fake(valid=False)
    try:
        code, output = _run()
    finally:
        server.close()
    assert code == 4 and "invalid packet" in output


def test_output_and_input_bits_and_vacuum_state_are_read():
    server = _start_fake(outputs=0b101, inputs=0b10)  # DO1 and DO3 on, DI2 on
    try:
        code, output = _run()
    finally:
        server.close()
    assert code == 0
    assert "digital outputs: 0x5, ON: [1, 3]" in output and "digital inputs: 0x2, ON: [2]" in output
    assert "vacuum output DO1 (hardware.json, ASSUMED channel) reads ON" in output
    assert server.commands == ["GetErrorID()", "RobotMode()", "GetPose()"]  # still read-only


def test_allowlist_blocks_enable_before_anything_is_sent():
    dashboard = dry_client(API.DobotApiDashboard, HOST, DASHBOARD_PORT)
    guard_read_only(dashboard)
    for command in (dashboard.EnableRobot, lambda: dashboard.DO(1, 1), lambda: dashboard.SpeedFactor(20)):
        with pytest.raises(ReadOnlyViolation):
            command()
    assert dashboard.socket_dobot.sent == []
    dashboard.RobotMode()
    assert dashboard.socket_dobot.sent == ["RobotMode()"]


def test_unreachable_robot_exits_3_with_a_hint():
    with socket.socket() as probe:
        if probe.connect_ex((HOST, DASHBOARD_PORT)) == 0:
            pytest.skip("something listens on 29999 on this PC")
    code, output = _run(dataclasses.replace(SETTINGS, connect_timeout_s=0.3))
    assert code == 3 and "cannot connect" in output and "192.168.1.x" in output


def test_cli_connect_check_uses_the_ip_option(fake, capsys):
    assert main(["connect-check", "--ip", HOST, "--timeout-s", "2"]) == 0
    output = capsys.readouterr().out
    assert f"robot {HOST}" in output and "ROBOT_MODE_ENABLE" in output
    assert fake.commands == ["GetErrorID()", "RobotMode()", "GetPose()"]
