"""Arm, start and steer a real run (what the API endpoints call).

Arm: collect the facts (config, Choton's settings and calibration read now, the live robot
status checked now, the vision session) and run the gate. Only a clean gate gives a one-time
token. Start: redeem the token, run the gate again, open the robot session, start the cycle.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any, Callable

from ..adapters.choton import ChotonCodeUnavailable, load_choton_modules, read_json
from ..dobot_link import dobot_api_loader
from ..live_config import REPO_ROOT
from .arm_reach import arm_reach_from
from .belts import BoxRestart, BoxRestartNotSet, ObjectBeltDO3
from .cycle import RunController
from .gate import NOT_FOR_A_RUN, ArmTokens, GateFacts, check
from .idle_stop import outputs_off
from .pictures import RunPictures, pictures_folder
from .robot_session import RobotSession, SessionError, SessionValues
from .run_context import Limits, RunContext
from .runlog import RunLog
from .states import Action, CycleState
from .vision_service import VisionService
from .vision_session import VisionSession
from .way_home import gate_item, way_home_problem

LIVE_RUNS_DIR = REPO_ROOT / "testing" / "live_runs"


class RunService:
    def __init__(self, config: Any, link: Any, poller: Any, load_choton: Callable[[Path], Any] = load_choton_modules,
                 make_vision: Callable[..., Any] = VisionSession, make_session: Callable[..., Any] = RobotSession,
                 out_dir: Path = LIVE_RUNS_DIR, clock: Callable[[], float] = time.monotonic,
                 vision_service: VisionService | None = None, hub: Any = None) -> None:
        self.config = config
        self.link = link
        self.poller = poller
        self.load_choton = load_choton
        self.make_vision = make_vision
        self.make_session = make_session
        self.out_dir = out_dir
        self.clock = clock
        self.tokens = ArmTokens(float(config.value("control", "arm_token_s")), clock)
        self._armed_operator: dict[str, dict[str, Any]] = {}
        self.vision_service = vision_service or VisionService(config, load_choton, make_vision, run_active=lambda: self.detecting)
        self.hub = hub  # run snapshots and log rows go to the live stream
        self.controller: RunController | None = None
        self.last_report: dict[str, Any] | None = None

    @property
    def active(self) -> bool:
        return self.controller is not None and not self.controller.finished

    @property
    def detecting(self) -> bool:
        """The cycle is taking pictures now. Not while PAUSED or in FAULT: the robot stands still then, and the
        live view detects again, so the operator sees what a Resume would find (the lid just moved, say)."""
        return self.active and self.controller.state not in (CycleState.PAUSED, CycleState.FAULT)

    @property
    def vision(self) -> Any:
        return self.vision_service.session

    def _publish(self, kind: str) -> Callable[[dict[str, Any]], None] | None:
        if self.hub is None:
            return None
        return lambda event: self.hub.publish(event, kind)

    def gate(self, body: dict[str, Any]) -> dict[str, Any]:
        """The gate item by item, for the live checklist. Never gives a token."""
        limits = {"speed_percent": self.config.value("dobot", "speed_percent"),
                  "speed_percent_max": self.config.value("control", "speed_percent_max")}
        if self.active:
            return {"active": True, "ok": False, "items": [], "problems": ["a run is active"], "notes": [],
                    "cell": [] if self.detecting else self._cell_now(), **limits}
        report = self._report(*self._facts(self._operator(body)))
        return {"active": False, "ok": report.ok, "items": report.items, "problems": report.problems,
                "notes": report.notes, "cell": self._cell_now(), **limits}

    def _report(self, facts: GateFacts, _choton: Any, settings: dict[str, Any] | None) -> Any:
        """The gate, plus one item it cannot know from values and files: where the arm stands now (way_home.py)."""
        report = check(facts)
        packet = getattr(self.link, "last_packet", None)
        pose = packet.fields.get("pose_xyzr") if packet is not None else None
        range_entry = self.config.raw.get("dobot", {}).get("j1_range_deg") or {}
        gate_item(report, way_home_problem(arm_reach_from(self.config), range_entry.get("value"), pose,
                                           ((settings or {}).get("robot") or {}).get("home")))
        report.notes.extend(note for note in [self.vision_service.view_note()] if note)
        return report

    def _cell_now(self) -> list[dict[str, Any]]:
        """What the camera shows of the box and the lid right now, in the run's own words, for the Run screen.
        It never blocks Arm: the box may still arrive, and the lid can be laid down while the run goes on."""
        summary = self.vision_service.summary()
        return [{"name": name, **summary[key]} for name, key in (("Box", "box"), ("Lid", "lid")) if key in summary]

    # Arm and start

    def arm(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.active:
            return {"armed": False, "problems": ["a run is active: abort it first"], "notes": []}
        operator = self._operator(body)
        report = self._report(*self._facts(operator))
        self.last_report = {"problems": report.problems, "notes": report.notes}
        if not report.ok:
            return {"armed": False, "problems": report.problems, "notes": report.notes}
        token = self.tokens.issue(operator["boxes"], operator["speed_percent"])
        self._armed_operator[token] = operator
        return {"armed": True, "token": token, "expires_in_s": self.tokens.lifetime_s, "notes": report.notes}

    def start(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.active:
            return {"started": False, "problems": ["a run is already active"]}
        token = body.get("token")
        operator = self._armed_operator.pop(token, None) if isinstance(token, str) else None
        boxes, speed = body.get("boxes"), body.get("speed_percent")
        problem = self.tokens.redeem(token, boxes, speed)
        if problem or operator is None:
            return {"started": False, "problems": [problem or "no valid arm token: press Arm first"]}
        facts, choton, settings = self._facts(operator)
        report = self._report(facts, choton, settings)  # checked again: things may have changed since Arm
        if not report.ok:
            return {"started": False, "problems": report.problems}
        return self._launch(choton, settings, operator, report.notes)

    def _launch(self, choton: Any, settings: dict[str, Any], operator: dict[str, Any], notes: list[str]) -> dict[str, Any]:
        config = self.config
        restart_mode = config.value("belts", "box_restart")
        box_belt_do = config.value("dobot", "box_belt_do") if restart_mode == "dobot_output" else None
        dobot = lambda key: config.value("dobot", key)  # noqa: E731 (short local helper)
        values = SessionValues(
            speed_percent=operator["speed_percent"], vacuum_do=dobot("vacuum_do"), blow_do=dobot("blow_do"),
            belt_do=dobot("belt_do"), belt_on_value=dobot("belt_on_value"),
            belt_dir_do=dobot("belt_dir_do"), belt_dir_forward_value=dobot("belt_dir_forward_value"),
            belt_enable_do=dobot("belt_enable_do"), belt_enable_on_value=dobot("belt_enable_on_value"), box_belt_do=box_belt_do,
            reach_min_mm=config.value("control", "reach_min_mm"), reach_max_mm=config.value("control", "reach_max_mm"),
            move_port=config.value("dobot", "move_port"), reply_timeout_s=float(config.value("control", "move_reply_timeout_s")),
        )
        hashed = {
            "live_config": config.path,
            "settings": Path(choton.folder) / "config" / "settings.json",
            "homography": config.path_value("calibration", "file"),
        }
        log = RunLog(self.out_dir, values.speed_percent, str(config.value("dobot", "teacher_approval")), operator["boxes"], hashed,
                     on_row=self._publish("trace"))
        session = self.make_session(self.link, choton, settings, values, log.command, dobot_api_loader(config.path_value("dobot", "api_path")))
        try:
            restart = BoxRestart(restart_mode, session, box_belt_do, float(config.value("control", "belt_settle_s")))
            set_at_start = session.open()
        except (SessionError, BoxRestartNotSet) as error:
            log.event("start refused", fault=str(error), state="IDLE")
            log.close()
            return {"started": False, "problems": [str(error)]}
        if set_at_start:
            log.event(f"outputs at the start: {'; '.join(set_at_start)}", state="IDLE")
        belt = ObjectBeltDO3(session, values.belt_do, values.belt_on_value,
                             enable=(values.belt_enable_do, values.belt_enable_on_value))
        limits = self._limits()
        pictures = RunPictures(pictures_folder(log.path), _jpeg_encoder(choton))

        def build(controller: RunController) -> RunContext:
            return RunContext(session, self.vision, belt, restart, choton.yolo_lib, choton.pick, settings, limits,
                              log, controller.checkpoint, controller.sleep, self.clock, pictures)

        self.controller = RunController(build, operator["boxes"], session, log, on_change=self._publish("run"))
        self.controller.start()
        return {"started": True, "run_log": str(log.path), "notes": notes}

    def _limits(self) -> Limits:
        value = lambda key: self.config.value("control", key)  # noqa: E731 (short local helper)
        return Limits(
            reach_min_mm=value("reach_min_mm"), reach_max_mm=value("reach_max_mm"),
            box_wait_timeout_s=float(value("box_wait_timeout_s")), feed_timeout_s=float(value("object_feed_timeout_s")),
            settle_s=float(value("belt_settle_s")), box_still_frames=int(value("box_still_frames")),
            box_still_px=float(value("box_still_px")), ready_frames=int(value("objects_ready_frames")),
            detect_frames=int(value("detect_frames")), gone_px=float(value("gone_match_px")),
            box_leave_timeout_s=float(value("box_leave_timeout_s")), close_lid=bool(value("close_lid")),
            feed_stop_y_mm=None if value("feed_stop_y_mm") is None else float(value("feed_stop_y_mm")),
            stop_line_frames=int(value("feed_stop_line_frames")), refeeds_max=int(value("refeeds_without_pick_max")),
            arm=arm_reach_from(self.config),
            box_slot_tolerance_mm=None if value("box_slot_tolerance_mm") is None else float(value("box_slot_tolerance_mm")),
            lid_min_from_slot_mm=float(value("lid_min_from_slot_mm")),
            lid_grip_offset_max_mm=float(value("lid_grip_offset_max_mm")),
        )

    # Operator actions during a run

    def pause(self) -> dict[str, Any]:
        return self._with_run(lambda c: (c.request_pause(), "pause requested: at the next safe point")[1])

    def resume(self) -> dict[str, Any]:
        return self._with_run(lambda c: c.act(Action.RETRY))

    def skip(self) -> dict[str, Any]:
        return self._with_run(lambda c: c.act(Action.SKIP_BOX))

    def abort(self) -> dict[str, Any]:
        return self._with_run(lambda c: c.act(Action.ABORT))

    def estop(self) -> dict[str, Any]:
        if not self.active:  # no run: switch the outputs off anyway (the arm is not moving, nothing else is sent)
            return _idle_reply("software stop with no run active", outputs_off(self.link, self.config))
        return {"ok": True, "message": "software e-stop sent (not the physical emergency stop)", "outputs": self.controller.estop()}

    def belt_stop(self) -> dict[str, Any]:
        """Stop the object belt: during a run by pausing it (the pause switches the belt off), else at once."""
        if self.active:
            return self.pause()
        return _idle_reply("object belt stop", outputs_off(self.link, self.config, belt_only=True))

    def clear_alarm(self) -> dict[str, Any]:
        return self._with_run(lambda c: c.clear_alarm())

    def status(self) -> dict[str, Any]:
        if self.controller is None:
            return {"state": "IDLE", "last_arm": self.last_report}
        return {**self.controller.snapshot(), "last_arm": self.last_report}

    def _with_run(self, action: Callable[[RunController], str]) -> dict[str, Any]:
        if not self.active:
            return {"ok": False, "message": "no run is active"}
        return {"ok": True, "message": action(self.controller)}

    # Facts for the gate

    def _operator(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "hand_on_estop": body.get("hand_on_estop") is True,
            "boxes": body.get("boxes"),
            "speed_percent": body.get("speed_percent", self.config.value("dobot", "speed_percent")),
            "accept_open_box": body.get("accept_open_box") is True,
        }

    def _facts(self, operator: dict[str, Any]) -> tuple[GateFacts, Any, dict[str, Any] | None]:
        choton, settings, choton_error = None, None, ""
        try:
            choton = self.load_choton(self.config.path_value("choton", "folder"))
            settings = copy.deepcopy(choton.vision_lib.load_settings())
        except ChotonCodeUnavailable as error:
            choton_error = str(error)
        calibration, calibration_error = None, ""
        try:
            calibration = read_json(self.config.path_value("calibration", "file"))
        except (OSError, ValueError, TypeError) as error:
            calibration_error = str(error)
        robot_status = self.poller.check_now("dobot_dashboard").to_dict() if "dobot_dashboard" in self.poller.checks else None
        facts = GateFacts(
            config=self.config, choton_robot=(settings or {}).get("robot"), choton_error=choton_error,
            box_contents=(settings or {}).get("box_contents"), calibration=calibration,
            calibration_error=calibration_error, vision=self._vision_facts(choton, settings),
            robot_status=robot_status, operator=operator,
        )
        return facts, choton, settings

    def _vision_facts(self, choton: Any, settings: dict[str, Any] | None) -> dict[str, Any]:
        entry = self.config.entry("camera", "index")
        if entry["value"] is None or entry["status"] in NOT_FOR_A_RUN or settings is None:
            model = self.poller.check_now("vision_model").to_dict() if "vision_model" in self.poller.checks else {}
            reason = "camera.index not confirmed" if settings is not None else "Choton's settings not readable"
            return {"model_loaded": False, "model_error": model.get("detail", reason), "frame_age_s": None, "camera_error": reason}
        status = self.vision_service.ensure_started(choton, settings)
        self._wait_for_first_frame()
        return self.vision_service.status() if status.get("running") else status

    def _wait_for_first_frame(self) -> None:
        deadline_s = time.monotonic() + float(self.config.value("control", "camera_frame_max_age_s"))
        while self.vision is not None and self.vision.status()["frame_age_s"] is None and time.monotonic() < deadline_s:
            time.sleep(0.05)

    def stop(self) -> None:
        if self.active:
            self.controller.act(Action.ABORT)
            self.controller.wait()
        self.vision_service.stop()


def _jpeg_encoder(choton: Any) -> Callable[[Any], bytes | None]:
    """A camera frame -> JPEG bytes with Choton's cv2 (quality 85: about 120 kB per picture)."""
    def encode(frame: Any) -> bytes | None:
        cv2 = choton.vision_lib.cv2  # looked up per picture: without it the save fails and the run goes on
        ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return data.tobytes() if ok else None

    return encode


def _idle_reply(what: str, result: dict[str, Any]) -> dict[str, Any]:
    done = "; ".join(result["sent"]) or "nothing switched"
    problems = f" Not done: {'; '.join(result['problems'])}." if result["problems"] else ""
    return {**result, "message": f"{what}: {done}.{problems} Note: {result['note']}."}
