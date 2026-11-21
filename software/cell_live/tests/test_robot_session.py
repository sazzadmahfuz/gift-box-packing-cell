"""Choton's real robot_lib over our controlled connections, against a fake robot network."""

import sys
import threading
import time

import pytest

from cell_live.control.robot_client import ControlConnectionLost, ControlRefused
from cell_live.adapters.choton import AlarmTexts
from cell_live.checks.dobot import DashboardCheck
from cell_live.control.robot_session import RobotSession, SessionError, SessionValues
from cell_live.dobot_link import DobotLink, FeedbackPacket
from cell_live.tests.control_fakes import CHOTON, CONFIG, FakeNet, choton_settings, wait_for
from cell_live.tests.fakes import DOBOT_API

DASHBOARD, MOVE = 29999, 30003
VALUES = SessionValues(speed_percent=40, vacuum_do=1, blow_do=2, belt_do=3, belt_on_value=1, belt_dir_do=4,
                       belt_dir_forward_value=1, belt_enable_do=16, belt_enable_on_value=1, box_belt_do=None,
                       reach_min_mm=150, reach_max_mm=375, move_port=MOVE, reply_timeout_s=0.5)
START_LEVELS = ["DO(3,0)", "DO(4,1)", "DO(16,1)"]  # object belt stopped, forward, enabled (test values)
SLOT = [369.6, 17.1]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(CHOTON.robot_lib.time, "sleep", lambda seconds: None)  # robot_lib's pauses


def _session(net, values=VALUES, settings=None):
    link = DobotLink(CONFIG.value("dobot", "ip"), DASHBOARD, 30004, 0.5, connect=net.connect)
    session = RobotSession(link, CHOTON, settings or choton_settings(), values, lambda port, c, r: None, lambda: DOBOT_API)
    return session, link


def test_open_runs_chotons_enable_sequence_over_our_sockets():
    net = FakeNet()
    session, link = _session(net)
    session.open()
    assert net.commands(DASHBOARD) == ["ClearError()", "EnableRobot()", "SpeedFactor(40)", "SetArmOrientation(0)", *START_LEVELS]
    assert net.commands(MOVE) == []  # no move at the start
    assert link.control_session is session and "dobot_api" not in sys.modules  # stand-in removed again
    reports = session.close()
    assert reports[:4] == ["DO3 = 0 (DOExecute)", "DO16 = 0 (DOExecute)", "DO1 = 0 (DOExecute)", "DO2 = 0 (DOExecute)"]
    assert net.commands(DASHBOARD)[-1] == "DisableRobot()" and link.control_session is None
    assert all(connection.closed for connection in net.connections)


def test_pick_and_place_sends_only_movl_and_the_expected_outputs():
    net = FakeNet()
    session, _ = _session(net)
    session.open()
    session.pick_and_place(250.0, 0.0, SLOT, "red card", "card", 0.0)
    moves = net.commands(MOVE)
    assert moves and all(c.startswith(("MovL(", "Sync(")) for c in moves) and not any("MovJ" in c for c in moves)
    assert moves[0] == "MovL(369.600000,17.100000,104.700000,-73.800000)"  # via the box slot at travel height (17 Nov)
    assert moves[1] == "MovL(250.000000,0.000000,104.700000,-73.800000)"  # above the item, Choton's r_angle
    assert "MovL(250.000000,0.000000,63.700000,-73.800000)" in moves  # card pick height
    outputs = [c for c in net.commands(DASHBOARD) if c.startswith("DO(")]
    assert outputs == [*START_LEVELS, "DO(1,1)", "DO(1,0)", "DO(2,1)", "DO(2,0)"]  # then suction on, off, blow-off pulse


@pytest.mark.parametrize("call, words", [
    (lambda s: s.robot.move.MovJ(250.0, 0.0, 104.7, 0.0), "MovJ is not allowed"),
    (lambda s: s.robot.move.MoveJog("X+"), "MoveJog is not allowed"),
    (lambda s: s.robot.dash.DO(5, 1), "DO5 is not one of the cell outputs"),
    (lambda s: s.robot.dash.SpeedFactor(90), "armed speed is 40 %"),
    (lambda s: s.pick_and_place(390.0, 0.0, SLOT, "card", "card", 0.0), "allowed 150-375 mm"),
    (lambda s: s.robot.movl(250.0, 0.0, 10.0), "below the lowest taught height"),
])
def test_the_run_allowlist_refuses_before_sending(call, words):
    net = FakeNet()
    session, _ = _session(net)
    session.open()
    sent_before = len(net.sent)
    with pytest.raises(ControlRefused, match=words):
        call(session)
    assert len(net.sent) == sent_before


def test_a_sync_without_reply_raises_instead_of_carrying_on():
    net = FakeNet()
    net.silent.add("Sync")
    session, _ = _session(net)
    session.open()
    with pytest.raises(ControlConnectionLost, match="no reply to Sync"):
        session.home()


def test_after_a_sync_without_reply_the_alarm_is_read_only_when_fresh_feedback_shows_an_error():
    # 17 Nov: alarm 23 stopped the first pick move; Sync() never answered and the fault said "connection lost"
    net = FakeNet()
    net.silent.add("Sync")
    net.replies["GetErrorID"] = "0,{[[23],[],[],[],[],[]]},GetErrorID();"
    session, link = _session(net)
    session.open()
    with pytest.raises(ControlConnectionLost):
        session.home()
    assert session.alarm_that_stopped_a_move() == "" and "GetErrorID()" not in net.commands(DASHBOARD)  # no packet yet
    link.last_packet = FeedbackPacket({"error_status": 0}, time.monotonic(), 1.0)
    assert session.alarm_that_stopped_a_move() == "" and "GetErrorID()" not in net.commands(DASHBOARD)
    link.last_packet = FeedbackPacket({"error_status": 1}, time.monotonic() - 30.0, 1.0)  # old: the robot may be gone
    assert session.alarm_that_stopped_a_move() == ""
    link.last_packet = FeedbackPacket({"error_status": 1}, time.monotonic(), 1.0)
    assert session.alarm_that_stopped_a_move() == "controller 23: Plan point during linear motion out of working area"


def test_software_estop_goes_out_while_a_move_is_still_running():
    net = FakeNet()
    net.blocked["Sync"] = threading.Event()  # the robot is still moving
    session, _ = _session(net, values=SessionValues(**{**VALUES.__dict__, "reply_timeout_s": 5.0}))
    session.open()
    errors = []

    def move_home():
        try:
            session.home()
        except Exception as error:
            errors.append(error)

    mover = threading.Thread(target=move_home)
    mover.start()
    wait_for(lambda: "Sync()" in net.commands(MOVE))
    reports = session.software_estop()
    assert mover.is_alive() or errors  # the e-stop did not wait for the move
    after = net.commands(DASHBOARD)[-5:]
    assert after == ["DOExecute(3,0)", "DOExecute(16,0)", "DOExecute(1,0)", "DOExecute(2,0)", "EmergencyStop()"]
    assert reports[-1].startswith("EmergencyStop() sent")
    mover.join(2.0)
    assert errors and isinstance(errors[0], ControlConnectionLost)  # the waiting Sync ended
    with pytest.raises(ControlRefused, match="only switching outputs off is allowed after the software e-stop"):
        session.robot.dash.DO(3, 1)
    with pytest.raises(ControlRefused, match="software e-stop is active"):
        session.robot.movl(250.0, 0.0, 104.7)
    assert "ClearError sent" in session.clear_alarm()


def test_doexecute_refused_falls_back_to_queued_do():
    net = FakeNet()
    session, _ = _session(net)
    session.open()
    net.replies["DOExecute"] = "-1,{},DOExecute();"
    sent_before = len(net.commands(DASHBOARD))
    reports = session.outputs_off()
    assert reports[0] == "DO3 = 0 (DOExecute refused, queued DO used)"
    assert "DO(3,0)" in net.commands(DASHBOARD)[sent_before:]


def test_lost_connection_says_to_use_the_physical_emergency_stop():
    net = FakeNet()
    session, _ = _session(net)
    session.open()
    net.close_all()
    reports = session.outputs_off()
    assert all("NOT switched off" in line and "physical emergency stop" in line for line in reports)
    assert "not switched off" in session.problem


def test_inverted_belt_polarity_switches_the_belt_off_with_1():
    values = SessionValues(**{**VALUES.__dict__, "belt_on_value": 0})
    assert values.off_levels() == {3: 1, 16: 0, 1: 0, 2: 0}


def test_the_dashboard_check_does_not_connect_while_the_session_starts():
    # 17 Nov: the check opened its own 29999 during EnableRobot(); the robot keeps one client and closed the run's
    net, enable_reply = FakeNet(), threading.Event()
    net.blocked["EnableRobot"] = enable_reply
    session, link = _session(net)
    opening = threading.Thread(target=session.open)
    opening.start()
    wait_for(lambda: "EnableRobot()" in net.commands(DASHBOARD))
    connections_before = len(net.connections)
    result = DashboardCheck(link, AlarmTexts(None), 2.0).run()
    assert link.control_session is session and result.data == {"in_use_by_run": True}
    assert len(net.connections) == connections_before  # no second client on 29999
    enable_reply.set()
    opening.join(2.0)
    assert net.commands(DASHBOARD)[:4] == ["ClearError()", "EnableRobot()", "SpeedFactor(40)", "SetArmOrientation(0)"]
    session.close()


def test_enable_refused_gives_a_session_error_and_closes_the_sockets():
    net = FakeNet()
    net.replies["EnableRobot"] = "-1,{},EnableRobot();"
    session, link = _session(net)
    with pytest.raises(SessionError, match="EnableRobot refused"):
        session.open()
    assert link.control_session is None and all(connection.closed for connection in net.connections)


def test_a_different_robot_ip_in_chotons_settings_is_refused():
    settings = choton_settings()
    settings["robot"]["ip"] = "192.168.1.99"
    session, _ = _session(FakeNet(), settings=settings)
    with pytest.raises(SessionError, match="the configured robot is"):
        session.open()
