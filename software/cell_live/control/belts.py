"""Belts in a real run (wiring as built on 17 Nov, see cell_live/README.md, Cell wiring).

ObjectBeltDO3: the object belt (cards and candies). Its TB6600 driver gets the step pulses from
the box belt's UNO; the robot switches ENA with DO3 (start and stop) and DIR with DO4, and DO16
enables it. Every pause switches DO16 off with the other outputs, so start() switches it on again
first. is_running() is the COMMANDED state only.

BoxBeltObserver: the box belt is run by its own controller (an Arduino UNO R4 WiFi on the box
sensor); we only watch it (camera, or a controller reply when one is configured), otherwise
NOT_OBSERVABLE.

BoxRestart: how the closed box moves on, set in belts.box_restart (since 17 Nov: operator, a
person takes the box). It refuses to work while the setting is null.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

from .gate import BOX_RESTART_MODES


class ObjectBeltDO3:
    """Implements cell_sim's BeltDriver (name, start, stop, is_running)."""

    name = "object belt"
    label = "DO3 commanded"  # the robot output, not proof that the belt moves

    def __init__(self, session: Any, channel: int, on_value: int, enable: tuple[int, int] | None = None) -> None:
        self.session = session
        self.channel = channel
        self.on_value = on_value
        self.enable = enable  # (enable output, its on level): DO16, switched off with the other outputs at a pause
        self._commanded = False

    def start(self) -> None:
        if self.enable is not None:
            self.session.set_output(self.enable[0], self.enable[1], "object belt: enable on")
        self.session.set_output(self.channel, self.on_value, "object belt: DO commanded ON")
        self._commanded = True

    def stop(self) -> None:
        self.session.set_output(self.channel, 1 - self.on_value, "object belt: DO commanded OFF")
        self._commanded = False

    def is_running(self) -> bool:
        return self._commanded


class BoxBeltObserver:
    """What we can see of the box belt. It never sends a command."""

    def __init__(self, vision: Any = None, nano_reply: Callable[[], str | None] | None = None) -> None:
        self.vision = vision
        self.nano_reply = nano_reply

    def describe(self, objects: list[dict[str, Any]] | None, slot: Any) -> dict[str, Any]:
        reply = self.nano_reply() if self.nano_reply is not None else None
        if self.vision is None or objects is None:
            if reply:
                return {"state": "OK", "source": "nano", "nano": reply}
            return {"state": "NOT_OBSERVABLE", "detail": "no camera session and no box belt controller reply configured"}
        present = self.vision.box_present(objects, slot)
        return {"state": "OK", "source": "camera", "box_at_robot": present, "nano": reply}


def box_nearest_the_slot(boxes: list[dict[str, Any]], slot: Any) -> dict[str, Any]:
    """The open box the run works on: the detected box nearest the box slot (the highest score if none has
    robot X/Y). 17 Nov (testing/live_runs/20261117_204319.csv): next to the real box (0.92) a second
    "box 0.9" was seen at (349.0, 174.9), 136 mm from the slot; the score alone could pick that one."""
    located = [found for found in boxes if "x_robot" in found]
    if not located:
        return max(boxes, key=lambda found: found["conf"])
    return min(located, key=lambda found: math.dist((found["x_robot"], found["y_robot"]), slot))


def box_off_the_slot(found: dict[str, Any], slot: Any, tolerance_mm: float | None) -> str:
    """Why the open box does not stand under the taught box slot, or '' (no tolerance set, or no robot X/Y).
    17 Nov: the box centre was 78 mm from the slot and every item landed beside the box
    (testing/live_runs/20261117_193551.csv)."""
    if tolerance_mm is None or "x_robot" not in found:
        return ""
    dx_mm, dy_mm = slot[0] - found["x_robot"], slot[1] - found["y_robot"]
    off_mm = math.hypot(dx_mm, dy_mm)
    if off_mm <= tolerance_mm:
        return ""
    return (f"the open box's centre ({found['x_robot']:.0f}, {found['y_robot']:.0f}) is {off_mm:.0f} mm from the box slot "
            f"({slot[0]:g}, {slot[1]:g}), allowed {tolerance_mm:g} mm: move the box {dy_mm:+.0f} mm along the belt and "
            f"{dx_mm:+.0f} mm across it, until the box slot mark on Vision is in its middle")


class BoxRestartNotSet(RuntimeError):
    pass


class BoxRestart:
    def __init__(self, mode: str | None, session: Any, channel: int | None, settle_s: float,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if mode not in BOX_RESTART_MODES:
            raise BoxRestartNotSet(f"belts.box_restart is {mode!r}: set one of {list(BOX_RESTART_MODES)} in the lab")
        if mode == "dobot_output" and channel is None:
            raise BoxRestartNotSet("belts.box_restart is dobot_output but dobot.box_belt_do is not set")
        self.mode = mode
        self.session = session
        self.channel = channel
        self.settle_s = settle_s
        self.sleep = sleep
        self._on = False

    def begin(self) -> str:
        if self.mode == "dobot_output":
            self.session.set_output(self.channel, 1, "box belt: move the closed box on")
            self._on = True
            return f"DO{self.channel} on: the box belt controller moves the closed box on"
        if self.mode == "operator":
            return "take the closed box away (the camera watches)"
        return "waiting for the box belt controller to move the closed box on (the camera watches)"

    def finish(self) -> None:
        if self._on:
            self.sleep(self.settle_s)
            self.session.set_output(self.channel, 0, "box belt command off")
            self._on = False
