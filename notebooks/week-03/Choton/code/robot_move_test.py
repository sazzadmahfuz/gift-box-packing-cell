"""
Robot move test - which kind of move works on our M1 Pro?

    python robot_move_test.py

Close the Dobot demo and 15_robot_setup.py first (only one program can control the robot).
Keep a hand near the emergency stop. Every test moves only a few mm UP.

For each test it prints OK or the alarm in plain words, then clears the alarm.
Send me the whole output.
"""

import time

from dobot_api import DobotApiDashboard, DobotApiMove
from robot_lib import explain_error, ok, _value

IP = "192.168.1.6"
dash = DobotApiDashboard(IP, 29999)
move = DobotApiMove(IP, 30003)


def pose():
    try:
        return [float(t) for t in _value(dash.GetPose()).split(",")[:4]]
    except Exception:
        return None


def start():
    dash.ClearError()
    time.sleep(0.5)
    dash.EnableRobot()
    time.sleep(1.5)
    dash.SpeedFactor(10)


def check(name, resp):
    time.sleep(0.5)
    err = explain_error(dash.GetErrorID())
    mode = str(dash.RobotMode()).strip()
    good = ok(resp) and err == "no error"
    print(f"\n[{'OK ' if good else 'BAD'}] {name}")
    print(f"      answer: {str(resp).strip()}")
    print(f"      mode:   {mode}   (5 = enabled, 9 = alarm)")
    print(f"      alarm:  {err}")
    print(f"      pose:   {pose()}")
    if not good:
        start()                           # clear the alarm before the next test


start()
p = pose()
print("start pose:", p)
if p is None:
    raise SystemExit("Could not read the pose - is the robot connected and the demo closed?")

print("\n=== Test 1: MoveJog Z+ for 0.3 s (like the demo button) ===")
r = move.MoveJog("Z+")
time.sleep(0.3)
move.MoveJog("")
check("MoveJog Z+", r)

print("\n=== Test 2: RelMovL  5 mm up ===")
r = move.RelMovL(0, 0, 5, 0)
move.Sync()
check("RelMovL z+5", r)

print("\n=== Test 3: MovJ  5 mm up, same R ===")
p = pose()
r = move.MovJ(p[0], p[1], p[2] + 5, p[3])
move.Sync()
check("MovJ z+5", r)

print("\n=== Test 4: MovL  5 mm up, same R ===")
p = pose()
r = move.MovL(p[0], p[1], p[2] + 5, p[3])
move.Sync()
check("MovL z+5", r)

print("\n=== Test 5: MovL  5 mm in X, same R ===")
p = pose()
r = move.MovL(p[0] + 5, p[1], p[2], p[3])
move.Sync()
check("MovL x+5", r)

dash.DisableRobot()
move.close()
dash.close()
print("\nDone. Send me everything above.")
