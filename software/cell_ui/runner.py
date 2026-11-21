"""Run `python -m cell_sim ...` as a subprocess and stream its output (no tkinter here).

The UI never runs cell code in its own process: the CLI keeps every safety check, and a crash
or hang in a run cannot freeze the window.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .discover import SOFTWARE_DIR, full_command

STDOUT, STDERR = "stdout", "stderr"
CSV_PATH_PATTERN = re.compile(r"([A-Za-z]:[\\/][^\s]+?\.csv|/[^\s]+?\.csv|[^\s]+?\.csv)")


@dataclass(frozen=True)
class OutputLine:
    stream: str  # STDOUT or STDERR
    text: str


class CellRun:
    def __init__(self, argv: list[str], cwd: Path = SOFTWARE_DIR) -> None:
        self.argv = list(argv)
        self.command = full_command(self.argv)
        self.cwd = cwd
        self.lines: "queue.Queue[OutputLine]" = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.stopped_by_user = False
        self.csv_paths: list[Path] = []
        self._readers: list[threading.Thread] = []

    def start(self) -> None:
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=env,
            stdin=subprocess.DEVNULL,  # the CLI must never wait for keyboard input from the UI
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        for stream_name, stream in ((STDOUT, self.process.stdout), (STDERR, self.process.stderr)):
            reader = threading.Thread(target=self._read, args=(stream_name, stream), daemon=True)
            reader.start()
            self._readers.append(reader)

    def _read(self, stream_name: str, stream) -> None:
        for raw_line in stream:
            text = raw_line.rstrip("\r\n")
            self._note_csv(text)
            self.lines.put(OutputLine(stream_name, text))
        stream.close()

    def _note_csv(self, text: str) -> None:
        for match in CSV_PATH_PATTERN.findall(text):
            path = Path(match)
            path = path if path.is_absolute() else self.cwd / path
            if path.is_file() and path not in self.csv_paths:
                self.csv_paths.append(path)

    def new_lines(self) -> list[OutputLine]:
        lines = []
        while True:
            try:
                lines.append(self.lines.get_nowait())
            except queue.Empty:
                return lines

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def is_finished(self) -> bool:
        """True when the process ended and all its output has been read."""
        return self.process is not None and self.process.poll() is not None and not any(
            reader.is_alive() for reader in self._readers
        )

    def exit_code(self) -> int | None:
        if self.process is None or self.stopped_by_user:
            return None
        return self.process.poll()

    def stop(self) -> None:
        if self.is_running():
            self.stopped_by_user = True
            self.process.terminate()

    def wait(self, timeout_s: float | None = None) -> int | None:
        if self.process is not None:
            self.process.wait(timeout=timeout_s)
            for reader in self._readers:
                reader.join(timeout=timeout_s)
        return self.exit_code()
