"""
Dobot M1 Pro - connection and error check. The robot does NOT move.

    python robot_check.py

Prints the robot mode, the error IDs, then tries ClearError, Continue and
EnableRobot and prints the answer of each. "0,..." = OK, "-1,..." = refused.
Close DobotStudio Pro and the Python demo first (only one program at a time).
"""
import time
from dobot_api import DobotApiDashboard

IP = "192.168.1.6"
MODES = {1: "INIT", 2: "BRAKE_OPEN", 3: "POWER_OFF", 4: "DISABLED", 5: "ENABLE",
         6: "BACKDRIVE", 7: "RUNNING", 8: "RECORDING", 9: "ERROR", 10: "PAUSE", 11: "JOG"}


def mode(d):
    r = d.RobotMode()
    try:
        m = int(r.split("{")[1].split("}")[0])
        return f"{m} = {MODES.get(m, '?')}   ({r.strip()})"
    except Exception:
        return r


d = DobotApiDashboard(IP, 29999)
print("Robot mode :", mode(d))
print("Error IDs  :", d.GetErrorID())
print("ClearError :", d.ClearError())
time.sleep(1)
print("Continue   :", d.Continue())
time.sleep(1)
print("EnableRobot:", d.EnableRobot())
time.sleep(2)
print("Robot mode :", mode(d))
print("Error IDs  :", d.GetErrorID())
print("Pose       :", d.GetPose())
d.close()
print("\nIf EnableRobot still answers -1: set DobotStudio Pro -> Settings -> Remote Control"
      " -> 'TCP/IP Secondary development' -> Apply, release the emergency stop, then disconnect DobotStudio.")
