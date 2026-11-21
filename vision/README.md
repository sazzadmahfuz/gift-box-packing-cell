# Machine Vision + Robot Code (Week 3) – Choton

Camera (YOLO) finds cards, candies, the box and the lid → Dobot M1 Pro picks 1 card + 2 candies,
turns them straight, puts them in the box and closes it with the lid.

Run everything from this folder:

```
cd "C:\Users\anamu\Desktop\Project 2 machine vision\notebooks\week-03\Choton\code"
```

## 1. Programs (in the order you use them)

| Step | Command | What it does |
|---|---|---|
| Check | `python 00_check.py` | Camera, model, calibration, robot network – all OK? |
| Camera number | `python find_camera.py` | Shows cameras 0–3, saves the USB camera number |
| Pictures | `python 10_collect_images.py --session belt_usb_3` | `b` = empty background, SPACE = picture, `q` = quit |
| Labels | `python 11_label.py --session belt_usb_3` | Draw boxes, `1`–`4` = card / candy / box / lid, SPACE = next |
| Train | `python 12_train.py --val belt_usb_1_test home_phone_1 --repeat belt_usb_2=3` | Writes `../models/best.pt` (about 30 min on the laptop CPU) |
| Detect | `python 13_yolo_detect.py` | Live camera with class, score, angle and robot X/Y |
| Robot setup | `python 15_robot_setup.py` | Calibration + teaching points + I/O test (keys below) |
| Run | `python 14_pick_and_place.py` | Dry run (robot does not move, commands printed) |
| Run robot | `python 14_pick_and_place.py --run --speed 30` | Robot moves – hand on the emergency stop |
| Practice | `python 14_pick_and_place.py --sim --image picture.jpg` | Whole cycle with a simulated robot (at home) |

Helpers: `robot_check.py` (connection + alarms), `robot_move_test.py` (tests the move commands),
`robot_arm_left.py` (puts the arm back to Left). Old week 2 scripts, not needed any more:
`01_camera_test.py`, `04_calibrate.py`, `09_robot_calibrate.py`.

### Keys in `15_robot_setup.py` (click the camera window first)

| Key | Action |
|---|---|
| w / s, a / d, r / f | Move X+ / X−, Y+ / Y−, Z up / down |
| 1 / 2 / 3 | Jog small / medium / big |
| e | Clear a robot alarm (red light) |
| m | Hand-guiding on/off |
| k, click, k | Freeze the picture, click the calibration crosses in order, live again |
| c | Cup is on the current cross → save robot point (4+ points = calibrated) |
| x + click | Test: robot goes above the clicked spot |
| t / p / o | Save travel height / card pick height / candy pick height |
| b | Save box position + drop height |
| l / j | Save lid pick height / lid close height (lid on the box) |
| h | Save home (out of the camera view) |
| v / g / i | Suction on/off, blow-off pulse, read the 16 inputs |
| q | Save and quit |

## 2. Hardware and I/O

| Item | Value |
|---|---|
| Robot | Dobot M1 Pro, IP `192.168.1.6`, dashboard port 29999, move port 30003 |
| Connection | Only ONE program at a time (close DobotStudio / Dobot demo first) |
| Arm side | Left (`SetArmOrientation(0)` at start); every move is `MovL` (a `MovJ` can flip the arm) |
| DO1 | Suction cup |
| DO2 | Blow-off pulse 0.2 s (drops the object) |
| DO3 | Relay → Arduino Nano → object conveyor (CB2). ON = runs (to check) |
| Box conveyor (CB1) | Sensor + motor on the Arduino Nano – stops the box by itself |
| Camera | USB camera, 1280 × 720, above both conveyors |

## 3. Settings (`config/settings.json`)

| Key | Meaning |
|---|---|
| `yolo.model`, `yolo.classes`, `yolo.conf` | Model file, classes (card, candy, box, lid), score limit 0.45 |
| `box_contents` | `{"card": 1, "candy": 2}` |
| `require_different_colors` | `false` (both KitKats are red) |
| `robot.travel_z` | Safe flying height (104.7 – higher hits the vacuum hose) |
| `robot.pick_z_by_type` | Pick height per class: card 63.7, candy 72.1 |
| `robot.box_slots`, `robot.place_z` | Box middle X/Y and drop height |
| `robot.home` | Home X, Y, Z, R (robot out of the camera view) |
| `robot.r_angle` | Tool angle R used for picking |
| `robot.lid_pick_z`, `robot.lid_place_z` | Lid heights (keys l, j) – box stays open until they are set |
| `robot.straighten`, `robot.r_sign` | Turn objects straight; `r_sign` = −1 if R+ turns the other way |
| `robot.belt_do`, `robot.belt_on` | Object conveyor output (3) and the value that makes it run (1) |
| `robot.belt_timeout_s` | Conveyor stops if not enough objects arrive (60 s) |
| `robot.box_check` | `"camera"` = wait until the camera sees the box standing still |

`config/homography.json`: 3 × 3 matrix pixel → robot X/Y (mm), the clicked pixels and the robot points.

## 4. What the vision gives (for the UI)

`yolo_lib.detect_stable(...)` returns a list of objects (dicts):

| Field | Example | Meaning |
|---|---|---|
| `type` | `"card"` | card / candy / box / lid |
| `conf` | `0.94` | YOLO score |
| `box` | `(x1, y1, x2, y2)` | Picture box in pixels |
| `u`, `v` | `858, 525` | Centre in pixels |
| `x_robot`, `y_robot` | `223.3, -127.8` | Centre in robot mm |
| `angle_img`, `angle_robot` | `59, -30` | Angle of the long side (picture / robot), degrees |
| `color` | `"red"` | Main colour |
| `edge` | `False` | Cut by the picture edge → not picked |
| `reachable` / `off_belt` | `True` / `False` | Inside the pick area / outside (e.g. the box) |

## 5. One box cycle (`14_pick_and_place.py --run`)

1. Wait until the camera sees an open box standing still (box conveyor stopped by its sensor).
2. DO3 on → object conveyor runs; camera watches live.
3. 1 card + 2 candies fully in the pick area (3 pictures in a row) → DO3 off.
4. Robot home, 8 pictures → stable positions and angles.
5. For each object: above it (travel_z) → down (pick height) → DO1 on → up → fly to the box,
   tool turned by (box angle − object angle) → down → DO1 off, DO2 pulse → up.
6. Lid: same as 5 with the lid heights → box closed → home.
