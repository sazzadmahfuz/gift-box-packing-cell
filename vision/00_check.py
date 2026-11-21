"""
STEP 0 - Check that everything is ready. Run it FIRST at the university.

    python 00_check.py            (everything)
    python 00_check.py --no-robot (at home: skip the robot)

Nothing moves. Every line says OK or what to do.
"""

import argparse
import os
import socket

import vision_lib as vl
import yolo_lib as yl

ok_all = True


def line(ok, text, fix=""):
    global ok_all
    ok_all &= ok
    print(f"  {'OK  ' if ok else 'TODO'}  {text}" + ("" if ok else f"\n        -> {fix}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-robot", action="store_true")
    args = ap.parse_args()
    s = vl.load_settings()
    r = s.get("robot", {})

    print("\n1. Software")
    try:
        import ultralytics  # noqa: F401
        line(True, "YOLO (ultralytics) installed")
    except ImportError:
        line(False, "YOLO not installed", "pip install ultralytics")
    line(os.path.exists(yl.model_path(s)), f"trained model {yl.model_path(s)}", "python 12_train.py")

    print("\n2. Camera")
    cam = s.get("camera")
    line(cam == "usb", f'camera = "{cam}"', 'settings.json: "camera": "usb" (USB camera on the belt)')
    try:
        src = vl.FrameSource(None, s)
        f = src.read()
        src.release()
        line(f is not None, f"camera picture {f.shape[1]} x {f.shape[0]}")
    except Exception as e:
        line(False, f"camera does not open ({e})",
             "plug in the USB camera; wrong number? change cameras -> usb -> camera_index (0, 1, 2)")

    print("\n3. Calibration")
    h = vl.load_json(vl.homography_file()) or {}
    line(not h.get("practice"), "calibration is not from practice (--sim)",
         "python 15_robot_setup.py on the REAL robot (part A)")
    line(not r.get("_practice"), "robot points are not from practice (--sim)",
         "python 15_robot_setup.py on the REAL robot (keys h t p b)")
    line(h.get("frame") == "robot", f'{vl.homography_file()}: {h.get("frame", "missing")}'
         + (f', {len(h.get("pixel_points", []))} marks, error {h.get("mean_error_mm", 0):.1f} mm'
            if h.get("frame") == "robot" else ""),
         "python 15_robot_setup.py  (part A)")

    print("\n4. Robot points (settings.json -> robot)")
    for k, what in [("home", "h"), ("travel_z", "t"), ("pick_z", "p"), ("place_z", "b"), ("box_slots", "b")]:
        line(r.get(k) is not None, f"{k} = {r.get(k)}", f"python 15_robot_setup.py, key {what}")
    if r.get("pick_z") is not None and r.get("travel_z") is not None:
        line(r["travel_z"] > r["pick_z"] + 20, f"travel_z {r['travel_z']} is > 20 mm above pick_z {r['pick_z']}",
             "teach a higher travel height (key t)")
    pzt = r.get("pick_z_by_type") or {}
    line("candy" in pzt, f"pick height candy = {pzt.get('candy')}", "15_robot_setup.py key o (cup on top of a candy)")
    line(r.get("box_sensor_di") is not None, f"box sensor = DI{r.get('box_sensor_di')}",
         "15_robot_setup.py key i (or leave it: then you press ENTER when the box is there)")
    print(f"        (taught at home from Rashmika's program - CHECK them: home {r.get('home')}, "
          f"pick_z {r.get('pick_z')}, box {r.get('box_slots')})")

    print("\n5. Box contents")
    print(f"        {s.get('box_contents')}  different colours: {s.get('require_different_colors')}")

    if not args.no_robot:
        print("\n6. Robot network")
        ip = r.get("ip", "192.168.1.6")
        for port in (29999, 30003):
            try:
                c = socket.create_connection((ip, port), timeout=2)
                c.close()
                line(True, f"robot {ip}:{port} answers")
            except OSError:
                line(False, f"robot {ip}:{port} does not answer",
                     "LAN cable in, laptop IP 192.168.1.x, robot on, DobotStudio DISCONNECTED")

    print("\n" + ("ALL READY:  python 14_pick_and_place.py   (dry run)   then   --run --speed 10"
                  if ok_all else "Fix the TODO lines above, then run this check again."))


if __name__ == "__main__":
    main()
