# cell_live: live checks, real control and the operator console

**HARDWARE RUN.** cell_live talks to the real cell. Nothing in it is simulated: a component it
cannot see is shown as `NOT_OBSERVABLE`, with the reason. Teacher present and a hand on the
physical emergency stop for every run.

## What it does
Three parts, one program (`python -m cell_live`):
- **Live checks** (`checks/`): the state of every component, read-only. They never move the robot
  and never switch an output.
- **Real control** (`control/`): the box cycle on the real robot, only after the safety gate.
- **Operator console** (`web/`): a browser page at http://127.0.0.1:8765/, served by the same program.

One box, as the cell is built (17 Nov):
1. The box belt (boxes and lids, run by its own Arduino UNO) brings an open box until its sensor
   stops it. The camera confirms the box stands still under the taught box slot.
2. The robot runs the object belt (cards and candies) with DO3, DO16 and DO4. The belt stops when
   the objects the box still needs are usable in the pick area, or one reaches the stop line.
3. The robot goes home, out of the camera view, and the camera takes the pictures.
4. The robot picks each item (via the box slot) and places it in the box, then puts the lid on.
5. An operator takes the closed box away. The UNO brings the next box.

## Requirements
- Python 3.11 or newer, 64-bit. The core files use the standard library only.
- Packages, each used only by its own check: `numpy` (robot feedback), `opencv-python` (camera),
  `ultralytics` (vision model), `pyserial` (box belt controller, only if it is ever connected).
  Install all with `python -m pip install -r requirements.txt` (about 1.5 GB; do it before the lab).
  A missing package shows `FAIL` with the install command.
- Choton's code, model and calibration in `vision` (loaded by path, never changed).
- Laptop Ethernet on a fixed 192.168.1.x address (not .6, the robot), cable in the robot's LAN1.
- Close DobotStudio Pro and Choton's scripts: the robot keeps only one client on port 29999.

## How to run
Run every command from the `software/` folder:
```powershell
cd software
python -m cell_live                 # checks + console at http://127.0.0.1:8765/
python -m cell_live --once          # every check once, as JSON, then exit
python -m cell_live find-camera     # which camera indexes open on this laptop
python -m pytest cell_live -q       # the tests (no hardware needed)
```
Projector window: http://127.0.0.1:8765/?viewer=1#/show (Viewer mode, F11 for full screen).

Settings are in `live_config.json`. Every entry has a value, unit, source and status (VERIFIED,
FROM PHOTO, ASSUMED, CONFIRM, or SETTING for a choice). Change the lab values on the Settings
screen: a save needs a new status and source, keeps `live_config.json.bak`, and reloads the backend.

## A run
1. **Run screen:** speed, number of boxes, tick "My hand is on the physical emergency stop".
2. **Arm:** the gate checks 12 items and lists every problem, or gives a one-time token for 60 s.
3. **Start** within 60 s: the gate runs again, then the robot session opens.
4. During the run: **Pause** (at the next safe point, never while holding an item), **Resume**,
   **Skip box**, **Abort**, **Clear alarm**.

| Gate item | Passes when |
|---|---|
| 1 Speed | set, and not above `control.speed_percent_max` |
| 2 Teacher approval | `dobot.teacher_approval` holds a name and a date |
| 3 Reach | every taught point is 175–375 mm from the robot axis |
| 4 Calibration | Choton's `homography.json` is from the real robot and not older than `calibration.valid_from` |
| 5 Heights | the taught heights are set (no lid heights: tick "accept open box") |
| 6 Vision | model loaded, classes right, a camera frame younger than 2 s |
| 7 Robot | the dashboard check is OK and no other program holds the robot |
| 8 Outputs | DO channels set, all different, and the same as in Choton's `settings.json` |
| 9 Object belt levels | DO3 run, DO4 forward and DO16 enable levels confirmed |
| 10 Operator | hand on the emergency stop, a box count |
| 11 Cycle settings | the timeouts and `belts.box_restart` are set |
| 12 Way home | the straight move from where the arm stands to home stays inside `dobot.j1_range_deg` (`control/way_home.py`) |

## Stops
- **Physical emergency stop:** always first. The belts are not on it.
- **SOFTWARE STOP** (every screen, Viewer mode too): during a run, DO3, DO16, DO1 and DO2 off,
  then `EmergencyStop()`; then only Abort. With no run active, it switches the same outputs off
  and sends nothing else (`control/idle_stop.py`).
- **Stop object belt** (Run screen, any time): pauses a run, or stops the belt at once when idle.
- **PAUSED and FAULT** switch the object belt, suction and blow-off off. A lost connection cannot
  switch them off from the PC: the message says to use the physical stop.
- **The box belt cannot be stopped by software.** Its UNO has no link to the robot or this laptop.
  It stops only at its sensor, with the physical emergency stop, or by its power supply.

## The cell as built (17 Nov)
Sources: photos of the station, Rashmika's notebook and sketch
(`hardware/box_belt_arduino/ArduinoCode.ino`), the handwritten DO list, Choton's handover.
Always say "object belt" and "box belt": Rashmika's belt A is the box belt.

| Part | Wiring | Levels (`live_config.json`) |
|---|---|---|
| Object belt, DTCB 25261249 | TB6600 driver; step pulses from the box belt's UNO. DO3 = start/stop (ENA), DO4 = direction (DIR), DO16 = enable | runs with DO3 0 and DO16 1 (runs 17 Nov); DO4 1 = forward (DobotStudio test, 17 Nov) |
| Box belt, DTCB-2418-0718 | UNO R4 WiFi with an E18-D80NK sensor on pin 5; stops 50 ms after it sees a box, starts 50 ms after the box is lifted. Sends nothing over USB | `belts.box_restart` = `operator` |
| Gripper | vacuum cup on DO1, blow-off pulse on DO2 (0.2 s) | |
| Camera | USB camera on the stand, 1280 × 720 | `camera.index` = 1 on the demo laptop |
| Robot | Dobot M1 Pro at 192.168.1.6: dashboard 29999, moves 30003, feedback 30004 | speed from the teacher (`dobot.speed_percent`) |

## Live checks
States: `OK`, `WARN`, `FAIL`, `UNKNOWN`, `NOT_OBSERVABLE`. Each has a plain-language detail.

| id | Checks | Does not prove |
|---|---|---|
| `dobot_dashboard` | port 29999: `RobotMode()`, `GetErrorID()`, `GetPose()` only; alarms in words | that the robot can move |
| `dobot_feedback` | port 30004: one feedback packet (pose, DI/DO bits, enable, errors) | |
| `object_belt_do3`, `object_belt_dir`, `object_belt_power` | the DO3, DO4 and DO16 bits from the feedback | that the belt runs: they are the commanded outputs |
| `camera` | opens the camera, size and frames per second; while a run holds the camera, reports the run's frames instead | image quality |
| `vision_model` | Choton's `best.pt` loads, classes match | detection accuracy |
| `calibration` | `homography.json` parses; date and mean error; WARN if older than `calibration.valid_from` | that the camera has not moved |
| `robodk` | TCP connect to localhost:20500 | that the station is right |
| `box_belt_nano` | the box belt controller over serial; NOT_OBSERVABLE (not connected to this PC) | |

`dobot_link.py` is the only file that opens robot sockets. A run holds port 29999 from its first
command; the checks then report the run's state instead of connecting.

## How the control works
- **Choton's code, unchanged:** `robot_lib`, `yolo_lib`, `vision_lib` and `straighten_turn` are loaded
  from his folder. His `main()` and his waiting loops (`input()`, windows) are not used.
- **Allowlist** (`control/robot_client.py`): on the move port only `MovL` and `Sync`. Every target
  is checked against the reach and the lowest taught height; only the configured outputs and the
  armed speed are allowed. A missing reply stops the run instead of letting it go on.
- **Object belt** (`control/feed.py`): the belt stops when the objects the box still needs are
  usable in the pick area (3 pictures in a row), or one reaches the stop line
  `control.feed_stop_y_mm` (2 pictures). Usable: not at the picture edge, inside the reach, inside
  `control.pick_area_mm`. Nothing left in reach: the belt runs again, at most
  `control.refeeds_without_pick_max` times, then PAUSED "object missing".
- **Every pick goes via the box slot** (approved by the teacher, 17 Nov): a straight MovL from home to
  the object belt needed J1 near 90° and stopped with alarm 23. Items whose pick needs J1 above
  `control.arm_j1_max_deg` are out of reach (`control/arm_reach.py`).
- **Box and lid:** WAIT_BOX pauses when the box centre is more than `control.box_slot_tolerance_mm`
  from the taught slot. The lid (`control/lid.py`) is taken at its centre, which must be inside
  375 mm. Laid against the right side of the box, its centre is at 366–376 mm, so the lid step can
  pause by a few mm; the Run and Vision screens have a Lid line that says so before the run.
- **Camera:** one reader at a time. A lost camera is released at once, so it can be opened again.

## State table
| State | Does | Leaves to |
|---|---|---|
| IDLE | no run | WAIT_BOX at Start |
| WAIT_BOX | robot home; waits for an open box standing still under the slot | FEED_OBJECTS; PAUSED "no box" after `control.box_wait_timeout_s` |
| FEED_OBJECTS | object belt on until the stop rule holds | LOOK; PAUSED "not enough objects" after `control.object_feed_timeout_s` |
| LOOK | robot home, pictures | PICK_PLACE |
| PICK_PLACE | pick and place each item | CLOSE_LID, or FEED_OBJECTS for missing items |
| CLOSE_LID | lid on the box | RELEASE_BOX |
| RELEASE_BOX | waits until the operator has taken the box | BOX_DONE; PAUSED "box did not leave" after `control.box_leave_timeout_s` |
| BOX_DONE | box counted | WAIT_BOX, or IDLE after the last box |
| PAUSED | outputs off, robot still | Resume (the paused step again), Skip box, Abort |
| FAULT | robot alarm, lost connection or lost camera; outputs off if possible | Abort only |

## How to read the run log
- **File:** `testing/live_runs/<YYYYmmdd_HHMMSS>.csv`. The pictures of each decision are in
  `<stamp>_pictures/`. `testing/` is gitignored: add evidence with `git add -f`.
- **Line 1:** `# HARDWARE RUN; speed ...; boxes requested ...; teacher approval: ...; sha256 ...` (hashes
  of `live_config.json`, Choton's `settings.json` and `homography.json`). **Line 2:** the header.
- **Columns:** `time_s` (s since the start), `box`, `state`, `event`, `command`, `reply`,
  `detections`, `fault`. One row per command and reply, state change, detection change, pause and fault.

## Operator console
| Screen | Shows |
|---|---|
| Overview | the cycle belt, the cell map and one row per component; click a row for its history and raw reply |
| Run | the gate checklist, Arm and Start, the run controls, Stop object belt, recent events |
| Vision | the camera with the reach circle, pick area, stop line and box slot, and what the belt would do now |
| Logs | live events and the run logs, per-box times and failures |
| Settings | the lab values with status and source; camera and serial port scan |
| Help | the wiring, the start-up order, what each status means, what to do if something goes wrong |

Plain HTML, CSS and JavaScript, nothing from the internet; Chrome or Edge 111 or newer. Control
(`/api/run/*`, `POST /api/config`, `/api/vision/start`) answers only on this laptop, unless started
with `--host`. Hand checks of the page are in `web/MANUAL_TESTS.md`.

The simulation of the same cell is `software/cell_sim/` (see its README); its desktop window is
`software/cell_ui/`.

## What is not validated
- **Three full boxes so far.** On 17 Nov evening three boxes were filled and closed on the real
  cell (`testing/live_runs/20261117_220813.csv`, `_221031`, `_221307`; the last in 65 s without a
  pause). The lid lands a little off and does not close perfectly. Several boxes in a row are not tested.
- **Commanded is not running.** The DO lamps show what the robot commands, not what the belt does.
- **Calibration:** made with Choton's `15_robot_setup.py` on 17 Nov at 21:26 (5 marks, mean error
  0.92 mm), with `calibration.view_correction` for the camera's small turn in its holder afterwards.
  It is valid on the object belt surface only; the box and lid are higher, so their X/Y is a few mm
  off. If the camera or the robot moves, calibrate again. The console does not notice a camera move.
- **Speed:** Choton tested the real robot up to 40 %. Higher speeds are not tested.
- **Moves:** only `MovL`. Choton's long moves use `MovJ` after `SetArmOrientation(0)`; that is not
  allowed here until it is requested with the teacher's approval.
- **The box belt** is not observed or controlled by this program: the camera is the only check of the box.
