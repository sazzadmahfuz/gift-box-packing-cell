"""Outputs-off stop while no run is active: the SOFTWARE STOP and the "Stop object belt" button.

Only DOExecute(channel, off level) is sent: DO3 (belt stop level) and DO16 (enable off) for the
object belt, DO1 and DO2 (suction, blow-off) for the gripper. No motion, no enabling, no robot
e-stop: the arm is not touched. This is the one exception to "outputs only through the gate"
(decided by Sazzad, 17 Nov; CLAUDE.md). A level that is not confirmed is not used: its off level
could be the run level. The box belt cannot be stopped from here (see BOX_BELT_NOTE).
"""

from __future__ import annotations

import socket
from typing import Any

from cell_sim.drivers.dobot_tcp_robot import parse_reply

from .gate import NOT_FOR_A_RUN

BOX_BELT_NOTE = ("the box belt is not stopped by software: it runs on its UNO, which has no link to the robot "
                 "or this PC. Stop it with the physical emergency stop or its power supply")
BELT = (("belt_do", "belt_on_value", "object belt stopped"), ("belt_enable_do", "belt_enable_on_value", "object belt not enabled"))
GRIPPER = (("vacuum_do", "suction off"), ("blow_do", "blow-off off"))


def off_levels(config: Any, belt_only: bool) -> tuple[list[tuple[int, int, str]], list[str]]:
    """(channel, off level, words) for each output to switch off, and why any is left out."""
    pairs, left_out = [], []
    for do_key, level_key, words in BELT:
        channel, on = config.value("dobot", do_key), config.value("dobot", level_key)
        unconfirmed = config.status("dobot", level_key) in NOT_FOR_A_RUN
        if channel is None or on is None or unconfirmed:
            name = f"dobot.{do_key}" if channel is None else f"dobot.{level_key}"
            left_out.append(f"{name} is not set or not confirmed: '{words}' not sent")
        else:
            pairs.append((int(channel), 1 - int(on), words))
    if not belt_only:
        pairs += [(int(config.value("dobot", key)), 0, words) for key, words in GRIPPER if config.value("dobot", key) is not None]
    return pairs, left_out


def _reply(connection: socket.socket) -> str:
    data = b""
    while not data.rstrip().endswith(b";"):
        chunk = connection.recv(1024)
        if not chunk:
            raise ConnectionError("the robot closed the dashboard port")
        data += chunk
    return data.decode("utf-8", "replace").strip()


def outputs_off(link: Any, config: Any, belt_only: bool = False, timeout_s: float = 2.0) -> dict[str, Any]:
    """Switch the outputs off now, with one short dashboard connection. Never raises."""
    if link is None:
        return {"ok": False, "sent": [], "problems": ["no robot link in this backend"], "note": BOX_BELT_NOTE}
    if link.control_session is not None:
        return {"ok": False, "sent": [], "problems": ["a run holds the robot: use Pause or the SOFTWARE STOP"], "note": BOX_BELT_NOTE}
    pairs, problems = off_levels(config, belt_only)
    sent: list[str] = []
    try:
        with link._lock:  # one conversation with the robot at a time (the checks wait)
            with link.open_control_socket(link.dashboard_port, timeout_s) as connection:
                for channel, level, words in pairs:
                    command = f"DOExecute({channel},{level})"
                    connection.sendall(command.encode("utf-8"))
                    reply = _reply(connection)
                    if parse_reply(reply)[0] == 0:
                        sent.append(f"DO{channel} = {level} ({words})")
                    else:
                        problems.append(f"{command} refused by the robot: {reply}")
    except (OSError, ConnectionError) as error:  # RobotHeld / RobotUnreachable are ConnectionErrors
        problems.append(f"robot not reached: {error}")
    return {"ok": bool(sent) and not problems, "sent": sent, "problems": problems, "note": BOX_BELT_NOTE}
