"""The one owner of the Dobot sockets.

Checks: only the commands in READ_ONLY_COMMANDS (RobotMode, GetErrorID, GetPose,
shared with cell_sim's connect-check) can be sent; anything else is refused before a socket is
opened. Check sockets are opened per check and closed again, so DobotStudio or Choton's program
can use the robot between checks.
Control: open_control_socket() gives control/robot_session.py the persistent run
sockets (dashboard and move port), only after the safety gate passed; control/robot_client.py
decides what may be sent on them.

The sockets are plain standard-library sockets, not dobot_api's: dobot_api replaces the
socket error with a generic Exception, which hides the difference between "robot not
reachable" and "port held by another program". The command strings are the same ones
dobot_api sends. Decoding the 30004 packet uses dobot_api's MyType (needs numpy).
"""

from __future__ import annotations

import errno
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cell_sim.drivers.dobot_connect_check import FEEDBACK_PACKET_BYTES, FEEDBACK_TEST_VALUE, READ_ONLY_COMMANDS

UNREACHABLE_HINT = "check the cable in LAN1, this PC on 192.168.1.x, and that the robot is powered"
HELD_HINT = "another program (DobotStudio Pro or Choton's script) probably holds the port; close it and check again"
HELD_IS_A_GUESS = "(how the M1 Pro rejects a second program is CONFIRM: lab test 17 Nov, row 2)"


class ReadOnlyViolation(RuntimeError):
    """A command outside the read-only list was asked for. Nothing was sent."""


class RobotUnreachable(ConnectionError):
    pass


class RobotHeld(ConnectionError):
    """The robot answers the network, but this port is busy or silent."""


@dataclass(frozen=True)
class Reply:
    text: str
    latency_ms: float


@dataclass(frozen=True)
class FeedbackPacket:
    fields: dict[str, Any]
    received_at_s: float  # time.monotonic() when it arrived
    latency_ms: float


class DobotLink:
    def __init__(
        self,
        ip: str,
        dashboard_port: int,
        feedback_port: int,
        timeout_s: float,
        load_api: Callable[[], Any] | None = None,
        connect: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        self.ip = ip
        self.dashboard_port = dashboard_port
        self.feedback_port = feedback_port
        self.timeout_s = timeout_s
        self.load_api = load_api
        self._connect = connect
        self._lock = threading.Lock()  # one conversation with the robot at a time
        self.last_packet: FeedbackPacket | None = None  # the last valid packet
        self.last_feedback_error: tuple[float, str] | None = None  # (time.monotonic(), why the last read failed)
        self.control_session: Any = None  # the running RobotSession, which holds 29999 and 30003
        self.on_trace: Callable[[dict[str, Any]], None] | None = None  # the console's trace panel

    # Persistent sockets for a gate-approved run (control/robot_session.py only)

    def open_control_socket(self, port: int, reply_timeout_s: float) -> socket.socket:
        """A socket that stays open for the whole run. What may be sent on it is decided by
        control/robot_client.py (its allowlist), not here."""
        connection = self._open(port)
        connection.settimeout(reply_timeout_s)
        return connection

    # Dashboard (29999)

    def query(self, command: str) -> Reply:
        if command not in READ_ONLY_COMMANDS:
            raise ReadOnlyViolation(f"cell_live may not send {command!r} (read-only: {sorted(READ_ONLY_COMMANDS)})")
        with self._lock:
            start_s = time.perf_counter()
            with self._open(self.dashboard_port) as connection:
                connection.sendall(command.encode("utf-8"))
                text = self._receive_reply(connection)
            return Reply(text, (time.perf_counter() - start_s) * 1000.0)

    def query_all(self, commands: tuple[str, ...]) -> dict[str, Reply]:
        """Several read-only commands on one dashboard connection."""
        refused = [command for command in commands if command not in READ_ONLY_COMMANDS]
        if refused:
            raise ReadOnlyViolation(f"cell_live may not send {refused}")
        replies: dict[str, Reply] = {}
        try:
            with self._lock, self._open(self.dashboard_port) as connection:
                for command in commands:
                    start_s = time.perf_counter()
                    connection.sendall(command.encode("utf-8"))
                    replies[command] = Reply(self._receive_reply(connection), (time.perf_counter() - start_s) * 1000.0)
                    self._trace(self.dashboard_port, command, replies[command].text.strip(), replies[command].latency_ms)
        except (RobotHeld, RobotUnreachable) as error:
            self._trace(self.dashboard_port, ", ".join(commands), f"no reply: {error}", None)
            raise
        return replies

    def _trace(self, port: int, command: str, reply: str, latency_ms: float | None) -> None:
        if self.on_trace is not None:
            try:
                self.on_trace({"source": f"check port {port}", "command": command, "reply": reply, "latency_ms": latency_ms})
            except Exception:  # the UI must never break a check
                pass

    # Feedback (30004)

    def read_feedback(self) -> FeedbackPacket:
        """Read and decode one packet. Only a valid packet becomes last_packet; every failure is
        remembered in last_feedback_error, so the output checks can say why they see nothing."""
        try:
            api = self.load_api() if self.load_api is not None else None  # fails early if numpy is missing
            data, latency_ms = self._read_packet_bytes()
        except (RobotHeld, RobotUnreachable, ModuleNotFoundError) as error:
            self.last_feedback_error = (time.monotonic(), str(error))
            raise
        packet = FeedbackPacket(decode_feedback(api, data), time.monotonic(), latency_ms)
        if not packet.fields["valid"]:
            self.last_feedback_error = (packet.received_at_s, f"invalid packet (test_value {packet.fields['test_value_hex']})")
            return packet
        self.last_packet = packet
        self.last_feedback_error = None
        return packet

    def feedback_failed_since_last_packet(self) -> str | None:
        """Why the latest feedback read failed, if it failed after the last good packet."""
        failure = self.last_feedback_error
        if failure is None:
            return None
        failed_at_s, message = failure
        if self.last_packet is not None and self.last_packet.received_at_s > failed_at_s:
            return None
        return message

    def packet_age_s(self) -> float | None:
        return None if self.last_packet is None else time.monotonic() - self.last_packet.received_at_s

    def _read_packet_bytes(self) -> tuple[bytes, float]:
        with self._lock:
            start_s = time.perf_counter()
            with self._open(self.feedback_port) as connection:
                data = b""
                while len(data) < FEEDBACK_PACKET_BYTES:
                    try:
                        chunk = connection.recv(FEEDBACK_PACKET_BYTES - len(data))
                    except socket.timeout as error:
                        raise RobotHeld(f"port {self.feedback_port} connected but sent no packet. {HELD_HINT} {HELD_IS_A_GUESS}") from error
                    if not chunk:
                        raise RobotHeld(f"port {self.feedback_port} closed the connection. {HELD_HINT} {HELD_IS_A_GUESS}")
                    data += chunk
            return data, (time.perf_counter() - start_s) * 1000.0

    # Sockets

    def _open(self, port: int) -> socket.socket:
        try:
            connection = self._connect((self.ip, port), timeout=self.timeout_s)
        except ConnectionRefusedError as error:
            raise RobotHeld(f"{self.ip}:{port} refused the connection. {HELD_HINT}, or TCP/IP mode is off {HELD_IS_A_GUESS}") from error
        except ConnectionResetError as error:
            raise RobotHeld(f"{self.ip}:{port} reset the connection. {HELD_HINT} {HELD_IS_A_GUESS}") from error
        except (socket.timeout, TimeoutError) as error:
            raise RobotUnreachable(f"no answer from {self.ip}:{port} within {self.timeout_s:g} s: {UNREACHABLE_HINT}") from error
        except OSError as error:
            if getattr(error, "errno", None) in (errno.ECONNREFUSED, 10061):
                raise RobotHeld(f"{self.ip}:{port} refused the connection. {HELD_HINT} {HELD_IS_A_GUESS}") from error
            raise RobotUnreachable(f"cannot reach {self.ip}:{port} ({error}): {UNREACHABLE_HINT}") from error
        connection.settimeout(self.timeout_s)
        return connection

    def _receive_reply(self, connection: socket.socket) -> str:
        """Read until the reply ends with ';' (the dashboard reply form '0,{...},Cmd();')."""
        data = b""
        while not data.rstrip().endswith(b";"):
            try:
                chunk = connection.recv(1024)
            except socket.timeout as error:
                raise RobotHeld(f"port {self.dashboard_port} connected but did not answer. {HELD_HINT} {HELD_IS_A_GUESS}") from error
            except ConnectionResetError as error:
                raise RobotHeld(f"port {self.dashboard_port} reset the connection. {HELD_HINT} {HELD_IS_A_GUESS}") from error
            if not chunk:
                raise RobotHeld(f"port {self.dashboard_port} closed the connection. {HELD_HINT} {HELD_IS_A_GUESS}")
            data += chunk
        return data.decode("utf-8", errors="replace")


def decode_feedback(api: Any, data: bytes) -> dict[str, Any]:
    """The fields the checks show, decoded with dobot_api's MyType layout."""
    if api is None:
        raise RuntimeError("dobot_api is needed to decode the feedback packet")
    info = api.np.frombuffer(data, dtype=api.MyType)
    test_value = int(info["test_value"][0])
    return {
        "valid": test_value == FEEDBACK_TEST_VALUE,
        "test_value_hex": hex(test_value),
        "robot_mode": int(info["robot_mode"][0]),
        "pose_xyzr": [round(float(v), 3) for v in info["tool_vector_actual"][0][:4]],
        "digital_inputs": int(info["digital_input_bits"][0]) & 0xFFFFFFFFFFFFFFFF,
        "digital_outputs": int(info["digital_outputs"][0]) & 0xFFFFFFFFFFFFFFFF,
        "enable_status": int(info["EnableStatus"][0][0]),
        "error_status": int(info["ErrorStatus"][0][0]),
    }


def dobot_api_loader(api_path: Path) -> Callable[[], Any]:
    """Lazy loader for dobot_api (needs numpy and tkinter); raises with the install command."""

    def load() -> Any:
        from cell_sim.drivers.dobot_tcp_robot import DobotUnavailable, load_dobot_api

        try:
            return load_dobot_api(api_path)
        except DobotUnavailable as error:
            raise ModuleNotFoundError(str(error)) from error

    return load
