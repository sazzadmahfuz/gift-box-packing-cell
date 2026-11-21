# dobot_api (vendor copy, unmodified)

- **What:** `dobot_api.py` from Dobot's TCP-IP-4Axis-Python demo, MIT licence (`LICENSE`, "Copyright (c) 2022 Dobot").
- **Copied from:** Dobot TCP-IP-4Axis-Python, `dobot_api.py` (as downloaded by the team in week 2)
  (last changed in commit `4388701`), byte for byte (SHA-256 checked on 2026-11-12).
- **Do not edit.** It is an unmodified vendor file, so it is exempt from the 300-line rule. Keeping
  it unmodified means the command strings are exactly the ones Dobot's own code builds.
- **Loaded only by** `software/cell_sim/drivers/dobot_tcp_robot.py` (path set in
  `software/cell_sim/hardware.json`, `dobot.api_path`). It needs numpy and tkinter.

Quirks of this file (do not copy them into our code):
- `DobotApi.__init__` connects in the constructor and accepts only ports 29999, 30003 and 30004.
- `ToolDI()` sends `DI(...)`; `DOGroup()` never sends; `SetHoldRegs` swaps its two format branches.
- `send_data` and `wait_reply` print errors and swallow them; `MovJ`/`MovL` print every command.
- Sockets have no timeout.
- The demo's `main.py` (not copied) loops forever with MG400 points (z = -60 mm, outside the
  M1 Pro J3 range). Never run it on the M1 Pro.
