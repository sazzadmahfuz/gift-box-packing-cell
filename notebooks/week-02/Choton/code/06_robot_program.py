"""
STEP 6 - Make an igus robot program from what the camera sees.

    python 06_robot_program.py                 (live camera, one snapshot)
    python 06_robot_program.py --image photo.png

1. Detects the cards and candies (needs 04_calibrate.py done first).
2. Chooses what goes into box 1 (config/settings.json -> "box_contents").
3. Converts each pick position to robot X/Y (settings.json -> "robot").
4. Writes an igus Robot Control program (.xml, same format as Sazzad's
   prg_giftbox_sim.xml) into the folder  robot_programs/
5. Saves a picture with the robot reach area and the pick order.

Load the .xml in igus Robot Control (simulation first!) to run it.
If an object is outside the robot's reach, NO program is written:
move the object inside the yellow area and run again.

NOTE: robot positions are TEMPORARY until we calibrate with the robot tip.
"""

import argparse
import os

import cv2

import vision_lib as vl

PROGRAM_DIR = os.path.join(vl.VISION_DIR, "robot_programs")


class Program:
    """Builds the igus Robot Control XML, one command at a time."""

    def __init__(self, r):
        self.r = r
        self.lines = []
        self.nr = 0

    def linear(self, x, y, z, vel, descr):
        self.nr += 1
        self.lines.append(
            f'    <Linear AbortCondition="False" Nr="{self.nr}" Source="Numerical" '
            f'vel="{vel}" acc="200" smooth="0" UserFrame="#base" '
            f'x="{x:.1f}" y="{y:.1f}" z="{z:.1f}" a="0" b="0" c="180" '
            f'e1="0" e2="0" e3="0" Descr="{descr}" />')

    def output(self, state, descr):
        self.nr += 1
        self.lines.append(
            f'    <Output Nr="{self.nr}" Channel="{self.r["vacuum_output"]}" '
            f'State="{"True" if state else "False"}" Descr="{descr}" />')

    def wait(self, seconds, descr):
        self.nr += 1
        self.lines.append(
            f'    <Wait Nr="{self.nr}" Type="Time" Seconds="{seconds}" Descr="{descr}" />')

    def text(self):
        head = ('<?xml version="1.0" encoding="utf-8"?>\n<Program>\n'
                '    <Header RobotName="igus Delta" RobotType="DLE-DR-0001" GripperType="" '
                'Software="iRC V902-15-000" VelocitySetting="0" />\n')
        return head + "\n".join(self.lines) + "\n</Program>\n"


def build_program(items, r):
    """items = list of (object, (place_x, place_y)) in pick order."""
    p = Program(r)
    fast, slow = r["fast_vel"], r["slow_vel"]
    tz, pz, lz, hz = r["travel_z"], r["pick_z"], r["place_z"], r["home_z"]

    p.linear(0, 0, hz, fast, "Home")
    p.output(False, "Vacuum off at start")
    p.linear(0, 0, tz, fast, "Down to travel height")
    for o, (bx, by) in items:
        name = f'{o["color"]} {o["type"]}'
        x, y = o["x_robot"], o["y_robot"]
        p.linear(x, y, tz, fast, f"Above {name}")
        p.linear(x, y, pz, slow, f"Down to {name}")
        p.output(True, f"Vacuum on {name}")
        p.wait(0.3, f"Build vacuum {name}")
        p.linear(x, y, tz, slow, f"Lift {name}")
        p.linear(bx, by, tz, fast, f"Above box for {name}")
        p.linear(bx, by, lz, slow, f"Lower {name} into box")
        p.output(False, f"Vacuum off {name}")
        p.wait(0.15, f"Release {name}")
        p.linear(bx, by, tz, slow, f"Lift clear {name}")
    p.linear(0, 0, tz, fast, "Back above centre")
    p.linear(0, 0, hz, fast, "Home")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use a saved photo instead of the live camera")
    ap.add_argument("--no-window", action="store_true")
    args = ap.parse_args()

    settings = vl.load_settings()
    colors = vl.load_colors()
    H = vl.load_homography()
    r = settings.get("robot")
    if H is None:
        print("No calibration yet - run 04_calibrate.py first.")
        return
    if not r:
        print('No "robot" section in config/settings.json.')
        return

    src = vl.FrameSource(args.image, settings)
    frame, objects, _ = vl.detect_stable(src, colors, settings, H)   # 15 frames, median position
    src.release()

    print(vl.summarize(objects))
    boxes, problems = vl.plan_boxes(objects, 1, settings)
    annotated = vl.draw_objects(frame, objects, colors, settings, H)

    if not boxes:
        for p in problems:
            print("WARNING:", p)
        print("No program written.")
        return

    items = boxes[0]["items"]
    slots = r["box_slots"]
    if len(items) > len(slots):
        print(f"Only {len(slots)} box_slots in settings.json, but {len(items)} items. No program written.")
        return

    bad_slots = [sl for sl in slots[:len(items)] if not vl.in_reach(sl[0], sl[1], settings)]
    if bad_slots:
        print(f"Box positions {bad_slots} are outside the robot reach - fix box_slots in settings.json. No program written.")
        return

    print("\n=== PICK ORDER (box 1) ===")
    out = [o for o in items if not o["reachable"]]
    for i, (o, slot) in enumerate(zip(items, slots), 1):
        flag = "" if o["reachable"] else "   <-- OUT OF REACH"
        if o.get("covered"):
            flag += "   (partly covered - picked last)"
        print(f"{i}. {o['color']:<7} {o['type']:<6} pick robot ({o['x_robot']:6.1f}, {o['y_robot']:6.1f})"
              f"  ->  place ({slot[0]}, {slot[1]}){flag}")
        vl._put_label(annotated, f"#{i}", (int(o["u"]) - 12, int(o["v"]) + 30), (0, 255, 255))

    os.makedirs(vl.RESULTS_DIR, exist_ok=True)
    img_path = os.path.join(vl.RESULTS_DIR, f"robot_plan_{vl.timestamp()}.jpg")
    cv2.imwrite(img_path, annotated)
    print(f"[saved] {img_path}")

    if out:
        print(f"\n{len(out)} object(s) OUT OF REACH - move them inside the yellow area.")
        print("No program written.")
    else:
        prog = build_program(list(zip(items, slots)), r)
        os.makedirs(PROGRAM_DIR, exist_ok=True)
        xml_path = os.path.join(PROGRAM_DIR, f"prg_from_vision_{vl.timestamp()}.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(prog.text())
        print(f"\n[saved] {xml_path}  ({prog.nr} commands)")
        print("Load it in igus Robot Control - test in SIMULATION first.")

    if not args.no_window:
        vl.show("06 robot program (any key = close)", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
