"""Status timing, config rules, the poller, and the HTTP/SSE API (on a free local port)."""

import copy
import json
import threading
import urllib.request

import pytest

from cell_live.checks import build_checks
from cell_live.dobot_link import DobotLink
from cell_live.live_config import LiveConfig, LiveConfigError, load_live_config
from cell_live.poller import Poller
from cell_live.server import make_server
from cell_live.status import FAIL, OK, CheckResult, ComponentStatus
from cell_live.tests.baseline import baseline_config
from cell_live.tests.fakes import FakeRobot


class ScriptedCheck:
    def __init__(self, id, results):
        self.id, self.name, self.interval_s = id, id, 60.0
        self.results = list(results)

    def run(self):
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def test_fail_keeps_last_ok_and_clears_latency():
    status = ComponentStatus("x", "x")
    status.apply(CheckResult(OK, "fine", 3.0), checked_at=100.0)
    status.apply(CheckResult(FAIL, "cable out", 2.0), checked_at=105.0)
    assert (status.state, status.last_ok_at, status.checked_at, status.latency_ms) == (FAIL, 100.0, 105.0, None)
    with pytest.raises(ValueError):
        CheckResult("GREAT", "no such state")


def test_every_config_entry_has_a_source_and_status_and_nulls_are_confirm_or_not_used():
    config = load_live_config()
    for section, entries in config.raw.items():
        if section.startswith("_"):
            continue
        for key, entry in entries.items():
            assert entry["source"], f"{section}.{key}"
            if entry["value"] is None:  # not known yet (CONFIRM) or deliberately not used (SETTING)
                assert entry["status"] in ("CONFIRM", "SETTING"), f"{section}.{key}"
    assert {"dobot.teacher_approval", "dobot.belt_on_value", "dobot.belt_enable_on_value"} <= set(baseline_config().unknowns())
    assert "arduino.serial_port" not in config.unknowns()  # not used: the UNO is not connected to this PC (17 Nov)
    raw = copy.deepcopy(config.raw)
    raw["dobot"]["teacher_approval"].update(value=None, status="VERIFIED")  # null may not claim to be verified
    with pytest.raises(LiveConfigError):
        LiveConfig(raw)


def test_all_components_are_built_and_a_crashing_check_becomes_fail():
    config = load_live_config()
    link = DobotLink("192.168.1.6", 29999, 30004, 0.5, connect=FakeRobot(failure="timeout").connect)
    ids = [check.id for check in build_checks(config, link)]
    assert ids == ["dobot_dashboard", "dobot_feedback", "object_belt_do3", "object_belt_dir", "object_belt_power", "camera",
                   "vision_model", "calibration", "robodk", "box_belt_nano"]  # no box_belt_do: an operator takes the box

    class Broken:
        id = name = "broken"
        interval_s = 60.0

        def run(self):
            raise KeyError("oops")

    status = Poller([Broken()]).check_now("broken")
    assert status.state == FAIL and "check crashed" in status.detail


@pytest.fixture
def server():
    poller = Poller([ScriptedCheck("robot", [CheckResult(OK, "fine", 1.5)])])
    http = make_server(poller, "127.0.0.1", 0, ["dobot.speed_percent"])
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield poller, f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def test_api_lists_components_and_checks_on_demand(server):
    poller, base = server
    listing = _get(f"{base}/api/components")
    assert listing["components"][0]["state"] == "UNKNOWN" and listing["unconfirmed_config"] == ["dobot.speed_percent"]
    request = urllib.request.Request(f"{base}/api/components/robot/check", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        checked = json.loads(response.read())
    assert checked["state"] == "OK" and checked["latency_ms"] == 1.5 and checked["last_ok_at"] is not None
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(urllib.request.Request(f"{base}/api/components/nope/check", method="POST"), timeout=5)


def test_stream_sends_the_current_status_then_every_change(server):
    poller, base = server
    with urllib.request.urlopen(f"{base}/api/stream", timeout=5) as stream:
        assert stream.headers["Content-Type"] == "text/event-stream"
        first = [stream.readline() for _ in range(3)]
        assert first[0] == b"event: status\n" and json.loads(first[1][len(b"data: "):])["id"] == "robot"
        poller.check_now("robot")
        update = [stream.readline() for _ in range(3)]
        assert json.loads(update[1][len(b"data: "):])["state"] == "OK"
