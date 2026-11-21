"""The stop that works with no run active: only output-off commands, never motion (17 Nov: the belt kept running)."""

import socket

from cell_live.control.idle_stop import BOX_BELT_NOTE, outputs_off
from cell_live.dobot_link import DobotLink
from cell_live.tests.control_fakes import CONFIG, FakeNet
from cell_live.tests.test_gate import config_with
from cell_live.tests.test_runlog_and_api import service

DASHBOARD = 29999


def _link(net):
    return DobotLink("192.168.1.6", DASHBOARD, 30004, 0.5, connect=net.connect)


def test_software_stop_with_no_run_switches_the_belt_and_the_gripper_off_and_nothing_else():
    net = FakeNet()
    config = config_with(dobot__belt_on_value=0, dobot__belt_enable_on_value=0)  # 17 Nov: 0 runs the belt, 0 enables it
    result = outputs_off(_link(net), config)
    assert net.commands(DASHBOARD) == ["DOExecute(3,1)", "DOExecute(16,1)", "DOExecute(1,0)", "DOExecute(2,0)"]
    assert result["ok"] and result["note"] == BOX_BELT_NOTE and all(connection.closed for connection in net.connections)


def test_the_belt_stop_switches_only_the_object_belt():
    net = FakeNet()
    result = outputs_off(_link(net), config_with(dobot__belt_on_value=1, dobot__belt_enable_on_value=1), belt_only=True)
    assert net.commands(DASHBOARD) == ["DOExecute(3,0)", "DOExecute(16,0)"] and result["ok"]


def test_a_level_that_is_not_confirmed_is_not_used():
    net = FakeNet()
    result = outputs_off(_link(net), CONFIG, belt_only=True)  # the levels as before the lab: null, CONFIRM
    assert net.commands(DASHBOARD) == [] and not result["ok"]
    assert any("belt_on_value" in problem for problem in result["problems"])


def test_while_a_run_holds_the_robot_nothing_is_sent():
    net = FakeNet()
    link = _link(net)
    link.control_session = object()
    result = outputs_off(link, config_with())
    assert net.connections == [] and not result["ok"] and "a run holds the robot" in result["problems"][0]


def test_a_refused_output_and_an_absent_robot_are_reported_not_raised():
    net = FakeNet()
    net.replies["DOExecute"] = "-1,{},DOExecute();"
    refused = outputs_off(_link(net), config_with(), belt_only=True)
    assert not refused["ok"] and "refused by the robot" in refused["problems"][0]

    def absent(address, timeout=None):
        raise socket.timeout("timed out")

    gone = outputs_off(DobotLink("192.168.1.6", DASHBOARD, 30004, 0.5, connect=absent), config_with())
    assert not gone["ok"] and "robot not reached" in gone["problems"][0]


def test_the_service_uses_it_when_no_run_is_active(tmp_path):
    net = FakeNet()
    run = service(tmp_path, config=config_with(dobot__belt_on_value=0, dobot__belt_enable_on_value=0))
    run.link = _link(net)
    estop = run.estop()
    assert estop["ok"] and "software stop with no run active: DO3 = 1 (object belt stopped)" in estop["message"]
    belt = run.belt_stop()
    assert belt["ok"] and "box belt is not stopped by software" in belt["message"]
    assert net.commands(DASHBOARD)[-2:] == ["DOExecute(3,1)", "DOExecute(16,1)"]


def test_the_idle_stop_source_sends_no_motion():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "control" / "idle_stop.py").read_text(encoding="utf-8")
    assert not [word for word in ("MovL", "MovJ", "EnableRobot", "EmergencyStop(", "SpeedFactor", '"DO(') if word in text]
