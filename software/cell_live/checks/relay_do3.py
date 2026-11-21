"""Belt outputs as the robot commands them: DO3 (start and stop), DO4 (direction) and DO16 (enable)
of the object belt, and box_belt_do only when a Dobot output moves the closed box on.

This is the robot's output bit from the last feedback packet: the commanded state only. It is
not proof that a belt runs (the belt driver and the motor are not observed).
"""

from __future__ import annotations

from cell_sim.drivers.dobot_connect_check import on_channels

from ..dobot_link import DobotLink
from ..status import NOT_OBSERVABLE, OK, UNKNOWN, CheckResult

NOT_PROOF = "commanded state only, not proof that the belt runs"


class OutputStateCheck:
    def __init__(
        self,
        id: str,
        name: str,
        link: DobotLink,
        channel: int | None,
        on_value: int | None,
        interval_s: float,
        max_packet_age_s: float,
        unset_reason: str,
        *,
        level_words: tuple[str, str] = ("the level that should run the belt", "belt should be stopped"),
    ) -> None:
        self.id = id
        self.name = name
        self.link = link
        self.channel = channel
        self.on_value = on_value  # None while the lab has not confirmed which level does what
        self.interval_s = interval_s
        self.max_packet_age_s = max_packet_age_s
        self.unset_reason = unset_reason
        self.level_words = level_words  # what on_value means, and what the other level means

    def run(self) -> CheckResult:
        """Never opens a socket: it reads the packet the feedback check fetched."""
        if self.channel is None:
            return CheckResult(NOT_OBSERVABLE, self.unset_reason)
        failure = self.link.feedback_failed_since_last_packet()
        if failure is not None:
            return CheckResult(NOT_OBSERVABLE, f"DO{self.channel} cannot be observed: robot feedback not readable ({failure})")
        packet, age_s = self.link.last_packet, self.link.packet_age_s()
        if packet is None or age_s is None:
            return CheckResult(UNKNOWN, f"DO{self.channel}: no feedback packet read yet (see Dobot feedback)")
        if age_s > self.max_packet_age_s:
            return CheckResult(UNKNOWN, f"DO{self.channel}: last feedback packet is {age_s:.1f} s old", data={"packet_age_s": round(age_s, 1)})
        level = 1 if self.channel in on_channels(packet.fields["digital_outputs"]) else 0
        meaning = ""
        if self.on_value is not None:
            meaning = f" ({self.level_words[0] if level == self.on_value else self.level_words[1]})"
        detail = f"DO{self.channel} commanded {'ON' if level else 'OFF'}{meaning}; {NOT_PROOF}"
        data = {"channel": self.channel, "commanded_level": level, "packet_age_s": round(age_s, 2), "bit_order": "bit 0 = DO1 (CONFIRM)"}
        return CheckResult(OK, detail, data=data)
