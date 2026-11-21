"""Results tab: list run logs, show one as a table with a cycle-time chart, or compare two."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .results import RunLog, list_logs, read_banner, read_log

SERIES_COLOURS = ("#1f6fb2", "#d9822b")
MAX_TABLE_ROWS = 2000


class ResultsTab(ttk.Frame):
    def __init__(self, master: tk.Misc, log_folder: Path) -> None:
        super().__init__(master, padding=8)
        self.log_folder = log_folder
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        header = ttk.Frame(left)
        header.pack(fill="x")
        self.folder_label = ttk.Label(header, text=f"Logs in {log_folder}", wraplength=330)
        self.folder_label.pack(side="left")
        ttk.Button(header, text="Refresh", command=self.refresh).pack(side="right")
        ttk.Label(left, text="Select one log, or Ctrl+click two to compare.", foreground="#555555").pack(anchor="w")
        self.files = ttk.Treeview(left, columns=("label",), selectmode="extended", height=25)
        self.files.heading("#0", text="file")
        self.files.heading("label", text="label (CSV line 1)")
        self.files.column("#0", width=170)
        self.files.column("label", width=230)
        self.files.pack(fill="both", expand=True)
        self.files.bind("<<TreeviewSelect>>", lambda _event: self._show_selection())
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        self.banner = ttk.Label(right, font=("Segoe UI", 11, "bold"), wraplength=760, justify="left")
        self.banner.pack(anchor="w")
        self.summary = ttk.Label(right, wraplength=760, justify="left")
        self.summary.pack(anchor="w", pady=(2, 6))
        self.chart = tk.Canvas(right, height=220, background="white", highlightthickness=1, highlightbackground="#cccccc")
        self.chart.pack(fill="x")
        self.chart.bind("<Configure>", lambda _event: self._show_selection())
        table_box = ttk.Frame(right)
        table_box.pack(fill="both", expand=True, pady=(6, 0))
        self.table = ttk.Treeview(table_box, show="headings")
        y_scroll = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_box, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        panes.add(right, weight=3)
        self.refresh()

    def refresh(self, select: Path | None = None) -> None:
        if select is not None and select.parent != self.log_folder:  # a run used another --out-dir
            self.log_folder = select.parent
            self.folder_label.configure(text=f"Logs in {self.log_folder}")
        self.files.delete(*self.files.get_children())
        for path in list_logs(self.log_folder):
            label = read_banner(path).split(";")[0] or "(no banner)"
            self.files.insert("", "end", iid=str(path), text=path.name, values=(label,))
        target = str(select) if select is not None else None
        children = self.files.get_children()
        if target in children:
            self.files.selection_set(target)
            self.files.see(target)
        elif children:
            self.files.selection_set(children[0])

    def _show_selection(self) -> None:
        selected = [Path(iid) for iid in self.files.selection()][:2]
        logs = []
        for path in selected:
            try:
                logs.append(read_log(path))
            except OSError as error:
                self.banner.configure(text=f"cannot read {path.name}: {error}")
                return
        if not logs:
            return
        if len(logs) == 1:
            self._show_one(logs[0])
        else:
            self._show_compare(logs)
        self._draw_chart(logs)

    def _show_one(self, log: RunLog) -> None:
        self.banner.configure(text=log.label)
        counts = ", ".join(f"{count} {kind or '(blank)'}" for kind, count in log.count_by_record_type().items())
        mean_s = log.mean_cycle_time_s()
        mean_text = f"; mean cycle time {mean_s:.3f} s" if mean_s is not None else ""
        self.summary.configure(text=f"{log.path.name}: {counts}{mean_text}\n{log.banner}")
        self._fill_table(log)

    def _show_compare(self, logs: list[RunLog]) -> None:
        self.banner.configure(text="Compare: " + "  vs  ".join(log.label for log in logs))
        lines = []
        for log in logs:
            mean_s = log.mean_cycle_time_s()
            lines.append(f"{log.path.name}: " + (f"mean {mean_s:.3f} s over {len(log.cycle_times_s())} cycles" if mean_s is not None else "no cycle times"))
        self.summary.configure(text="\n".join(lines))
        columns = ("cycle",) + tuple(log.path.name for log in logs)
        times = [dict(log.cycle_times_s()) for log in logs]
        cycles = sorted({cycle for series in times for cycle in series}, key=lambda c: (len(c), c))
        self._set_table(columns, [(cycle, *(f"{series[cycle]:.3f}" if cycle in series else "" for series in times)) for cycle in cycles])

    def _fill_table(self, log: RunLog) -> None:
        rows = [tuple(row.get(column, "") for column in log.columns) for row in log.rows[:MAX_TABLE_ROWS]]
        self._set_table(log.columns, rows)

    def _set_table(self, columns: tuple[str, ...], rows: list[tuple]) -> None:
        self.table.delete(*self.table.get_children())
        self.table.configure(columns=columns)
        for column in columns:
            self.table.heading(column, text=column)
            self.table.column(column, width=max(70, min(220, 9 * len(column))), stretch=False)
        for row in rows:
            self.table.insert("", "end", values=row)

    def _draw_chart(self, logs: list[RunLog]) -> None:
        canvas = self.chart
        canvas.delete("all")
        series = [log.cycle_times_s() for log in logs]
        if not any(series):
            canvas.create_text(10, 10, anchor="nw", text="No cycle_time_s values in this log.", fill="#555555")
            return
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), 150)
        left, bottom, top = 50, height - 28, 14
        peak_s = max(time_s for times in series for _cycle, time_s in times) or 1.0
        count = max(len(times) for times in series)
        slot = (width - left - 10) / count
        bar = slot * 0.8 / len(series)
        canvas.create_line(left, top, left, bottom, width - 10, bottom, fill="#999999")
        canvas.create_text(left - 6, top, anchor="e", text=f"{peak_s:.1f} s", fill="#555555")
        canvas.create_text(left - 6, bottom, anchor="e", text="0 s", fill="#555555")
        for index, times in enumerate(series):
            colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
            for position, (cycle, time_s) in enumerate(times):
                x0 = left + position * slot + slot * 0.1 + index * bar
                y0 = bottom - (bottom - top) * time_s / peak_s
                canvas.create_rectangle(x0, y0, x0 + bar - 2, bottom, fill=colour, outline="")
                canvas.create_text(x0 + bar / 2, y0 - 2, anchor="s", text=f"{time_s:.1f}", font=("Segoe UI", 7))
                if index == 0:
                    canvas.create_text(left + position * slot + slot / 2, bottom + 4, anchor="n", text=f"cycle {cycle}", font=("Segoe UI", 8))
            mean_s = sum(t for _c, t in times) / len(times) if times else 0.0
            y_mean = bottom - (bottom - top) * mean_s / peak_s
            canvas.create_line(left, y_mean, width - 10, y_mean, fill=colour, dash=(4, 3))
            canvas.create_text(width - 12, y_mean - 2, anchor="se", text=f"mean {mean_s:.2f} s", fill=colour, font=("Segoe UI", 8))
