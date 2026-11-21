import pytest

from cell_sim.modes import MODES
from cell_ui.readiness import FAIL, INFO, OK, WARN, mode_checks, overall_level


def _checks(mode, port_open=False):
    return mode_checks(mode, port_open=lambda port, host: port_open)


def test_sim_is_ready_but_warns_about_assumed_values():
    checks = _checks("sim")
    assert overall_level(checks) == WARN and "ASSUMED" in checks[0].messages[0]


def test_robodk_depends_on_the_api_port():
    assert overall_level(_checks("robodk", port_open=False)) == FAIL
    assert [c.level for c in _checks("robodk", port_open=True)][-1] == OK


def test_dobot_dry_is_possible_with_assumed_values():
    (_, dry) = _checks("dobot-dry")
    assert dry.level == WARN and "ASSUMED" in dry.messages[0]


def test_dobot_real_lists_the_gate_problems_offline():
    real = _checks("dobot-real")[-1]
    assert real.level == FAIL and any("teacher_approval" in message for message in real.messages)


def test_every_cli_mode_gets_checks_and_unknown_modes_do_not_fail():
    for mode in MODES:
        assert _checks(mode)
    assert _checks("future-mode")[-1].level == INFO


def test_window_builds_and_every_tab_opens():
    tk = pytest.importorskip("tkinter")
    from cell_ui.app import OperatorApp

    try:
        app = OperatorApp()
    except tk.TclError as error:
        pytest.skip(f"no display: {error}")
    try:
        tabs = [app.notebook.tab(tab_id, "text") for tab_id in app.notebook.tabs()]
        assert tabs[:4] == ["Run", "Readiness", "Config", "Results"] and "Robot check" in tabs
        for tab_id in app.notebook.tabs():
            app.notebook.select(tab_id)
            app.update()
        run_panel = app.run_panels[0]
        run_panel.form.set_value("mode", "dobot-dry")
        run_panel.form.set_value("cycles", "2")
        run_panel._refresh()
        assert run_panel.argv() == ["--cycles", "2", "--mode", "dobot-dry"]
        assert "cell_sim --cycles 2 --mode dobot-dry" in run_panel.command_text.get()
        assert str(run_panel.form.widgets["teacher_approved"][0].cget("state")) == "disabled"
        run_panel.form.set_value("mode", "dobot-real")
        run_panel._refresh()
        assert str(run_panel.form.widgets["teacher_approved"][0].cget("state")) == "normal"
    finally:
        app.destroy()
