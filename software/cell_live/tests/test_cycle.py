"""The real box cycle against fakes: every state, every PAUSED and FAULT path, stop actions.
After every pause, fault or abort DO1, DO2 and DO3 must be off."""

import threading

import pytest

from cell_live.control.belts import BoxRestart, ObjectBeltDO3
from cell_live.control.cycle import RunController
from cell_live.control.cycle_steps import Limits, RunContext
from cell_live.control.robot_client import ControlConnectionLost
from cell_live.control.states import SOFTWARE_ESTOP, Action, CycleState
from cell_live.tests.control_fakes import (
    CHOTON, FakeClock, FakeLog, FakeSession, FakeVision, choton_settings, full_set, item, objects_come_with_the_belt, wait_for,
)

LIMITS = Limits(reach_min_mm=150, reach_max_mm=375, box_wait_timeout_s=5, feed_timeout_s=5, settle_s=0,
                box_still_frames=5, box_still_px=6, ready_frames=3, detect_frames=8, gone_px=10,
                box_leave_timeout_s=5, close_lid=True)
LID = item("lid", 300.0, 120.0, 700)


def make_run(boxes=1, vision_kwargs=None, session=None, restart_mode="operator", settings=None):
    clock = FakeClock()
    session = session or FakeSession()
    kwargs = {"objects": full_set() + [LID], **(vision_kwargs or {})}
    vision = FakeVision(clock, **kwargs)
    belt = ObjectBeltDO3(session, 3, 1)
    restart = BoxRestart(restart_mode, session, 4 if restart_mode == "dobot_output" else None, 0.0, sleep=lambda s: None)
    log = FakeLog()
    settings = settings or choton_settings()

    def build(controller):
        return RunContext(session, vision, belt, restart, CHOTON.yolo_lib, CHOTON.pick, settings, LIMITS, log,
                          controller.checkpoint, controller.sleep, clock)

    return RunController(build, boxes, session, log), session, vision, log


def _outputs_off(session):
    assert session.outputs_off_calls >= 1
    assert (session.outputs[3], session.outputs[1], session.outputs[2]) == (0, 0, 0)


def _paused(controller, reason):
    wait_for(lambda: controller.state is CycleState.PAUSED)
    assert controller.pause_reason.startswith(reason), controller.pause_reason


def _finish(controller):
    wait_for(lambda: controller.finished)
    assert controller.state is CycleState.IDLE


# Normal operation


def test_one_box_runs_every_state_in_order():
    controller, session, vision, log = make_run()
    objects_come_with_the_belt(vision, session)
    controller.start()
    _finish(controller)
    entered = [row["event"][6:] for row in log.rows if row["event"].startswith("enter ")]
    assert entered == ["WAIT_BOX", "FEED_OBJECTS", "LOOK", "PICK_PLACE", "CLOSE_LID", "RELEASE_BOX", "BOX_DONE"]
    assert [kind for kind, _, _ in session.picks] == ["card", "candy", "candy"]
    assert session.lids == [(300.0, 120.0)]
    assert controller.box_results[0]["result"] == "done" and controller.box_results[0]["lid"] == "on"
    belt_on, belt_off = session.calls.index("DO3=1"), session.calls.index("DO3=0")
    assert session.calls.index("home") < belt_on < belt_off < session.calls.index("pick_and_place")
    assert session.closed
    _outputs_off(session)


def test_objects_already_in_the_pick_area_do_not_start_the_belt():
    controller, session, _, log = make_run()  # the full set lies in the pick area from the start
    controller.start()
    _finish(controller)
    assert controller.box_results[0]["result"] == "done" and "DO3=1" not in session.calls
    assert any(row["event"].startswith("objects already in place, the object belt is not started") for row in log.rows)


def test_three_boxes_in_a_row():
    controller, session, _, _ = make_run(boxes=3)
    controller.start()
    _finish(controller)
    assert [r["result"] for r in controller.box_results] == ["done", "done", "done"] and len(session.picks) == 9


def test_lid_heights_missing_leaves_the_box_open_and_logs_it():
    settings = choton_settings(lid=False)
    controller, session, _, log = make_run(settings=settings)
    controller.start()
    _finish(controller)
    assert session.lids == [] and controller.box_results[0]["lid"].startswith("open: lid heights not taught")


def test_dobot_output_restart_pulses_the_box_belt_output():
    controller, session, _, _ = make_run(restart_mode="dobot_output")
    controller.start()
    _finish(controller)
    assert session.calls.index("DO4=1") < session.calls.index("DO4=0")
    assert session.calls.index("place_lid") < session.calls.index("DO4=1")


# PAUSED paths (outputs off, operator decides)


def test_no_box_pauses_then_abort():
    controller, session, _, _ = make_run(vision_kwargs={"box": False})
    controller.start()
    _paused(controller, "no box")
    _outputs_off(session)
    assert controller.act(Action.ABORT) == "abort accepted"
    _finish(controller)
    assert controller.box_results[0]["result"] == "aborted"


def test_not_enough_objects_pauses_with_belt_off_then_retry_continues():
    controller, session, vision, _ = make_run(vision_kwargs={"objects": [item("card", 250.0, 0.0, 100)]})
    controller.start()
    _paused(controller, "not enough objects")
    _outputs_off(session)
    vision.objects = full_set() + [LID]  # the operator put more objects on the belt
    controller.act(Action.RETRY)
    _finish(controller)
    assert controller.box_results[0]["result"] == "done"


def test_object_missing_pauses_and_skip_box():
    look = [o for o in full_set() if o["color"] != "orange"] + [LID]  # one candy gone before the pictures
    controller, session, _, _ = make_run(vision_kwargs={"look_objects": look})
    controller.start()
    _paused(controller, "object missing")
    assert len(session.picks) == 2
    _outputs_off(session)
    controller.act(Action.SKIP_BOX)
    _finish(controller)
    assert controller.box_results[0]["result"] == "skipped by the operator"


@pytest.mark.parametrize("lid", [None, item("lid", 390.0, 0.0, 700)], ids=["no lid", "lid out of reach"])
def test_lid_not_found_or_out_of_reach_pauses(lid):
    look = full_set() + ([lid] if lid else [])
    controller, session, _, log = make_run(vision_kwargs={"look_objects": look})
    controller.start()
    _paused(controller, "lid not found or out of reach")
    _outputs_off(session)
    if lid:
        assert any(row["event"] == "centre out of reach" for row in log.rows)
        assert "the lid at (390, 0) is 390 mm from the robot: move it 17 mm or more towards the robot" in controller.pause_reason
    controller.act(Action.ABORT)
    _finish(controller)


def test_box_did_not_leave_pauses_then_retry():
    controller, session, vision, _ = make_run(vision_kwargs={"box_leaves": False})
    controller.start()
    _paused(controller, "box did not leave")
    _outputs_off(session)
    vision.box_leaves = True
    controller.act(Action.RETRY)
    _finish(controller)
    assert controller.box_results[0]["result"] == "done"


def test_refused_move_without_alarm_pauses_and_retry_looks_again():
    session = FakeSession()
    session.fail_pick = RuntimeError("MovL(250.0, 0.0, 104.7, -73.8) refused: -1,{},MovL();  (outside the work area?)")
    controller, session, _, _ = make_run(session=session)
    controller.start()
    _paused(controller, "move refused")
    _outputs_off(session)
    controller.act(Action.RETRY)
    _finish(controller)
    assert controller.box_results[0]["result"] == "done" and len(session.picks) == 3


# FAULT paths (only Abort)


def _fault(controller, words):
    wait_for(lambda: controller.state is CycleState.FAULT)
    assert words in controller.fault, controller.fault


def test_robot_alarm_faults_and_only_abort_works():
    session = FakeSession()
    session.fail_pick, session.alarm = RuntimeError("MovL refused"), "controller 22: Joint 3 drive alarm"
    controller, session, _, _ = make_run(session=session)
    controller.start()
    _fault(controller, "robot alarm: controller 22")
    _outputs_off(session)
    assert controller.act(Action.RETRY) == "after a FAULT only Abort is possible"
    assert "ClearError" in controller.clear_alarm()
    controller.act(Action.ABORT)
    _finish(controller)
    assert controller.box_results[0]["result"].startswith("fault: robot alarm")


def test_lost_robot_connection_faults():
    session = FakeSession()
    session.fail_pick = ControlConnectionLost("no reply to Sync() on port 30003 in time")
    controller, session, _, _ = make_run(session=session)
    controller.start()
    _fault(controller, "connection to the robot lost")
    _outputs_off(session)
    controller.act(Action.ABORT)
    _finish(controller)


def test_a_move_stopped_by_a_robot_alarm_faults_with_the_alarm_not_lost_connection():
    session = FakeSession()
    session.fail_pick = ControlConnectionLost("no reply to Sync() on port 30003 in time")
    session.alarm_that_stopped_a_move = lambda: "controller 23: Plan point during linear motion out of working area"
    controller, session, _, _ = make_run(session=session)
    controller.start()
    _fault(controller, "robot alarm: controller 23: Plan point during linear motion out of working area")
    _outputs_off(session)
    controller.act(Action.ABORT)
    _finish(controller)


def test_lost_camera_faults():
    controller, session, vision, _ = make_run()
    vision.lost_after = 3
    controller.start()
    _fault(controller, "CameraLost")
    _outputs_off(session)
    controller.act(Action.ABORT)
    _finish(controller)


# Operator stop actions


def test_pause_waits_for_the_current_pick_to_finish():
    controller, session, _, _ = make_run()
    session.on_pick = lambda done: controller.request_pause() if done == 0 else None
    controller.start()
    _paused(controller, "paused by the operator")
    assert len(session.picks) == 1  # the item was placed before the pause (never paused holding it)
    _outputs_off(session)
    controller.act(Action.RETRY)
    _finish(controller)
    assert [kind for kind, _, _ in session.picks] == ["card", "candy", "candy"]


def test_pause_in_a_waiting_loop_and_resume():
    controller, _, vision, _ = make_run()
    vision.on_read = lambda n: controller.request_pause() if n == 2 else None
    controller.start()
    _paused(controller, "paused by the operator")
    assert controller.step is CycleState.WAIT_BOX
    controller.act(Action.RETRY)
    _finish(controller)


def test_abort_while_running():
    controller, session, vision, _ = make_run()
    vision.on_read = lambda n: controller.act(Action.ABORT) if n == 2 else None
    controller.start()
    _finish(controller)
    assert controller.box_results[0]["result"] == "aborted" and session.closed
    _outputs_off(session)


def test_software_estop_during_a_pick_stays_in_fault_until_abort():
    controller, session, _, _ = make_run()
    estop = threading.Thread(target=controller.estop)
    session.on_pick = lambda done: (estop.start(), estop.join()) if done == 1 else None
    controller.start()
    _fault(controller, SOFTWARE_ESTOP)
    assert session.estopped and any("EmergencyStop" in line for line in controller.output_reports)
    _outputs_off(session)
    assert not controller.finished  # waits: the operator may clear the alarm first
    controller.act(Action.ABORT)
    _finish(controller)


def test_software_estop_while_paused_needs_one_abort():
    controller, session, _, _ = make_run(vision_kwargs={"box": False})
    controller.start()
    _paused(controller, "no box")
    controller.estop()
    assert controller.state is CycleState.FAULT and controller.fault == SOFTWARE_ESTOP
    controller.act(Action.ABORT)
    _finish(controller)
    _outputs_off(session)
