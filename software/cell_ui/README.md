# cell_ui: operator window for cell_sim

One desktop window (tkinter, standard library only) for the whole operation of `cell_sim`:
run every mode, check readiness, edit both config files safely, and look at run logs.

## Start
From the `software/` folder:
```
python -m cell_ui
python -m pytest cell_ui -q      # tests; the window smoke test skips without a display
```

## How it works
- **It never talks to hardware or RoboDK itself.** Every run starts the CLI as a separate
  program, `python -m cell_sim ...` with `software/` as the working folder, so every safety
  check stays in the CLI. The only network contact of its own is the RoboDK readiness check: it
  opens `localhost:20500` and closes it at once, without sending data.
- **Nothing is hard-coded.** At start-up it reads the commands and options from
  `cell_sim.__main__.COMMANDS`, the exit codes from the `EXIT_*` constants, the config entries
  from the JSON files, and the log columns from the CSV header. A new CLI option or config key
  shows up without a UI change.
- **Labels:** each result shows the CSV's first line (SIMULATION, ROBODK SIMULATION or DOBOT DRY,
  assumed parameters). The window title says "SIMULATION / assumed parameters" except on the
  Robot check tab. No result is called a hardware result.

## Tabs
1. **Run:** pick a mode; the form is built from the CLI options (choices = dropdown, flags =
   checkbox, numbers and paths = entry with the default). Run, Stop, and a copyable command line.
   The log pane colours errors red and `[... DRY, nothing sent]` lines grey, then shows the exit
   code and its meaning. A written CSV opens on the Results tab with one click.
   `--teacher-approved` is offered only for dobot-real, and only when the operator ticks it.
2. **Readiness:** offline checks per mode, on demand:
   sim (config loads), robodk (settings load, RoboDK port answers), dobot-dry (the values it
   needs are set), dobot-real (the CLI's list of reasons it would refuse). Each check shows a
   mark and the exact messages.
3. **Config:** one sub-tab each for `config.json` and `hardware.json`. A tree of entries and a
   form with value, unit, source and status. Validate uses the program's own loaders; Save
   validates, keeps `<name>.bak`, and writes UTF-8 with the key order and `_comment` keys kept.
   It warns when a value changed but its status and source did not.
4. **Results:** CSV logs, newest first, with their first line; a table and a cycle-time bar chart
   with the mean; two logs side by side.
5. **Robot check:** `connect-check` (read-only) after a dialog that says exactly what is sent.
6. **About:** simulation versus hardware, what each mode touches, where the settings live.

## Code layout
- `discover.py`: CLI parsers to option specs, the argv, exit-code names.
- `config_model.py`: load, flatten, edit, validate and save the JSON files.
- `runner.py`: the subprocess, line streaming, stop and exit code.
- `results.py`: CSV list, first line, rows, cycle times and mean.
- `readiness.py`: the offline checks per mode.
- `app.py`, `widgets.py`, `tab_*.py`: the tkinter window, thin, calling the modules above.
- `tests/`: pytest for every module without tkinter, plus a window smoke test.
