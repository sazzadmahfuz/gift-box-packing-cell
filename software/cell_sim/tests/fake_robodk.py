"""A fake RoboDK API (robolink + robomath) for tests. No RoboDK needed.

It copies only the behaviour cell_sim relies on, including one trap of the real API:
Robolink.Item(name) returns the closest match when there is no exact one.
"""

from __future__ import annotations

from types import SimpleNamespace

ITEM_TYPE_ROBOT, ITEM_TYPE_FRAME, ITEM_TYPE_TOOL, ITEM_TYPE_OBJECT, ITEM_TYPE_TARGET = 2, 3, 4, 5, 6
RUNMODE_SIMULATE = 1


class TargetReachError(Exception):
    pass


class FakeMat:
    """Translation-only pose: enough to check the approach offsets."""

    def __init__(self, x=0.0, y=0.0, z=0.0, rz_deg=0.0):
        self.x, self.y, self.z, self.rz_deg = x, y, z, rz_deg

    def __mul__(self, other):
        return FakeMat(self.x + other.x, self.y + other.y, self.z + other.z, self.rz_deg + other.rz_deg)

    def __eq__(self, other):
        return isinstance(other, FakeMat) and vars(self) == vars(other)

    def __repr__(self):
        return f"FakeMat({self.x}, {self.y}, {self.z}, {self.rz_deg})"


class FakeItem:
    def __init__(self, name, item_type, pose=None, parent=None, valid=True):
        self.name, self.type = name, item_type
        self.pose = pose or FakeMat()
        self.parent = parent
        self.valid = valid

    def Name(self):
        return self.name

    def Valid(self):
        return self.valid

    def Type(self):
        return self.type

    def Pose(self):
        return self.pose

    def PoseAbs(self):
        return self.pose

    def setPoseAbs(self, pose):
        self.pose = pose
        return self

    def Parent(self):
        return self.parent


INVALID = FakeItem("", 0, valid=False)


class FakeTool(FakeItem):
    def __init__(self, station):
        super().__init__("vacuum cup", ITEM_TYPE_TOOL)
        self.station = station
        self.held = []

    def AttachClosest(self, keyword="", tolerance_mm=-1, list_objects=[]):
        for item in self.station.items:
            if item.type == ITEM_TYPE_OBJECT and keyword in item.name and item not in self.held:
                self.held.append(item)
                return item
        return INVALID

    def DetachAll(self, parent=0):
        self.held = []


class FakeRobot(FakeItem):
    def __init__(self, name, station, clock=None, move_s=1.0):
        super().__init__(name, ITEM_TYPE_ROBOT)
        self.station, self.clock, self.move_s = station, clock, move_s
        self.moves = []
        self.unreachable = set()  # target names that raise TargetReachError
        self.tool = FakeTool(station)
        self.frame = None
        self.stopped = False

    def _move(self, kind, goal):
        label = goal.name if isinstance(goal, FakeItem) else goal
        if isinstance(goal, FakeItem) and goal.name in self.unreachable:
            raise TargetReachError(f"cannot reach {goal.name}")
        self.moves.append((kind, label))
        self.pose = goal.pose if isinstance(goal, FakeItem) else goal
        if self.clock is not None:
            self.clock.now += self.move_s

    def MoveJ(self, target, blocking=True):
        self._move("MoveJ", target)

    def MoveL(self, target, blocking=True):
        self._move("MoveL", target)

    def setPoseFrame(self, frame):
        self.frame = frame

    def getLink(self, type_linked=ITEM_TYPE_ROBOT):
        return self.tool if type_linked == ITEM_TYPE_TOOL else INVALID

    def Stop(self):
        self.stopped = True


class FakeStation:
    """Robolink stand-in. Build it, add items, then hand out fake_modules(station)."""

    def __init__(self):
        self.items = []
        self.run_mode = None
        self.simulation_speed = None
        self.messages = []
        self.frame = FakeItem("Dobot base", ITEM_TYPE_FRAME)

    def add_robot(self, name="Dobot M1 Pro", clock=None, move_s=1.0):
        robot = FakeRobot(name, self, clock, move_s)
        self.items.append(robot)
        return robot

    def add_target(self, name, x, y, z):
        target = FakeItem(name, ITEM_TYPE_TARGET, FakeMat(x, y, z), parent=self.frame)
        self.items.append(target)
        return target

    def add_object(self, name, x, y, z):
        item = FakeItem(name, ITEM_TYPE_OBJECT, FakeMat(x, y, z))
        self.items.append(item)
        return item

    # Robolink methods
    def Item(self, name, itemtype=None):
        same_type = [i for i in self.items if itemtype is None or i.type == itemtype]
        exact = [i for i in same_type if i.name == name]
        if exact:
            return exact[0]
        return same_type[-1] if same_type else INVALID  # "last closest match", like RoboDK

    def ItemList(self, filter=None, list_names=False):
        return [i for i in self.items if filter is None or i.type == filter]

    def setRunMode(self, run_mode=1):
        self.run_mode = run_mode

    def setSimulationSpeed(self, speed):
        self.simulation_speed = speed

    def ShowMessage(self, message, popup=True):
        self.messages.append((message, popup))


def fake_modules(station):
    from cell_sim.drivers.robodk_robot import RoboDKModules

    robolink = SimpleNamespace(
        Robolink=lambda robodk_ip="localhost", port=None: station,
        ITEM_TYPE_ROBOT=ITEM_TYPE_ROBOT,
        ITEM_TYPE_TARGET=ITEM_TYPE_TARGET,
        ITEM_TYPE_TOOL=ITEM_TYPE_TOOL,
        RUNMODE_SIMULATE=RUNMODE_SIMULATE,
        TargetReachError=TargetReachError,
    )
    robomath = SimpleNamespace(
        transl=lambda x=0.0, y=0.0, z=0.0: FakeMat(x, y, z),
        pose_2_xyzrpw=lambda m: [m.x, m.y, m.z, 0.0, 0.0, m.rz_deg],
    )
    return RoboDKModules(robolink=robolink, robomath=robomath)


def cell_station(clock=None, move_s=1.0, robot_name="Dobot M1 Pro"):
    """A station like the README describes. Coordinates are test values, not cell measurements."""
    station = FakeStation()
    robot = station.add_robot(robot_name, clock, move_s)
    station.add_target("home", 0.0, 0.0, 100.0)
    station.add_target("pick", 10.0, 0.0, 20.0)
    station.add_target("place_box", 0.0, 10.0, 30.0)
    station.add_object("item", 10.0, 0.0, 20.0)
    return station, robot
