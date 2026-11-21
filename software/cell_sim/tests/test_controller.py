import pytest

from cell_sim.controller import TRANSITIONS, IllegalTransition, State, StateMachine
from cell_sim.events import EventKind, EventQueue

SPEC_TRANSITIONS = {  # Choton's cycle, team-confirmed 2026-11-16
    (State.INIT, State.READY),
    (State.READY, State.WAIT_BOX),
    (State.WAIT_BOX, State.FEED_SET),
    (State.FEED_SET, State.DETECT),
    (State.DETECT, State.PICK),
    (State.PICK, State.PLACE),
    (State.PLACE, State.PICK),
    (State.PLACE, State.CLOSE_LID),
    (State.CLOSE_LID, State.RELEASE_BOX),
    (State.RELEASE_BOX, State.CYCLE_DONE),
    (State.CYCLE_DONE, State.READY),
}


def test_transition_table_matches_spec_plus_fault():
    allowed = {(src, dst) for src, targets in TRANSITIONS.items() for dst in targets}
    fault_moves = {(state, State.FAULT) for state in State if state is not State.FAULT}
    assert allowed == SPEC_TRANSITIONS | fault_moves
    assert TRANSITIONS[State.FAULT] == frozenset()


def test_illegal_transition_raises():
    machine = StateMachine(EventQueue(), {})
    with pytest.raises(IllegalTransition):
        machine.enter(State.PICK)


@pytest.mark.parametrize("state", [s for s in State if s is not State.FAULT])
def test_every_state_can_fault(state):
    machine = StateMachine(EventQueue(), {})
    machine.state = state
    machine.enter(State.FAULT)
    assert machine.state is State.FAULT


def test_timeout_is_armed_and_stale_timeout_is_ignored():
    queue = EventQueue()
    machine = StateMachine(queue, {State.WAIT_BOX: 10.0})
    machine.enter(State.READY)
    machine.enter(State.WAIT_BOX)
    timeout = queue.pop()
    assert timeout.kind is EventKind.TIMEOUT and timeout.time_s == 10.0
    assert machine.is_current_timeout(timeout)

    machine.enter(State.FEED_SET)  # state moved on before the timeout fired
    assert not machine.is_current_timeout(timeout)


def test_same_time_events_keep_scheduling_order():
    queue = EventQueue()
    first = queue.schedule_at(1.0, EventKind.S1_ON)
    second = queue.schedule_at(1.0, EventKind.S1_OFF)
    assert [queue.pop(), queue.pop()] == [first, second]
