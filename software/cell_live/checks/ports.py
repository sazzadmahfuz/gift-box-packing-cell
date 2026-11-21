"""Which cameras and serial ports this PC has (Settings screen). Optional packages load lazily here.

Cameras: find_cameras() opens indexes 0-3; an index held by the vision session is reported as
"in use" and not opened. Serial ports: pyserial if installed, otherwise the Windows registry.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from .camera import find_cameras


def camera_ports(in_use_index: int | None = None, finder: Callable[..., list[dict[str, Any]]] = find_cameras,
                 size_px: tuple[int, int] | None = None) -> dict[str, Any]:
    """size_px: (width, height) to ask each camera for; None = the finder's default."""
    try:
        found = finder() if size_px is None else finder(width_px=size_px[0], height_px=size_px[1])
    except ImportError:
        return {"cameras": [], "detail": "opencv is missing: python -m pip install opencv-python"}
    for camera in found:
        if camera["index"] == in_use_index:
            camera["opens"], camera["frame"] = True, "in use by the vision session"
    return {"cameras": found, "detail": ""}


def serial_ports(list_pyserial: Callable[[], list[str]] | None = None, list_registry: Callable[[], list[str]] | None = None) -> dict[str, Any]:
    try:
        return {"ports": (list_pyserial or _pyserial_ports)(), "source": "pyserial", "detail": ""}
    except ImportError:
        pass
    if sys.platform == "win32" or list_registry is not None:
        try:
            return {"ports": (list_registry or _registry_ports)(), "source": "Windows registry", "detail": "pyserial not installed"}
        except OSError as error:
            return {"ports": [], "source": "none", "detail": f"no serial port list: {error}"}
    return {"ports": [], "source": "none", "detail": "install pyserial to list serial ports: python -m pip install pyserial"}


def _pyserial_ports() -> list[str]:
    from serial.tools import list_ports  # optional package (pyserial)

    return sorted(port.device for port in list_ports.comports())


def _registry_ports() -> list[str]:
    import winreg  # standard library, Windows only

    ports = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
        index = 0
        while True:
            try:
                ports.append(str(winreg.EnumValue(key, index)[1]))
            except OSError:  # no more values
                return sorted(ports)
            index += 1
