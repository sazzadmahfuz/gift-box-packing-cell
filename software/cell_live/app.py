"""The cell_live backend as one object: config, robot link, checks, run service, vision, UI data.

The HTTP server reads its parts from here on every request, so a Settings save can rebuild them
(reload) while the server keeps running. Reload is refused while a run is active.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters.choton import load_choton_modules
from .checks import build_checks, build_link
from .checks.ports import camera_ports, serial_ports
from .config_store import ConfigStore
from .control.service import LIVE_RUNS_DIR, RunService
from .control.vision_service import VisionService
from .live_config import load_live_config
from .poller import EventHub, Poller


class LiveApp:
    def __init__(self, config_path: str | Path | None = None, allow_remote_control: bool = False,
                 logs_dir: Path = LIVE_RUNS_DIR) -> None:
        self.config_path = config_path
        self.allow_remote_control = allow_remote_control
        self.logs_dir = logs_dir
        self.hub = EventHub()  # kept across reloads, so open browser streams keep working
        self.config_store = ConfigStore(lambda: self.config)
        self._started = False
        self._build()

    def _build(self) -> None:
        self.config = load_live_config(self.config_path)
        self.link = build_link(self.config)
        self.link.on_trace = lambda trace: self.hub.publish(trace, "trace")
        self.vision = VisionService(self.config, load_choton_modules, run_active=lambda: self.run.detecting)
        checks = build_checks(self.config, self.link, camera_session=self.vision.camera_holder)
        self.poller = Poller(checks, hub=self.hub)
        self.run = RunService(self.config, self.link, self.poller, vision_service=self.vision, hub=self.hub)

    def unknowns(self) -> list[str]:
        return self.config.unknowns()

    def start(self) -> None:
        if not self.vision.camera_reason():
            self.vision.start_async()  # first: the camera check then leaves the camera to the vision session
        self.poller.start()
        self._started = True

    def stop(self) -> None:
        self.run.stop()
        self.poller.stop()

    def reload(self) -> str:
        """Rebuild everything from live_config.json (after a Settings save)."""
        if self.run.active:
            return "not reloaded: a run is active"
        was_started = self._started
        self.stop()
        self._build()
        if was_started:
            self.start()
        return "reloaded: the new settings are in use"

    def ports(self) -> dict[str, Any]:
        session = self.vision.session
        in_use = self.config.value("camera", "index") if session is not None else None
        size_px = (self.config.value("camera", "width_px"), self.config.value("camera", "height_px"))
        return {"cameras": camera_ports(in_use, size_px=size_px if None not in size_px else None), "serial": serial_ports()}
