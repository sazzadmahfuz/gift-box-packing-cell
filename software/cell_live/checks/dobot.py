"""Dobot dashboard (29999) and feedback (30004) checks. Read-only, through DobotLink only."""

from __future__ import annotations

from cell_sim.drivers.dobot_connect_check import ROBOT_MODE_NAMES, on_channels
from cell_sim.drivers.dobot_tcp_robot import parse_reply, reply_numbers

from ..adapters.choton import AlarmTexts, parse_error_lists
from ..dobot_link import DobotLink, RobotHeld, RobotUnreachable
from ..status import FAIL, OK, WARN, CheckResult, missing_package, now_s

DASHBOARD_COMMANDS = ("RobotMode()", "GetErrorID()", "GetPose()")
ROBOT_MODE_ERROR = 9  # ROBOT_MODE_ERROR in Dobot's ui.py LABEL_ROBOT_MODE


def connection_failure(error: Exception) -> CheckResult:
    reason = "held" if isinstance(error, RobotHeld) else "unreachable"
    lead = "Robot is held by another program" if reason == "held" else "Robot unreachable"
    return CheckResult(FAIL, f"{lead}: {error}", data={"reason": reason})


class DashboardCheck:
    id = "dobot_dashboard"
    name = "Dobot dashboard (port 29999)"

    def __init__(self, link: DobotLink, alarms: AlarmTexts, interval_s: float) -> None:
        self.link = link
        self.alarms = alarms
        self.interval_s = interval_s

    def run(self) -> CheckResult:
        session = self.link.control_session
        if session is not None:  # a run holds 29999: no extra dashboard commands (pose: see feedback)
            healthy = not session.problem
            return CheckResult(OK if healthy else FAIL, f"Dashboard {session.describe()}", data={"in_use_by_run": True})
        try:
            replies = self.link.query_all(DASHBOARD_COMMANDS)
        except (RobotHeld, RobotUnreachable) as error:
            return connection_failure(error)
        mode_numbers = reply_numbers(parse_reply(replies["RobotMode()"].text)[1])
        mode = int(mode_numbers[0]) if mode_numbers else None
        mode_name = ROBOT_MODE_NAMES.get(mode, "unknown mode") if mode is not None else "no mode in reply"
        try:
            alarm_ids = parse_error_lists(parse_reply(replies["GetErrorID()"].text)[1])
        except ValueError:
            alarm_ids = []
        alarm_words = self.alarms.describe(alarm_ids)
        pose = reply_numbers(parse_reply(replies["GetPose()"].text)[1])[:4]
        latency_ms = sum(reply.latency_ms for reply in replies.values())
        data = {
            "robot_mode": mode,
            "robot_mode_name": mode_name,
            "alarms": alarm_words,
            "alarm_ids": alarm_ids,
            "pose_xyzr": pose,
            "alarm_text_source": self.alarms.problem or "Dobot alarm lists",
            "raw": {command: reply.text.strip() for command, reply in replies.items()},
        }
        if alarm_words or mode == ROBOT_MODE_ERROR:
            shown = "; ".join(alarm_words) if alarm_words else "robot mode ERROR"
            return CheckResult(WARN, f"Connected, robot reports an alarm: {shown}", latency_ms, data)
        return CheckResult(OK, f"Connected; robot mode {mode} {mode_name}; no alarms", latency_ms, data)


class FeedbackCheck:
    id = "dobot_feedback"
    name = "Dobot feedback (port 30004)"

    def __init__(self, link: DobotLink, interval_s: float) -> None:
        self.link = link
        self.interval_s = interval_s

    def run(self) -> CheckResult:
        try:
            packet = self.link.read_feedback()
        except ModuleNotFoundError as error:
            return missing_package("numpy (for dobot_api)", f"python -m pip install numpy  ({error})")
        except (RobotHeld, RobotUnreachable) as error:
            return connection_failure(error)
        fields = packet.fields
        if not fields["valid"]:
            return CheckResult(FAIL, f"Packet received but invalid (test_value {fields['test_value_hex']})", packet.latency_ms)
        data = {
            "pose_xyzr": fields["pose_xyzr"],
            "robot_mode": fields["robot_mode"],
            "robot_mode_name": ROBOT_MODE_NAMES.get(fields["robot_mode"], "unknown mode"),
            "digital_outputs_on": on_channels(fields["digital_outputs"]),
            "digital_inputs_on": on_channels(fields["digital_inputs"]),
            "bit_order": "bit 0 = channel 1 (CONFIRM)",
            "enable_status": fields["enable_status"],
            "error_status": fields["error_status"],
            "packet_age_s": 0.0,
            "received_at": round(now_s(), 3),  # wall clock, so the age can be worked out between checks
        }
        x_mm, y_mm, z_mm, r_deg = fields["pose_xyzr"]
        summary = f"pose x={x_mm} y={y_mm} z={z_mm} mm r={r_deg} deg; enabled={fields['enable_status']}"
        if fields["error_status"]:
            return CheckResult(WARN, f"Packet OK, robot ErrorStatus=1; {summary}", packet.latency_ms, data)
        return CheckResult(OK, f"Packet OK; {summary}", packet.latency_ms, data)
