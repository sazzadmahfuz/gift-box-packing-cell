"""A run panel: generated option form, Run/Stop, live log, exit code. Used by the Run and
Robot check tabs (each with its own CLI command)."""

from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from .discover import build_argv, check_argv, describe_exit, full_command, option_specs
from .runner import STDERR, CellRun
from .widgets import LogPane, OptionForm, line_tag

POLL_INTERVAL_MS = 100
Rules = Callable[[dict[str, Any]], dict[str, bool]]  # form values -> {dest: enabled}
Confirm = Callable[[list[str], dict[str, Any]], bool]  # argv, form values -> go ahead?


class RunPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        command: str,
        parser_builder: Callable[[], Any],
        intro: str,
        exit_names: dict[int, str],
        on_csv: Callable[[Path], None],
        confirm: Confirm | None = None,
        rules: Rules | None = None,
        run_label: str = "Run",
    ) -> None:
        super().__init__(master, padding=8)
        self.command = command
        self.parser_builder = parser_builder
        self.exit_names = exit_names
        self.on_csv = on_csv
        self.confirm = confirm or (lambda argv, values: True)
        self.rules = rules or (lambda values: {})
        self.run: CellRun | None = None
        self.specs = option_specs(parser_builder())

        ttk.Label(self, text=intro, wraplength=900, justify="left").pack(anchor="w", pady=(0, 6))
        form_box = ttk.LabelFrame(self, text="Options (read from the program's command line)", padding=6)
        form_box.pack(fill="x")
        self.form = OptionForm(form_box, self.specs, on_change=self._refresh)
        self.form.pack(fill="x")

        command_row = ttk.Frame(self)
        command_row.pack(fill="x", pady=6)
        ttk.Label(command_row, text="Command:").pack(side="left")
        self.command_text = tk.StringVar()
        ttk.Entry(command_row, textvariable=self.command_text, state="readonly").pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(command_row, text="Copy", command=self._copy_command).pack(side="left")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.run_button = ttk.Button(buttons, text=run_label, command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Clear log", command=lambda: self.log.clear()).pack(side="left")
        self.csv_button = ttk.Button(buttons, text="Open log in Results", command=self._open_csv, state="disabled")
        self.csv_button.pack(side="left", padx=4)
        self.status = tk.StringVar(value="ready")
        ttk.Label(buttons, textvariable=self.status, font=("Segoe UI", 9, "bold")).pack(side="left", padx=12)

        self.log = LogPane(self)
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        self._refresh()

    # Form

    def argv(self) -> list[str]:
        return build_argv(self.command, self.specs, self.form.values())

    def _refresh(self) -> None:
        values = self.form.values()
        for dest, enabled in self.rules(values).items():
            if dest in self.form.variables:
                self.form.set_enabled(dest, enabled)
        self.command_text.set(subprocess.list2cmdline(["python", *full_command(self.argv())[1:]]))

    def _copy_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.command_text.get())

    # Running

    def start(self) -> None:
        if self.run is not None and self.run.is_running():
            return
        argv = self.argv()
        problem = check_argv(self.parser_builder(), argv, self.command)
        if problem:
            messagebox.showerror("Invalid options", problem, parent=self)
            return
        if not self.confirm(argv, self.form.values()):
            self.status.set("cancelled")
            return
        self.log.append(f"$ {self.command_text.get()}", "status")
        self.run = CellRun(argv)
        try:
            self.run.start()
        except OSError as error:
            self.log.append(f"cannot start: {error}", "error")
            self.run = None
            return
        self.status.set("running...")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.csv_button.configure(state="disabled")
        self.after(POLL_INTERVAL_MS, self._poll)

    def stop(self) -> None:
        if self.run is not None:
            self.run.stop()
            self.status.set("stopping...")

    def _poll(self) -> None:
        run = self.run
        if run is None:
            return
        for line in run.new_lines():
            self.log.append(line.text, line_tag(line.text, line.stream == STDERR))
        if not run.is_finished():
            self.after(POLL_INTERVAL_MS, self._poll)
            return
        for line in run.new_lines():
            self.log.append(line.text, line_tag(line.text, line.stream == STDERR))
        outcome = describe_exit(run.exit_code(), self.exit_names)
        self.status.set(outcome)
        self.log.append(f"--- {outcome}", "status")
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if run.csv_paths:
            self.csv_button.configure(state="normal")

    def _open_csv(self) -> None:
        if self.run is not None and self.run.csv_paths:
            self.on_csv(self.run.csv_paths[-1])

    def is_running(self) -> bool:
        return self.run is not None and self.run.is_running()
