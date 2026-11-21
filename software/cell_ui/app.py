"""Main window of the operator UI. Everything shown is discovered from cell_sim at start-up."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from . import discover
from .discover import RUN_COMMAND, SOFTWARE_DIR, option_specs
from .tab_about import about_text
from .tab_config import ConfigTab
from .tab_readiness import ReadinessTab
from .tab_results import ResultsTab
from .tab_run import RunPanel

TITLE = "Packing cell operator"
SIM_TITLE = f"{TITLE}: SIMULATION / assumed parameters"
# Modes that never leave this PC and never move anything: no confirmation needed.
QUIET_MODES = ("sim", "dobot-dry")
TEACHER_FLAG_DEST, TEACHER_MODE = "teacher_approved", "dobot-real"
MODE_NOTES = {
    "robodk": "moves the robot model in the RoboDK station on this PC and sets RoboDK's simulation speed.",
    "dobot-real": "is meant for the REAL robot. The program's safety gate decides whether it may start.",
}


def spec_default(parser_builder, dest: str, fallback: Any) -> Any:
    for spec in option_specs(parser_builder()):
        if spec.dest == dest:
            return spec.choices or spec.default or fallback
    return fallback


class OperatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(SIM_TITLE)
        self.geometry("1280x820")
        self.minsize(900, 600)
        cli = discover.cli_module()
        self.commands = discover.commands(cli)
        self.exit_names = discover.exit_code_names(cli)
        run_parser = self.commands[RUN_COMMAND]
        self.modes = list(spec_default(run_parser, "mode", ("sim",)))
        out_dir = Path(spec_default(run_parser, "out_dir", SOFTWARE_DIR.parent / "testing" / "sim_runs"))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.results = ResultsTab(self.notebook, out_dir)
        self.run_panels: list[RunPanel] = []
        self.run_panels.append(self._add_run_panel(
            RUN_COMMAND, "Run",
            "Runs the cell program as `python -m cell_sim` with the options below. SIMULATION results "
            "use assumed parameters and are never hardware results.",
            confirm=self._confirm_run, rules=self._run_rules,
        ))
        self.readiness = ReadinessTab(self.notebook, self.modes)
        self.notebook.add(self.readiness, text="Readiness")
        self.notebook.add(ConfigTab(self.notebook), text="Config")
        self.notebook.add(self.results, text="Results")
        for command in self.commands:
            if command != RUN_COMMAND:
                self.run_panels.append(self._add_run_panel(
                    command, _tab_name(command), _intro(self.commands[command]),
                    confirm=lambda argv, values, name=command: self._confirm_command(name),
                    run_label=f"Run {command}",
                ))
        about = tk.Text(self.notebook, wrap="word", font=("Segoe UI", 10), padx=12, pady=12)
        about.insert("1.0", about_text(self.modes, list(self.commands), self.exit_names))
        about.configure(state="disabled")
        self.notebook.add(about, text="About")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self._update_title())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.readiness.refresh()

    def _add_run_panel(self, command: str, tab_name: str, intro: str, confirm, rules=None, run_label="Run") -> RunPanel:
        panel = RunPanel(
            self.notebook, command, self.commands[command], intro, self.exit_names,
            on_csv=self.show_log, confirm=confirm, rules=rules, run_label=run_label,
        )
        self.notebook.add(panel, text=tab_name)
        return panel

    # Safety prompts

    @staticmethod
    def _run_rules(values: dict[str, Any]) -> dict[str, bool]:
        return {TEACHER_FLAG_DEST: values.get("mode") == TEACHER_MODE}

    def _confirm_run(self, argv: list[str], values: dict[str, Any]) -> bool:
        mode = values.get("mode", "sim")
        if mode in QUIET_MODES:
            return True
        note = MODE_NOTES.get(mode, "is new to this UI: check software/cell_sim/README.md for what it touches.")
        message = f"Mode '{mode}' {note}\n\nCommand: python -m cell_sim {' '.join(argv)}\n\nContinue?"
        if not messagebox.askokcancel(f"Run mode {mode}?", message, icon="warning", parent=self):
            return False
        if values.get(TEACHER_FLAG_DEST):
            return messagebox.askyesno(
                "Teacher approval",
                "Tick --teacher-approved only if the teacher approved this real-robot run today, and "
                "dobot.teacher_approval in hardware.json names them.\n\nWas this run approved?",
                icon="warning", parent=self,
            )
        return True

    def _confirm_command(self, command: str) -> bool:
        description = self.commands[command]().description or ""
        return messagebox.askokcancel(
            f"Run {command}?",
            f"{description}\n\nThis contacts the real robot over the network (read-only, as described "
            "above). Only run it in the lab with the PC on the robot's network.\n\nContinue?",
            icon="warning", parent=self,
        )

    # Navigation

    def show_log(self, path: Path) -> None:
        self.results.refresh(select=path)
        self.notebook.select(self.results)

    def _update_title(self) -> None:
        current = self.notebook.nametowidget(self.notebook.select())
        hardware_panel = isinstance(current, RunPanel) and current.command != RUN_COMMAND
        self.title(f"{TITLE}: {current.command.upper()} (real robot, read-only)" if hardware_panel else SIM_TITLE)

    def _close(self) -> None:
        running = [panel for panel in self.run_panels if panel.is_running()]
        if running and not messagebox.askyesno("Stop the running program?", "A run is still going. Stop it and quit?", parent=self):
            return
        for panel in running:
            panel.stop()
        self.destroy()


def _tab_name(command: str) -> str:
    return "Robot check" if command == "connect-check" else command.replace("-", " ").capitalize()


def _intro(parser_builder) -> str:
    parser = parser_builder()
    return f"{parser.description or parser.prog}\nRuns: {parser.prog}"


def main() -> None:
    OperatorApp().mainloop()
