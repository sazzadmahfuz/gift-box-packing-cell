"""Rules for the browser files in cell_live/web: local only, honest words, small files, safe controls."""

import re
from pathlib import Path

import pytest

from cell_live.api_routes import RUN_ACTIONS

WEB = Path(__file__).resolve().parents[1] / "web"
SERVED = sorted(path for path in WEB.rglob("*") if path.suffix in (".html", ".js", ".css"))
ALL_TEXT = {path.relative_to(WEB).as_posix(): path.read_text(encoding="utf-8") for path in SERVED}


def test_the_console_files_exist():
    names = set(ALL_TEXT)
    for screen in ("overview", "run", "vision", "logs", "settings", "help", "show", "drawer", "trace"):
        assert f"js/{screen}.js" in names
    assert {"index.html", "css/theme.css", "css/layout.css", "js/api.js", "js/app.js", "js/ui.js"} <= names


@pytest.mark.parametrize("name", sorted(ALL_TEXT))
def test_each_file_is_under_300_lines(name):
    assert ALL_TEXT[name].count("\n") < 300


@pytest.mark.parametrize("name", sorted(ALL_TEXT))
def test_nothing_is_loaded_from_the_internet(name):
    for url in re.findall(r"https?://[^\s\"'`)<]+", ALL_TEXT[name]):
        assert url.startswith("http://127.0.0.1:"), f"{name}: {url} (no CDN, web font or external call)"
    assert not re.search(r"@import\s+url|fonts\.googleapis|cdn\.", ALL_TEXT[name])


@pytest.mark.parametrize("name", sorted(ALL_TEXT))
def test_no_simulation_or_pretend_wording(name):
    found = re.findall(r"simulat\w*|demo mode|\bmock\w*|\bfake\w*", ALL_TEXT[name], flags=re.IGNORECASE)
    assert not found, f"{name} says {found}: the console shows the real cell only"


def test_theme_uses_root_variables_and_has_a_light_theme():
    theme = ALL_TEXT["css/theme.css"]
    root = re.search(r":root\s*\{([^}]*)\}", theme)
    assert root and root.group(1).count("--") >= 10
    assert '[data-theme="light"]' in theme
    for state in ("OK", "WARN", "FAIL", "UNKNOWN", "NOT_OBSERVABLE"):
        assert f".st-{state}" in theme
    colours_outside_variables = [line for line in theme.splitlines()
                                 if re.search(r"#[0-9a-fA-F]{3,8}\b", line) and "--" not in line]
    assert not colours_outside_variables, colours_outside_variables


def test_every_status_has_a_shape_and_a_word():
    ui = ALL_TEXT["js/ui.js"]
    for state, shape in (("OK", "●"), ("WARN", "▲"), ("FAIL", "✖"), ("UNKNOWN", "?"), ("NOT_OBSERVABLE", "⊘")):
        assert re.search(rf"{state}\s*:\s*\{{[^}}]*{re.escape(shape)}", ui), state


def test_hardware_badge_and_software_stop_warning_are_always_on_the_page():
    page = ALL_TEXT["index.html"]
    assert "HARDWARE" in page and 'id="stop"' in page and "SOFTWARE STOP" in page
    assert "physical emergency stop first" in page and "PHYSICAL EMERGENCY STOP comes first" in page
    stop_tag = re.search(r"<button id=\"stop\"[^>]*>", page, flags=re.DOTALL).group(0)
    assert "data-operator" not in stop_tag  # Viewer mode hides data-operator parts; the stop stays
    assert "body.viewer [data-operator]" in ALL_TEXT["css/layout.css"]


def test_viewer_mode_locks_run_and_settings():
    app = ALL_TEXT["js/app.js"]
    assert re.search(r"OPERATOR_SCREENS\s*=\s*\[\"run\", \"settings\"\]", app)
    assert 'data-route="run" data-operator' in ALL_TEXT["index.html"]
    assert 'data-route="settings" data-operator' in ALL_TEXT["index.html"]


def test_only_api_js_talks_to_the_backend():
    for name, text in ALL_TEXT.items():
        if name != "js/api.js":
            assert not re.search(r"\bfetch\(|new EventSource|WebSocket|XMLHttpRequest", text), name


def test_every_backend_path_the_console_uses_exists():
    known = {"/api/components", "/api/run", "/api/vision", "/api/vision/start", "/api/logs", "/api/config",
             "/api/ports", "/api/stream", "/api/camera.mjpg"}
    used = set()
    for text in ALL_TEXT.values():
        used.update(re.findall(r"[\"`](/api/[A-Za-z0-9_./-]*)", text))
    for path in used:
        if path.startswith("/api/run/"):
            assert path.removeprefix("/api/run/") in RUN_ACTIONS or path == "/api/run/", path
        elif path.startswith(("/api/components/", "/api/logs/")):
            continue  # an id or a file name follows
        else:
            assert path in known, path
    actions = set(re.findall(r"\bact\(\"([a-z-]+)\"", ALL_TEXT["js/run.js"]))  # the run control buttons
    assert actions == {"pause", "resume", "skip", "abort", "clear-alarm", "belt-stop"} and actions <= set(RUN_ACTIONS), actions


def test_the_page_notices_a_silent_backend_after_two_missed_heartbeats():
    from cell_live.server import HEARTBEAT_S

    limit_ms = int(re.search(r"SILENCE_LIMIT_MS\s*=\s*(\d+)", ALL_TEXT["js/api.js"]).group(1))
    assert 2 * HEARTBEAT_S * 1000 < limit_ms <= 3 * HEARTBEAT_S * 1000


def test_the_console_sends_no_robot_command_itself():
    command_words = r"\b(MovL|MovJ|EnableRobot|DO\(|DOExecute|SpeedFactor|EmergencyStop\()"
    for name, text in ALL_TEXT.items():
        assert not re.search(command_words, text), f"{name} contains a robot command"
