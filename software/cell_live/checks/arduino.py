"""Box belt controller (Arduino UNO R4 WiFi) and its sensor, over USB serial (pyserial imported lazily here).

Since 17 Nov the UNO is not connected to this PC: it runs the box belt on its own E18-D80NK
sensor and is powered from a USB-C supply. Rashmika's sketch
(hardware/box_belt_arduino/ArduinoCode.ino) sends nothing over USB. Without a configured port this check reports
NOT_OBSERVABLE with that reason, and without a status command it only checks that the port opens.
"""

from __future__ import annotations

from typing import Any, Callable

from ..status import FAIL, NOT_OBSERVABLE, OK, WARN, CheckResult, missing_package, timed

PYSERIAL_INSTALL = "python -m pip install pyserial"


def load_serial() -> Any:
    import serial  # optional package (pyserial), only for the Arduino check

    return serial


class ArduinoCheck:
    id = "box_belt_nano"  # the id the console's map and register already use; the board is an UNO R4 WiFi
    name = "Box belt controller (UNO R4 WiFi) and sensor"

    def __init__(self, port: str | None, baud: int | None, status_command: str | None, interval_s: float,
                 timeout_s: float = 1.0, serial_loader: Callable[[], Any] = load_serial) -> None:
        self.port = port
        self.baud = baud
        self.status_command = status_command
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self.serial_loader = serial_loader

    def run(self) -> CheckResult:
        if self.port is None:
            return CheckResult(NOT_OBSERVABLE, "the box belt controller is not connected to this PC (arduino.serial_port not set): "
                                               "it runs the box belt on its own sensor, and its sketch sends no status over USB")
        if self.baud is None:
            return CheckResult(NOT_OBSERVABLE, f"arduino.baud is not set for {self.port}")
        try:
            serial = self.serial_loader()
        except ImportError:
            return missing_package("pyserial", PYSERIAL_INSTALL)
        try:
            link, open_ms = timed(lambda: serial.Serial(self.port, self.baud, timeout=self.timeout_s))
        except Exception as error:  # serial.SerialException: port missing or in use
            return CheckResult(FAIL, f"cannot open {self.port}: {error}")
        try:
            if not self.status_command:
                return CheckResult(WARN, f"{self.port} opens, but no status protocol is defined (arduino.status_command not set)", open_ms)

            def ask() -> bytes:
                link.write((self.status_command + "\n").encode("ascii"))
                return link.readline()

            reply, latency_ms = timed(ask)
        finally:
            link.close()
        text = reply.decode("ascii", errors="replace").strip()
        if not text:
            return CheckResult(FAIL, f"{self.port} gave no answer to {self.status_command!r} within {self.timeout_s:g} s")
        return CheckResult(OK, f"box belt controller answered: {text}", latency_ms, {"reply": text})
