"""Build every live check from live_config.json. One DobotLink is shared by all robot checks."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from ..adapters.choton import AlarmTexts
from ..dobot_link import DobotLink, dobot_api_loader
from ..live_config import LiveConfig
from ..status import CheckResult
from .arduino import ArduinoCheck
from .calibration import CalibrationCheck
from .camera import CameraCheck
from .dobot import DashboardCheck, FeedbackCheck
from .relay_do3 import OutputStateCheck
from .robodk import RoboDKCheck
from .vision import ModelCheck


class Check(Protocol):
    id: str
    name: str
    interval_s: float

    def run(self) -> CheckResult: ...


def build_link(config: LiveConfig) -> DobotLink:
    return DobotLink(
        config.value("dobot", "ip"),
        config.value("dobot", "dashboard_port"),
        config.value("dobot", "feedback_port"),
        float(config.value("dobot", "connect_timeout_s")),
        load_api=dobot_api_loader(config.path_value("dobot", "api_path")),
    )


def build_checks(config: LiveConfig, link: DobotLink | None = None,
                 camera_session: Callable[[], Any] | None = None) -> list[Check]:
    link = link or build_link(config)
    robot_interval_s = config.poll_interval_s("dobot", 2.0)
    stale_after_s = 3 * robot_interval_s
    feedback = FeedbackCheck(link, robot_interval_s)
    feedback.triggers = ("object_belt_do3", "object_belt_dir", "object_belt_power", "box_belt_do")  # they read its packet

    def output(id: str, what: str, key: str, level_key: str, **words: Any) -> OutputStateCheck:
        channel = config.value("dobot", key)
        return OutputStateCheck(id, f"Object belt {what} ({f'DO{channel}' if channel else 'no output set'})", link, channel,
                                config.value("dobot", level_key), robot_interval_s, stale_after_s, f"dobot.{key} is not set", **words)

    checks: list[Check] = [
        DashboardCheck(link, AlarmTexts(config.path_value("dobot", "alarm_files_dir")), robot_interval_s),
        feedback,
        output("object_belt_do3", "start and stop", "belt_do", "belt_on_value"),
        output("object_belt_dir", "direction", "belt_dir_do", "belt_dir_forward_value",
               level_words=("forward: objects move towards the robot", "reverse")),
        output("object_belt_power", "enable", "belt_enable_do", "belt_enable_on_value",
               level_words=("the level that enables the belt", "belt not enabled")),
    ]
    if config.value("belts", "box_restart") == "dobot_output":  # only then does a Dobot output move the closed box on
        checks.append(OutputStateCheck(
            "box_belt_do", "Box belt command (Dobot output)", link,
            config.value("dobot", "box_belt_do"), 1, robot_interval_s, stale_after_s,
            "dobot.box_belt_do is not set: which Dobot output tells the box belt controller to move the box on",
        ))
    return checks + [
        CameraCheck(
            config.value("camera", "index"), config.value("camera", "width_px"), config.value("camera", "height_px"),
            config.value("camera", "fps_sample_frames"), config.poll_interval_s("camera", 10.0),
            session_provider=camera_session,
        ),
        ModelCheck(
            config.path_value("vision", "model_path"), config.value("vision", "classes"),
            config.value("vision", "conf_limit"), config.poll_interval_s("vision", 300.0),
        ),
        CalibrationCheck(config.path_value("calibration", "file"), config.poll_interval_s("calibration", 60.0),
                         valid_from=config.value("calibration", "valid_from")),
        RoboDKCheck(config.value("robodk", "host"), config.value("robodk", "port"), config.poll_interval_s("robodk", 10.0)),
        ArduinoCheck(
            config.value("arduino", "serial_port"), config.value("arduino", "baud"),
            config.value("arduino", "status_command"), config.poll_interval_s("arduino", 5.0),
        ),
    ]
