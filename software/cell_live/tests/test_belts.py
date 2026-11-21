"""Belts: DO3 shown as commanded, box restart refused while not set, each restart mode."""

import pytest

from cell_live.control.belts import BoxBeltObserver, BoxRestart, BoxRestartNotSet, ObjectBeltDO3
from cell_live.tests.control_fakes import FakeSession
from cell_sim.interfaces import BeltDriver


def test_object_belt_is_a_belt_driver_and_shows_the_commanded_state():
    session = FakeSession()
    belt = ObjectBeltDO3(session, 3, 1)
    assert isinstance(belt, BeltDriver) and belt.label == "DO3 commanded"
    belt.start()
    assert belt.is_running() and session.outputs[3] == 1
    belt.stop()
    assert not belt.is_running() and session.outputs[3] == 0


def test_object_belt_with_inverted_polarity():
    session = FakeSession(belt_on_value=0)
    belt = ObjectBeltDO3(session, 3, 0)
    belt.start()
    assert session.outputs[3] == 0
    belt.stop()
    assert session.outputs[3] == 1


@pytest.mark.parametrize("mode, channel", [(None, None), ("magic", None), ("dobot_output", None)])
def test_box_restart_refuses_when_not_set(mode, channel):
    with pytest.raises(BoxRestartNotSet):
        BoxRestart(mode, FakeSession(), channel, 0.5)


def test_box_restart_by_dobot_output_switches_its_channel_on_then_off():
    session, waited = FakeSession(), []
    restart = BoxRestart("dobot_output", session, 4, 0.5, sleep=waited.append)
    assert "DO4 on" in restart.begin() and session.outputs[4] == 1
    restart.finish()
    assert session.outputs[4] == 0 and waited == [0.5]


@pytest.mark.parametrize("mode, words", [("nano_auto", "box belt controller"), ("operator", "take the closed box away")])
def test_watch_only_restart_modes_send_nothing(mode, words):
    session = FakeSession()
    restart = BoxRestart(mode, session, None, 0.5)
    assert words in restart.begin()
    restart.finish()
    assert session.calls == []


def test_box_belt_observer_never_commands_and_says_when_it_cannot_see():
    assert BoxBeltObserver().describe(None, [369.6, 17.1])["state"] == "NOT_OBSERVABLE"
    vision = type("Vision", (), {"box_present": lambda self, objects, slot: True})()
    seen = BoxBeltObserver(vision).describe([], [369.6, 17.1])
    assert seen["source"] == "camera" and seen["box_at_robot"] is True
