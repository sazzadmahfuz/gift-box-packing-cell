"""Fakes for the live checks: robot sockets, camera, serial port, YOLO model. No hardware."""

from __future__ import annotations

import socket
from types import SimpleNamespace

from cell_sim.drivers.dobot_tcp_robot import load_dobot_api
from cell_sim.hardware_config import dobot_settings, load_hardware_raw

DOBOT_API = load_dobot_api(dobot_settings(load_hardware_raw()).api_path)  # real MyType layout (numpy)
REPLIES = {
    "RobotMode()": "0,{4},RobotMode();",
    "GetErrorID()": "0,{[\n\t[],\n\t[],\n\t[],\n\t[],\n\t[],\n\t[]\n]\n},GetErrorID();",  # as seen 2026-11-12
    "GetPose()": "0,{183.386215,276.015349,151.372986,-43.644684,0.000000,0.000000,Left},GetPose();",
}


def feedback_bytes(outputs=0, inputs=0, valid=True, error_status=0, pose=(183.386, 276.015, 151.373, -43.645)):
    packet = DOBOT_API.np.zeros(1, dtype=DOBOT_API.MyType)
    packet["test_value"] = 0x123456789ABCDEF if valid else 0
    packet["robot_mode"] = 4
    packet["tool_vector_actual"][0][:4] = pose
    packet["digital_outputs"] = outputs
    packet["digital_input_bits"] = inputs
    packet["ErrorStatus"] = error_status
    return packet.tobytes()


class FakeConnection:
    def __init__(self, robot, port):
        self.robot, self.port = robot, port
        self.pending = b""

    def settimeout(self, timeout_s):
        pass

    def sendall(self, data):
        command = data.decode("utf-8")
        self.robot.sent.append((self.port, command))
        if self.robot.silent:
            return
        self.pending += self.robot.replies.get(command, f"0,{{}},{command};").encode("utf-8")

    def recv(self, size):
        if self.port == 30004:
            if self.robot.silent:
                raise socket.timeout("timed out")
            data, self.robot.packet = self.robot.packet[:size], self.robot.packet[size:]
            return data
        if not self.pending:
            raise socket.timeout("timed out")
        data, self.pending = self.pending[:size], self.pending[size:]
        return data

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeRobot:
    """A connect() stand-in. failure: None, 'refused', 'timeout', 'no_route', 'reset'."""

    def __init__(self, failure=None, silent=False, packet=None):
        self.failure = failure
        self.silent = silent  # connects, but never answers (port held by another program?)
        self.replies = dict(REPLIES)
        self.packet = packet if packet is not None else feedback_bytes()
        self.sent = []
        self.connects = []

    def connect(self, address, timeout=None):
        self.connects.append(address)
        if self.failure == "refused":
            raise ConnectionRefusedError(10061, "refused")
        if self.failure == "reset":
            raise ConnectionResetError(10054, "reset")
        if self.failure == "timeout":
            raise socket.timeout("timed out")
        if self.failure == "no_route":
            raise OSError(10065, "no route to host")
        return FakeConnection(self, address[1])


class FakeCapture:
    def __init__(self, opens=True, size=(720, 1280), frames=True):
        self.opens, self.size, self.frames = opens, size, frames
        self.released = False
        self.settings = {}

    def isOpened(self):
        return self.opens

    def set(self, prop, value):
        self.settings[prop] = value
        return True

    def read(self):
        if not self.frames:
            return False, None
        return True, SimpleNamespace(shape=(*self.size, 3))

    def release(self):
        self.released = True


def fake_cv2(capture):
    return SimpleNamespace(
        VideoCapture=lambda index, backend=0: capture,
        CAP_DSHOW=700, CAP_ANY=0, CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
    )


class FakeSerialPort:
    def __init__(self, reply=b"S1=1 BELT=0\n"):
        self.reply, self.written, self.closed = reply, [], False

    def write(self, data):
        self.written.append(data)

    def readline(self):
        return self.reply

    def close(self):
        self.closed = True


def fake_serial(port=None, error=None):
    def open_port(name, baud, timeout=None):
        if error:
            raise error
        return port

    return SimpleNamespace(Serial=open_port)
