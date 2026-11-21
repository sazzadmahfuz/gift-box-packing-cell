# Hardware and interface facts: Dobot M1 Pro cell

- **Date:** 2026-11-12. Compiled by Sazzad (with Claude Code) from repository files only. No hardware was connected or operated.
- **Refs read** (after `git fetch --all --prune`, no newer commits):
  - `origin/main` `a263e48`
  - `origin/Rashmika-Branch` `de1ef4b`
  - `origin/SubBranch` `667464e`
  - `origin/sazzad-week2-sim` `3165242`
- **Not read:** pull requests and issues (`gh` CLI not installed).
- **Purpose:** the facts needed to integrate the cell software with the Dobot M1 Pro over TCP/IP and with RoboDK.

**Status key**
- **VERIFIED:** in a repo file, code or screenshot that was read.
- **FROM PHOTO:** seen in a photo.
- **ASSUMED:** inferred or vendor-stated, not checked in the lab.
- **CONFLICT:** team documents disagree.

"Sazzad's lab photos" are not yet in the repo. Their file names must be added (see 4b, item 15).

**Short paths**
- `R2/` = `notebooks/week-02/Rashmika/`
- `C2/` = `notebooks/week-02/Choton/`
- `TCP/` = `R2/Project files/TCP-IP-4Axis-Python-main/`

---

## 1. Fact table (Dobot M1 Pro setup)

### Robot
| Item | Value | Source | Status |
|---|---|---|---|
| Robot model | Dobot M1 Pro, 4-axis SCARA (X Y Z R) | `R2/Images/day1/Image0.jpg`, `Image1.jpg` ("M1 Pro" label); `R2/Images/day1/Image6.jpg` (DobotStudio finds "M1Pro 192.168.1.6"); Sazzad's lab photos | VERIFIED. Project plan says Nova 2, see C1 |
| Spec: reach / payload / repeatability | 400 mm / 1.5 kg / ±0.02 mm | `origin/Rashmika-Branch:R2/Images/day2/Image3.jpg` (vendor spec screenshot) | FROM PHOTO (vendor spec, not measured) |
| Spec: joint ranges | J1 ±85°, J2 ±130°, J3 5–245 mm, J4 ±360° | same | FROM PHOTO |
| Spec: joint max speeds | J1 180 °/s, J2 180 °/s, J3 1000 mm/s, J4 1000 °/s | same | FROM PHOTO |
| Spec: communication | TCP/IP, Modbus TCP, Modbus RTU | same | FROM PHOTO |
| Initial pose | X 400, Y 0, Z 200 mm, R 0°; joints 0°, 0°, 200 mm, 0° | `R2/Images/day1/Image10.jpg`; `R2/Project files/Pick and Drop M1/point.json` ("InitialPose") | VERIFIED |
| Taught test points (Rashmika's bench test, not our cell layout) | P1 Pick_Down (295.81, 204.86, 106.84, 170.05) right arm; P2 Pick_Up (296.25, 204.47, 224.89, 179.88); P3 Drop_Up (369.44, −133.09, 189.65, 87.37) left arm; P4 Drop_Down (369.44, −133.09, 56.00, 87.37); X Y Z in mm, R in ° | `Pick and Drop M1/point.json` | VERIFIED |
| Pose seen over TCP/IP, 2026-11-10 12:13 | X 366.211, Y 122.182, Z 124.262 mm, R −7.66°; robot mode ROBOT_MODE_ENABLE | `R2/Images/day2/Image2.png` | FROM PHOTO |
| Jogging | Joint jog works. Cartesian X/Y/Z jog gives inverse-kinematics errors (cause unknown) | `R2/Readme.md` (2026-11-09); `R2/Images/day1/Image8.jpg` | VERIFIED (observation) |
| Software | DobotStudio Pro 2.8.1 works. 4.5 and 4.6 fail with "Invalid Device Type: M1Pro" | `R2/Readme.md`; `R2/Images/day1/Image6.jpg` | VERIFIED |
| Robot mode for Python control | Must be set to "TCP/IP secondary development" in DobotStudio Pro | `TCP/README.md` step 3 | ASSUMED (vendor doc). Python control worked, so it was probably set (CONFIRM) |
| Controller firmware | Unknown. The API needs V1.5.6.0 or later (README suggests ≥ V1.6.0.0 if ports fail) | `TCP/README.md` lines 26, 177 | ASSUMED, CONFIRM |

### Network and TCP/IP
| Item | Value | Source | Status |
|---|---|---|---|
| Controller IP | 192.168.1.6 on Ethernet 1 (LAN1); fixed, cannot be changed | Sazzad's lab photos; `R2/Readme.md` (ping OK); `R2/Images/day1/Image4.png`, `Image7.jpg` (manual table 3.1) | VERIFIED |
| Other interfaces | Ethernet 2 = 192.168.2.6; Wi-Fi = 192.168.9.1 | `TCP/README.md` line 18 | ASSUMED (vendor doc, untested) |
| PC address | Must be 192.168.1.x. The value used was not recorded | `TCP/README.md` step 2 | ASSUMED, CONFIRM |
| Ports | Dashboard 29999, move 30003, feedback 30004. `DobotApi.__init__` refuses any other port | Sazzad's lab photos; `TCP/dobot_api.py:115`; `R2/Images/day2/Image2.png` | VERIFIED |
| Protocol | Plain ASCII text commands over TCP, e.g. `EnableRobot()`, `MovJ(x,y,z,r)` | `TCP/dobot_api.py` | VERIFIED |
| Reply format | `0,{},EnableRobot();`, where the first field is the error code (0 = OK) and `{}` holds the error list | `R2/Images/day2/Image2.png` log; `TCP/test.py` `command_success()` | VERIFIED |
| Python control test | 2026-11-10: EnableRobot and MoveJog(Y±) accepted; DI/DO bits all 0 | `R2/Images/day2/Image2.png`; `R2/Readme.md` line 194 | FROM PHOTO |
| Feedback stream | 1440-byte packets on 30004, decoded with numpy dtype `MyType`. A packet is valid if `test_value == 0x123456789abcdef`. Useful fields: `digital_input_bits`, `digital_outputs`, `robot_mode`, `tool_vector_actual`, `q_actual`, `EnableStatus`, `ErrorStatus`, `isRunQueuedCmd` | `TCP/dobot_api.py:13-89`; `TCP/main.py` `GetFeed()` | VERIFIED (code). Update rate unknown |
| Motion done check | `Sync()` blocks until the queue is done, or compare target with feedback pose (±1 in `WaitArrive`) | `TCP/dobot_api.py:741`; `TCP/main.py` `WaitArrive()` | VERIFIED (code) |
| Command set | See section 2 | `TCP/dobot_api.py` | VERIFIED |

### Gripper and vacuum
| Item | Value | Source | Status |
|---|---|---|---|
| End effector | Vacuum suction cup on the tool flange | `R2/Images/day1/Image1.jpg`; `R2/Images/day2/Image0.jpg`; Sazzad's lab photos | FROM PHOTO |
| Vacuum control | Dobot vacuum box wired to the robot's DO terminals | Sazzad's lab photos (photo name needed) | FROM PHOTO |
| DO channels | Rashmika's M1 program: `DO(1,1)` then a 1 s wait at pick; `DO(1,0)` at drop, then a `DO(2,1)` pulse of 0.2 s. This suggests DO1 = suction and DO2 = blow-off | `R2/Project files/Pick and Drop M1/src0.lua` | ASSUMED (inferred from the program; wiring not checked) |
| Base I/O panel | DO1–DO16, DI1–DI16, 24V/GND terminals in two blocks; Ethernet 1, Ethernet 2, USB 1, USB 2, Encoder port, power switch | `R2/Images/day1/Image2.jpg` | FROM PHOTO |
| DO index range in API | 1–24 (docstring of `DO()`); the panel shows 16 | `TCP/dobot_api.py:258-265` | VERIFIED (code). The extra 8 may be tool I/O (CONFIRM) |
| DO/DI electrical type | Unknown (NPN/PNP, current, input voltage) | n/a | missing |
| Suction test | Two grippers failed to pick plastic-wrapped candies (suction too weak, or the surface too uneven) | `R2/Readme.md` 2026-11-10; `R2/Images/day2/Image0.jpg`, `Image1.jpg` | VERIFIED (observation) |

### Belts (no team document covers them; all from Sazzad's lab photos)
| Item | Value | Source | Status |
|---|---|---|---|
| Belt model | Both belts are Dobot Mini Conveyor Belt DT-AC-CB070-02E with NEMA 17-style steppers | Sazzad's lab photos (names needed) | FROM PHOTO |
| How they are started today | Manually | Sazzad's lab photos | FROM PHOTO. The CLAUDE.md target is automatic, see C3 |
| Control boards seen | (a) Arduino Uno with a small Pololu driver; (b) Arduino Nano on a breadboard; (c) Arduino UNO R4 WiFi with a 9–42 V microstep driver whose PUL/DIR/ENA inputs are not wired. Which set drives which belt is unknown | Sazzad's lab photos | FROM PHOTO |
| Belt speed | Unknown. cell_sim uses ASSUMED values | `software/cell_sim/config.json` | ASSUMED |
| Command path (PC or robot to belts) | Unknown (USB serial? robot DO into Arduino?) | n/a | missing |
| Belt power supply | Unknown | n/a | missing |

### Sensor S1
| Item | Value | Source | Status |
|---|---|---|---|
| Type | Yellow cylindrical photoelectric sensor | Sazzad's lab photos | FROM PHOTO |
| Supply | Tag shows about 5 VDC | Sazzad's lab photos | FROM PHOTO, CONFIRM |
| Output type / wiring / input pin | Unknown. If it goes to a robot DI, check the voltage level (the panel terminals are labelled 24V) | `R2/Images/day1/Image2.jpg` (24V labels) | missing |

### Camera and vision
| Item | Value | Source | Status |
|---|---|---|---|
| Camera | USB RGB camera, 1280×720 px, `camera_index` 1; the teacher agreed to it on 2026-11-06. Model name not recorded | `C2/Choton_Week2_Notebook.md` (2026-11-06); `C2/code/config/settings.json` | VERIFIED |
| Backup camera | Arduino Nicla Vision (GC2145): best usable 560×400 px; 640×480 fails (frame buffer overflow). Settings kept in `settings_nicla.json` | `C2/Choton_Week2_Notebook.md` | VERIFIED |
| Vision output format | In-memory Python list of dicts from `vision_lib.detect_objects()` / `detect_stable()`. Keys: `type` (card/candy/other), `color`, `u`, `v` (px), `angle` (°, 0–180, long side), `area`, `aspect`, `fill`, `covered`, `edge`, `box` (4 corner px), `length_mm`, `width_mm`, `x_mm`, `y_mm`, `x_robot`, `y_robot`, `reachable`. Nothing is sent over a network; the only outputs are igus XML programs and annotated JPGs | `C2/code/vision_lib.py:355-469`; `C2/code/06_robot_program.py` | VERIFIED |
| Vision frame | `x_mm`, `y_mm` are in a table (paper) frame from a 4-point homography on a 200×150 mm rectangle, origin at the first cross (pixel 249, 139), created 2026-11-09 20:33. `x_robot = x_mm − 100`, `y_robot = y_mm − 75` (`origin_on_table_mm` [100, 75], no flips), which the code marks TEMPORARY. It is not calibrated to any robot | `C2/code/vision_lib.py:515-527`; `C2/code/config/homography.json`; `settings.json` | VERIFIED (code). The robot frame is ASSUMED |
| Vision accuracy (table frame only) | Size within 1–2 mm; jitter 0.2–0.7 mm; calibration error ≤ 2 mm at 2 of 3 points (dot A off by 8.2 mm); bright light 8/11, distractors 11/12 | `C2/Choton_Week2_Notebook.md`; `notebooks/week-01/Choton/Choton.md`; `C2/test_results/summary.txt` | VERIFIED (Choton's measurements) |
| Test object sizes | Card 125×87 mm; test candy 150×28 mm (3D-printed). Real candies not yet measured | `C2/Choton_Week2_Notebook.md` | VERIFIED (test objects only) |
| Vision dependencies | OpenCV and numpy (not standard library), so our core must read its output via a file or socket, not import it | `C2/code/vision_lib.py` imports | VERIFIED |
| Camera position | Choton plans to mount it "at the robot"; CLAUDE.md says above belt A | `C2/Choton_Week2_Notebook.md` next steps | CONFLICT (C8) |

### Power
| Item | Value | Source | Status |
|---|---|---|---|
| Robot supply | Mean Well SDR-240-48: output 48 V DC, 5 A; input 100–240 VAC, 2.6 A, 50/60 Hz | `R2/Images/day1/Image3.jpg`; `R2/Readme.md` ("48V and 5A") | FROM PHOTO |
| Belt / Arduino / vacuum box supplies | Unknown | n/a | missing |

### Safety
| Item | Value | Source | Status |
|---|---|---|---|
| E-stop | Yellow box with a red "EMERGENCY STOP" mushroom button, cabled to the robot base | `R2/Images/day1/Image0.jpg`, `Image1.jpg` | FROM PHOTO |
| Safety connector | 4-pin connector labelled `SS0 SS1 24V 24V`, wired, with a cable tagged "SS…". That this is the e-stop cable is a guess | `R2/Images/day1/Image2.jpg` | FROM PHOTO. Meaning of SS0/SS1 and stop category unknown |
| Software e-stop | `DobotApiDashboard.EmergencyStop()`; alarm codes for hardware/external e-stop exist | `TCP/dobot_api.py:452`; `TCP/files/alarm_controller.json:692, 1056` | VERIFIED (code) |
| Does the e-stop stop the belts? | Unknown. The belts run on separate Arduinos | n/a | missing |
| Enclosure | Aluminium-profile frame with transparent panels; interlock unknown | `R2/Images/day1/Image1.jpg` | FROM PHOTO |

### RoboDK
| Item | Value | Source | Status |
|---|---|---|---|
| RoboDK material in repo | None on any branch | `git grep` on all branches | missing |

---

## 2. Dobot TCP-IP-4Axis-Python API (copied from `TCP/dobot_api.py`)
Classes: `DobotApi` (socket base), `DobotApiDashboard(DobotApi)`, `DobotApiMove(DobotApi)`, numpy dtype `MyType`, and `alarmAlarmJsonFile()`.

| Purpose | Exact signature | Sends |
|---|---|---|
| Connect | `DobotApi.__init__(self, ip, port, *args)`, used as `DobotApiDashboard(ip, 29999)`, `DobotApiMove(ip, 30003)`, `DobotApi(ip, 30004)` | opens socket |
| Close | `DobotApi.close(self)` | n/a |
| Send and receive | `DobotApi.sendRecvMsg(self, string)` (lock; `recv(1024)` once) | any |
| Enable | `DobotApiDashboard.EnableRobot(self, *dynParams)` | `EnableRobot(...)` |
| Disable | `DobotApiDashboard.DisableRobot(self)` | `DisableRobot()` |
| Clear error | `DobotApiDashboard.ClearError(self)` | `ClearError()` |
| Error ID | `DobotApiDashboard.GetErrorID(self)` | `GetErrorID()` |
| Reset / stop | `DobotApiDashboard.ResetRobot(self)` | `ResetRobot()` |
| E-stop | `DobotApiDashboard.EmergencyStop(self)` | `EmergencyStop()` |
| Mode | `DobotApiDashboard.RobotMode(self)` | `RobotMode()` |
| Global speed | `DobotApiDashboard.SpeedFactor(self, speed)` (int 1–100) | `SpeedFactor(n)` |
| Joint speed / accel | `DobotApiDashboard.SpeedJ(self, speed)`, `AccJ(self, speed)` (1–100) | `SpeedJ(n)`, `AccJ(n)` |
| Linear speed / accel | `DobotApiDashboard.SpeedL(self, speed)`, `AccL(self, speed)` (1–100) | `SpeedL(n)`, `AccL(n)` |
| Digital out (queued) | `DobotApiDashboard.DO(self, index, status)` (index 1–24, status 0/1) | `DO(i,s)` |
| Digital out (immediate, by name) | `DobotApiDashboard.DOExecute(self, offset1, offset2)` | `DOExecute(i,s)` |
| Tool DO | `ToolDO(self, offset1, offset2)`, `ToolDOExecute(self, offset1, offset2)` | n/a |
| Digital in | `DobotApiDashboard.DI(self, offset1)` | `DI(i)` |
| Pose / angles | `GetPose(self)`, `GetAngle(self)` | n/a |
| Queue control | `Continue(self)` sends `continue()`; `pause(self)` | n/a |
| Joint-space move to XYZR | `DobotApiMove.MovJ(self, x, y, z, r, *dynParams)` | `MovJ(...)` |
| Linear move | `DobotApiMove.MovL(self, x, y, z, r, *dynParams)` | `MovL(...)` |
| Joint move | `DobotApiMove.JointMovJ(self, j1, j2, j3, j4, *dynParams)` | `JointMovJ(...)` |
| Relative move | `DobotApiMove.RelMovJ(self, x, y, z, r, *dynParams)`, `RelMovL(self, offsetX, offsetY, offsetZ, offsetR, *dynParams)` | n/a |
| Jump (arch) | `DobotApiMove.Jump(self, x, y, z, r, User=None, Tool=None, SpeedL=None, AccL=None, Start=None, End=None, ZLimit=None, auxJoint=None)` | n/a |
| Wait for queue | `DobotApiMove.Sync(self)` | `Sync()` |
| Jog | `DobotApiMove.MoveJog(self, axis_id=None, *dynParams)` | `MoveJog(...)` |
| Feedback | `feed.socket_dobot.recv(...)` until 1440 bytes, then `np.frombuffer(data, dtype=MyType)` | n/a |

**Quirks found in the code (do not copy blindly):**
- `ToolDI()` sends `DI(...)`, not `ToolDI(...)`.
- `DOGroup()` builds the string but never sends it.
- `SetArmOrientation(self, offset1)` takes 1 argument, but `PythonExample.py` calls it with 4, which raises TypeError.
- `sample.py` calls `move.SpeedJ` and `move.AccJ`, which exist only on `DobotApiDashboard`, so it raises AttributeError.
- `send_data` prints errors and swallows them.
- `MovJ` and `MovL` print every command.
- The module imports `tkinter` and `numpy`.
- `main.py` loops forever with MG400 points (z = −60 mm, outside M1 Pro J3 5–245 mm). It must not be run on the M1 Pro.

**Licence:** MIT, "Copyright (c) 2022 Dobot" (`TCP/LICENSE`). Copying into our repo is allowed if the copyright notice and licence text are kept with the copy. Our rules keep Dobot code in its own driver file and adapters in `software/`, so the options are:
- a standard-library driver that speaks the same text protocol, or
- a copy of `dobot_api.py`, together with `LICENSE`, in a separate driver folder.

That choice belongs to the integration task.

---

## 3. Old setup (igus delta robot): does not apply to the M1 Pro
| Fact | Source | Applies to M1 Pro? |
|---|---|---|
| igus delta DLE-DR-0001; Commonplace Robotics controller; CAN bus; igus stepper driver; digital I/O module | `notebooks/week-01/Rashmika/Rashmika.md` (2026-10-27) | No |
| Mean Well NDR-240-24 supply, 24 V, 10 A | same, `Images/day1/Image7.jpg` | No (M1 uses SDR-240-48) |
| Controller on 192.168.3.x; PC 192.168.3.1/24; igus iRC V14/V15 | `Rashmika.md` 2026-10-28/29; `softwares/*.exe` | No |
| Vacuum on `DOut21` | `notebooks/week-01/Sazzad/Sazzad.md`; `C2/code/config/settings.json` `robot.vacuum_output` | No |
| Reach circle ~360 mm diameter (`reach_radius_mm` 180) | `C2/code/config/settings.json`; `vision_lib.in_reach()` | No (M1 reach is 400 mm, a SCARA arc) |
| Robot section of the vision settings (`home_z` 139, `travel_z` 60, `pick_z` 40, `place_z` 40 mm, `fast_vel` 300, `box_slots`) and `06_robot_program.py` (igus XML) | `C2/code/` | No |
| "Vacuum controller" seen on the delta | `Rashmika.md` `Images/day1/Image8.jpg` | Unknown whether it is the same unit |
| Vision detection, colour ranges, homography to the table | `C2/code/` | **Yes** (camera side only) |

---

## 4a. Conflicts between team documents
- **C1, robot model.** The documents disagree in three ways:
  - Nova 2 appears in `planning/project-plan.md` (lines 16, 27, 105, 107, 128, 153), `notebooks/week-02/Sazzad/Sazzad_Week2_Notebook.md`, and `software/cell_sim/README.md` and `config.json`.
  - M1 Pro appears in CLAUDE.md, the photos and Rashmika's week 2 notebook.
  - Rashmika's week 2 reflection (`R2/Readme.md` line 204) says **"The team agreed to move with NOVA 2"**, and `origin/Rashmika-Branch` adds "Nova 2 is faster than M1 Pro".

  The latest team note points away from the M1 Pro, so this needs a decision first.
- **C2, box contents.**
  - The plan (lines 15, 17, 111) and Sazzad's week 1 AC4-1 say 2 candy types + 1 card. cell_sim (candy_A, candy_B, card) matches this.
  - Choton's notebooks and `settings.json` `box_contents` say 2 cards + 2 candies.
- **C3, belt control.** CLAUDE.md says the belts start and stop automatically (camera stops A, S1 stops B). In the lab they are started and stopped manually, and no control path exists yet.
- **C4, number of belts.** The plan says "conveyor belt" (singular); CLAUDE.md and the photos show two.
- **C5, vacuum channel.** `DOut21` (igus, delta) vs `DO(1)`/`DO(2)` (Rashmika's M1 Lua) vs "channel unknown" (lab photos).
- **C6, robot reach in vision code.** A delta circle of 180 mm radius vs M1 Pro reach of 400 mm.
- **C7, gripper.** Sazzad week 2 D2.4 says "two-finger seen in photo". The M1 photos show a suction cup.
- **C8, camera position.** Choton plans "mount the camera at the robot"; CLAUDE.md puts it above belt A.
- **C9, task leads.**
  - T03 and T05 leads: Sazzad on `main`, Rashmika on `origin/SubBranch`.
  - Sazzad's D1.7 table numbers tasks differently from the plan (for example, T04 is camera there but robot in the plan).
- **C10, test status.** The plan says the "Nova 2 robot arm and conveyor belt have been tested". There are no test records for either in the repo.
- **C11, Python TCP/IP status.** `R2/Readme.md` line 216 says testing is "pending", but line 194 and `Image2.png` show it ran on 2026-11-10.
- **C12, I/O count.** "16 DI / 16 DO" (Rashmika, panel photo) vs DO index 1–24 in the API docstring.
- **Other.** `planning/project-plan.md` line 145 contains stray dictated text in the Week 4 risk review line.

## 4b. Missing facts to measure or ask the teacher
1. **Robot decision:** M1 Pro or Nova 2 (team and teacher). Everything below assumes the M1 Pro.
2. **Teacher-approval procedure** for real-robot runs, and the agreed safe speed cap (SpeedFactor %).
3. **Controller firmware version** (DobotStudio Pro 2.8.1, About page).
4. **Vacuum:**
   - Which DO switches suction and which switches blow-off; check the vacuum box wiring, with I/O-only tests, no motion.
   - DO electrical type (NPN/PNP, 24 V, max current).
   - Vacuum box model and supply.
5. **Workspace limits for our cell:** X/Y/Z min/max (mm), arm orientation (left/right), tool Z offset of the cup (mm), and payload setting.
6. **Layout:** positions of belt A pick point, belt B box stop and camera relative to the robot base (mm).
7. **Belts:**
   - Which Arduino set drives which belt, and what firmware is loaded.
   - How each belt is started.
   - Speed (mm/s) at each setting, and stopping distance (mm).
   - Microstep and current settings of the driver.
   - Supply voltage.
8. **S1:**
   - Model number, supply voltage (the ~5 VDC tag needs confirming), output type (NPN/PNP/relay, NO/NC) and sensing range (mm).
   - Where it is wired (Arduino pin or robot DI), and whether the voltage levels are compatible.
9. **E-stop and safety:**
   - Meaning of SS0/SS1 and the stop category, from the M1 Pro hardware manual.
   - Whether the e-stop also stops the belts.
   - Reset procedure, and whether the enclosure has an interlock.
10. **Camera:**
    - Model, mount position and height (mm).
    - Calibration from the camera to robot X/Y (robot-tip homography or a robot user frame).
11. **Items:** real candy and card sizes (mm) and masses, gift box inner size (mm), and whether wrapped candies can be picked at all (the 2026-11-10 suction test failed).
12. **Cartesian jog IK errors:** the cause has not been found.
13. **PC network settings** used for the robot (IP/mask), and the feedback update rate.
14. **RoboDK:** version, licence, whether an M1 Pro model and a Dobot post-processor are available.
15. **Photo names:** the lab photos of belts, Arduinos, S1, vacuum box and ports need file names, and should be committed, so every FROM PHOTO row has a source.
