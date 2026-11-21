"""
robot_lib.py - small wrapper around the Dobot TCP/IP API (dobot_api.py).

Used by 14_pick_and_place.py. In DRY RUN mode nothing is sent to the robot:
every command is only printed, so you can test everything at home.

Dobot M1 Pro: dashboard port 29999, move port 30003.
DobotStudio Pro -> Settings -> Remote Control must be "TCP/IP Secondary development",
and DobotStudio / the Python demo must be DISCONNECTED (only one program at a time).
"""

import json
import os
import re
import time

DASHBOARD_PORT = 29999
MOVE_PORT = 30003


def ok(resp):
    return bool(resp) and str(resp).strip().startswith("0,")


def _value(resp):
    """'0,{1},DI(1);' -> 1"""
    m = re.search(r"\{([^}]*)\}", str(resp))
    return m.group(1) if m else None


def explain_error(resp):
    """'0,{[[17],[],[],[],[]]},GetErrorID();' -> 'controller 17: Inverse kinematics error with no solution'"""
    m = re.search(r"\{(.*)\}", str(resp), re.S)      # the answer is several lines long
    try:
        groups = json.loads(m.group(1))
    except (AttributeError, ValueError):
        return str(resp).strip()
    texts = {}
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")
    for kind in ("controller", "servo"):
        try:
            with open(os.path.join(here, f"alarm_{kind}.json"), encoding="utf-8") as f:
                texts[kind] = {a["id"]: a["en"]["description"] for a in json.load(f)}
        except (OSError, ValueError, KeyError):
            texts[kind] = {}
    out = []
    for k, ids in enumerate(groups):
        kind, where = ("controller", "controller") if k == 0 else ("servo", f"joint {k}")
        for i in ids:
            out.append(f"{where} {i}: {texts[kind].get(i, '(unknown)')}")
    return "; ".join(out) if out else "no error"


class _SimRobot:
    """Pretend robot for practising at home (--sim). It remembers its position,
    answers like the real one and its box sensor always says "box is here"."""

    def __init__(self, r):
        self.p = [270.0, 0.0, 200.0, 0.0]     # starts in the middle of the practice picture
        self.box_di, self.box_on = r.get("box_sensor_di"), r.get("box_sensor_on", 1)

    def _ok(self, name, val=""):
        return "0,{%s},%s();" % (val, name)

    def GetPose(self):
        return self._ok("GetPose", ",".join(f"{v:.3f}" for v in self.p))

    def MovJ(self, x, y, z, r):
        if (x * x + y * y) ** 0.5 > 400 or z < 0:     # M1 Pro arm is 400 mm long
            return "-1,{},MovJ();"
        self.p = [x, y, z, r]
        return self._ok("MovJ")

    MovL = MovJ

    def DI(self, n):
        return self._ok("DI", str(self.box_on if n == self.box_di else 0))

    def __getattr__(self, name):                       # every other command: "OK"
        return lambda *a: self._ok(name)


class Robot:
    def __init__(self, settings, run=False, speed=10, sim=False):
        self.r = settings["robot"]
        self.run = run or sim
        self.sim = sim
        self.dash = self.move = None
        if sim:
            print("[SIMULATED ROBOT] practice mode - no real robot is used")
            self.dash = self.move = _SimRobot(self.r)
            return
        if not run:
            print("[DRY RUN] the robot will NOT move - commands are only printed")
            return
        from dobot_api import DobotApiDashboard, DobotApiMove
        ip = self.r.get("ip", "192.168.1.6")
        self.dash = DobotApiDashboard(ip, DASHBOARD_PORT)
        self.move = DobotApiMove(ip, MOVE_PORT)
        self.dash.ClearError()
        time.sleep(0.5)
        if not ok(self.dash.EnableRobot()):
            mode = str(self.dash.RobotMode()).strip()
            err = explain_error(self.dash.GetErrorID())
            print(f"\n  robot mode: {mode}   (4 = disabled, 5 = enabled, 9 = ALARM, 11 = collision)")
            print(f"  alarm     : {err}\n")
            self.close()
            raise RuntimeError("EnableRobot refused - run robot_check.py (emergency stop? alarm? "
                               "TCP/IP mode? DobotStudio still connected?)")
        time.sleep(1.5)
        self.dash.SpeedFactor(int(speed))
        if self.r.get("arm_left_code") is not None:      # found by robot_arm_left.py
            self.dash.SetArmOrientation(int(self.r["arm_left_code"]))

    # ---- motion -----------------------------------------------------------
    def _send(self, cmd, args, desc):
        print(f"   {cmd} {tuple(round(a, 1) for a in args)}   # {desc}")
        if not self.run:
            return
        resp = getattr(self.move, cmd)(*args)
        if not ok(resp):
            raise RuntimeError(f"{cmd}{tuple(round(a, 1) for a in args)} refused: {resp}  (outside the work area?)")

    def movj(self, x, y, z, desc="", r=None):
        # MovL, not MovJ: on our M1 Pro a MovJ flipped the arm from Left to Right
        # (robot_move_test.py, 12 Nov). MovL keeps the arm the way it is.
        self._send("MovL", (x, y, z, self.r.get("r_angle", 0) if r is None else r), desc)

    def movl(self, x, y, z, desc="", r=None):
        self._send("MovL", (x, y, z, self.r.get("r_angle", 0) if r is None else r), desc)

    def sync(self):
        if self.run:
            self.move.Sync()

    def home(self):
        x, y, z, _ = self.r["home"]
        self.movj(x, y, z, "home (out of the camera view)")
        self.sync()

    # ---- I/O --------------------------------------------------------------
    def do(self, index, value, desc=""):
        print(f"   DO({index},{value})   # {desc}")
        if self.run:
            self.sync()                      # arrive first, then switch
            self.dash.DO(int(index), int(value))

    def wait(self, s):
        if self.run:
            self.sync()
            time.sleep(s)

    def di(self, index):
        if not self.run:
            return None
        v = _value(self.dash.DI(int(index)))
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def pose(self):
        return self.dash.GetPose() if self.run else "(dry run)"

    def xyzr(self):
        """Current tool position as (x, y, z, r) numbers, or None."""
        if not self.run:
            return None
        v = _value(self.dash.GetPose())
        try:
            return tuple(float(t) for t in v.split(",")[:4])
        except (AttributeError, ValueError):
            return None

    # how long a jog key moves the robot, like holding a jog button in the Dobot demo
    JOG_TIME = {1.0: 0.1, 5.0: 0.3, 20.0: 1.0}

    def jog(self, dx=0.0, dy=0.0, dz=0.0):
        """Move the tool a little in X, Y or Z.
        Real robot: MoveJog, the same command as the jog buttons (X+, Y-, Z+ ...) of the
        official Dobot Python demo, which works on our M1 Pro. The robot moves while
        the key is 'held' for a short time and then stops."""
        if not self.run:
            return
        if self.sim:
            p = self.xyzr()
            self._send("MovL", (p[0] + dx, p[1] + dy, p[2] + dz, p[3]), "jog")
            return
        # keep away from the edge of the reach: a fully stretched arm (~400 mm) cannot
        # move sideways ("Inverse kinematics singularity", alarm 32, 12 Nov)
        p = self.xyzr()
        if p and (dx or dy):
            r_now = (p[0] ** 2 + p[1] ** 2) ** 0.5
            r_new = ((p[0] + dx) ** 2 + (p[1] + dy) ** 2) ** 0.5
            r_max = self.r.get("reach_radius_mm", 400) - 25
            r_min = self.r.get("min_radius_mm", 150)
            if r_new > r_now and r_new > r_max:
                raise RuntimeError(f"STOP: arm almost fully stretched ({r_now:.0f} mm from the base, "
                                   f"limit {r_max:.0f}). Move back towards the robot (s or a/d).")
            if r_new < r_now and r_new < r_min:
                raise RuntimeError(f"STOP: too close to the robot base ({r_now:.0f} mm). Move away (w).")
        for axis, d in (("X", dx), ("Y", dy), ("Z", dz)):
            if d:
                name = axis + ("+" if d > 0 else "-")
                t = self.JOG_TIME.get(abs(d), 0.3)
                print(f"   MoveJog({name}) for {t} s")
                resp = self.move.MoveJog(name)
                time.sleep(t)
                self.move.MoveJog("")              # = release the button: stop
                time.sleep(0.3)
                if not ok(resp):
                    raise RuntimeError(f"MoveJog({name}) refused: {resp}")
                err = explain_error(self.dash.GetErrorID())
                if err != "no error":
                    raise RuntimeError("robot alarm: " + err + "  (press e to clear)")

    def clear_alarm(self):
        """Red light / alarm: clear it and switch the robot on again."""
        if not self.run:
            return "dry run"
        err = explain_error(self.dash.GetErrorID())
        self.dash.ClearError()
        self.dash.Continue()
        time.sleep(0.5)
        en = self.dash.EnableRobot()
        time.sleep(1.0)
        return f"alarm was: {err[:200]}  -> EnableRobot {str(en).strip()}"

    def move_to(self, x, y, z, desc=""):
        p = self.xyzr()
        r = p[3] if p else self.r.get("r_angle", 0)       # keep the current tool rotation
        self._send("MovL", (x, y, z, r), desc)            # MovL: never flips the arm
        self.sync()

    def drag(self, on):
        """Hand-guiding mode: you can push the arm by hand (M1 Pro)."""
        if self.run:
            print("drag mode", "ON" if on else "OFF", "->", (self.dash.StartDrag() if on else self.dash.StopDrag()).strip())

    # ---- pick and place ---------------------------------------------------
    def pick_and_place(self, x, y, slot, name, kind=None, turn=0.0):
        """turn = how many degrees the tool (R axis) turns between picking and placing,
        so a crooked object lands straight in the box (0 = no turning)."""
        r = self.r
        # each object type can have its own pick height (a candy is thicker than a card)
        pz = (r.get("pick_z_by_type") or {}).get(kind, r["pick_z"])
        tz, lz = r["travel_z"], r["place_z"]
        bx, by = slot
        r0 = r.get("r_angle", 0)
        r1 = r0 + turn
        self.movj(x, y, tz, f"above {name}", r=r0)
        self.movl(x, y, pz, f"down to {name}", r=r0)
        self.do(r["vacuum_do"], 1, "suction ON")
        self.wait(r.get("vacuum_on_s", 0.6))
        self.movl(x, y, tz, f"lift {name}", r=r0)
        bz = max(tz, lz)       # never fly into the box lower than the drop height
        self.movj(bx, by, bz, f"above the box (tool turned {turn:+.0f} deg)", r=r1)
        self.movl(bx, by, lz, "lower into the box", r=r1)
        self.do(r["vacuum_do"], 0, "suction OFF")
        if r.get("blow_do"):
            self.do(r["blow_do"], 1, "blow-off ON (drops the object)")
            self.wait(r.get("blow_s", 0.2))
            self.do(r["blow_do"], 0, "blow-off OFF")
        self.wait(r.get("vacuum_off_s", 0.3))
        self.movl(bx, by, bz, "lift clear", r=r1)

    def place_lid(self, x, y, slot, turn=0.0):
        """Pick the lid at (x, y) and put it on the box at slot, turned by `turn` degrees.
        Heights come from 15_robot_setup.py (keys l and j)."""
        r = self.r
        lp, lz = r["lid_pick_z"], r["lid_place_z"]
        cz = max(r["travel_z"], lp, lz) + r.get("lid_clear_mm", 15)   # carry height: lid above the box edge
        bx, by = slot
        r0 = r.get("r_angle", 0)
        r1 = r0 + turn
        self.movj(x, y, cz, "above the lid", r=r0)
        self.movl(x, y, lp, "down to the lid", r=r0)
        self.do(r["vacuum_do"], 1, "suction ON")
        self.wait(r.get("vacuum_on_s", 0.6))
        self.movl(x, y, cz, "lift the lid", r=r0)
        self.movj(bx, by, cz, f"above the box (lid turned {turn:+.0f} deg)", r=r1)
        self.movl(bx, by, lz, "put the lid on the box", r=r1)
        self.do(r["vacuum_do"], 0, "suction OFF")
        if r.get("blow_do"):
            self.do(r["blow_do"], 1, "blow-off ON")
            self.wait(r.get("blow_s", 0.2))
            self.do(r["blow_do"], 0, "blow-off OFF")
        self.wait(r.get("vacuum_off_s", 0.3))
        self.movl(bx, by, cz, "lift clear", r=r1)

    def close(self):
        if not self.run:
            return
        try:
            self.dash.DO(int(self.r.get("vacuum_do", 1)), 0)
            if self.r.get("blow_do"):
                self.dash.DO(int(self.r["blow_do"]), 0)
            if self.r.get("conveyor_do"):
                self.dash.DO(int(self.r["conveyor_do"]), 0)
            self.dash.DisableRobot()
        except Exception:
            pass
        for c in (self.move, self.dash):
            try:
                c.close()
            except Exception:
                pass
