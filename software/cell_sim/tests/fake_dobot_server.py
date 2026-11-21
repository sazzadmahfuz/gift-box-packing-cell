"""Fake Dobot controller on 127.0.0.1 for tests: dashboard (29999) and feedback (30004).

dobot_api.DobotApi accepts only the real port numbers, so the fake servers use them too; tests
skip if another program already holds a port. Reply texts are test data, shaped like the replies
in notebooks/week-02/Rashmika/Images/day2/Image2.png.
"""

from __future__ import annotations

import socketserver
import sys
import threading

HOST = "127.0.0.1"
DASHBOARD_PORT, FEEDBACK_PORT = 29999, 30004
DEFAULT_REPLIES = {
    "GetErrorID()": "0,{[[],[],[],[],[],[]]},GetErrorID();",
    "RobotMode()": "0,{5},RobotMode();",
    "GetPose()": "0,{366.211,122.182,124.262,-7.66,0.0,0.0},GetPose();",
}


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # on Windows it would allow sharing a busy port


class FakeDobot:
    def __init__(self, feedback_packet: bytes) -> None:
        self.commands: list[str] = []
        self.replies = dict(DEFAULT_REPLIES)
        self.feedback_packet = feedback_packet
        fake = self

        class Dashboard(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                while True:
                    data = self.request.recv(1024)
                    if not data:
                        return
                    command = data.decode("utf-8")
                    fake.commands.append(command)
                    reply = fake.replies.get(command, f"0,{{}},{command};")
                    self.request.sendall(reply.encode("utf-8"))

        class Feedback(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                self.request.sendall(fake.feedback_packet)
                self.request.recv(1)  # hold the connection until the client closes it

        self._servers = [_Server((HOST, DASHBOARD_PORT), Dashboard), _Server((HOST, FEEDBACK_PORT), Feedback)]
        for server in self._servers:
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self) -> None:
        for server in self._servers:
            server.shutdown()
            server.server_close()


def feedback_packet(
    api, robot_mode=5, tool_xyzr=(366.211, 122.182, 124.262, -7.66), error_status=0, valid=True, outputs=0, inputs=0
):
    """One 1440-byte feedback packet built with Dobot's own MyType layout."""
    packet = api.np.zeros(1, dtype=api.MyType)
    packet["digital_outputs"] = outputs
    packet["digital_input_bits"] = inputs
    packet["test_value"] = 0x123456789ABCDEF if valid else 0
    packet["robot_mode"] = robot_mode
    packet["tool_vector_actual"][0][:4] = tool_xyzr
    packet["EnableStatus"] = 1
    packet["ErrorStatus"] = error_status
    return packet.tobytes()
