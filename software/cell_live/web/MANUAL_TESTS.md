# Operator console: browser checks by hand

Playwright is not installed on the demo laptop, so these checks are done by hand in Chrome or
Edge. The automated tests (`python -m pytest cell_live -q`) cover the API, the local-only guard,
the token expiry and the rules for the web files. These checks cover what only a person at the
screen can see.

Write the result (pass / fail + note) and take a screenshot of every fail. Do part A today, and
parts B to H in the lab on Tuesday 17 Nov. Parts C and the SOFTWARE STOP checks need the teacher
present and a hand on the physical emergency stop.

Start: in `software/`, run `python -m cell_live`, then open http://127.0.0.1:8765/.

## A. Nothing connected (any PC)
| # | Check | Expected | Result |
|---|---|---|---|
| A1 | Open the console | Top bar: "Gift Box Packing Cell", HARDWARE badge, backend lamp, clock, SOFTWARE STOP. Lamp rail down the left edge, one lamp per component | |
| A2 | Overview with no robot, camera or Nano | Every hardware port on the cell map, every register row and every rail lamp is FAIL or NOT OBSERVABLE, each with a reason. Never OK. Calibration and vision model are tagged "file" | |
| A3 | Click Check on one tile, then Check all | "last seen" and latency update; no error message | |
| A4 | Click a register row, a map port or a rail lamp | Drawer: every field, history, raw reply. Close with the Close button or Esc; focus goes back to what you clicked | |
| A5 | Open `#/overview?component=camera&trace=open` | Camera drawer and trace panel open | |
| A6 | Open the trace panel | Dashboard queries, each with its reply or "no reply" | |
| A7 | Stop the backend (Ctrl+C in its terminal) | Red "backend connection lost" banner, every tile grey, within a few seconds (at most 13 s if the backend hangs instead) | |
| A8 | Start the backend again, reload the page | Banner gone, tiles back | |
| A9 | Switch the theme, reload | The theme stays (first start is light); both themes readable | |
| A10 | Window at 1366 × 768 (or Ctrl+minus on a larger screen) | Whole top bar visible, SOFTWARE STOP not cut, no sideways scrolling | |
| A11 | Every screen: Overview, Run, Vision, Logs, Settings, Help | Each opens; no "undefined", "null" or "NaN" text; the browser console (F12) shows no red errors | |
| A12 | Help | Wiring numbers come from the config; values not set show "not set yet (CONFIRM)" | |

## B. Two windows: laptop and projector
| # | Check | Expected | Result |
|---|---|---|---|
| B1 | Second window: http://127.0.0.1:8765/?viewer=1#/show, move it to the projector, F11 | Big run-state word and cycle belt on top, component list with lamps beside the camera picture; "Viewer: ON"; Run and Settings hidden; SOFTWARE STOP visible | |
| B2 | In that window, type `#/run` in the address bar | Back on Overview, "run is locked in Viewer mode" | |
| B3 | Click "Viewer: ON" | A dialog asks before leaving; Cancel keeps Viewer mode | |
| B4 | Laptop window | Still shows Run and Settings (Viewer mode is per window) | |
| B5 | Readability from the back of B125 | The state word, the lamp words and the camera counts are readable. If not, switch the theme in the projector window | |
| B6 | Projector window at the projector's own resolution, during a run (write the resolution down) | State word on one line; all 9 component rows and the ready flag above the trace bar; no sideways scrolling. Checked in Chrome from 1280 x 720 up | |

## C. Run screen (teacher present, hand on the physical emergency stop)
| # | Check | Expected | Result |
|---|---|---|---|
| C1 | Run screen before the lab values are filled | Checklist lists each missing value with the reason; Arm refused; Start disabled | |
| C2 | All values filled, all tiles OK, tick "hand on the emergency stop", Arm | 60 s countdown; Start enabled | |
| C3 | Wait 60 s without Start | Countdown ends, Start disabled, Arm needed again | |
| C4 | Arm, Start (lab ladder steps 4 to 7) | The box marker sits on the current step of the cycle belt, with the step time; top bar shows the step and box n/N | |
| C5 | Pause during a pick | Pauses after the current pick and place, reason shown; belt and suction off | |
| C6 | Resume, then Skip box, then Abort | Each works; Abort opens a dialog first and Cancel leaves the run alone | |
| C7 | SOFTWARE STOP during a move (lab ladder step 9) | Robot stops, outputs off, message "Software stop sent"; FAULT with the alarm text; Clear alarm, then Abort | |
| C8 | SOFTWARE STOP from the projector window (Viewer mode) | Same result as C7 | |
| C9 | Pull the robot network cable during a run (only if the teacher agrees) | FAULT "connection to the robot lost", with the message to use the physical stop | |

## D. Vision
| # | Check | Expected | Result |
|---|---|---|---|
| D1 | Vision before `camera.index` is set | The reason is shown instead of a picture; no broken image icon | |
| D2 | After the index is saved: Start camera | Stream with Choton's overlay, the 375 mm reach circle, the pick area rectangle and the red stop line | |
| D3 | 1 card + 2 candies in the pick area, before the stop line | Counts right; "Object belt would stop: the full set is in the pick area" after 3 pictures in a row | |
| D3b | Only one candy, laid past the red stop line | "Object belt would stop: candy at y = ... mm reached the stop line" | |
| D4 | One item outside the reach circle or the pick area | Marked out of reach or outside the pick area, not counted as usable | |
| D4b | A card or candy laid across the object belt, inside the pick area | Counted as usable (with the camera view of 17 Nov 21:26 it does not touch the top of the picture) | |
| D4c | An open box at the sensor, a lid against it on the downstream side (left on Vision) | Box line: "open box under the box slot". Lid line: "lid at (x, y) (N mm of it below the picture, centre worked out from its size)" | |
| D4d | The same lid moved to the upstream side of the box | Lid line: "... is about 390 mm from the robot: move it N mm or more towards the robot" | |
| D4e | The arm left on the object belt's rail at about (254, 27), then the Run screen | Gate item 12 fails: "the arm stands at (254, 27): ... J1 would have to go to 85.8 deg"; after the arm is moved above the box slot it passes | |
| D5 | Vision during a run | Shows the cycle's own detections; no second camera user. While the run is PAUSED the picture detects live again | |
| D6 | One box in a run: card laid ALONG the object belt, lid on the downstream side of the box | Log: "pick card 1/1 ... turn" about +89 or -89 deg; the card lies along the box; "lid at ..."; the lid lands on the box | |
| D7 | After that run | `testing/live_runs/<run>_pictures/` holds the pictures named in the log rows (box, belt, look, closed_box) | |

## E. Logs
| # | Check | Expected | Result |
|---|---|---|---|
| E1 | After a run | The new CSV is listed first, with its HARDWARE RUN banner | |
| E2 | Open it | Per-box start, end, time and result; failures; mean of the done boxes. Check two numbers against the CSV | |
| E3 | Ctrl+click a second run | Both side by side | |

## F. Settings
| # | Check | Expected | Result |
|---|---|---|---|
| F1 | Save a value with the old source | Refused, with the reason; the file is not changed | |
| F2 | Save `camera.index` with status VERIFIED and a new source | Saved; `live_config.json.bak` exists; the camera tile re-checks | |
| F3 | Save while a run is active | Refused: "a run is active" | |
| F4 | Scan cameras and serial ports | Indexes and COM ports listed; "use" fills the value | |

## G. Other computers
| # | Check | Expected | Result |
|---|---|---|---|
| G1 | Started without `--host`: open the console from a phone on the same network | Not reachable | |
| G2 | Started with `--host 0.0.0.0` (only if needed, teacher agrees) | Terminal prints the WARNING; the phone sees the console | |

## H. Look and feel
| # | Check | Expected | Result |
|---|---|---|---|
| H1 | Overview with the robot and camera connected | Each check that finishes sends one pulse along its cable on the cell map. A check that cannot read anything (NOT OBSERVABLE) sends none | |
| H2 | Stop the backend (Ctrl+C) with the map on screen | No pulse and no moving lamp. Lamps and cables turn grey and the red banner shows. Nothing looks live | |
| H3 | Change a state on purpose (unplug the camera) | The lamp changes shape (disc to cross), the cable changes dash, the rail lamp matches, and the lamp rings once | |
| H4 | Windows setting "Show animations" off (or `prefers-reduced-motion`) | No pulse, no ring; states still change | |
| H5 | Press Tab through the top bar, the rail and one screen | Every control shows a visible focus outline; the order follows the screen | |
| H6 | F12, Network tab, reload | Every request goes to 127.0.0.1. The `.woff2` files the page uses load with status 200 and type `font/woff2` | |
| H7 | Run screen, pass the gate and Arm | The bar under Arm drains over 60 s together with the seconds counter | |
| H8 | A run in progress, change screens and come back | Pause, Resume, Skip box, Abort and Clear alarm are enabled and disabled correctly for the run state | |
| H9 | Ctrl+plus to 150 % on the laptop window | Nothing overlaps. SOFTWARE STOP stays visible. The page may scroll down but never sideways | |
