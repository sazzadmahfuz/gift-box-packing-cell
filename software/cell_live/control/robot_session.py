"""One real-robot session per run: Choton's robot_lib.Robot on our controlled connections.

robot_lib.Robot.__init__ does `from dobot_api import DobotApiDashboard, DobotApiMove` inside
the function. While the Robot is built, a stand-in `dobot_api` module whose two classes are
our ControlDashboard / ControlMove is put in sys.modules, so his __init__ (ClearError,
EnableRobot, SpeedFactor, SetArmOrientation) runs unchanged over sockets DobotLink opened.
His files are never edited. This file is the only place a Robot is created.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

from .robot_client import ControlConnectionLost, ControlPolicy, ControlRefused, RobotRefused, client_classes

LOST_HINT = "use the physical emergency stop: the outputs could not be switched off from this PC"
FRESH_FEEDBACK_S = 5.0  # a feedback packet younger than this shows the robot as it is now (packets every 2 s)


class SessionError(RuntimeError):
    """The robot session could not start."""


@dataclass(frozen=True)
class SessionValues:
    speed_percent: int
    vacuum_do: int
    blow_do: int
    belt_do: int  # object belt start and stop (DO3, ENA of its driver)
    belt_on_value: int
    belt_dir_do: int  # object belt direction (DO4, DIR of its driver)
    belt_dir_forward_value: int
    belt_enable_do: int  # object belt enable (DO16)
    belt_enable_on_value: int
    box_belt_do: int | None
    reach_min_mm: float
    reach_max_mm: float
    move_port: int
    reply_timeout_s: float

    def off_levels(self) -> dict[int, int]:
        """Every on/off output of the cell and its off level, in the order they go off: the object belt first
        (stop, then its enable), then suction and blow-off. DO4 (direction) is not on/off: it is left alone."""
        levels = {self.belt_do: 1 - self.belt_on_value, self.belt_enable_do: 1 - self.belt_enable_on_value,
                  self.vacuum_do: 0, self.blow_do: 0}
        if self.box_belt_do is not None:
            levels[self.box_belt_do] = 0
        return levels

    def start_levels(self) -> list[tuple[int, int, str]]:
        """Set at the session start, in this order and before any move: belt stopped, forward, enabled."""
        return [(self.belt_do, 1 - self.belt_on_value, "object belt stopped"),
                (self.belt_dir_do, self.belt_dir_forward_value, "object belt forward"),
                (self.belt_enable_do, self.belt_enable_on_value, "object belt enabled")]


def lowest_taught_z_mm(robot: dict[str, Any]) -> float:
    heights = [robot.get(key) for key in ("travel_z", "pick_z", "place_z", "lid_pick_z", "lid_place_z")]
    heights += list((robot.get("pick_z_by_type") or {}).values())
    home = robot.get("home") or []
    heights += [home[2]] if len(home) > 2 else []
    numbers = [float(z) for z in heights if isinstance(z, (int, float)) and not isinstance(z, bool)]
    if not numbers:
        raise SessionError("no taught heights in Choton's settings.json")
    return min(numbers)


class RobotSession:
    def __init__(self, link: Any, choton: Any, settings: dict[str, Any], values: SessionValues,
                 log: Callable[[int, str, str], None], load_api: Callable[[], Any]) -> None:
        self.link = link
        self.choton = choton
        self.settings = settings
        self.values = values
        self.log = log
        self.load_api = load_api
        self.robot: Any = None
        self.policy: ControlPolicy | None = None
        self.problem = ""

    # Opening and closing

    def open(self) -> list[str]:
        """Choton's enable sequence, then the object belt's start levels. Returns what was set, for the run log."""
        robot = self.settings["robot"]
        self.policy = ControlPolicy(
            speed_percent=self.values.speed_percent,
            off_levels=self.values.off_levels(),
            reach_min_mm=self.values.reach_min_mm,
            reach_max_mm=self.values.reach_max_mm,
            z_min_mm=lowest_taught_z_mm(robot),
            arm_codes=frozenset({int(robot["arm_left_code"])}) if robot.get("arm_left_code") is not None else frozenset({0}),
            fixed_levels={self.values.belt_dir_do: self.values.belt_dir_forward_value},
        )
        try:
            api = self.load_api()
        except Exception as error:
            raise SessionError(f"dobot_api not available: {error}") from error
        dashboard_class, move_class, self._opened = client_classes(
            api, self.link, self.policy, self.log, self.values.move_port, self.values.reply_timeout_s
        )
        stand_in = ModuleType("dobot_api")
        stand_in.DobotApiDashboard, stand_in.DobotApiMove = dashboard_class, move_class
        previous = sys.modules.get("dobot_api")
        sys.modules["dobot_api"] = stand_in
        self.link.control_session = self  # before the first command: the robot keeps one 29999 client, a check must not connect
        try:
            self.robot = self.choton.robot_lib.Robot(self.settings, run=True, speed=self.values.speed_percent)
        except Exception as error:  # EnableRobot refused, robot held or unreachable, refused command
            self._close_sockets()
            self.link.control_session = None
            raise SessionError(f"the robot did not start: {type(error).__name__}: {error}") from error
        finally:
            if previous is None:
                sys.modules.pop("dobot_api", None)
            else:
                sys.modules["dobot_api"] = previous
        set_now = []
        try:
            for channel, level, words in self.values.start_levels():  # nothing is queued yet: DO acts at once
                self.robot.dash.DO(channel, level)
                set_now.append(f"DO{channel} = {level} ({words})")
        except (ControlRefused, ControlConnectionLost, RobotRefused) as error:
            self.close()  # outputs off, robot disabled, sockets closed
            raise SessionError(f"the object belt start levels were not set ({', '.join(set_now) or 'none set'}): {error}") from error
        return set_now

    def close(self) -> list[str]:
        """Outputs off, then Choton's close (DO off, DisableRobot, sockets closed). Never raises."""
        reports = self.outputs_off() if self.robot is not None else []
        if self.robot is not None:
            try:
                self.robot.close()
            except Exception as error:
                reports.append(f"robot close: {error}")
        self._close_sockets()
        if self.link.control_session is self:
            self.link.control_session = None
        self.robot = None
        return reports

    # Motion (Choton's functions)

    def home(self) -> None:
        self.robot.home()

    def pick_and_place(self, x_mm: float, y_mm: float, slot: Any, name: str, kind: str, turn_deg: float) -> None:
        """Via the box slot first (requested by Sazzad, approved by the teacher Leo, 17 Nov): a straight MovL
        from home to the object belt needs J1 up to 90 deg in the left arm (controller alarm 23,
        testing/live_runs/20261117_190902.csv). Home -> above the box slot keeps J1 <= 82.3 deg, and from
        there J1 changes steadily to the item's own value. After the first pick the robot is already there."""
        robot = self.settings["robot"]
        travel_z_mm = robot["travel_z"]
        self.policy.check("move", f"MovL({x_mm},{y_mm},{travel_z_mm},{robot.get('r_angle', 0)})")  # refused: nothing is sent
        self.robot.movl(slot[0], slot[1], travel_z_mm, "via the box slot (keeps J1 inside its range)")
        self.robot.pick_and_place(x_mm, y_mm, slot, name, kind, turn_deg)

    def place_lid(self, x_mm: float, y_mm: float, slot: Any, turn_deg: float) -> None:
        self.robot.place_lid(x_mm, y_mm, slot, turn_deg)

    def set_output(self, channel: int, level: int, description: str) -> None:
        self.robot.do(channel, level, description)  # Choton's do(): Sync first, then DO

    # Stopping

    def outputs_off(self) -> list[str]:
        """Every cell output to its off level now: DOExecute (immediate), DO if refused. Never raises."""
        reports = []
        for channel, level in self.values.off_levels().items():
            reports.append(self._switch_off(channel, level))
        return reports

    def _switch_off(self, channel: int, level: int) -> str:
        dashboard = getattr(self.robot, "dash", None)
        if dashboard is None:
            return f"DO{channel}: no robot connection, {LOST_HINT}"
        try:
            dashboard.DOExecute(channel, level)
            return f"DO{channel} = {level} (DOExecute)"
        except RobotRefused:
            try:
                dashboard.DO(channel, level)
                return f"DO{channel} = {level} (DOExecute refused, queued DO used)"
            except Exception as error:
                return self._lost(channel, error)
        except Exception as error:  # ControlConnectionLost, ControlRefused, OSError
            return self._lost(channel, error)

    def _lost(self, channel: int, error: Exception) -> str:
        self.problem = f"DO{channel} not switched off: {error}"
        return f"DO{channel} NOT switched off ({error}): {LOST_HINT}"

    def software_estop(self) -> list[str]:
        """Software e-stop (not the physical one): outputs off, EmergencyStop(), unblock the move port."""
        if self.policy is not None:
            self.policy.estopped = True  # from now on every motion and output-on is refused
        reports = self.outputs_off()
        dashboard = getattr(self.robot, "dash", None)
        try:
            reply = dashboard.EmergencyStop() if dashboard is not None else ""
            reports.append(f"EmergencyStop() sent: {str(reply).strip()}")
        except Exception as error:
            reports.append(f"EmergencyStop() FAILED ({error}): press the physical emergency stop")
        move = getattr(self.robot, "move", None)
        if move is not None:
            try:
                move.close()  # a Sync() still waiting on the move port ends at once
            except Exception:
                pass
        return reports

    def alarm_text(self) -> str:
        """The robot's alarms in words (Choton's explain_error)."""
        try:
            return self.choton.robot_lib.explain_error(self.robot.dash.GetErrorID())
        except Exception as error:
            return f"alarm text not readable: {error}"

    def alarm_that_stopped_a_move(self) -> str:
        """After a move reply that never came: the robot's alarm text, or '' if none is known.
        The dashboard is asked only when the newest feedback packet (30004, read by the checks every
        2 s) is fresh and says ErrorStatus = 1: the robot is there and stopped its moves (17 Nov:
        alarm 23). Without that, the connection may really be lost and is not waited for again."""
        packet, age_s = getattr(self.link, "last_packet", None), getattr(self.link, "packet_age_s", lambda: None)()
        if packet is None or age_s is None or age_s > FRESH_FEEDBACK_S or not packet.fields.get("error_status"):
            return ""
        text = self.alarm_text()
        return "" if text in ("", "no error") or text.startswith("alarm text not readable") else text

    def clear_alarm(self) -> str:
        """Operator action after an alarm or the software e-stop: ClearError and continue, no motion."""
        text = self.alarm_text()
        try:
            self.robot.dash.ClearError()
            self.robot.dash.Continue()
        except (ControlConnectionLost, ControlRefused, RobotRefused) as error:
            return f"alarm was: {text}; clearing failed: {error}"
        return f"alarm was: {text}; ClearError sent"

    def describe(self) -> str:
        state = "software e-stop active" if self.policy is not None and self.policy.estopped else "in use by the running cycle"
        return state + (f"; last problem: {self.problem}" if self.problem else "")

    def _close_sockets(self) -> None:
        for client in getattr(self, "_opened", []):
            try:
                client.close()
            except Exception:
                pass
