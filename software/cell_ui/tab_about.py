"""About tab text, built from what was discovered at start-up."""

from __future__ import annotations


def about_text(modes: list[str], commands: list[str], exit_names: dict[int, str]) -> str:
    exit_lines = "\n".join(f"    {code}: {name}" for code, name in sorted(exit_names.items()))
    return f"""Packing cell operator UI

SIMULATION vs hardware
  Every result is SIMULATION or ROBODK SIMULATION with assumed parameters unless its CSV line 1
  says otherwise. Never present them as hardware results.

What each part touches
  Modes found in the program: {', '.join(modes)}
    sim, dobot-dry : this PC only. dobot-dry prints the Dobot commands and sends nothing.
    robodk         : the RoboDK station on this PC (simulate mode).
    dobot-real     : the real robot, behind the program's safety gate (speed cap, workspace
                     limits, vacuum DO, teacher approval in hardware.json and --teacher-approved).
  Other commands found: {', '.join(c for c in commands if c != 'run') or 'none'}
    connect-check  : the real robot, read-only (asks before it runs).

How the UI works
  The UI runs `python -m cell_sim` as a separate program; all safety checks stay in the program.
  Forms, modes, exit codes, config fields and log columns are read from the program and files
  each time the UI starts, so changes to the program or config show up without UI changes.

Where things live
  software/cell_sim/config.json    cell timings and timeouts (all ASSUMED)
  software/cell_sim/hardware.json  RoboDK and Dobot settings (value, unit, source, status)
  testing/sim_runs/                run logs (CSV)
  Saving a config keeps the previous file as <name>.bak.

Exit codes (from the program)
{exit_lines}
"""
