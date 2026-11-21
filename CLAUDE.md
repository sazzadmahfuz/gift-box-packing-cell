# Project: Applied Robotics Project II (HAMK)

Cell: Dobot M1 Pro robot, belt A (camera and items), belt B (boxes, stop sensor S1).
Task: Christmas gift box packing. Week 4 demo is V1, Week 8 is the public demo.

## Rules
- Python 3.11. Standard library only for cell_sim and for the core files of cell_live; hardware and vision packages are allowed in their own adapter files (pytest allowed for tests).
- Units: seconds, millimetres, mm/s. Put the unit in every variable name or comment.
- Never invent measured values. Any number that is not measured goes in config.json with the note "ASSUMED" and a reason.
- Simulation results must say "SIMULATION, assumed parameters". Never describe them as hardware results.
- Do not operate hardware. Code in software/cell_sim/ must run offline. The software/cell_live/ checks connect to the hardware read-only (no motion, no output writes). software/cell_live/control/ (real control) may send motion and outputs to the real robot only through its safety gate and a one-time arm token (motion code requested by the user with the teacher's approval, 2026-11-16; supervised lab runs only). One exception (decided by the user, 2026-11-17): with no run active, software/cell_live/control/idle_stop.py may switch outputs OFF for the SOFTWARE STOP and the "Stop object belt" button, only DOExecute to the off levels of DO3, DO16, DO1 and DO2, never motion.
- Keep each file under 300 lines. Prefer clear names over comments.
- Before saying a task is done, run the tests and show the output.
## Integration rules (added 2026-11-12)
- Never run or write code that sends motion commands to the real robot unless I ask in the same message and say the teacher approved it.
- Real-robot mode must refuse to start if any of these is missing: speed cap, workspace limits, vacuum DO channel, teacher-approval flag.
- Never edit teammates' folders (notebooks/*/Rashmika, notebooks/*/Choton, their code). Read them, and write adapters in software/.
- Every hardware fact in config or docs needs a source (file path or photo name) or the label ASSUMED or CONFIRM.
- Robot is the Dobot M1 Pro (4-axis SCARA, X Y Z R). Cell wiring as built on 17 Nov (photos of the station, Rashmika's notebook and her sketch notebooks/week-03/Rashmika/ArduinoCode/ArduinoCode.ino, the handwritten DO list): the object belt (cards and candies, DTCB 25261249) has a TB6600 driver whose step pulses come from the box belt's UNO; the robot switches its ENA with DO3 (start and stop; it stops when the camera sees the full set in the pick area) and its DIR with DO4, and DO16 is an enable whose job is still to trace. The box belt (boxes and lids, DTCB-2418-0718) is run by an Arduino UNO R4 WiFi on its own E18-D80NK sensor and stops when the sensor sees a box; no Dobot output goes to it, the UNO is not connected to the laptop, and the camera confirms the box. After the lid a person takes the closed box away and the UNO brings the next one (belts.box_restart = operator). Which levels run, turn and enable the object belt stays CONFIRM until the lab tests. Always say "object belt" and "box belt", never belt A or B alone (Rashmika's A and B are the other way round). A manual fallback exists only for bench debugging. Gripper is a vacuum cup on DO1, blow-off on DO2.
- Simulation results are always labelled SIMULATION or ROBODK SIMULATION, with assumed parameters.
- Standard library only for cell_sim and for the core files of cell_live; hardware and vision packages (robodk, the Dobot API, pyserial, opencv, numpy, ultralytics) are allowed in their own adapter or driver files and imported lazily there.
- Files under 300 lines. Keep all existing tests passing.
## Console look (software/cell_live/web)
- Theme "Cabinet". Colours only as variables in css/theme.css, no hex elsewhere.
- Status is a lamp shape plus a word, never colour alone. Shapes: OK disc, WARN triangle,
  FAIL cross, UNKNOWN ring with dot, NOT OBSERVABLE slashed ring, old data dashed ring.
- Motion only on a real event (finished check, state change, step change). No idle motion.
- The map wiring is TOPOLOGY in js/patchbay.js. Fonts are local files with an OFL notice.
- Nothing is copied from a UI library without a row in assets/NOTICE.md.
- No simulation wording anywhere, also not in comments. Files under 300 lines.