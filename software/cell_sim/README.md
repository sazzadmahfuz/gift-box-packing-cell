# cell_sim: packing cell simulation

**SIMULATION, assumed parameters.** These results are not hardware results.

## What it does
A discrete-event simulation of the gift-box packing cell, following the team's working set-up
(`notebooks/week-03/Choton/Choton_Week3_Notebook.md`, confirmed 2026-11-16):
1. Belt B (boxes, run by the Arduino Nano) brings a box until the Nano's sensor S1 stops it, and
   the camera sees the open box.
2. The robot switches belt A (objects) on with DO3. Belt A runs until the camera has seen the full
   set (1 card + 2 candies) in the pick area for `set_confirm_time_s`, then DO3 switches it off.
3. The robot moves home, out of the camera view, and takes the pictures.
4. It picks and places every item, then puts the lid on the box.
5. The operator takes the closed box away, and the Nano brings the next one.

Items arrive on belt A in seeded random order. Items that leave the pick area unpicked fall off
the far end and are logged as `skipped`. One cycle = one closed box.
Time is simulated, so a run of several minutes of cell time finishes instantly. If an expected event
does not arrive before its timeout, the run stops in FAULT.

## Requirements
- Python 3.11 or newer, standard library only. Runs offline; it never connects to the robot, belts or camera.
- pytest, for the tests only: `python -m pip install pytest`

## How to run
Run every command from the `software/` folder (PowerShell, starting in the repo root):
```powershell
cd software
python -m cell_sim --cycles 5                    # 5 boxes, CSV to testing/sim_runs/
python -m cell_sim --cycles 2 --realtime 10      # sleep between events, 10x real speed
python -m cell_sim --config my.json --out-dir out
python -m cell_sim --mode robodk --cycles 1      # arm in RoboDK, belts simulated (see RoboDK below)
python -m cell_sim --mode dobot-dry --cycles 1   # print the Dobot TCP commands, send nothing
python -m cell_sim connect-check                 # read-only check of the real robot (lab only)
python -m pytest cell_sim/tests -v               # run the tests
```
Compare the two newest runs (they should be identical):
```powershell
$f = Get-ChildItem ..\testing\sim_runs\*.csv | Sort-Object LastWriteTime | Select-Object -Last 2
fc.exe $f[0].FullName $f[1].FullName
```
Exit codes: `0` = all cycles done, `2` = FAULT, `1` = bad config or arguments, `3` = RoboDK or
robot not reachable, `4` = connect-check: the robot reports an error, `5` = dobot-real refused.
Parameters are in `config.json`; RoboDK settings are in `hardware.json`.

## Operator UI
`python -m cell_ui` (from `software/`) opens a window for the whole operation. It has these tabs:
- **Run:** every mode and option.
- **Readiness:** offline checks per mode.
- **Config:** edits `config.json` and `hardware.json`. Each edit is checked by the program's own
  loaders, and the old file is kept as `.bak`.
- **Results:** CSV logs with a cycle-time chart, or two logs compared.
- **Robot check:** `connect-check`, after a confirmation.
- **About.**

The UI runs `python -m cell_sim` as a separate program, so every safety check stays in the CLI.
It builds its forms, modes, exit codes, config fields and log columns from the program and files
at start-up, so changes there need no UI change. How to use it is in
`software/cell_ui/README.md`, and the tests run with `python -m pytest cell_ui -q`.

## RoboDK (--mode robodk)
**ROBODK SIMULATION, assumed parameters.** Only the arm runs in RoboDK. Belts, S1 and vision stay
simulated with the `config.json` values. The robot motion times are measured: each pick, place and
return is timed on the wall clock and multiplied by the RoboDK simulation speed
(`hardware.json` `robodk.simulation_speed`, 1 = real time). The run sets RoboDK to simulate mode
(`RUNMODE_SIMULATE`) and to that speed.

RoboDK must already be running with the station open. The program checks port 20500 first and
never starts RoboDK itself. Moves: `MoveJ` to `home`, to the points above `pick` and `place_box`
(`approach_dz_mm` higher, ASSUMED), and back; `MoveL` straight down and up. Vacuum on/off is
printed and shown in the RoboDK status bar. If the robot has a tool and an object whose name
contains `item`, vacuum on attaches the closest one and vacuum off detaches it; the item goes back
to the pick point at the start of the next pick.

Station set-up:
1. Start RoboDK and open a new station.
2. Load the robot: File > Open online library, search "Dobot", load **M1 Pro** if it is listed.
   If it is not listed, pick one of the two:
   - **MG400**: found automatically, but it is a 4-axis arm, not a SCARA.
   - **Dobot M1**: SCARA like ours, but not the M1 Pro. RoboDK lists its joints as Z 0–250 mm,
     then ±90°, ±135° and ±180°, which differs from the M1 Pro. To use it, set
     `robodk.robot_name` to `"Dobot M1"` in `hardware.json`.
3. Add the vacuum cup: right-click the robot > Add tool (empty), rename it "vacuum cup".
   Set its tool Z offset to the cup length, or leave 0 for a first look (CONFIRM in the lab).
4. Jog the robot to a safe start pose, then Program > Teach target (Ctrl+T). Rename the target
   (F2) to exactly `home`.
5. Jog to the belt A pick point with the cup touching the item top, Teach target, rename to `pick`.
6. Jog to the drop point inside the box on belt B, Teach target, rename to `place_box`.
7. Approach points. Either teach them: jog straight up from `pick`, Teach target, rename to
   `pick_approach` (and `place_approach` above `place_box`), and list them in
   `robodk.target_names`. Or leave them out: the program then uses the point `approach_dz_mm`
   (50 mm, ASSUMED) above. Check it is reachable: right-click the target > Move to target, then
   jog +Z by 50 mm. If not, lower `approach_dz_mm`.
8. Optional item: add a small object (any STL) under the station, rename it so the name contains
   `item`, and place it at the `pick` point.
9. Save the station (File > Save station), for example as `software/robodk/cell_station.rdk`.
10. Run `python -m cell_sim --mode robodk --cycles 1`. Exit code 3 means something is missing; the
    message says what.

Target coordinates taught in RoboDK are layout guesses, not measured cell positions.

## Dobot M1 Pro (TCP/IP)
The commands come from Dobot's own `dobot_api.py`, copied unmodified to
`software/third_party/dobot_api/` (MIT licence; it needs numpy and tkinter). Settings are in the
`dobot` section of `hardware.json`.

**`--mode dobot-dry`: SIMULATION, assumed parameters.** The cell runs as in sim mode with the
times from `config.json`. Every robot command is printed exactly as it would go to port 29999
(dashboard) or 30003 (moves), with the speed ratio and the target values. Nothing is sent, and no
socket is opened. It follows Choton's real-robot program (`notebooks/week-03/Choton/code/robot_lib.py`):
- `SetArmOrientation(0)` (Left) at start.
- Every move is `MovL`, because a `MovJ` flipped the arm on 12 Nov.
- Pick height per item type.
- Suction on DO1, then wait 0.6 s.
- Release: suction off, a 0.2 s blow-off pulse on DO2, then wait 0.3 s.
- Belt A switched with DO3.
- Every output off at the end.

The heights, box, home and outputs in `hardware.json` are Choton's values taught on the real robot
on 17 Nov, on the new worktable and camera stand (VERIFIED, from his handover). The pick X/Y is a
calibration cross (ASSUMED); in a real run it comes from the camera. The lid heights are known
(pick 86.3 mm, close 105.1 mm) but the lid targets need an R angle, which was not given, so the dry
run skips the lid moves and the CSV cycle row says so.

Choton's handover (17 Nov) also says that long moves in the air must be `MovJ` after
`SetArmOrientation(0)`: a long `MovL` from home to an object gave alarms 23 and 22. The dry run still
prints `MovL` for every move; it sends nothing.

**`connect-check`: read-only.** It opens ports 29999 and 30004 on the robot (192.168.1.6),
sends only `GetErrorID()`, `RobotMode()` and `GetPose()`, reads one feedback packet, prints
the results, and closes. An allowlist refuses every other command, so it never enables, moves or
switches an output. Options: `--ip`, `--timeout-s`. Run it in the lab with the PC on 192.168.1.x.

**`--mode dobot-real`: safety gate only.** It refuses to start (exit 5) and lists every problem
unless all of these hold:
- `speed_factor_percent` is from 1 to 20.
- All 8 `workspace_limits` values are set.
- `vacuum_do` and `arm_orientation_code` are set; `blow_off_do` and `object_conveyor_do` are
  valid; no two outputs share a channel.
- All targets, including the four lid targets, are set and lie inside the limits.
- None of those values is ASSUMED or CONFIRM.
- `teacher_approval` holds the teacher's name and the date.
- The command has `--teacher-approved`.

Even when the gate passes, the real motion path is not written yet. It comes in a later stage,
requested together with the teacher's approval.

## How to read the CSV
- **File name:** `testing/sim_runs/<YYYYmmdd_HHMMSS>.csv`. If that name is taken, the file gets a `_2` suffix.
- **Line 1:** `# SIMULATION, assumed parameters; cycle: ...; parameters: config.json (all ASSUMED); devices: ...`
  (the label, where the parameters come from, and which devices ran). **Line 2:** the column header.
- **Rows:** one row per placed item, skipped item, finished cycle, and fault.

The `record_type` column says what each row is:

| `record_type` | Columns filled |
|---|---|
| `item` | `cycle`, `item_index` (1 = first in box), `item_type`, `entered_area_s`, `pick_start_s`, `pick_done_s`, `place_done_s`, `item_time_s` |
| `skipped` | `cycle`, `item_type`, `entered_area_s`, `left_area_s`, `note` |
| `cycle` | `cycle`, `items` (separated by `\|`), `cycle_start_s`, `box_seen_s`, `set_ready_s`, `pictures_done_s`, `lid_done_s`, `box_removed_s`, `cycle_done_s`, `cycle_time_s`, `skipped_count`, `note` (for example when the robot has no lid targets) |
| `fault` | `note`: the state, the time, and the event that did not arrive |

- **Times** are simulated seconds since the start of the run, with 3 decimals. Columns that don't apply to a row are empty.
- **`item_time_s`** = `place_done_s − entered_area_s`.
- Logs from before 2026-11-16 (for example `20261109_022312.csv`) use the old one-item-at-a-time
  cycle and its columns.
- **`cycle_time_s`** = `cycle_done_s − cycle_start_s`.
- **Same config → identical file.** A given config always produces a byte-identical CSV.

## State table
| State | Entered when | Leaves to | Timeout key |
|---|---|---|---|
| INIT | program start | READY | – |
| READY | start, or previous box removed | WAIT_BOX | – |
| WAIT_BOX | waiting for a box | FEED_SET, when S1 fired and the camera saw the box (belt A on, DO3) | `WAIT_BOX` |
| FEED_SET | belt A on | DETECT, when the full set stayed in the pick area for `set_confirm_time_s` (belt A off) | `FEED_SET` |
| DETECT | belt A stopped | PICK, when the robot is home and the pictures are done | `DETECT` |
| PICK | robot picks the next item | PLACE | `PICK` |
| PLACE | robot places it in the box | PICK for the next item, otherwise CLOSE_LID | `PLACE` |
| CLOSE_LID | box full | RELEASE_BOX, when the lid is on | `CLOSE_LID` |
| RELEASE_BOX | box closed | CYCLE_DONE, when the operator has taken it away (S1 off) | `RELEASE_BOX` |
| CYCLE_DONE | box removed | READY, or stop after `--cycles` boxes | – |
| FAULT | a timeout expired or the robot reported an error | end of run (exit code 2) | – |

Safety rules enforced in `cell.py`: no pictures or pick while belt A runs; no place or lid unless a box is at S1.

## Devices
The state machine talks to the cell (`cell.py`), and the cell talks only to device interfaces
in `interfaces/`: `RobotDriver`, `BeltDriver`, `SensorS1`, `VisionSource`, `Clock`.

| Implementation | File | Used in |
|---|---|---|
| `SimRobot`, `SimBelt`, `SimSensor`, `MockVision`, `SimClock` | `drivers/sim_devices.py`, `drivers/sim_world.py` | sim mode (all times from `config.json`, ASSUMED) |
| `RobotOutputBelt` | `drivers/robot_output_belt.py` | belt A switched by robot output DO3 (dobot-dry) |
| `ManualBelt`, `ManualSensor` | `drivers/manual_devices.py` | bench debugging only: the operator runs the belts and reports S1 with Enter |
| `RoboDKRobot` | `drivers/robodk_robot.py` | robodk mode |
| `DobotTcpRobot` (dry sockets) | `drivers/dobot_tcp_robot.py` | dobot-dry mode |
| `connect_check` | `drivers/dobot_connect_check.py` | `connect-check` command |

`sequencer.py` turns the pictures, each pick and place, and the lid into robot steps (`home`,
`pick_above`, `pick`, vacuum on, ..., `lid_above`, `lid`, `lid_on_box`). A robot without lid targets
skips the lid moves, and the cycle row records it.
In sim and dobot-dry modes the steps take the times in `config.json`. `safety_gate.py` holds the
dobot-real checks.

## What is not validated
- **No hardware was used.** Nothing here has been run on or compared with the real robot, belts, camera or S1.
- **All timings, speeds, distances and timeouts are assumed placeholders.** Each is marked `ASSUMED` in `config.json`.
- **Simplified behaviour:**
  - Items arrive at a fixed spacing, and items that leave the pick area are not recirculated.
  - Robot motions take fixed times, and every item is picked at the same point.
  - The robot's return move and its move home take as long as its move to the box.
  - The Nano always has a new box ready, and the operator removes each closed box in a fixed time.
- **Not modelled:** sensor faults, missed detections and dropped items. The only fault path is the timeout hook.
- **Decided:** the box contents are 1 card + 2 candies (team, 2026-11-16).
- **Not yet decided:** how the full box leaves in the final cell. The operator removes it for now.
- **Cycle times are not performance figures.** Treat them as placeholders until they are re-run with measured values.
