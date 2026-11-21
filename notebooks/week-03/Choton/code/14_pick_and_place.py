"""
STEP 14 - The whole prototype: box arrives -> camera finds cards and candies
(YOLO) -> robot picks them one by one and puts them into the box.

SAFETY: default is a DRY RUN (only prints the robot commands).
    python 14_pick_and_place.py                         (dry run, live camera)
    python 14_pick_and_place.py --image photo.jpg       (dry run on a saved picture - works at home)
    python 14_pick_and_place.py --run --speed 10        (robot really moves - hand on the emergency stop!)
    python 14_pick_and_place.py --run --boxes 3         (fill 3 boxes one after the other)
    python 14_pick_and_place.py --pose                  (print the robot pose, no motion)
    python 14_pick_and_place.py --sim --image photo.jpg (PRACTICE at home: whole cycle, simulated robot)

One cycle (per box):
  1. Wait for the box. The box conveyor is stopped by its own sensor (Arduino Nano);
     the camera waits until it sees an open box standing still. (Or robot input
     "box_sensor_di", or ENTER when the model has no "box" class.)
  1b. Object conveyor: robot output "belt_do" (DO3 -> relay -> Nano) runs the belt until
     the camera sees 1 card + 2 candies fully in the pick area, then stops it.
     belt_do = null: objects are put on the belt by hand.
  2. Robot goes "home" (out of the camera view), camera looks (YOLO, 8 frames).
  3. Chooses the next object: box_contents (1 card + 2 candies), different
     colours if "require_different_colors" is true, not at the picture edge,
     inside the robot reach. Highest confidence first.
  4. Pick -> place into the box -> back home -> look again (so a failed pick
     or a moved object is seen) -> until the box is complete.
  5. Box finished: conveyor moves it on (if conveyor_do) / next box.

Before --run, settings.json -> "robot" must be measured (see notebook week 3):
home, travel_z, pick_z, place_z, box_slots, vacuum_do, blow_do, box_sensor_di.
And the camera must be calibrated to robot X/Y (04_calibrate.py + 09_robot_calibrate.py).
"""

import argparse
import time

import cv2

import robot_lib
import vision_lib as vl
import yolo_lib as yl

WIN = "14 pick and place"


def wait_for_box(robot, r, run, src=None, model=None, settings=None, H=None):
    di = r.get("box_sensor_di")
    if di is None and src is not None and src.image is None and r.get("box_check", "camera") == "camera" \
            and "box" in getattr(model, "names", {}).values():     # the model knows boxes
        wait_box_camera(robot, src, model, settings, H)
        return
    if di is None or not run:
        input(">>> Put the box in place and press ENTER ")
        return
    on = r.get("box_sensor_on", 1)
    if r.get("conveyor_do"):
        robot.do(r["conveyor_do"], 1, "box conveyor ON")
    print(f"Waiting for the box sensor (DI{di} = {on}) ... Ctrl+C = stop")
    while robot.di(di) != on:
        time.sleep(0.05)
    if r.get("conveyor_do"):
        robot.do(r["conveyor_do"], 0, "box conveyor OFF - box is here")
    print("Box detected.")


def wait_box_camera(robot, src, model, settings, H, frames_needed=5):
    """The box conveyor is stopped by its own sensor (Arduino Nano). We only WATCH:
    the box is ready when the camera sees an open box that stands still."""
    robot.home()
    print("Waiting for the box (camera) ... Ctrl+C = stop")
    last, still = None, 0
    while still < frames_needed:
        frame = src.read()
        objs = yl.detect(frame, model, settings, H)
        boxes = [o for o in objs if o["type"] == "box" and not o["edge"]]
        vl.show(WIN, yl.draw(frame, objs, settings, H))
        cv2.waitKey(1)
        if not boxes:
            last, still = None, 0
            continue
        b = max(boxes, key=lambda o: o["conf"])
        moved = last is None or abs(b["u"] - last[0]) + abs(b["v"] - last[1]) > 6
        still = 0 if moved else still + 1
        last = (b["u"], b["v"])
    print("Box is here and stopped.")


def feed_objects(robot, r, src, model, settings, H):
    """Object conveyor (robot output belt_do -> relay -> Arduino Nano -> belt motor):
    run the belt until the camera sees everything the box needs (fully inside the
    pick area), then stop it."""
    do = r.get("belt_do")
    if do is None or src.image is not None:
        return                                   # no belt control: objects are put there by hand
    on = int(r.get("belt_on", 1))
    want = settings.get("box_contents", {"card": 1, "candy": 2})
    robot.home()                                 # robot out of the camera view
    robot.do(do, on, "object conveyor ON")
    t0, ready_frames = time.time(), 0
    try:
        while ready_frames < 3:                  # 3 pictures in a row: not a flicker
            frame = src.read()
            objs = yl.detect(frame, model, settings, H)
            count = {k: sum(1 for o in objs if o["type"] == k and yl.usable(o)) for k in want}
            ready = all(count[k] >= n for k, n in want.items())
            ready_frames = ready_frames + 1 if ready else 0
            view = yl.draw(frame, objs, settings, H)
            vl._put_label(view, "conveyor running - waiting for " +
                          ", ".join(f"{k} {count[k]}/{n}" for k, n in want.items()),
                          (10, view.shape[0] - 12), (0, 255, 255))
            vl.show(WIN, view)
            cv2.waitKey(1)
            if time.time() - t0 > r.get("belt_timeout_s", 60):
                robot.do(do, 1 - on, "object conveyor OFF (timeout)")
                input(">>> Not enough objects arrived. Put more on the belt and press ENTER ")
                robot.do(do, on, "object conveyor ON")
                t0 = time.time()
    finally:
        robot.do(do, 1 - on, "object conveyor OFF")
    time.sleep(r.get("belt_settle_s", 0.5))     # let the objects stop moving


def send_box_away(robot, r, run):
    if not (run and r.get("conveyor_do")):
        print(">>> Box complete - take it away / start the conveyor.")
        return
    di, on = r.get("box_sensor_di"), r.get("box_sensor_on", 1)
    robot.do(r["conveyor_do"], 1, "box conveyor ON - send the full box on")
    t0 = time.time()
    while di is not None and robot.di(di) == on and time.time() - t0 < 10:
        time.sleep(0.05)
    time.sleep(0.5)
    robot.do(r["conveyor_do"], 0, "box conveyor OFF")


def close_box(robot, r, objects, settings):
    """Box is full: pick the lid (found by the camera) and put it on the box."""
    if not r.get("close_lid", True):
        return
    if r.get("lid_pick_z") is None or r.get("lid_place_z") is None:
        print(">>> Lid heights not taught yet (15_robot_setup.py keys l and j) - box stays open.")
        return
    lids = [o for o in objects if o["type"] == "lid" and "x_robot" in o
            and vl.in_reach(o["x_robot"], o["y_robot"], settings)]
    if not lids:
        print(">>> No lid found by the camera - box stays open.")
        return
    lid = max(lids, key=lambda o: o["conf"])
    slot = r["box_slots"][0]
    print(f"--- close the box: lid (conf {lid['conf']}) at robot ({lid['x_robot']:.1f}, {lid['y_robot']:.1f})")
    robot.place_lid(lid["x_robot"], lid["y_robot"], slot, straighten_turn(lid, objects, r))


def straighten_turn(target, objects, r):
    """How many degrees the robot turns the object so its long side lies along the box.
    Box direction: from the camera (a detected "box"), else settings robot -> box_angle_deg.
    r_sign = +1 or -1 (which way R+ turns the tool - check once on the robot)."""
    if not r.get("straighten", True) or "angle_robot" not in target:
        return 0.0
    boxes = [o for o in objects if o["type"] == "box" and "angle_robot" in o]
    if boxes:
        box_angle = max(boxes, key=lambda o: o["conf"])["angle_robot"]
        src = "camera"
    elif r.get("box_angle_deg") is not None:
        box_angle, src = r["box_angle_deg"], "settings"
    else:
        print("    (no box direction known - object is not turned)")
        return 0.0
    turn = yl.wrap90(box_angle - target["angle_robot"]) * r.get("r_sign", 1)
    print(f"    object long side {target['angle_robot']:+.0f} deg, box {box_angle:+.0f} deg ({src})"
          f" -> turn the tool {turn:+.0f} deg")
    return turn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="really move the robot")
    ap.add_argument("--speed", type=int, default=10, help="speed in %% (start low!)")
    ap.add_argument("--boxes", type=int, default=1, help="how many boxes to fill")
    ap.add_argument("--image", help="saved picture instead of the camera (dry run only)")
    ap.add_argument("--pose", action="store_true", help="only print the robot pose")
    ap.add_argument("--sim", action="store_true", help="practice: simulated robot (no real robot)")
    args = ap.parse_args()
    if args.sim:
        args.run = False
    if args.image and args.run:
        raise SystemExit("--image is for dry runs only.")

    settings = vl.load_settings()
    r = settings["robot"]

    if args.pose:
        rb = robot_lib.Robot(settings, run=True, speed=1)
        print("Pose (X, Y, Z, R):", rb.pose())
        rb.close()
        return

    H = vl.load_homography()
    hdata = vl.load_json(vl.homography_file()) or {}
    pixel_test = False
    if H is None or hdata.get("frame") != "robot":
        if args.run:
            raise SystemExit("Not calibrated to the robot - run 15_robot_setup.py (part A) first.")
        print("NOT calibrated to the robot -> PIXEL TEST: the printed X/Y are picture pixels, "
              "not robot mm.\nThis only tests detection + pick order + robot command sequence.")
        H, pixel_test = None, True
    else:
        if args.run and (hdata.get("practice") or r.get("_practice")):
            raise SystemExit("The calibration / robot points are from PRACTICE (--sim). "
                             "Do 15_robot_setup.py on the real robot first.")
        bad = [s for s in r["box_slots"] if not vl.in_reach(s[0], s[1], settings)]
        if bad:
            raise SystemExit(f"box_slots {bad} are outside the robot reach - check settings.json.")

    model = yl.load_model(settings)
    src = vl.FrameSource(args.image, settings)

    if args.run and input(f"Robot {r.get('ip')} will MOVE at {args.speed} %. "
                          "Hand on the emergency stop. Type yes: ").strip().lower() != "yes":
        raise SystemExit("Cancelled.")
    robot = robot_lib.Robot(settings, run=args.run, speed=args.speed, sim=args.sim)

    try:
        for box in range(1, args.boxes + 1):
            print(f"\n========== BOX {box}/{args.boxes} ==========")
            wait_for_box(robot, r, args.run, src, model, settings, H)
            feed_objects(robot, r, src, model, settings, H)
            placed = []
            gone = []          # dry run: objects we pretend were picked
            look = True        # take a new picture only when needed (not after every pick)
            while not yl.box_complete(placed, settings):
                if look:
                    robot.home()   # robot out of the camera view for the picture
                    frame, objects = yl.detect_stable(src, model, settings, H, frames=8)
                    if pixel_test:     # no calibration: use the pixel centre as "robot" X/Y
                        for o in objects:
                            o["x_robot"], o["y_robot"], o["reachable"] = o["u"], o["v"], True
                    look = False
                    if args.run:
                        gone = []  # new picture: picked objects are really gone from it
                # objects already picked are no longer on the belt
                objects = [o for o in objects
                           if all(abs(o["u"] - g["u"]) + abs(o["v"] - g["v"]) > 10 for g in gone)]
                target, msg = yl.next_pick(objects, placed, settings)
                vl.show(WIN, yl.draw(frame, objects, settings, H, highlight=target))
                cv2.waitKey(1)
                print(yl.summarize(objects))
                if target is None:
                    print(">>>", msg)
                    if args.image:
                        print("(saved picture: cannot change the objects - stopping)")
                        break
                    input(">>> Fix it and press ENTER to look again ")
                    look = True
                    continue
                slot = r["box_slots"][len(placed) % len(r["box_slots"])]
                name = f'{target["color"]} {target["type"]}'
                print(f"--- pick {msg}: {name} (conf {target['conf']}) at robot "
                      f"({target['x_robot']:.1f}, {target['y_robot']:.1f}) -> box {tuple(slot)}")
                turn = straighten_turn(target, objects, r)
                robot.pick_and_place(target["x_robot"], target["y_robot"], slot, name, target["type"], turn)
                placed.append(target)
                gone.append(target)
            if yl.box_complete(placed, settings):
                close_box(robot, r, objects, settings)
            robot.home()
            print(f"Box {box}: placed " + ", ".join(f'{p["color"]} {p["type"]}' for p in placed))
            if yl.box_complete(placed, settings):
                send_box_away(robot, r, args.run)
            else:
                break
        print("\nDone." if args.run else "\nPractice run finished." if args.sim else
              "\nDry run finished. Check the X/Y numbers, then try --run --speed 10.")
        cv2.waitKey(0 if not args.run else 1000)
    except KeyboardInterrupt:
        print("\nStopped by the user (Ctrl+C).")
    except Exception as e:
        print("\nSTOPPED:", e)
    finally:
        robot.close()
        src.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
