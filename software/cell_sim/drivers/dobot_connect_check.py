"""Read-only connection check for the Dobot M1 Pro: python -m cell_sim connect-check

Opens the dashboard port (29999) and the feedback port (30004), sends only GetErrorID(),
RobotMode() and GetPose(), reads one feedback packet, prints what it got, and closes.
It never enables the robot, never sets an output and never sends a move: every dashboard
command goes through an allowlist that refuses anything else before it is sent.
"""

from __future__ import annotations

import contextlib
import io
import socket
from typing import Any, Callable

from ..hardware_config import DobotSettings
from .dobot_tcp_robot import QuietLog, load_dobot_api, parse_reply, reply_numbers

LABEL = "CONNECT-CHECK, read-only"
READ_ONLY_COMMANDS = frozenset({"GetErrorID()", "RobotMode()", "GetPose()"})
FEEDBACK_PACKET_BYTES = 1440  # TCP-IP-4Axis-Python-main/main.py GetFeed
FEEDBACK_TEST_VALUE = 0x123456789ABCDEF  # main.py GetFeed: a packet is valid if test_value matches
# TCP-IP-4Axis-Python-main/ui.py LABEL_ROBOT_MODE (3 is blank there)
ROBOT_MODE_NAMES = {
    1: "ROBOT_MODE_INIT", 2: "ROBOT_MODE_BRAKE_OPEN", 4: "ROBOT_MODE_DISABLED", 5: "ROBOT_MODE_ENABLE",
    6: "ROBOT_MODE_BACKDRIVE", 7: "ROBOT_MODE_RUNNING", 8: "ROBOT_MODE_RECORDING", 9: "ROBOT_MODE_ERROR",
    10: "ROBOT_MODE_PAUSE", 11: "ROBOT_MODE_JOG",
}
EXIT_OK, EXIT_UNREACHABLE, EXIT_ROBOT_ERROR = 0, 3, 4
UNREACHABLE_HINT = (
    "Check: Ethernet cable in LAN1, PC address 192.168.1.x, robot powered, DobotStudio Pro set to "
    "TCP/IP secondary development mode, and no other program holding the port."
)


class ReadOnlyViolation(RuntimeError):
    pass


def guard_read_only(client: Any) -> None:
    """Make the client refuse every command that is not on the read-only list."""
    send = client.sendRecvMsg

    def guarded(command: str) -> str:
        if command not in READ_ONLY_COMMANDS:
            raise ReadOnlyViolation(f"connect-check may not send {command!r}")
        return send(command)

    client.sendRecvMsg = guarded


def connect_check(settings: DobotSettings, api: Any = None, say: Callable[[str], None] = print) -> int:
    api = api or load_dobot_api(settings.api_path)
    ip = settings.robot_ip
    say(f"[{LABEL}] robot {ip}: no commands that enable, move or switch outputs are sent")
    previous_timeout_s = socket.getdefaulttimeout()
    socket.setdefaulttimeout(settings.connect_timeout_s)
    dashboard = feed = None
    try:
        try:
            with contextlib.redirect_stdout(io.StringIO()):  # dobot_api prints socket errors itself
                dashboard = api.DobotApiDashboard(ip, settings.dashboard_port, QuietLog())
                feed = api.DobotApi(ip, settings.feedback_port, QuietLog())
        except Exception as error:
            say(f"[{LABEL}] cannot connect to {ip}: {error}. {UNREACHABLE_HINT}")
            return EXIT_UNREACHABLE
        guard_read_only(dashboard)
        robot_error = _report_dashboard(dashboard, say)
        robot_error = _report_feedback(api, feed, say, settings.vacuum_do) or robot_error
    finally:
        for client in (dashboard, feed):
            if client is not None:
                client.close()
        socket.setdefaulttimeout(previous_timeout_s)
    say(f"[{LABEL}] connections closed")
    return EXIT_ROBOT_ERROR if robot_error else EXIT_OK


def _report_dashboard(dashboard: Any, say: Callable[[str], None]) -> bool:
    """Print error ID, robot mode and pose from port 29999. Return True if the robot reports an error."""
    error_reply = dashboard.GetErrorID()
    mode_reply = dashboard.RobotMode()
    pose_reply = dashboard.GetPose()
    if not error_reply:
        say(f"[{LABEL}] no reply on the dashboard port (timeout)")
        return True
    _code, error_inside = parse_reply(error_reply)
    error_ids = [int(n) for n in reply_numbers(error_inside)]
    say(f"[{LABEL}] GetErrorID: {error_reply.strip()} -> " + (f"errors {error_ids}" if error_ids else "no errors"))
    mode_numbers = reply_numbers(parse_reply(mode_reply)[1])
    mode = int(mode_numbers[0]) if mode_numbers else None
    say(f"[{LABEL}] RobotMode: {mode_reply.strip()} -> {mode} {ROBOT_MODE_NAMES.get(mode, 'unknown')}")
    pose = reply_numbers(parse_reply(pose_reply)[1])[:4]
    pose_text = f"x={pose[0]} y={pose[1]} z={pose[2]} mm r={pose[3]} deg" if len(pose) == 4 else "no pose"
    say(f"[{LABEL}] GetPose: {pose_reply.strip()} -> {pose_text}")
    return bool(error_ids) or mode == 9


def _report_feedback(api: Any, feed: Any, say: Callable[[str], None], vacuum_do: int | None = None) -> bool:
    """Read one feedback packet from port 30004. Return True if it shows an error or is invalid."""
    data = b""
    try:
        while len(data) < FEEDBACK_PACKET_BYTES:
            chunk = feed.socket_dobot.recv(FEEDBACK_PACKET_BYTES - len(data))
            if not chunk:
                break
            data += chunk
    except OSError as error:
        say(f"[{LABEL}] feedback port: no packet ({error})")
        return True
    if len(data) < FEEDBACK_PACKET_BYTES:
        say(f"[{LABEL}] feedback port: short packet ({len(data)} of {FEEDBACK_PACKET_BYTES} bytes)")
        return True
    info = api.np.frombuffer(data, dtype=api.MyType)
    if int(info["test_value"][0]) != FEEDBACK_TEST_VALUE:
        say(f"[{LABEL}] feedback port: invalid packet (test_value {hex(int(info['test_value'][0]))})")
        return True
    mode = int(info["robot_mode"][0])
    tool = [round(float(v), 3) for v in info["tool_vector_actual"][0][:4]]
    enabled, errored = int(info["EnableStatus"][0][0]), int(info["ErrorStatus"][0][0])
    say(
        f"[{LABEL}] feedback: robot_mode={mode} {ROBOT_MODE_NAMES.get(mode, 'unknown')}, "
        f"tool_vector_actual x,y,z,r={tool}, EnableStatus={enabled}, ErrorStatus={errored}"
    )
    for name, field in (("digital outputs", "digital_outputs"), ("digital inputs", "digital_input_bits")):
        bits = int(info[field][0]) & 0xFFFFFFFFFFFFFFFF
        say(f"[{LABEL}] {name}: 0x{bits:X}, ON: {on_channels(bits) or 'none'} {BIT_ORDER_NOTE}")
    if vacuum_do is not None:
        state = "ON" if vacuum_do in on_channels(int(info["digital_outputs"][0])) else "OFF"
        say(f"[{LABEL}] vacuum output DO{vacuum_do} (hardware.json, ASSUMED channel) reads {state}")
    return errored != 0


BIT_ORDER_NOTE = "(ASSUMED bit 0 = channel 1)"


def on_channels(bits: int) -> list[int]:
    """1-based channel numbers whose bit is set (bit 0 = channel 1, ASSUMED)."""
    bits &= 0xFFFFFFFFFFFFFFFF
    return [index + 1 for index in range(64) if bits >> index & 1]
