"""Logs and Settings endpoints: run-log summaries, safe names, validated config saves."""

import json
import os
import shutil

import pytest

from cell_live.app import LiveApp
from cell_live.config_store import LAB_FIELDS, ConfigStore, check_type, format_config
from cell_live.live_config import DEFAULT_LIVE_CONFIG_PATH, load_live_config
from cell_live.logs_api import list_logs
from cell_live.tests.web_fakes import Served, context

HEADER = "time_s,box,state,event,command,reply,detections,fault"
RUN_A = [
    "# HARDWARE RUN; speed 40 %; boxes requested 3",
    HEADER,
    "0.000,1,WAIT_BOX,enter WAIT_BOX,,,,",
    "60.500,1,RELEASE_BOX,box 1: done; placed card candy candy; lid placed,,,,",
    "61.000,2,WAIT_BOX,enter WAIT_BOX,,,,",
    "70.000,2,PAUSED,PAUSED (no box) in WAIT_BOX; outputs: DO3 off,,,,",
    "75.000,2,WAIT_BOX,enter WAIT_BOX,,,,",  # after Resume: the box keeps its first start time
    "120.000,2,RELEASE_BOX,box 2: done; placed card candy candy; lid placed,,,,",
    "121.000,3,WAIT_BOX,enter WAIT_BOX,,,,",
    "130.000,3,FAULT,FAULT: vacuum lost; outputs: DO1 off,,,,vacuum lost",
    "131.000,3,FAULT,box 3: skipped; placed card; lid none,,,,",
]


@pytest.fixture
def served():
    servers = []

    def start(ctx):
        servers.append(Served(ctx))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


def write_log(folder, name, lines, modified_s):
    path = folder / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (modified_s, modified_s))
    return path


def test_logs_list_newest_first_and_skip_other_files(tmp_path):
    write_log(tmp_path, "20261117_101500.csv", RUN_A, 1_000)
    write_log(tmp_path, "20261117_113000.csv", RUN_A[:4], 2_000)
    (tmp_path / "notes.csv").write_text("x\n", encoding="utf-8")
    logs = list_logs(tmp_path)
    assert [log["name"] for log in logs] == ["20261117_113000.csv", "20261117_101500.csv"]
    assert logs[0]["banner"] == "HARDWARE RUN; speed 40 %; boxes requested 3"
    assert list_logs(tmp_path / "missing") == []


def test_one_log_gives_box_times_failures_and_the_mean_of_done_boxes(served, tmp_path):
    write_log(tmp_path, "20261117_101500.csv", RUN_A, 1_000)
    server = served(context(logs_dir=tmp_path))
    code, log = server.get_json("/api/logs/20261117_101500.csv")
    assert code == 200 and len(log["rows"]) == 9 and log["columns"][0] == "time_s"
    summary = log["summary"]
    assert [(box["box"], box["result"], box["duration_s"]) for box in summary["boxes"]] == [
        (1, "done", 60.5), (2, "done", 59.0), (3, "skipped", 10.0)]
    assert summary["boxes_done"] == 2 and summary["mean_box_s"] == 59.75  # the skipped box is not in the mean
    assert [failure["event"][:6] for failure in summary["failures"]] == ["PAUSED", "FAULT:"]
    assert summary["failures"][1]["fault"] == "vacuum lost" and summary["end_s"] == 131.0
    code, listing = server.get_json("/api/logs")
    assert code == 200 and listing["logs"][0]["name"] == "20261117_101500.csv"


@pytest.mark.parametrize("name", ["..%2Flive_config.json", "notes.csv", "20261117_101500.txt", "20261117_999999.csv"])
def test_bad_or_missing_log_names_are_refused(served, tmp_path, name):
    (tmp_path / "notes.csv").write_text("x\n", encoding="utf-8")
    server = served(context(logs_dir=tmp_path))
    code, reply = server.get_json(f"/api/logs/{name}")
    assert code == 404 and "error" in reply


def copied_config(tmp_path):
    path = tmp_path / "live_config.json"
    shutil.copy2(DEFAULT_LIVE_CONFIG_PATH, path)
    return path


def store_for(path):
    return ConfigStore(lambda: load_live_config(path))


def test_config_lists_every_entry_and_marks_the_lab_fields(tmp_path):
    described = store_for(copied_config(tmp_path)).describe()
    editable = {f"{entry['section']}.{entry['key']}" for entry in described["entries"] if entry["editable"]}
    assert editable == set(LAB_FIELDS)
    ip = next(entry for entry in described["entries"] if entry["key"] == "ip")
    assert ip["editable"] is False and ip["status"] == "VERIFIED"
    restart = next(entry for entry in described["entries"] if entry["key"] == "box_restart")
    assert restart["type"] == "choice" and "nano_auto" in restart["choices"]


@pytest.mark.parametrize("body, problem", [
    ({"section": "dobot", "key": "ip", "value": "10.0.0.1", "status": "VERIFIED", "source": "x"}, "not a lab field"),
    ({"section": "camera", "key": "index", "value": "one", "status": "VERIFIED", "source": "lab"}, "whole number"),
    ({"section": "camera", "key": "index", "value": 12, "status": "VERIFIED", "source": "lab"}, "from 0 to 9"),
    ({"section": "camera", "key": "index", "value": 1, "status": "CONFIRM", "source": "lab"}, "other than CONFIRM"),
    ({"section": "camera", "key": "index", "value": 1, "status": "GUESS", "source": "lab"}, "status must be one of"),
    ({"section": "camera", "key": "index", "value": 1, "status": "VERIFIED", "source": ""}, "new source"),
    ({"section": "belts", "key": "box_restart", "value": "magic", "status": "VERIFIED", "source": "lab"}, "must be one of"),
    ({"section": "dobot", "key": "teacher_approval", "value": "20", "status": "VERIFIED", "source": "lab"}, "teacher's name and the date"),
])
def test_config_saves_without_type_status_or_source_are_refused(tmp_path, body, problem):
    path = copied_config(tmp_path)
    before = path.read_text(encoding="utf-8")
    result = store_for(path).save(body)
    assert result["saved"] is False and any(problem in text for text in result["problems"]), result
    assert path.read_text(encoding="utf-8") == before and not (tmp_path / "live_config.json.bak").exists()


def test_a_good_save_keeps_a_backup_and_the_file_still_loads(tmp_path):
    path = copied_config(tmp_path)
    before = path.read_text(encoding="utf-8")
    result = store_for(path).save({"section": "camera", "key": "index", "value": 1, "status": "VERIFIED",
                                   "source": "lab 17 Nov, find-camera on the demo laptop"})
    assert result == {"saved": True, "entry": "camera.index", "backup": "live_config.json.bak", "problems": []}
    assert (tmp_path / "live_config.json.bak").read_text(encoding="utf-8") == before
    entry = load_live_config(path).raw["camera"]["index"]
    assert entry["value"] == 1 and entry["status"] == "VERIFIED" and "find-camera" in entry["source"]
    assert "camera.index" not in load_live_config(path).unknowns()
    assert json.loads(path.read_text(encoding="utf-8"))["dobot"]["ip"]["value"] == "192.168.1.6"  # others untouched


def test_a_save_keeps_changes_made_to_the_file_after_the_backend_loaded_it(tmp_path):
    path = copied_config(tmp_path)
    store = ConfigStore(lambda loaded=load_live_config(path): loaded)  # the backend's copy, loaded before the edit below
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["control"]["box_wait_timeout_s"].update(value=40.0, status="VERIFIED", source="lab test T2, 17 Nov")
    path.write_text(format_config(raw), encoding="utf-8")
    assert store.save({"section": "camera", "key": "index", "value": 0, "status": "VERIFIED", "source": "find-camera"})["saved"]
    saved = load_live_config(path)
    assert saved.value("camera", "index") == 0 and saved.value("control", "box_wait_timeout_s") == 40.0


def test_type_rules():
    assert check_type(("int", 1, 100), True) == "must be a whole number"  # a bool is not a number
    assert check_type(("number", 1, 3600), 7.5) == "" and check_type(("int", 1, 100), 7.5) != ""
    assert check_type(("bool",), "yes") and check_type(("text",), "  ") and check_type(("text",), None) == ""


def test_save_over_http_reloads_the_backend(served, tmp_path):
    app = LiveApp(config_path=copied_config(tmp_path), logs_dir=tmp_path / "runs")  # built, not started: nothing connects
    old_link = app.link
    server = served(app)
    code, result = server.post("/api/config", {"section": "arduino", "key": "baud", "value": 115200,
                                               "status": "VERIFIED", "source": "Nano sketch shown in the lab"})
    assert code == 200 and result["saved"] and result["reloaded"].startswith("reloaded")
    assert app.link is not old_link and app.config.raw["arduino"]["baud"]["value"] == 115200
    code, described = server.get_json("/api/config")
    assert code == 200 and "arduino.baud" not in described["unconfirmed"]
    code, refused = server.post("/api/config", {"section": "arduino", "key": "baud", "value": "fast",
                                                "status": "VERIFIED", "source": "x"})
    assert code == 400 and refused["saved"] is False


def test_no_settings_change_while_a_run_is_active(served, tmp_path):
    class ActiveRun:
        active = True

    class Store:
        def save(self, body):
            raise AssertionError("must not be called during a run")

    server = served(context(run=ActiveRun(), config_store=Store()))
    code, reply = server.post("/api/config", {"section": "camera", "key": "index", "value": 1})
    assert code == 409 and "run is active" in reply["problems"][0]


def test_reload_is_refused_while_a_run_is_active(tmp_path):
    app = LiveApp(config_path=copied_config(tmp_path), logs_dir=tmp_path / "runs")
    app.run.controller = type("RunningController", (), {"finished": False})()  # as if a run had started
    old_link = app.link
    assert app.reload() == "not reloaded: a run is active" and app.link is old_link
