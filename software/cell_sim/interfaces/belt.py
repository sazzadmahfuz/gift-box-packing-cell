"""Belt interface: belt A carries items through the camera's pick area (switched by robot DO3).

Belt B (boxes) is run by the Arduino Nano on its own; the cell only sees its sensor S1.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BeltDriver(Protocol):
    name: str  # "A" or "B"

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def is_running(self) -> bool: ...
