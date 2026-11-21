"""Fakes for real control: robot network (all three ports), vision, robot session, run log. No hardware."""

from __future__ import annotations

import socket
import threading
import time

from cell_live.control.robot_client import ControlConnectionLost, ControlRefused
from cell_live.tests.baseline import CHOTON, CONFIG, choton_settings  # noqa: F401 (re-exported for the tests)

NO_ERROR = "0,{[[],[],[],[],[],[]]},GetErrorID();"


# Robot network


class FakeNet:
    """connect() stand-in. Every command gets '0,{},Cmd();' unless overridden, silenced or blocked."""

    def __init__(self):
        self.sent = []  # (port, command)
        self.replies = {"GetErrorID": NO_ERROR}  # command name -> reply text
        self.silent = set()  # command names that never get a reply
        self.blocked = {}  # command name -> threading.Event: reply only once it is set
        self.connections = []

    def connect(self, address, timeout=None):
        connection = FakeConnection(self, address[1])
        self.connections.append(connection)
        return connection

    def commands(self, port):
        return [command for sent_port, command in self.sent if sent_port == port]

    def close_all(self):
        for connection in self.connections:
            connection.closed = True


class FakeConnection:
    def __init__(self, net, port):
        self.net, self.port = net, port
        self.pending = b""
        self.waiting = None
        self.timeout_s = 1.0
        self.closed = False

    def settimeout(self, timeout_s):
        self.timeout_s = timeout_s

    def sendall(self, data):
        if self.closed:
            raise OSError("connection closed")
        command = data.decode("utf-8")
        self.net.sent.append((self.port, command))
        name = command.split("(")[0]
        if name in self.net.silent:
            return
        reply = self.net.replies.get(name, f"0,{{}},{command};").encode("utf-8")
        if name in self.net.blocked:
            self.waiting = (self.net.blocked[name], reply)
        else:
            self.pending += reply

    def recv(self, size):
        if self.waiting is not None:
            event, reply = self.waiting
            deadline_s = time.monotonic() + self.timeout_s
            while not event.is_set():
                if self.closed:
                    raise OSError("connection closed while waiting")
                if time.monotonic() > deadline_s:
                    raise socket.timeout("timed out")
                time.sleep(0.005)
            self.pending, self.waiting = self.pending + reply, None
        if self.closed:
            raise OSError("connection closed")
        if not self.pending:
            raise socket.timeout("timed out")
        data, self.pending = self.pending[:size], self.pending[size:]
        return data

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# Vision


def item(kind, x_mm, y_mm, u, conf=0.9, color="red", angle=0.0, edge=False):
    return {"type": kind, "conf": conf, "u": float(u), "v": 200.0, "x_robot": x_mm, "y_robot": y_mm, "edge": edge,
            "reachable": True, "color": color, "angle_robot": angle, "box": (u - 20, 180, u + 20, 220)}


def full_set():
    return [item("card", 250.0, 0.0, 100), item("candy", 250.0, 40.0, 200, color="red"),
            item("candy", 250.0, -40.0, 300, color="orange"), item("box", 369.6, 17.1, 600, angle=5.0)]


class FakeVision:
    """objects: what the camera sees in the pick area (detect and detect_stable).
    box: an open box stands still at the robot. box_leaves: after the lid, the box leaves."""

    image = None

    def __init__(self, clock, objects=None, look_objects=None, box=True, box_leaves=True, frame_s=0.1):
        self.clock = clock
        self.objects = full_set() if objects is None else objects
        self.look_objects = look_objects
        self.box = box
        self.box_leaves = box_leaves
        self.box_at_mm = (369.6, 17.1)  # where the open box stands (robot X/Y); the test slot is here too
        self.frame_s = frame_s
        self.reads = 0
        self.latest = None  # (frame, detections, time) of the last detect, like VisionSession
        self.H = None
        self.on_read = None  # test hook: called on every read
        self.lost_after = None  # reads after which the camera is lost

    def read(self):
        from cell_live.control.vision_session import CameraLost

        self.reads += 1
        self.clock.advance(self.frame_s)
        if self.lost_after is not None and self.reads > self.lost_after:
            raise CameraLost("camera lost (test)")
        if self.on_read is not None:
            self.on_read(self.reads)
        return f"frame {self.reads}"

    def peek(self):
        return self.reads, f"frame {self.reads}"

    def detect(self, frame):
        found = [dict(o) for o in self.objects if o["type"] != "box"]
        if self.box:
            found.append(item("box", *self.box_at_mm, 600, angle=5.0))
        self.latest = (frame, found, self.clock())
        return found

    def detect_stable(self, frames):
        for _ in range(frames):
            self.read()
        chosen = self.objects if self.look_objects is None else self.look_objects
        return "frame", [dict(o) for o in chosen]

    def box_present(self, objects, slot):
        return not self.box_leaves

    def status(self):
        return {"model_loaded": True, "classes": ["card", "candy", "box", "lid"], "frame_age_s": 0.1, "fps": 10.0,
                "width_px": 1280, "height_px": 720, "camera_error": "", "running": True}

    def start(self):
        pass

    def stop(self):
        pass


def objects_come_with_the_belt(vision, session, run_level=1):
    """The cards and candies appear only once DO3 is at the belt's run level: they ride in on the belt."""
    still = [o for o in vision.objects if o["type"] in ("box", "lid")]
    arriving = [o for o in vision.objects if o["type"] in ("card", "candy")]
    vision.objects = still

    def on_read(_reads):
        if session.outputs.get(3) == run_level:
            vision.objects = arriving + still

    vision.on_read = on_read


class FakeClock:
    def __init__(self):
        self.now_s = 0.0

    def __call__(self):
        return self.now_s

    def advance(self, seconds):
        self.now_s += seconds


# Robot session (for the cycle)


class FakeSession:
    """Records what the cycle asks the robot to do; outputs as a dict channel -> level."""

    def __init__(self, belt_on_value=1):
        self.off = {3: 1 - belt_on_value, 1: 0, 2: 0}
        self.outputs = dict(self.off)
        self.calls = []
        self.picks = []
        self.lids = []
        self.lid_places = []  # where the cup puts each lid down
        self.problem = ""
        self.alarm = "no error"
        self.fail_pick = None  # exception to raise on the next pick_and_place
        self.on_pick = None  # test hook: called during each pick
        self.estopped = False
        self.closed = False
        self.outputs_off_calls = 0

    def _motion(self, name):
        if self.estopped:
            raise ControlRefused(f"{name} refused: the software e-stop is active")
        self.calls.append(name)

    def home(self):
        self._motion("home")

    def pick_and_place(self, x_mm, y_mm, slot, name, kind, turn_deg):
        self._motion("pick_and_place")
        if self.on_pick is not None:
            self.on_pick(len(self.picks))
        if self.fail_pick is not None:
            error, self.fail_pick = self.fail_pick, None
            raise error
        self.picks.append((kind, x_mm, y_mm))

    def place_lid(self, x_mm, y_mm, place, turn_deg):
        self._motion("place_lid")
        self.lids.append((x_mm, y_mm))
        self.lid_places.append(tuple(place))

    def set_output(self, channel, level, description):
        if self.estopped and level != self.off.get(channel, 0):
            raise ControlRefused("output on refused after the software e-stop")
        self.outputs[channel] = level
        self.calls.append(f"DO{channel}={level}")

    def outputs_off(self):
        self.outputs_off_calls += 1
        self.outputs.update(self.off)
        return [f"DO{channel} = {level} (fake)" for channel, level in self.off.items()]

    def software_estop(self):
        self.estopped = True
        return self.outputs_off() + ["EmergencyStop() sent (fake)"]

    def alarm_text(self):
        return self.alarm

    def clear_alarm(self):
        return f"alarm was: {self.alarm}; ClearError sent"

    def describe(self):
        return "in use by the running cycle (fake)"

    def close(self):
        self.closed = True
        return self.outputs_off()


class FakeLog:
    def __init__(self):
        self.rows = []
        self.box = 0
        self.state = ""
        self.events = []
        self.path = "fake.csv"
        self.closed = False

    def event(self, event, command="", reply="", detections=None, fault="", state=None):
        row = {"state": state or self.state, "event": event, "fault": fault, "detections": detections}
        self.rows.append(row)
        self.events.append(row)

    def command(self, port, command, reply):
        self.event(f"port {port}", command=command, reply=reply)

    def close(self):
        self.closed = True


def wait_for(condition, timeout_s=5.0):
    deadline_s = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline_s:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


__all__ = ["ControlConnectionLost", "threading"]
