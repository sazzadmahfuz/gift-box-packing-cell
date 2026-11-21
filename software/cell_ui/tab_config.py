"""Config tab: a generic editor for any settings file made of {value, ...} entries."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config_model import KNOWN_FILES, STATUS_FIELD, VALUE_FIELD, SettingsFile

MULTI_LINE_FIELDS = (VALUE_FIELD, "source", "note")


class SettingsEditor(ttk.Frame):
    def __init__(self, master: tk.Misc, path: Path) -> None:
        super().__init__(master, padding=6)
        self.model = SettingsFile(path)
        self.selected: tuple[str, ...] | None = None
        self.field_widgets: dict[str, tk.Widget] = {}

        self.comment = ttk.Label(self, wraplength=1000, justify="left", foreground="#555555")
        self.comment.pack(fill="x")
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, pady=6)
        tree_box = ttk.Frame(panes)
        self.tree = ttk.Treeview(tree_box, columns=("value", "status"), selectmode="browse")
        self.tree.heading("#0", text="entry")
        self.tree.heading("value", text="value")
        self.tree.heading("status", text="status / note")
        self.tree.column("#0", width=230)
        self.tree.column("value", width=260)
        self.tree.column("status", width=200)
        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._select())
        panes.add(tree_box, weight=3)
        self.form = ttk.LabelFrame(panes, text="Selected entry", padding=6)
        panes.add(self.form, weight=2)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        for text, action in (("Validate", self.validate), ("Save", self.save), ("Revert edits", self.revert),
                             ("Reload from disk", self.reload)):
            ttk.Button(buttons, text=text, command=action).pack(side="left", padx=(0, 4))
        self.message = tk.Text(self, height=5, wrap="word", font=("Segoe UI", 9), state="disabled")
        self.message.pack(fill="x", pady=(6, 0))
        self._fill_tree()

    # Tree

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.comment.configure(text="  ".join(self.model.comments().values()) or str(self.model.path))
        for ref in self.model.entries():
            parent = ""
            for depth in range(len(ref.path) - 1):
                section_id = "/".join(ref.path[: depth + 1])
                if not self.tree.exists(section_id):
                    self.tree.insert(parent, "end", iid=section_id, text=ref.path[depth], open=True)
                parent = section_id
            self.tree.insert(parent, "end", iid="/".join(ref.path), text=ref.path[-1], values=self._row(ref.path))

    def _row(self, path: tuple[str, ...]) -> tuple[str, str]:
        entry = self.model.entry(path)
        unit = entry.get("unit")
        value = self.model.field_text(path, VALUE_FIELD) + (f"  [{unit}]" if isinstance(unit, str) and len(unit) < 20 else "")
        tag = entry.get(STATUS_FIELD) or str(entry.get("note", ""))[:40]
        return value, tag

    # Form

    def _select(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        path = tuple(selection[0].split("/"))
        if path not in [ref.path for ref in self.model.entries()]:
            return
        self.selected = path
        for child in self.form.winfo_children():
            child.destroy()
        self.field_widgets = {}
        ref = next(ref for ref in self.model.entries() if ref.path == path)
        ttk.Label(self.form, text=".".join(path), font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        for row, field_name in enumerate(ref.fields, start=1):
            ttk.Label(self.form, text=field_name).grid(row=row, column=0, sticky="nw", padx=(0, 6), pady=2)
            text = self.model.field_text(path, field_name)
            if field_name == STATUS_FIELD:
                choices = list(self.model.status_choices())
                widget: tk.Widget = ttk.Combobox(self.form, values=choices + ([text] if text not in choices else []), state="readonly")
                widget.set(text)
            elif field_name in MULTI_LINE_FIELDS:
                widget = tk.Text(self.form, height=4 if field_name == VALUE_FIELD else 3, width=48, wrap="word", font=("Consolas", 9))
                widget.insert("1.0", text)
            else:
                widget = ttk.Entry(self.form, width=48)
                widget.insert(0, text)
            widget.grid(row=row, column=1, sticky="ew", pady=2)
            self.field_widgets[field_name] = widget
        hint = "value is JSON: 50, \"text\", null, [1, 2], {\"x_mm\": 1}. Plain words are kept as text."
        ttk.Label(self.form, text=hint, foreground="#555555", wraplength=380).grid(row=len(ref.fields) + 1, column=0, columnspan=2, sticky="w")
        ttk.Button(self.form, text="Apply to entry", command=self.apply).grid(row=len(ref.fields) + 2, column=1, sticky="e", pady=4)
        self.form.columnconfigure(1, weight=1)

    def apply(self) -> None:
        if self.selected is None:
            return
        for field_name, widget in self.field_widgets.items():
            text = widget.get("1.0", "end").strip() if isinstance(widget, tk.Text) else widget.get()
            self.model.set_field(self.selected, field_name, text)
        self.tree.item("/".join(self.selected), values=self._row(self.selected))
        warnings = self.model.provenance_warnings()
        problem = self.model.validate()
        lines = [f"Applied {'.'.join(self.selected)} (not saved yet)."]
        lines += [f"Warning: {warning}" for warning in warnings]
        lines.append(f"Program would reject this file: {problem}" if problem else "The program accepts the edited file.")
        self._say("\n".join(lines))

    # File actions

    def validate(self) -> None:
        problem = self.model.validate()
        self._say(f"Rejected: {problem}" if problem else f"OK: the program accepts {self.model.path.name}.")

    def save(self) -> None:
        if not self.model.is_dirty():
            self._say("No changes to save.")
            return
        warnings = self.model.provenance_warnings()
        if warnings and not messagebox.askyesno(
            "Save without updating status/source?", "\n".join(warnings) + "\n\nSave anyway?", parent=self
        ):
            return
        try:
            backup = self.model.save()
        except ValueError as error:
            self._say(f"Not saved. Rejected: {error}")
            return
        self._say(f"Saved {self.model.path}. Previous version kept as {backup.name}.")

    def revert(self) -> None:
        self.model.revert()
        self._fill_tree()
        self._say("Edits reverted to the last saved version.")

    def reload(self) -> None:
        if self.model.is_dirty() and not messagebox.askyesno("Discard edits?", "Reload and lose unsaved edits?", parent=self):
            return
        self.model.reload()
        self._fill_tree()
        self._say(f"Reloaded {self.model.path.name} from disk.")

    def _say(self, text: str) -> None:
        self.message.configure(state="normal")
        self.message.delete("1.0", "end")
        self.message.insert("1.0", text)
        self.message.configure(state="disabled")


class ConfigTab(ttk.Frame):
    def __init__(self, master: tk.Misc, paths: tuple[Path, ...] = KNOWN_FILES) -> None:
        super().__init__(master, padding=4)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        self.editors = []
        for path in paths:
            editor = SettingsEditor(notebook, path)
            notebook.add(editor, text=path.name)
            self.editors.append(editor)
