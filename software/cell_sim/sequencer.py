"""The robot's part of a cycle as steps: pictures from home, pick, place, close the lid.

TimedSequencer (sim, dobot-dry): the steps run at once on a robot that moves instantly; the
*_DONE events come after the times in config.json.
MeasuredSequencer (robodk): the steps block until the robot is done; the measured time is used.
"""

from __future__ import annotations

from .config import CellConfig
from .events import EventKind, EventQueue
from .interfaces import Clock, RobotDriver

VACUUM_ON = "vacuum_on"
VACUUM_OFF = "vacuum_off"

PICTURE_STEPS: tuple[str, ...] = ("home",)  # out of the camera view (Choton: 8 pictures from home)
PICK_STEPS: tuple[str, ...] = ("pick_above", "pick", VACUUM_ON, "pick_above")
PLACE_STEPS: tuple[str, ...] = ("place_above", "place_box", VACUUM_OFF, "place_above")
RETURN_STEPS: tuple[str, ...] = ("pick_above",)
LID_STEPS: tuple[str, ...] = ("lid_above", "lid", VACUUM_ON, "lid_above", "lid_box_above", "lid_on_box", VACUUM_OFF, "lid_box_above")


def announce_item(robot: RobotDriver, item_type: str) -> None:
    """Robots that need the item type (e.g. a pick height per type) define select_item()."""
    select_item = getattr(robot, "select_item", None)
    if select_item is not None:
        select_item(item_type)


def missing_targets(robot: RobotDriver, steps: tuple[str, ...]) -> list[str]:
    """Targets the robot says it does not have (robots without has_target() have them all)."""
    has_target = getattr(robot, "has_target", None)
    if has_target is None:
        return []
    return [step for step in steps if step not in (VACUUM_ON, VACUUM_OFF) and not has_target(step)]


def lid_note(missing: list[str]) -> str:
    return f"lid moves not sent: the robot has no targets {missing} (time from config.json)" if missing else ""


def run_steps(robot: RobotDriver, steps: tuple[str, ...]) -> None:
    for step in steps:
        if step == VACUUM_ON:
            robot.set_vacuum(True)
        elif step == VACUUM_OFF:
            robot.set_vacuum(False)
        else:
            robot.move_to(step)


class TimedSequencer:
    def __init__(self, config: CellConfig, queue: EventQueue, robot: RobotDriver) -> None:
        self.config = config
        self.queue = queue
        self.robot = robot
        self.robot_ready_s = 0.0  # when the robot has finished its last move

    def _start_s(self) -> float:
        return max(self.queue.now_s, self.robot_ready_s)

    def start_pictures(self) -> None:
        start_s = self._start_s()
        run_steps(self.robot, PICTURE_STEPS)
        self.robot_ready_s = start_s + self.config.move_to_box_time_s + self.config.pictures_time_s
        self.queue.schedule_at(self.robot_ready_s, EventKind.PICTURES_DONE)

    def start_pick(self, item_type: str, item_id: int | None = None) -> float:
        pick_start_s = self._start_s()
        announce_item(self.robot, item_type)
        run_steps(self.robot, PICK_STEPS)
        self.queue.schedule_at(
            pick_start_s + self.config.pick_time_s, EventKind.PICK_DONE, item_type=item_type, item_id=item_id
        )
        return pick_start_s

    def start_place(self, item_type: str) -> None:
        run_steps(self.robot, PLACE_STEPS)
        self.queue.schedule_in(
            self.config.move_to_box_time_s + self.config.place_time_s, EventKind.PLACE_DONE, item_type=item_type
        )

    def place_finished(self) -> None:
        """The return move to the pick area takes move_to_box_time_s."""
        run_steps(self.robot, RETURN_STEPS)
        self.robot_ready_s = self.queue.now_s + self.config.move_to_box_time_s

    def start_close_lid(self) -> None:
        start_s = self._start_s()
        missing = missing_targets(self.robot, LID_STEPS)
        if not missing:
            run_steps(self.robot, LID_STEPS)
        self.robot_ready_s = start_s + self.config.lid_time_s
        self.queue.schedule_at(self.robot_ready_s, EventKind.LID_DONE, note=lid_note(missing))


class MeasuredSequencer:
    """Steps run on a robot whose moves block until done (RoboDK).

    Each step list is timed on `clock`. The simulated cell clock does not move while the
    robot works; the *_DONE events are scheduled after the measured time instead.
    time_scale converts the measured time to motion time (RoboDK simulation speed ratio).
    Camera time (pictures_time_s) and a lid step the robot cannot do come from config.
    """

    def __init__(
        self, queue: EventQueue, robot: RobotDriver, clock: Clock, time_scale: float = 1.0, config: CellConfig | None = None
    ) -> None:
        if time_scale <= 0:
            raise ValueError("time_scale must be positive")
        self.queue = queue
        self.robot = robot
        self.clock = clock
        self.time_scale = time_scale
        self.config = config
        self.robot_ready_s = 0.0
        self.step_times_s: list[tuple[str, float]] = []  # (step list name, measured motion time)

    def start_pictures(self) -> None:
        start_s = max(self.queue.now_s, self.robot_ready_s)
        camera_s = self.config.pictures_time_s if self.config is not None else 0.0
        self.robot_ready_s = start_s + self._timed("pictures", PICTURE_STEPS) + camera_s
        self.queue.schedule_at(self.robot_ready_s, EventKind.PICTURES_DONE)

    def start_pick(self, item_type: str, item_id: int | None = None) -> float:
        pick_start_s = max(self.queue.now_s, self.robot_ready_s)
        announce_item(self.robot, item_type)
        duration_s = self._timed("pick", PICK_STEPS)
        self.queue.schedule_at(pick_start_s + duration_s, EventKind.PICK_DONE, item_type=item_type, item_id=item_id)
        return pick_start_s

    def start_place(self, item_type: str) -> None:
        duration_s = self._timed("place", PLACE_STEPS)
        self.queue.schedule_in(duration_s, EventKind.PLACE_DONE, item_type=item_type)

    def place_finished(self) -> None:
        duration_s = self._timed("return", RETURN_STEPS)
        self.robot_ready_s = self.queue.now_s + duration_s

    def start_close_lid(self) -> None:
        start_s = max(self.queue.now_s, self.robot_ready_s)
        missing = missing_targets(self.robot, LID_STEPS)
        if missing:
            duration_s = self.config.lid_time_s if self.config is not None else 0.0
        else:
            duration_s = self._timed("lid", LID_STEPS)
        self.robot_ready_s = start_s + duration_s
        self.queue.schedule_at(self.robot_ready_s, EventKind.LID_DONE, note=lid_note(missing))

    def _timed(self, name: str, steps: tuple[str, ...]) -> float:
        start_s = self.clock.now_s()
        run_steps(self.robot, steps)
        duration_s = (self.clock.now_s() - start_s) * self.time_scale
        self.step_times_s.append((name, duration_s))
        return duration_s
