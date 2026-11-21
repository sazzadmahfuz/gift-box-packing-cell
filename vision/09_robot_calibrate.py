"""
STEP 9 - Turn the paper calibration into ROBOT coordinates (no clicking needed).

04_calibrate.py saved where the 4 crosses are in the picture (pixels).
Here you only type the ROBOT X Y of the same 4 crosses, in the same order
(1 top-left, 2 top-right, 3 bottom-right, 4 bottom-left).

How to get the robot X Y: jog the suction cup exactly onto the cross centre
and read X and Y in the Python demo (Feedback panel) or in DobotStudio Pro.

    python 09_robot_calibrate.py

The camera and the crosses must not have moved since 04_calibrate.py.
"""
import cv2
import numpy as np

import vision_lib as vl

settings = vl.load_settings()
name = vl.homography_file()
old = vl.load_json(name)
if not old or "pixel_points" not in old:
    raise SystemExit("No calibration found - run 04_calibrate.py first.")

px = np.array(old["pixel_points"], dtype=np.float64)
labels = ["1 top-left", "2 top-right", "3 bottom-right", "4 bottom-left"]
robot = []
for i in range(len(px)):
    lab = labels[i] if i < 4 else str(i + 1)
    while True:
        t = input(f"Cross {lab}: robot X Y (e.g. 285.4 -120.7): ")
        try:
            x, y = [float(v) for v in t.replace(",", " ").split()]
            robot.append((x, y))
            break
        except ValueError:
            print("Type two numbers separated by a space.")

rb = np.array(robot, dtype=np.float64)
H, _ = cv2.findHomography(px, rb)
if H is None:
    raise SystemExit("Failed - check the numbers (points must not be in one line).")

# sanity check: compare distances between crosses (paper mm vs robot mm)
if "mm_points" in old:
    mm = np.array(old["mm_points"], dtype=np.float64)
    print("\nDistance check (paper ruler vs robot):")
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)]:
        d_paper = np.linalg.norm(mm[a] - mm[b])
        d_robot = np.linalg.norm(rb[a] - rb[b])
        print(f"  cross {a+1}-{b+1}: ruler {d_paper:6.1f} mm   robot {d_robot:6.1f} mm   diff {d_robot - d_paper:+.1f} mm")
    print("  (differences of a few mm are OK; big ones = a wrong number or the wrong order)")

vl.save_json(name.replace(".json", "_paper_backup.json"), old)
vl.save_json(name, {
    "H": H.tolist(),
    "pixel_points": px.tolist(),
    "robot_points_mm": rb.tolist(),
    "frame": "robot",
    "created": vl.timestamp(),
})
print("\nDone: positions are now in ROBOT coordinates.")
print('Next: in config/settings.json -> "robot" set "origin_on_table_mm": [0, 0]')
