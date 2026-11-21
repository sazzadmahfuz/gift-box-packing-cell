"""Robot clients for a real run: Dobot's own command strings, our sockets, our allowlist.

ControlDashboard / ControlMove subclass the vendor dobot_api clients (so every string is
exactly Dobot's), but skip the vendor constructor (it would open its own socket) and replace
sendRecvMsg:
  1. ControlPolicy refuses everything outside the run's allowlist before it is sent;
  2. one lock per socket, so a Sync() waiting on the move port never blocks the dashboard
     (the software e-stop goes out on the dashboard at once);
  3. a missing, late or empty reply RAISES (vendor dobot_api returns "" and robot_lib.sync()
     does not check it, which would let the cycle go on as if a move had finished);
  4. every command and reply goes to the run log.
"""

from __future__ import annotations

import math
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from cell_sim.drivers.dobot_tcp_robot import parse_reply

DASHBOARD_COMMANDS = frozenset({
    "ClearError", "EnableRobot", "DisableRobot", "RobotMode", "GetErrorID", "GetPose", "SpeedFactor",
    "SetArmOrientation", "DO", "DOExecute", "DI", "continue", "EmergencyStop",
})
MOVE_COMMANDS = frozenset({"MovL", "Sync"})  # never MovJ: on the M1 Pro it flipped the arm (Choton, 12 Nov)
AFTER_ESTOP = frozenset({"ClearError", "continue", "GetErrorID", "RobotMode", "GetPose", "DisableRobot", "DO", "DOExecute", "EmergencyStop"})
CHECKED_REPLIES = frozenset({"DO", "DOExecute", "SpeedFactor", "SetArmOrientation", "Sync", "EmergencyStop", "ClearError", "continue"})


class ControlRefused(RuntimeError):
    """Our safety layer refused the command. Nothing was sent."""


class RobotRefused(RuntimeError):
    """The robot answered with an error code."""


class ControlConnectionLost(ConnectionError):
    """No reply in time, or the robot closed the connection."""


def split_command(command: str) -> tuple[str, list[str]]:
    name, _, rest = command.partition("(")
    inside = rest.rsplit(")", 1)[0]
    return name.strip(), [part.strip() for part in inside.split(",") if part.strip()]


@dataclass
class ControlPolicy:
    speed_percent: int
    off_levels: dict[int, int]  # output channel -> level that means "off" (DO3: the belt-stopped level)
    reach_min_mm: float
    reach_max_mm: float
    z_min_mm: float  # lowest taught height: no MovL may go below it
    arm_codes: frozenset[int] = field(default_factory=lambda: frozenset({0}))
    fixed_levels: dict[int, int] = field(default_factory=dict)  # outputs set to one level only (DO4: forward)
    estopped: bool = False

    def check(self, port_kind: str, command: str) -> None:
        name, args = split_command(command)
        allowed = MOVE_COMMANDS if port_kind == "move" else DASHBOARD_COMMANDS
        if name not in allowed:
            raise ControlRefused(f"{name} is not allowed on the {port_kind} port (run allowlist)")
        if self.estopped and (port_kind == "move" or name not in AFTER_ESTOP):
            raise ControlRefused(f"{name} refused: the software e-stop is active")
        try:
            numbers = [float(arg) for arg in args]
        except ValueError as error:
            raise ControlRefused(f"{command!r} has arguments that are not numbers") from error
        if name in ("DO", "DOExecute"):
            self._check_output(command, numbers)
        elif name == "SpeedFactor" and (len(numbers) != 1 or int(numbers[0]) != self.speed_percent):
            raise ControlRefused(f"{command} refused: the armed speed is {self.speed_percent} %")
        elif name == "SetArmOrientation" and (len(numbers) != 1 or int(numbers[0]) not in self.arm_codes):
            raise ControlRefused(f"{command} refused: arm orientation must be one of {sorted(self.arm_codes)}")
        elif name == "MovL":
            self._check_target(command, numbers)

    def _check_output(self, command: str, numbers: list[float]) -> None:
        if len(numbers) != 2:
            raise ControlRefused(f"{command} refused: needs an output and a level")
        channel, level = int(numbers[0]), int(numbers[1])
        if channel not in self.off_levels and channel not in self.fixed_levels:
            outputs = sorted({*self.off_levels, *self.fixed_levels})
            raise ControlRefused(f"{command} refused: DO{channel} is not one of the cell outputs {outputs}")
        if level not in (0, 1):
            raise ControlRefused(f"{command} refused: level must be 0 or 1")
        if channel in self.fixed_levels:  # the belt direction: set at the start, never changed by the run
            if self.estopped or level != self.fixed_levels[channel]:
                raise ControlRefused(f"{command} refused: DO{channel} may only be set to {self.fixed_levels[channel]}, "
                                     "and not after the software e-stop")
        elif self.estopped and level != self.off_levels[channel]:
            raise ControlRefused(f"{command} refused: only switching outputs off is allowed after the software e-stop")

    def _check_target(self, command: str, numbers: list[float]) -> None:
        if len(numbers) < 4:
            raise ControlRefused(f"{command} refused: needs x, y, z, r")
        x_mm, y_mm, z_mm = numbers[:3]
        distance_mm = math.hypot(x_mm, y_mm)
        if not self.reach_min_mm <= distance_mm <= self.reach_max_mm:
            raise ControlRefused(f"{command} refused: {distance_mm:.1f} mm from the robot, allowed {self.reach_min_mm:g}-{self.reach_max_mm:g} mm")
        if z_mm < self.z_min_mm:
            raise ControlRefused(f"{command} refused: z {z_mm:.1f} mm is below the lowest taught height {self.z_min_mm:g} mm")


Logger = Callable[[int, str, str], None]  # port, command, reply


def read_reply(connection: socket.socket, port: int, command: str) -> str:
    data = b""
    while not data.rstrip().endswith(b";"):
        try:
            chunk = connection.recv(1024)
        except socket.timeout as error:
            raise ControlConnectionLost(f"no reply to {command} on port {port} in time") from error
        except OSError as error:
            raise ControlConnectionLost(f"connection on port {port} lost during {command}: {error}") from error
        if not chunk:
            raise ControlConnectionLost(f"the robot closed port {port} during {command}")
        data += chunk
    return data.decode("utf-8", errors="replace")


def client_classes(api: Any, link: Any, policy: ControlPolicy, log: Logger, move_port: int, reply_timeout_s: float):
    """The two classes robot_lib.Robot will construct, bound to this run's link, policy and log."""
    opened: list[Any] = []
    expected_ports = {"dashboard": link.dashboard_port, "move": move_port}

    def setup(client: Any, ip: str, port: int) -> None:
        client.socket_dobot = 0  # first: the vendor __del__ reads it even if we refuse below
        if ip != link.ip or port != expected_ports[client.port_kind]:
            raise ControlRefused(f"robot_lib asked for {ip}:{port}, the configured robot is {link.ip}:{expected_ports[client.port_kind]}")
        client.ip, client.port, client.text_log = ip, port, None
        client._DobotApi__globalLock = threading.Lock()  # vendor name-mangled lock, unused here
        client.socket_lock = threading.Lock()
        client.socket_dobot = link.open_control_socket(port, reply_timeout_s)
        opened.append(client)

    def send(client: Any, command: str) -> str:
        policy.check(client.port_kind, command)
        with client.socket_lock:
            try:
                client.socket_dobot.sendall(command.encode("utf-8"))
            except OSError as error:
                raise ControlConnectionLost(f"cannot send {command} on port {client.port}: {error}") from error
            reply = read_reply(client.socket_dobot, client.port, command)
        log(client.port, command, reply.strip())
        name = split_command(command)[0]
        code, _inside = parse_reply(reply)
        if name in CHECKED_REPLIES and code != 0:
            raise RobotRefused(f"robot refused {command}: {reply.strip()}")
        return reply

    class ControlDashboard(api.DobotApiDashboard):
        port_kind = "dashboard"

        def __init__(self, ip: str, port: int) -> None:  # called inside robot_lib.Robot.__init__
            setup(self, ip, port)

        def sendRecvMsg(self, string: str) -> str:
            return send(self, string)

    class ControlMove(api.DobotApiMove):
        port_kind = "move"

        def __init__(self, ip: str, port: int) -> None:
            setup(self, ip, port)

        def sendRecvMsg(self, string: str) -> str:
            return send(self, string)

    return ControlDashboard, ControlMove, opened
