import pytest

from cell_sim.cell import SafetyViolation
from cell_sim.config import load_config
from cell_sim.drivers.manual_devices import ManualBelt, ManualSensor
from cell_sim.drivers.sim_devices import (
    MockVision,
    SimBelt,
    SimClock,
    SimRobot,
    SimSensor,
    SimWorld,
    build_sim_cell,
)
from cell_sim.events import EventKind, EventQueue
from cell_sim.interfaces import (
    BeltDriver,
    Clock,
    Pose,
    RobotDriver,
    RobotError,
    SensorS1,
    VisionSource,
    WallClock,
)
from cell_sim.simulation import Simulation, run_simulation


def _world(s1_working=True):
    queue = EventQueue()
    return SimWorld(load_config(), queue, s1_working=s1_working), queue


def _dispatch_next(world, queue):
    event = queue.pop()
    world.on_event(event)
    return event


# Every implementation satisfies its interface


def test_implementations_satisfy_interfaces():
    world, queue = _world()
    assert isinstance(SimRobot(), RobotDriver)
    assert isinstance(SimBelt(world, "A"), BeltDriver)
    assert isinstance(ManualBelt("B", ask=lambda _: ""), BeltDriver)
    assert isinstance(SimSensor(world), SensorS1)
    assert isinstance(ManualSensor(ask=lambda _: ""), SensorS1)
    assert isinstance(MockVision(world), VisionSource)
    assert isinstance(SimClock(queue), Clock)
    assert isinstance(WallClock(), Clock)


# Event queue cancelling


def test_cancelled_event_never_pops():
    queue = EventQueue()
    dropped = queue.schedule_at(1.0, EventKind.S1_ON)
    kept = queue.schedule_at(2.0, EventKind.S1_OFF)
    queue.cancel(dropped)
    assert len(queue) == 1
    assert queue.pop() == kept and queue.now_s == 2.0
    assert len(queue) == 0


# SimBelt A, MockVision: items move through the pick area


def test_items_enter_the_pick_area_one_spacing_apart_and_leave_at_the_far_end():
    world, queue = _world()
    config = world.config
    SimBelt(world, "A").start()
    first = _dispatch_next(world, queue)
    assert first.kind is EventKind.ITEM_ENTERS_AREA and first.payload["item_index"] == 0
    assert first.time_s == pytest.approx(config.item_spacing_time_s)
    second = _dispatch_next(world, queue)
    assert second.kind is EventKind.ITEM_ENTERS_AREA
    assert second.time_s == pytest.approx(2 * config.item_spacing_time_s)
    events = [_dispatch_next(world, queue) for _ in range(4)]
    leave = next(e for e in events if e.kind is EventKind.ITEM_LEAVES_AREA)
    assert leave.payload["item_index"] == 0
    assert leave.time_s == pytest.approx(first.time_s + config.time_in_pick_area_s)
    assert leave.payload["entered_s"] == first.time_s


def test_stopped_belt_keeps_every_item_where_it_is():
    world, queue = _world()
    belt_a = SimBelt(world, "A")
    belt_a.start()
    _dispatch_next(world, queue)  # item 0 in the pick area; item 1 is on its way
    queue.schedule_in(0.4, EventKind.START)  # move the clock 0.4 s on
    queue.pop()
    belt_a.stop()
    assert len(queue) == 0 and not belt_a.is_running()
    assert world.odometer_mm() == pytest.approx(world.config.item_spacing_mm + 0.4 * world.config.belt_a_speed_mm_s)
    queue.schedule_in(5.0, EventKind.START)  # belt A stands still for 5 s
    queue.pop()
    belt_a.start()
    restarted = queue.pop()
    assert restarted.payload["item_index"] == 1
    assert restarted.time_s == pytest.approx(5.0 + 2 * world.config.item_spacing_time_s)  # only the stop is lost


def test_vision_reports_every_item_in_the_pick_area_with_its_id():
    world, queue = _world()
    vision = MockVision(world)
    assert vision.detections() == []
    SimBelt(world, "A").start()
    first = _dispatch_next(world, queue)
    second = _dispatch_next(world, queue)
    seen = vision.detections()
    assert [d.item_id for d in seen] == [0, 1]
    assert [d.item_type for d in seen] == [first.payload["item_type"], second.payload["item_type"]]
    assert seen[0].time_s == first.time_s


def test_a_picked_item_leaves_the_pick_area():
    world, queue = _world()
    SimBelt(world, "A").start()
    _dispatch_next(world, queue)
    SimBelt(world, "A").stop()
    world.on_event(queue.schedule_in(0.0, EventKind.PICK_DONE, item_type="card", item_id=0))
    assert world.items_in_area() == []


# Belt B (Arduino Nano) and S1


def test_box_arrives_at_s1_and_the_next_one_comes_after_the_operator_removes_it():
    world, queue = _world()
    s1 = SimSensor(world)
    world.on_event(queue.schedule_in(0.0, EventKind.START))
    queue.pop()
    s1_on = _dispatch_next(world, queue)
    assert s1_on.kind is EventKind.S1_ON and s1.is_active()
    assert s1_on.time_s == pytest.approx(world.config.box_to_s1_time_s)
    world.on_event(queue.schedule_in(0.0, EventKind.LID_DONE))
    queue.pop()
    s1_off = _dispatch_next(world, queue)
    assert s1_off.kind is EventKind.S1_OFF and not s1.is_active()
    assert s1_off.time_s - s1_on.time_s == pytest.approx(world.config.box_removal_time_s)
    assert _dispatch_next(world, queue).kind is EventKind.S1_ON  # the Nano brings the next box


def test_broken_s1_never_fires():
    world, queue = _world(s1_working=False)
    world.on_event(queue.schedule_in(0.0, EventKind.START))
    queue.pop()
    assert len(queue) == 0


def test_belt_name_is_checked():
    world, _ = _world()
    with pytest.raises(ValueError):
        SimBelt(world, "C")
    with pytest.raises(ValueError):
        ManualBelt("C")


# SimRobot


def test_sim_robot_records_commands_and_rejects_unknown_targets():
    robot = SimRobot()
    robot.enable()
    robot.move_to("pick")
    robot.set_vacuum(True)
    assert robot.commands == ["enable", "move_to pick", "vacuum on"]
    with pytest.raises(RobotError):
        robot.move_to("somewhere")
    with pytest.raises(RobotError):
        robot.current_pose()  # names only, no coordinates in simulation


def test_sim_robot_pose_comes_only_from_given_coordinates():
    pose = Pose(1.0, 2.0, 3.0, 4.0)  # test value, not a cell coordinate
    robot = SimRobot({"home": pose})
    robot.move_to("home")
    assert robot.current_pose() == pose


def test_robot_runs_pictures_picks_places_and_lid_in_order():
    simulation = Simulation(load_config(), 1, cell_factory=build_sim_cell)
    simulation.run()
    robot = simulation.cell.devices.sequencer.robot
    one_item = [
        "move_to pick_above", "move_to pick", "vacuum on", "move_to pick_above",
        "move_to place_above", "move_to place_box", "vacuum off", "move_to place_above",
        "move_to pick_above",
    ]
    lid = [
        "move_to lid_above", "move_to lid", "vacuum on", "move_to lid_above",
        "move_to lid_box_above", "move_to lid_on_box", "vacuum off", "move_to lid_box_above",
    ]
    assert robot.commands == ["enable", "move_to home"] + one_item * 3 + lid


# Cell safety rules


def test_cell_refuses_pick_while_belt_a_runs_and_place_without_s1():
    queue = EventQueue()
    cell = build_sim_cell(load_config(), queue)
    cell.start_feed()
    with pytest.raises(SafetyViolation):
        cell.start_pick("card")
    with pytest.raises(SafetyViolation):
        cell.take_pictures()
    cell.stop_belt_a()
    cell.finish_pick("card")
    with pytest.raises(SafetyViolation):
        cell.start_place()
    with pytest.raises(SafetyViolation):
        cell.close_lid()


def test_fault_stops_belts_and_robot():
    result = run_simulation(load_config(), 5, s1_working=False)
    assert result.fault_reason is not None
    assert not any(a.action in ("place", "lid") for a in result.actions)
