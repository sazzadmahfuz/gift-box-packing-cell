"""Reusable tkinter pieces: a colour-coded log pane and a form generated from option specs."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .discover import KIND_CHOICE, KIND_FLAG, KIND_OPTIONAL_VALUE, OptionSpec

LEVEL_COLOURS = {"ok": "#1a7f37", "warn": "#b35900", "fail": "#c62828", "info": "#555555"}
LEVEL_SYMBOLS = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "info": "INFO"}


def line_tag(text: str, is_error_stream: bool) -> str:
    """Which colour a log line gets. Based on words the CLI prints, falling back to plain."""
    upper = text.upper()
    if is_error_stream or "FAULT" in upper or "ERROR" in upper or "CANNOT" in upper or "REFUSED" in upper:
        return "error"
    if "NOTHING SENT" in upper:
        return "dry"
    if "] CYCLE " in upper:
        return "cycle"
    if upper.startswith("[") and "ASSUMED" in upper:
        return "label"
    return "plain"


class LogPane(ttk.Frame):
    def __init__(self, master: tk.Misc, height: int = 18) -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=height, wrap="none", font=("Consolas", 9), state="disabled")
        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.text.tag_configure("error", foreground=LEVEL_COLOURS["fail"])
        self.text.tag_configure("dry", foreground="#777777")
        self.text.tag_configure("cycle", font=("Consolas", 9, "bold"))
        self.text.tag_configure("label", foreground="#1f4e9c")
        self.text.tag_configure("status", foreground="#1f4e9c", font=("Consolas", 9, "bold"))

    def append(self, text: str, tag: str = "plain") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", text + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def content(self) -> str:
        return self.text.get("1.0", "end").rstrip("\n")


class OptionForm(ttk.Frame):
    """One row per CLI option: dropdown, checkbox or entry, chosen from the option kind."""

    def __init__(self, master: tk.Misc, specs: list[OptionSpec], on_change: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.specs = specs
        self.on_change = on_change or (lambda: None)
        self.variables: dict[str, Any] = {}
        self.widgets: dict[str, list[tk.Widget]] = {}
        for row, spec in enumerate(specs):
            self._add_row(row, spec)
        self.columnconfigure(1, weight=1)

    def _add_row(self, row: int, spec: OptionSpec) -> None:
        name = spec.flag or spec.dest
        ttk.Label(self, text=name).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        if spec.kind == KIND_FLAG:
            variable: Any = tk.BooleanVar(value=False)
            widgets = [ttk.Checkbutton(self, variable=variable, command=self.on_change)]
        elif spec.kind == KIND_CHOICE:
            variable = tk.StringVar(value=spec.default or (spec.choices[0] if spec.choices else ""))
            combo = ttk.Combobox(self, textvariable=variable, values=spec.choices, state="readonly", width=24)
            combo.bind("<<ComboboxSelected>>", lambda _event: self.on_change())
            widgets = [combo]
        elif spec.kind == KIND_OPTIONAL_VALUE:
            enabled = tk.BooleanVar(value=False)
            variable = (enabled, tk.StringVar(value=spec.const))
            holder = ttk.Frame(self)
            ttk.Checkbutton(holder, text="on", variable=enabled, command=self.on_change).pack(side="left")
            ttk.Entry(holder, textvariable=variable[1], width=12).pack(side="left", padx=4)
            widgets = [holder]
        else:
            variable = tk.StringVar(value=spec.default)
            entry = ttk.Entry(self, textvariable=variable, width=40)
            entry.bind("<KeyRelease>", lambda _event: self.on_change())
            widgets = [entry]
        widgets[0].grid(row=row, column=1, sticky="w", pady=2)
        hint = ttk.Label(self, text=spec.help, foreground="#555555", wraplength=520, justify="left")
        hint.grid(row=row, column=2, sticky="w", padx=8)
        self.variables[spec.dest] = variable
        self.widgets[spec.dest] = widgets + [hint]

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for dest, variable in self.variables.items():
            result[dest] = (variable[0].get(), variable[1].get()) if isinstance(variable, tuple) else variable.get()
        return result

    def set_value(self, dest: str, value: Any) -> None:
        variable = self.variables[dest]
        if isinstance(variable, tuple):
            variable[0].set(bool(value[0]))
            variable[1].set(value[1])
        else:
            variable.set(value)

    def set_enabled(self, dest: str, enabled: bool) -> None:
        for widget in self.widgets.get(dest, [])[:1]:
            targets = widget.winfo_children() or [widget]
            for target in targets:
                on_state = "readonly" if isinstance(target, ttk.Combobox) else "normal"
                try:
                    target.configure(state=on_state if enabled else "disabled")
                except tk.TclError:
                    pass
        if not enabled and dest in self.variables and isinstance(self.variables[dest], tk.BooleanVar):
            self.variables[dest].set(False)


def status_label(master: tk.Misc, level: str, text: str) -> ttk.Label:
    return ttk.Label(master, text=f"[{LEVEL_SYMBOLS.get(level, level)}] {text}", foreground=LEVEL_COLOURS.get(level, "#000"))
