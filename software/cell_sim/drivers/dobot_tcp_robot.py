"""Dobot M1 Pro over TCP/IP, using Dobot's own dobot_api.py (vendor copy, MIT).

dobot_api is optional and is loaded only here, from the path in hardware.json (dobot.api_path).
Only the DRY transport exists: Dobot's own methods build every command string, and a stand-in
socket prints it instead of sending it. There is no code here that sends a move to a real robot.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from ..hardware_config import DobotSettings, HardwareConfigError
from ..interfaces import Pose, RobotError

DRY_LABEL = "DOBOT DRY, nothing sent"
STEP_TO_TARGET = {
    "pick_above": "pick_approach",
    "place_above": "place_approach",
    "lid_above": "lid_approach",
    "lid_box_above": "lid_box_approach",
}
REPLY_PATTERN = re.compile(r"^\s*(-?\d+)\s*,\s*\{(.*)\}\s*,", re.DOTALL)

_loaded: dict[Path, ModuleType] = {}


class DobotUnavailable(RuntimeError):
    """dobot_api.py, numpy/tkinter, or the robot connection is not available."""


def load_dobot_api(api_path: Path) -> ModuleType:
    """Load Dobot's dobot_api.py from a file path (it is not an installed package)."""
    if api_path in _loaded:
        return _loaded[api_path]
    if not api_path.is_file():
        raise DobotUnavailable(f"dobot_api.py not found at {api_path} (hardware.json dobot.api_path)")
    spec = importlib.util.spec_from_file_location("dobot_api", api_path)
    if spec is None or spec.loader is None:
        raise DobotUnavailable(f"cannot load {api_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as error:  # dobot_api imports numpy and tkinter at load time
        raise DobotUnavailable(
            f"dobot_api.py needs a package that is missing ({error}). Run: python -m pip install numpy"
        ) from error
    _loaded[api_path] = module
    return module


def parse_reply(reply: str) -> tuple[int | None, str]:
    """'0,{1.0,2.0},GetPose();' -> (0, '1.0,2.0'). (None, reply) if the shape is unknown."""
    match = REPLY_PATTERN.match(reply or "")
    if match is None:
        return None, reply or ""
    return int(match.group(1)), match.group(2)


def reply_numbers(inside: str) -> list[float]:
    return [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", inside)]


class QuietLog:
    """Stands in for dobot_api's tkinter Text log, so the API's own log lines stay quiet."""

    def insert(self, *_args: Any) -> None:
        pass


class DrySocket:
    """Stands in for dobot_api's socket_dobot: records each command, sends nothing."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.sent: list[str] = []
        self._last = ""

    def send(self, data: bytes) -> int:
        self._last = data.decode("utf-8")
        self.sent.append(self._last)
        return len(data)

    def recv(self, _size: int) -> bytes:
        return f"0,{{}},{self._last};".encode("utf-8")  # reply shape: R2/Images/day2/Image2.png

    def close(self) -> None:
        pass


def dry_client(api_class: type, ip: str, port: int) -> Any:
    """A dobot_api client whose constructor is skipped (it would connect) and whose socket is dry."""
    client = api_class.__new__(api_class)
    client.ip, client.port = ip, port
    client.socket_dobot = DrySocket(port)
    client._DobotApi__globalLock = threading.Lock()  # set by DobotApi.__init__ (name-mangled)
    client.text_log = QuietLog()
    return client


class DobotTcpRobot:
    """RobotDriver that talks the Dobot TCP/IP protocol. Dry clients only."""

    def __init__(
        self,
        dashboard: Any,
        move: Any,
        settings: DobotSettings,
        say: Callable[[str], None] = print,
        label: str = DRY_LABEL,
        pause: Callable[[float], None] = lambda duration_s: None,
    ) -> None:
        missing = settings.missing_for_dry_run()
        if missing:
            raise HardwareConfigError(f"dobot values needed for the command strings are null: {missing}")
        self.dashboard, self.move = dashboard, move
        self.settings = settings
        self.say = say
        self.label = label
        self.name = "Dobot M1 Pro"
        self.at_step: str | None = None
        self.item_type: str | None = None
        self.pause = pause  # real mode would sleep; dry mode only prints the wait

    def enable(self) -> None:
        self._call(self.dashboard, "ClearError")
        self._call(self.dashboard, "EnableRobot")
        speed_percent = self.settings.speed_factor_percent
        self._call(self.dashboard, "SpeedFactor", speed_percent, note=f"speed ratio {speed_percent} %")
        if self.settings.arm_orientation_code is not None:
            self._call(self.dashboard, "SetArmOrientation", self.settings.arm_orientation_code,
                       note="keep the arm Left (a MovJ flipped it to Right on 12 Nov)")

    def has_target(self, step: str) -> bool:
        return self.settings.targets.get(STEP_TO_TARGET.get(step, step)) is not None

    def select_item(self, item_type: str) -> None:
        """The next pick is this item type: its pick height comes from pick_z_by_type_mm."""
        self.item_type = item_type

    def move_to(self, target_name: str) -> None:
        """Every move is MovL: on the M1 Pro a MovJ flipped the arm side (Choton, 12 Nov)."""
        station_name = STEP_TO_TARGET.get(target_name, target_name)
        pose = self.settings.targets.get(station_name)
        if pose is None:
            raise RobotError(f"no Dobot target for {target_name!r}")
        height_note = ""
        if station_name == "pick" and self.item_type is not None:
            pick_z_mm = self._pick_height_mm(self.item_type)
            if pick_z_mm is not None:
                pose = (pose[0], pose[1], pick_z_mm, pose[3])
                height_note = f", pick height for {self.item_type}"
        status = self.settings.statuses.get(f"target_{station_name}", "?")
        note = (
            f"target {station_name} x={pose[0]:g} y={pose[1]:g} z={pose[2]:g} mm r={pose[3]:g} deg "
            f"({status}{height_note}), speed ratio {self.settings.speed_factor_percent} %"
        )
        self._call(self.move, "MovL", *pose, note=note)
        self._call(self.move, "Sync", note="wait until the move is done")
        self.at_step = target_name

    def set_vacuum(self, on: bool) -> None:
        """Suction on, wait; or suction off, blow-off pulse, wait (as in the 12 Nov real runs)."""
        settings = self.settings
        if on:
            self._call(self.dashboard, "DO", settings.vacuum_do, 1, note="suction ON")
            self._wait(settings.vacuum_on_wait_s, "let the suction grip")
            return
        self._call(self.dashboard, "DO", settings.vacuum_do, 0, note="suction OFF")
        if settings.blow_off_do is not None:
            self._call(self.dashboard, "DO", settings.blow_off_do, 1, note="blow-off ON (drops the object)")
            self._wait(settings.blow_off_s, "blow-off pulse")
            self._call(self.dashboard, "DO", settings.blow_off_do, 0, note="blow-off OFF")
        self._wait(settings.vacuum_off_wait_s, "let the object settle")

    def set_object_conveyor(self, running: bool) -> None:
        """Belt A (objects) runs while object_conveyor_do is 1: DO3 -> relay -> Arduino Nano."""
        if self.settings.object_conveyor_do is None:
            raise RobotError("dobot.object_conveyor_do is not set")
        state = 1 if running else 0
        note = f"object conveyor {'ON' if running else 'OFF'}"
        self._call(self.dashboard, "DO", self.settings.object_conveyor_do, state, note=note)

    def _pick_height_mm(self, item_type: str) -> float | None:
        for kind, z_mm in self.settings.pick_z_by_type_mm.items():
            if item_type.startswith(kind):
                return z_mm
        return None

    def _wait(self, duration_s: float, reason: str) -> None:
        if duration_s > 0:
            self.say(f"[{self.label}] wait {duration_s:g} s on the PC  # {reason}")
            self.pause(duration_s)

    def current_pose(self) -> Pose:
        _code, inside = parse_reply(self._call(self.dashboard, "GetPose"))
        numbers = reply_numbers(inside)
        if len(numbers) < 4:
            raise RobotError(f"no pose in the GetPose reply {inside!r}")
        return Pose(*numbers[:4])

    def stop(self) -> None:
        try:
            self._call(self.dashboard, "ResetRobot", note="stop")
        except Exception:  # stop must never raise
            pass

    def close(self) -> None:
        """Every output this driver uses goes off, then the robot is disabled."""
        for channel in (self.settings.vacuum_do, self.settings.blow_off_do, self.settings.object_conveyor_do):
            if channel is not None:
                self._call(self.dashboard, "DO", channel, 0, note="output off at the end")
        self._call(self.dashboard, "DisableRobot")

    def _call(self, client: Any, method: str, *args: Any, note: str = "") -> str:
        """Call Dobot's own method, print what it put on the wire, and check the reply."""
        socket_stub = client.socket_dobot
        already_sent = len(socket_stub.sent)
        with contextlib.redirect_stdout(io.StringIO()):  # MovJ/MovL print every command themselves
            reply = getattr(client, method)(*args)
        for command in socket_stub.sent[already_sent:]:
            self.say(f"[{self.label}] port {client.port} <- {command}" + (f"  # {note}" if note else ""))
        code, _inside = parse_reply(reply)
        if code != 0:
            raise RobotError(f"Dobot replied {reply!r} to {method}")
        return reply


def build_dry_robot(settings: DobotSettings, say: Callable[[str], None] = print) -> DobotTcpRobot:
    api = load_dobot_api(settings.api_path)
    dashboard = dry_client(api.DobotApiDashboard, settings.robot_ip, settings.dashboard_port)
    move = dry_client(api.DobotApiMove, settings.robot_ip, settings.move_port)
    return DobotTcpRobot(dashboard, move, settings, say)
