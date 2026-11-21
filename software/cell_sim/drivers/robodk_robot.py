"""RoboDK robot driver: shows the arm moving in a RoboDK station (ROBODK SIMULATION).

The robodk package is optional and is loaded only here, with importlib. RoboDK must
already be running: Robolink() would otherwise start RoboDK itself, so the API port is
checked first. Method names are from robodk 6.0.2 and robodk.com/doc/en/PythonAPI/robodk.html.
"""

from __future__ import annotations

import importlib
import socket
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

from ..hardware_config import RoboDKSettings
from ..interfaces import Pose, RobotError

APPROACH_OF = {"pick_above": "pick", "place_above": "place_box", "lid_above": "lid", "lid_box_above": "lid_on_box"}
TAUGHT_APPROACH = {
    "pick_above": "pick_approach",
    "place_above": "place_approach",
    "lid_above": "lid_approach",
    "lid_box_above": "lid_box_approach",
}
VERTICAL_PAIRS = {(above, base) for above, base in APPROACH_OF.items()}
LID_OBJECT_KEYWORD = "lid"  # at the lid target the vacuum attaches an object named *lid*
OPEN_HINT = (
    "Open RoboDK on this PC, load the cell station ({robot} with the "
    "targets {targets}), and run again. Station set-up: software/cell_sim/README.md, section RoboDK."
)
API_OFF_HINT = (
    "If RoboDK is already open, its API server is off: check Tools > Options > Other (API port "
    "{port}), restart RoboDK, and test with: Test-NetConnection localhost -Port {port}. "
    "A limited licence may also block the API (check Help)."
)


class RoboDKUnavailable(RuntimeError):
    """RoboDK, its station, or the robodk package is not ready. The message says what to do."""


@dataclass
class RoboDKModules:
    robolink: ModuleType
    robomath: ModuleType


def load_robodk_modules() -> RoboDKModules:
    try:
        return RoboDKModules(
            robolink=importlib.import_module("robodk.robolink"),
            robomath=importlib.import_module("robodk.robomath"),
        )
    except ImportError as error:
        raise RoboDKUnavailable(f"the robodk package is missing ({error}). Run: python -m pip install robodk") from error


def robodk_api_listening(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def connect_robodk(
    settings: RoboDKSettings,
    modules: RoboDKModules | None = None,
    api_listening: Callable[[str, int], bool] | None = None,
    say: Callable[[str], None] = print,
) -> RoboDKRobot:
    wanted_robot = f"robot {settings.robot_name!r}" if settings.robot_name else "a Dobot M1 Pro or MG400 robot"
    hint = OPEN_HINT.format(robot=wanted_robot, targets=", ".join(settings.target_names.values()))
    if not (api_listening or robodk_api_listening)(settings.host, settings.port):
        api_off = API_OFF_HINT.format(port=settings.port)
        raise RoboDKUnavailable(
            f"no RoboDK API at {settings.host}:{settings.port}: RoboDK is not running, "
            f"or its API is off. {hint} {api_off}"
        )
    modules = modules or load_robodk_modules()
    robolink = modules.robolink
    rdk = robolink.Robolink(robodk_ip=settings.host, port=settings.port)
    robot = _find_robot(rdk, robolink, settings, hint)
    targets = {}
    for cell_name, station_name in settings.target_names.items():
        target = rdk.Item(station_name, robolink.ITEM_TYPE_TARGET)
        if not target.Valid() or target.Name() != station_name:  # Item() returns the closest match
            raise RoboDKUnavailable(f"target {station_name!r} not found in the station. {hint}")
        targets[cell_name] = target
    tool = robot.getLink(robolink.ITEM_TYPE_TOOL)
    return RoboDKRobot(rdk, modules, robot, targets, settings, tool if tool.Valid() else None, say)


def _find_robot(rdk: Any, robolink: ModuleType, settings: RoboDKSettings, hint: str) -> Any:
    robots = rdk.ItemList(robolink.ITEM_TYPE_ROBOT)
    names = [robot.Name() for robot in robots]
    if settings.robot_name is not None:
        chosen = [robot for robot in robots if robot.Name() == settings.robot_name]
    else:
        chosen = [r for r in robots if any(k in r.Name() for k in settings.robot_name_keywords)]
    if len(chosen) == 1:
        return chosen[0]
    wanted = settings.robot_name or f"a name containing one of {list(settings.robot_name_keywords)}"
    if not chosen:
        use_anyway = (
            f" To use {names[0]!r} anyway, set robodk.robot_name to {names[0]!r} in hardware.json."
            if names
            else ""
        )
        raise RoboDKUnavailable(
            f"no robot with {wanted} in the open station (robots found: {names}). {hint}{use_anyway}"
        )
    raise RoboDKUnavailable(f"several robots match ({names}); set robodk.robot_name in hardware.json")


class RoboDKRobot:
    """RobotDriver for RoboDK. Moves are blocking: MoveJ/MoveL return when the motion is done."""

    def __init__(
        self,
        rdk: Any,
        modules: RoboDKModules,
        robot: Any,
        targets: dict[str, Any],
        settings: RoboDKSettings,
        tool: Any | None,
        say: Callable[[str], None] = print,
    ) -> None:
        self.rdk = rdk
        self.robolink = modules.robolink
        self.robomath = modules.robomath
        self.robot = robot
        self.targets = targets
        self.settings = settings
        self.tool = tool
        self.say = say
        self.name = robot.Name()
        self.at_target: str | None = None
        self._held: Any | None = None  # object attached to the tool
        self._placed: tuple[Any, Any] | None = None  # (object, its start pose) after a place

    def enable(self) -> None:
        self.rdk.setRunMode(self.robolink.RUNMODE_SIMULATE)  # never drive a connected real robot
        self.rdk.setSimulationSpeed(self.settings.simulation_speed)

    def move_to(self, target_name: str) -> None:
        if target_name == "pick_above" and self._placed is not None:
            self._bring_next_item()
        base_name = APPROACH_OF.get(target_name, target_name)
        if base_name not in self.targets:
            raise RobotError(f"no RoboDK target for {target_name!r}")
        base = self.targets[base_name]
        vertical = self._is_vertical_move(target_name)
        try:
            if TAUGHT_APPROACH.get(target_name) in self.targets:
                goal = self.targets[TAUGHT_APPROACH[target_name]]
            elif target_name in APPROACH_OF:
                self.robot.setPoseFrame(base.Parent())
                goal = self.robomath.transl(0, 0, self.settings.approach_dz_mm) * base.Pose()
            else:
                goal = base
            if vertical:
                self.robot.MoveL(goal)
            else:
                self.robot.MoveJ(goal)
        except Exception as error:  # TargetReachError, StoppedError, InputError, lost connection
            raise RobotError(f"RoboDK could not move to {target_name}: {type(error).__name__}: {error}") from error
        self.at_target = target_name

    def set_vacuum(self, on: bool) -> None:
        state = "ON" if on else "OFF"
        self.say(f"[ROBODK SIMULATION] vacuum {state} at {self.at_target}")
        self.rdk.ShowMessage(f"cell_sim: vacuum {state} at {self.at_target}", False)
        if self.tool is None or not self.settings.attach_object_keyword:
            return
        if on:
            keyword = LID_OBJECT_KEYWORD if self.at_target == "lid" else self.settings.attach_object_keyword
            held = self.tool.AttachClosest(keyword, self.settings.attach_tolerance_mm)
            if held.Valid():
                self._held = (held, held.PoseAbs())
            else:
                self.say(f"[ROBODK SIMULATION] no object named '*{keyword}*' near the tool to attach")
        elif self._held is not None:
            self.tool.DetachAll()
            self._placed, self._held = self._held, None

    def current_pose(self) -> Pose:
        x_mm, y_mm, z_mm, _rx_deg, _ry_deg, rz_deg = self.robomath.pose_2_xyzrpw(self.robot.Pose())
        return Pose(x_mm, y_mm, z_mm, rz_deg)

    def stop(self) -> None:
        try:
            self.robot.Stop()
        except Exception:  # stop must never raise
            pass

    def close(self) -> None:
        """Leave RoboDK open; the station stays as it is."""

    def has_target(self, step: str) -> bool:
        """Lid targets are optional: without them the sequencer skips the lid moves."""
        return APPROACH_OF.get(step, step) in self.targets

    def _is_vertical_move(self, target_name: str) -> bool:
        """Straight up or down between a target and its approach point uses MoveL."""
        pairs = VERTICAL_PAIRS
        return (self.at_target, target_name) in pairs or (target_name, self.at_target) in pairs

    def _bring_next_item(self) -> None:
        """Move the placed object back to the pick point: the next item has arrived."""
        placed_object, start_pose = self._placed
        placed_object.setPoseAbs(start_pose)
        self._placed = None
