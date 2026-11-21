"""What every step of the real box cycle shares: the run's limits, the state of one box, the run
context, the reach marks and the wrapper around robot moves. Standard library only.

The steps are in cycle_steps.py (box, belt, pictures, picks, release) and lid.py (the lid).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from .robot_client import ControlConnectionLost, ControlRefused, RobotRefused
from .states import MOVE_REFUSED, StepFault, StepPause


@dataclass(frozen=True)
class Limits:
    reach_min_mm: float
    reach_max_mm: float
    box_wait_timeout_s: float
    feed_timeout_s: float
    settle_s: float
    box_still_frames: int
    box_still_px: float
    ready_frames: int
    detect_frames: int
    gone_px: float
    box_leave_timeout_s: float
    close_lid: bool
    feed_stop_y_mm: float | None = None  # stop line of the object belt (feed.py); None: only the full set stops it
    stop_line_frames: int = 2  # pictures in a row with a needed object at the stop line
    refeeds_max: int = 0  # belt restarts in a row with nothing picked, then PAUSED (object missing)
    arm: Any = None  # arm_reach.ArmReach: points beyond the arm's J1 range are out of reach; None: not checked
    box_slot_tolerance_mm: float | None = None  # the open box's centre must be this close to the box slot; None: not checked
    lid_min_from_slot_mm: float = 0.0  # a lid seen nearer the box slot is the filled box itself, never picked
    lid_grip_offset_max_mm: float = 0.0  # a lid whose centre is beyond the reach may be gripped this far from its centre


@dataclass
class BoxState:
    number: int
    placed: list[dict[str, Any]] = field(default_factory=list)
    objects: list[dict[str, Any]] = field(default_factory=list)  # from the last LOOK
    gone: list[dict[str, Any]] = field(default_factory=list)  # picked since the last LOOK
    lid: str = "not done"
    refeeds: int = 0  # object belt restarts in a row that brought nothing to pick
    box_angle_deg: float | None = None  # direction of the OPEN box's long side (robot X/Y), kept for every turn (turn.py)


@dataclass
class RunContext:
    session: Any  # RobotSession (or a test fake)
    vision: Any  # VisionSession (or a test fake)
    belt: Any  # ObjectBeltDO3
    restart: Any  # BoxRestart
    yolo: Any  # Choton's yolo_lib (next_pick, box_complete, usable)
    pick: Any  # Choton's 14_pick_and_place module (straighten_turn)
    settings: dict[str, Any]  # Choton's settings.json, read at Start
    limits: Limits
    log: Any  # RunLog
    checkpoint: Callable[[], None]
    sleep: Callable[[float], None]
    clock: Callable[[], float]
    pictures: Any = None  # pictures.RunPictures: what the camera saw at each decision; None: nothing is saved

    @property
    def robot(self) -> dict[str, Any]:
        return self.settings["robot"]

    def picture(self, label: str, frame: Any) -> str:
        """Save the camera picture a decision was made on. Returns ' (picture <file>)' for the log row, or ''."""
        name = self.pictures.save(label, frame) if self.pictures is not None else None
        return f" (picture {name})" if name else ""


def mark_reach_objects(objects: list[dict[str, Any]], reach_min_mm: float, reach_max_mm: float,
                       arm: Any = None) -> list[dict[str, Any]]:
    """Our reach (175-375 mm, and the arm's J1 range when arm is given) on top of Choton's 400 mm.
    Returns the objects marked out of reach."""
    for found in objects:
        if "x_robot" not in found:
            found["reachable"] = False
            continue
        distance_mm = math.hypot(found["x_robot"], found["y_robot"])
        if not reach_min_mm <= distance_mm <= reach_max_mm:
            found["reachable"] = False
            found["out_of_reach_mm"] = round(distance_mm, 1)
        elif arm is not None and (j1_deg := arm.j1_beyond_limit_deg(found["x_robot"], found["y_robot"])) is not None:
            found["reachable"] = False
            found["out_of_reach_j1_deg"] = round(j1_deg, 1)
    return [found for found in objects if out_of_reach(found)]


def out_of_reach(found: dict[str, Any]) -> bool:
    return "out_of_reach_mm" in found or "out_of_reach_j1_deg" in found


def mark_reach(ctx: RunContext, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Objects whose centre is outside the reach are logged. Cards and candies there are never picked;
    a lid may still be gripped a little off its centre (lid.py)."""
    beyond = mark_reach_objects(objects, ctx.limits.reach_min_mm, ctx.limits.reach_max_mm, ctx.limits.arm)
    if beyond:
        ctx.log.event("centre out of reach", detections=beyond)
    return objects


def robot_call(ctx: RunContext, action: Callable[[], None]) -> None:
    """A robot move. Lost connection -> FAULT; refused move -> FAULT if the robot reports an alarm, else PAUSED.
    A reply that never came because the robot stopped its moves with an alarm is a FAULT with the alarm text."""
    try:
        action()
    except ControlConnectionLost as error:
        alarm_of = getattr(ctx.session, "alarm_that_stopped_a_move", None)
        alarm = alarm_of() if alarm_of is not None else ""
        if alarm:  # 17 Nov: alarm 23 stopped the first pick move, and Sync() never answered
            raise StepFault(f"robot alarm: {alarm} (the robot stopped its moves: {error})") from error
        raise StepFault(f"connection to the robot lost: {error}") from error
    except (ControlRefused, RobotRefused, RuntimeError) as error:
        alarm = ctx.session.alarm_text()
        if alarm and alarm != "no error":
            raise StepFault(f"robot alarm: {alarm} ({error})") from error
        raise StepPause(MOVE_REFUSED, str(error)) from error


def quietly(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:  # the caller is already pausing or faulting; outputs_off() reports
        pass
