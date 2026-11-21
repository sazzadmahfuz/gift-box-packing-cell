"""Sensor S1 interface: active while a box stands at the stop position on belt B."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SensorS1(Protocol):
    def is_active(self) -> bool: ...
