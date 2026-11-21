"""
STEP 15 - Robot setup at the university, ALL in one window (about 15 minutes).

    python 15_robot_setup.py               (robot speed 10 %)
    python 15_robot_setup.py --speed 20
    python 15_robot_setup.py --sim         (PRACTICE at home: simulated robot, real camera)

It does three jobs and saves everything by itself:
  A. CALIBRATION camera -> robot  (no ruler, no typing: the robot measures)
  B. TEACH the robot points        (home, heights, box position)
  C. FIND the I/O                  (suction, blow-off, box sensor input)

Before: camera fixed above the belt, DobotStudio / Python demo DISCONNECTED,
emergency stop in reach. Click the camera window before pressing keys.

MOVE THE ROBOT (keys)                      w / s = X + / -    a / d = Y + / -
                                           r / f = Z up / down
                                           1 / 2 / 3 = jog small / medium / big (0.1 / 0.3 / 1 s)
                                           m = hand-guiding on/off (push the arm)
                                           e = RED LIGHT / alarm: clear it and switch on again

A. CALIBRATION
   1. Put 4-6 small marks (crosses on tape / paper) spread over the belt,
      robot OUT of the picture.
   2. k  = freeze the picture, then CLICK each mark (u = undo), k again = live.
   3. For each mark in order: move the suction cup exactly onto it, press c.
      (--sim practice: move the PINK circle onto the mark with w/a/s/d, press c.)
      After the 4th mark the calibration is computed and saved (more marks = better).
   4. x then click anywhere on the picture = the robot goes above that spot.
      Check it is right above it. (TEST - do this a few times.)

B. TEACH (move the robot there, then press the key)
   h = HOME (out of the camera view)     t = TRAVEL height (safe height above everything)
   p = PICK height CARD  (cup touches the top of a card lying on the belt)
   o = PICK height CANDY (cup touches the top of a candy lying on the belt)
   b = BOX position (cup above the box, at the height where things are dropped)
   l = LID pick height  (lid lying flat beside the box, cup touches the top of the lid)
   j = LID close height (lid put ON the box by hand, cup touches the top of the lid)

C. I/O
   v = suction on/off (vacuum_do)        g = blow-off pulse (blow_do)
   i = read the 16 inputs. Press i with NO box at the sensor, then put the box
       there and press i again: the input that changed is saved as the box sensor.

q = save and quit (the robot is disabled).
"""

import argparse
import json
import os

import cv2
import numpy as np

import robot_lib
import vision_lib as vl

WIN = "15 robot setup"


class Setup:
    def __init__(self, settings, robot, src):
        self.s, self.robot, self.src = settings, robot, src
        self.r = settings["robot"]
        self.step = 5.0
        self.dragging = False
        self.frozen = None          # picture used to click the marks
        self.marks = []             # [u, v] pixels
        self.robot_pts = []         # [x, y] robot mm, same order
        self.H = vl.load_homography() if self._calib_is_robot() else None
        self.test_armed = False
        self.di_before = None
        self.pose = None
        self.msg = "Click this window, then use the keys (see the terminal)."
        self.sim = isinstance(robot.dash, robot_lib._SimRobot)
        saved = vl.load_json("calib_marks.json") or {}
        if saved.get("marks") and self.H is None:
            self.marks = saved["marks"]
            self.msg = (f"{len(self.marks)} marks loaded from last time (k = click new ones). "
                        "Put the cup on mark 1 and press c.")

    # practice mode: the picture covers robot X 180..360, Y +150..-150 (pretend)
    def sim_tool_pixel(self, p, shape):
        h, w = shape[:2]
        return int((150 - p[1]) / 300.0 * w), int((360 - p[0]) / 180.0 * h)

    # ---------------- helpers ----------------
    def _calib_is_robot(self):
        d = vl.load_json(vl.homography_file()) or {}
        return d.get("frame") == "robot"

    def say(self, text):
        self.msg = text
        print(text)

    def safe(self, fn, *a):
        try:
            fn(*a)
        except Exception as e:      # refused move (outside work area) etc.
            self.say(f"ROBOT: {e}  -> if the light is red press e")

    def save_robot_settings(self):
        self.r["_practice"] = self.sim       # practice values must be taught again on the real robot
        raw = vl.load_json("settings.json", {})
        raw.setdefault("robot", {}).update(self.r)
        vl.save_json("settings.json", raw)

    # ---------------- calibration ----------------
    def add_robot_point(self):
        if len(self.robot_pts) >= len(self.marks):
            self.say("Mark the points first: k, click the marks, k.")
            return
        p = self.robot.xyzr()
        if p is None:
            self.say("Could not read the robot position.")
            return
        self.robot_pts.append([round(p[0], 2), round(p[1], 2)])
        n = len(self.robot_pts)
        self.say(f"mark {n}: robot X {p[0]:.1f}  Y {p[1]:.1f}")
        if n >= 4 and n == len(self.marks):
            self.compute_calibration()

    def compute_calibration(self):
        pix = np.array(self.marks, dtype=np.float64)
        rob = np.array(self.robot_pts, dtype=np.float64)
        H, _ = cv2.findHomography(pix, rob, 0)
        if H is None:
            self.say("Calibration failed - marks in a line? Spread them out.")
            return
        back = cv2.perspectiveTransform(pix.reshape(-1, 1, 2), H).reshape(-1, 2)
        err = np.linalg.norm(back - rob, axis=1)
        old = vl.load_json(vl.homography_file())
        if old and old.get("frame") != "robot":
            vl.save_json(vl.homography_file().replace(".json", "_before_robot.json"), old)
        vl.save_json(vl.homography_file(), {
            "H": H.tolist(), "pixel_points": self.marks, "robot_points": self.robot_pts,
            "frame": "robot", "mean_error_mm": float(err.mean()), "created": vl.timestamp(),
            "practice": self.sim})
        self.r["origin_on_table_mm"] = [0, 0]
        self.r["flip_x"] = self.r["flip_y"] = False
        self.H = H
        txt = f"CALIBRATED with {len(self.marks)} marks, mean error {err.mean():.1f} mm"
        if len(self.marks) == 4:
            txt += " (4 marks always give ~0 - add a 5th/6th mark to really check it)"
        elif err.max() > 5:
            txt += f"  - WARNING max {err.max():.1f} mm: a mark was hit badly, redo it"
        self.say(txt + ". Now test with x + click.")

    def test_click(self, u, v):
        if self.H is None:
            self.say("Not calibrated yet.")
            return
        x, y = vl.pixel_to_robot(self.H, u, v)
        tz = self.r["travel_z"]
        self.say(f"test: pixel ({u},{v}) -> robot ({x:.1f}, {y:.1f}) - moving above it")
        self.safe(self.robot.move_to, x, y, tz, "above the clicked spot")

    # ---------------- mouse / keys ----------------
    def mouse(self, event, x, y, flags, _):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        u, v = vl.to_image_xy(x, y)
        if self.frozen is not None:
            self.marks.append([float(u), float(v)])
            self.robot_pts = self.robot_pts[:len(self.marks)]
            self.say(f"mark {len(self.marks)} at pixel ({u},{v})")
        elif self.test_armed:
            self.test_armed = False
            self.test_click(u, v)

    def key(self, k):
        r, j = self.r, self.robot
        moves = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0),
                 "r": (0, 0, 1), "f": (0, 0, -1)}
        c = chr(k) if k < 256 else ""
        if c in moves:
            dx, dy, dz = (self.step * m for m in moves[c])
            self.safe(j.jog, dx, dy, dz)
        elif c in "123":
            self.step = {"1": 1.0, "2": 5.0, "3": 20.0}[c]
            self.say("jog " + {1.0: "small", 5.0: "medium", 20.0: "big"}[self.step])
        elif c == "e":
            self.say("clearing alarm ... " + j.clear_alarm())
        elif c == "m":
            self.dragging = not self.dragging
            self.safe(j.drag, self.dragging)
        elif c == "k":
            if self.frozen is None:
                self.frozen = self.src.read()
                self.marks, self.robot_pts = [], []
                self.say("Picture frozen: CLICK the marks in order, then press k.")
            else:
                self.frozen = None
                vl.save_json("calib_marks.json", {"marks": self.marks})   # kept if the program restarts
                self.say(f"{len(self.marks)} marks. Now put the cup on mark 1 and press c.")
        elif c == "u" and self.marks:
            self.marks.pop()
            self.robot_pts = self.robot_pts[:len(self.marks)]
            self.say(f"removed - {len(self.marks)} marks")
        elif c == "c":
            self.add_robot_point()
        elif c == "x":
            self.test_armed = True
            self.say("Click a spot on the picture - the robot goes above it.")
        elif c in "hptbolj":
            p = j.xyzr()
            if p is None:
                self.say("Could not read the robot position.")
                return
            if c == "h":
                r["home"] = [round(p[0], 1), round(p[1], 1), round(p[2], 1), round(p[3], 1)]
                self.say(f"HOME = {r['home']}")
            elif c == "t":
                r["travel_z"] = round(p[2], 1)
                self.say(f"TRAVEL height = {r['travel_z']}")
            elif c == "p":
                r["pick_z"] = round(p[2], 1)
                r.setdefault("pick_z_by_type", {})["card"] = round(p[2], 1)
                r["r_angle"] = round(p[3], 1)
                self.say(f"PICK height CARD = {r['pick_z']}  (tool angle {r['r_angle']})")
            elif c == "o":
                r.setdefault("pick_z_by_type", {})["candy"] = round(p[2], 1)
                self.say(f"PICK height CANDY = {r['pick_z_by_type']['candy']}")
            elif c == "b":
                r["box_slots"] = [[round(p[0], 1), round(p[1], 1)]]
                r["place_z"] = round(p[2], 1)
                self.say(f"BOX = {r['box_slots'][0]}  drop height {r['place_z']}")
            elif c == "l":
                r["lid_pick_z"] = round(p[2], 1)
                self.say(f"LID pick height = {r['lid_pick_z']}")
            elif c == "j":
                r["lid_place_z"] = round(p[2], 1)
                self.say(f"LID close height (lid on the box) = {r['lid_place_z']}")
            self.save_robot_settings()
        elif c == "v":
            on = not getattr(self, "vac", False)
            self.vac = on
            self.safe(j.do, r["vacuum_do"], int(on), "suction test")
            self.say(f"suction DO{r['vacuum_do']} {'ON' if on else 'OFF'} - do you hear / feel it?")
        elif c == "g" and r.get("blow_do"):
            self.safe(j.do, r["blow_do"], 1, "blow test")
            j.wait(r.get("blow_s", 0.2))
            self.safe(j.do, r["blow_do"], 0, "blow test")
            self.say(f"blow-off DO{r['blow_do']} pulse")
        elif c == "i":
            now = {n: j.di(n) for n in range(1, 17)}
            print("inputs:", " ".join(f"DI{n}={v}" for n, v in now.items()))
            if self.di_before is None:
                self.di_before = now
                self.say("Inputs read (no box). Put the box at the sensor and press i again.")
            else:
                changed = [n for n in now if now[n] != self.di_before[n]]
                self.di_before = None
                if len(changed) == 1:
                    n = changed[0]
                    r["box_sensor_di"], r["box_sensor_on"] = n, now[n]
                    self.save_robot_settings()
                    self.say(f"BOX SENSOR = DI{n} (box present = {now[n]}) - saved")
                else:
                    self.say(f"{len(changed)} inputs changed {changed} - try again (i, box, i).")

    # ---------------- drawing ----------------
    def view(self):
        frame = self.frozen if self.frozen is not None else self.src.read()
        out = frame.copy()
        if self.H is not None and self.frozen is None:
            try:
                vl.draw_reach(out, self.H, self.s)
            except Exception:
                pass
        for n, (u, v) in enumerate(self.marks):
            done = n < len(self.robot_pts)
            col = (0, 220, 0) if done else (0, 0, 255)
            cv2.drawMarker(out, (int(u), int(v)), col, cv2.MARKER_CROSS, 24 * max(1, out.shape[0] // 700), 2 * max(1, out.shape[0] // 700))
            vl._put_label(out, str(n + 1), (int(u) + 8, int(v) - 8), col)
        import time
        if time.time() - getattr(self, "_t_pose", 0) > 0.3:      # ask the robot 3x per second
            self._t_pose, self.pose = time.time(), self.robot.xyzr()
        p = self.pose
        pos = f"X {p[0]:.1f}  Y {p[1]:.1f}  Z {p[2]:.1f}  R {p[3]:.1f}" if p else "robot ?"
        if self.sim and p:
            tu, tv = self.sim_tool_pixel(p, out.shape)
            cv2.circle(out, (tu, tv), 14, (255, 0, 255), 3)
            vl._put_label(out, f"robot tool (sim) Z {p[2]:.0f}", (tu + 18, tv), (255, 0, 255))
        state = ("FROZEN - click marks, k = live" if self.frozen is not None else
                 "TEST: click a spot" if self.test_armed else
                 f"calibrated" if self.H is not None else "NOT calibrated")
        vl._put_label(out, f"{pos} | jog {({1.0: 'small', 5.0: 'medium', 20.0: 'big'})[self.step]} | {state}", (10, 22), (0, 255, 255))
        vl._put_label(out, self.msg[:110], (10, out.shape[0] - 12), (255, 255, 255))
        return out

    def run(self):
        cv2.namedWindow(WIN)
        cv2.setMouseCallback(WIN, self.mouse)
        print(__doc__)
        while True:
            vl.show(WIN, self.view())
            k = cv2.waitKey(30)
            if k == -1:
                continue
            k &= 0xFF
            if k == ord("q"):
                break
            self.key(k)
        if self.dragging:
            self.safe(self.robot.drag, False)
        self.save_robot_settings()
        print("\nSaved robot section:\n" + json.dumps(self.r, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=int, default=10)
    ap.add_argument("--sim", action="store_true", help="practice with a simulated robot")
    ap.add_argument("--image", help="practice with a saved picture instead of the camera")
    args = ap.parse_args()
    settings = vl.load_settings()
    src = vl.FrameSource(args.image, settings)
    if not args.sim:
        print(f"Connecting to the robot {settings['robot'].get('ip')} ...")
    robot = robot_lib.Robot(settings, run=True, speed=args.speed, sim=args.sim)
    try:
        Setup(settings, robot, src).run()
    finally:
        robot.close()
        src.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
