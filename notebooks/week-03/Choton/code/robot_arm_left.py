"""
Put the arm back to LEFT (the normal way Rashmika uses it).

    python robot_arm_left.py

During robot_move_test.py a MovJ flipped the elbow from Left to Right
(same X, Y, Z, but the arm bent the other way). This script flips it back once.

!! The arm SWINGS to the other side (the tool stays at the same point).
!! Before you run it: nothing within the arm's reach, hand on the emergency stop.
Close the demo and the other scripts first.
"""

import time

from dobot_api import DobotApiDashboard, DobotApiMove
from robot_lib import _value, explain_error

import vision_lib as vl

IP = "192.168.1.6"
dash = DobotApiDashboard(IP, 29999)
move = DobotApiMove(IP, 30003)


def pose():
    t = _value(dash.GetPose()).split(",")
    return [float(v) for v in t[:4]], t[-1].strip()


dash.ClearError()
time.sleep(0.5)
dash.EnableRobot()
time.sleep(1.5)
dash.SpeedFactor(10)

p, hand = pose()
print(f"\nNow: {p}  arm = {hand}")
if hand == "Left":
    print("The arm is already Left. Nothing to do.")
else:
    input("The arm will swing to LEFT. Area clear and hand on the emergency stop? Press ENTER ...")
    for code in (0, 1):
        print(f"\nTrying SetArmOrientation({code}) ...")
        print("  answer:", str(dash.SetArmOrientation(code)).strip())
        print("  MovJ  :", str(move.MovJ(*p)).strip())
        move.Sync()
        time.sleep(0.5)
        p2, hand = pose()
        print(f"  now {p2}  arm = {hand}  alarm: {explain_error(dash.GetErrorID())}")
        if hand == "Left":
            raw = vl.load_json("settings.json", {})
            raw["robot"]["arm_left_code"] = code
            vl.save_json("settings.json", raw)
            print(f"\nDONE: the arm is Left again. Code for Left = {code} (saved in settings.json).")
            break
    else:
        print("\nThe arm did not flip. Use the demo or the drag button to bring it back, and tell Claude.")

dash.DisableRobot()
move.close()
dash.close()
