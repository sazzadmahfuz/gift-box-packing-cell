"""Readiness tab: offline checks for every mode the CLI offers."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from .readiness import mode_checks, overall_level
from .widgets import LEVEL_COLOURS, LEVEL_SYMBOLS

POLL_INTERVAL_MS = 100


class ReadinessTab(ttk.Frame):
    def __init__(self, master: tk.Misc, modes: list[str]) -> None:
        super().__init__(master, padding=8)
        self.modes = modes
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(
            top,
            text="Offline checks for each mode, using the default config.json and hardware.json. "
            "Nothing here contacts the robot; the RoboDK check only opens a connection to this PC.",
            wraplength=900,
            justify="left",
        ).pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right")
        self.text = tk.Text(self, wrap="word", font=("Segoe UI", 10), state="disabled", height=30)
        self.text.pack(fill="both", expand=True, pady=(8, 0))
        for level, colour in LEVEL_COLOURS.items():
            self.text.tag_configure(level, foreground=colour, font=("Segoe UI", 10, "bold"))
        self.text.tag_configure("mode", font=("Segoe UI", 11, "bold"))
        self.text.tag_configure("detail", lmargin1=28, lmargin2=28)

    def refresh(self) -> None:
        """Checks run in a worker thread (the RoboDK port check can take 0.5 s); tkinter is only
        touched from the main thread, which polls the result queue."""
        self._show([("(checking...)", [])])
        results: "queue.Queue[list]" = queue.Queue()
        threading.Thread(target=lambda: results.put([(m, mode_checks(m)) for m in self.modes]), daemon=True).start()
        self._wait_for(results)

    def _wait_for(self, results: "queue.Queue[list]") -> None:
        try:
            self._show(results.get_nowait())
        except queue.Empty:
            self.after(POLL_INTERVAL_MS, lambda: self._wait_for(results))

    def _show(self, results) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for mode, checks in results:
            if checks:
                level = overall_level(checks)
                self.text.insert("end", f"[{LEVEL_SYMBOLS[level]}] ", level)
            self.text.insert("end", f"{mode}\n", "mode")
            for check in checks:
                self.text.insert("end", f"    [{LEVEL_SYMBOLS[check.level]}] ", check.level)
                self.text.insert("end", f"{check.name}\n")
                for message in check.messages:
                    self.text.insert("end", f"{message}\n", "detail")
            self.text.insert("end", "\n")
        self.text.configure(state="disabled")
