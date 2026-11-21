"""Vision model check: Choton's YOLO model exists and loads (ultralytics imported lazily here)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..status import FAIL, OK, WARN, CheckResult, missing_package, timed

ULTRALYTICS_INSTALL = "python -m pip install ultralytics"


def load_yolo(path: Path) -> Any:
    from ultralytics import YOLO  # optional package, only for the vision check

    return YOLO(str(path))


class ModelCheck:
    id = "vision_model"
    name = "Vision model (YOLO)"
    kind = "file"  # a file on this PC, not a device

    def __init__(self, model_path: Path | None, classes: list[str], conf_limit: float, interval_s: float,
                 loader: Callable[[Path], Any] = load_yolo) -> None:
        self.model_path = model_path
        self.classes = list(classes)
        self.conf_limit = conf_limit
        self.interval_s = interval_s
        self.loader = loader
        self._loaded: tuple[float, list[str]] | None = None  # (file mtime, class names) of the last load

    def run(self) -> CheckResult:
        if self.model_path is None or not self.model_path.is_file():
            return CheckResult(FAIL, f"model file not found: {self.model_path} (vision.model_path)")
        mtime_s = self.model_path.stat().st_mtime
        data: dict[str, Any] = {"model_path": str(self.model_path), "conf_limit": self.conf_limit}
        latency_ms = None
        if self._loaded is None or self._loaded[0] != mtime_s:
            try:
                model, latency_ms = timed(lambda: self.loader(self.model_path))
            except ImportError:
                return missing_package("ultralytics", ULTRALYTICS_INSTALL)
            except Exception as error:  # a broken or incompatible model file
                return CheckResult(FAIL, f"model file did not load: {type(error).__name__}: {error}")
            names = getattr(model, "names", {})
            names_list = [names[key] for key in sorted(names)] if isinstance(names, dict) else list(names)
            self._loaded = (mtime_s, names_list)
        names_list = self._loaded[1]
        data["classes"] = names_list
        if sorted(names_list) != sorted(self.classes):
            return CheckResult(WARN, f"model classes {names_list} differ from vision.classes {self.classes}", latency_ms, data)
        return CheckResult(OK, f"model loaded, classes {names_list}, confidence limit {self.conf_limit}", latency_ms, data)
