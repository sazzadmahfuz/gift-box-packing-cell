import argparse

from cell_sim.__main__ import COMMANDS, build_parser
from cell_sim.modes import MODES
from cell_ui.discover import (
    KIND_CHOICE,
    KIND_FLAG,
    KIND_OPTIONAL_VALUE,
    KIND_VALUE,
    build_argv,
    check_argv,
    commands,
    describe_exit,
    exit_code_names,
    option_specs,
)


def _specs(parser=None):
    return {spec.dest: spec for spec in option_specs(parser or build_parser())}


def test_every_cli_command_is_found():
    assert set(commands()) == set(COMMANDS) and "connect-check" in commands()


def test_run_options_come_from_the_parser():
    specs = _specs()
    assert specs["mode"].kind == KIND_CHOICE and specs["mode"].choices == MODES
    assert specs["teacher_approved"].kind == KIND_FLAG
    assert specs["realtime"].kind == KIND_OPTIONAL_VALUE and specs["realtime"].const == "1.0"
    assert specs["cycles"].kind == KIND_VALUE and specs["cycles"].default == "1"
    assert "help" not in specs


def test_a_new_cli_option_shows_up_without_ui_changes():
    parser = build_parser()
    parser.add_argument("--belt-speed-mm-s", type=float, default=50.0, help="new option")
    parser.add_argument("--dry-belts", action="store_true")
    specs = _specs(parser)
    assert specs["belt_speed_mm_s"].kind == KIND_VALUE and specs["belt_speed_mm_s"].default == "50.0"
    assert specs["dry_belts"].kind == KIND_FLAG


def test_argv_leaves_out_defaults_and_keeps_changes():
    specs = option_specs(build_parser())
    values = {"mode": "dobot-dry", "cycles": "3", "realtime": (False, "1.0"), "teacher_approved": False}
    assert build_argv("run", specs, values) == ["--cycles", "3", "--mode", "dobot-dry"]  # parser order
    assert build_argv("run", specs, {"mode": "sim", "realtime": (True, "10")}) == ["--realtime", "10"]
    assert build_argv("run", specs, {"realtime": (True, "1.0")}) == ["--realtime"]


def test_connect_check_argv_starts_with_the_command_word():
    specs = option_specs(COMMANDS["connect-check"]())
    argv = build_argv("connect-check", specs, {"ip": "127.0.0.1", "timeout_s": ""})
    assert argv == ["connect-check", "--ip", "127.0.0.1"]
    assert check_argv(COMMANDS["connect-check"](), argv, "connect-check") == ""


def test_bad_values_are_reported_before_running():
    assert "invalid int value" in check_argv(build_parser(), ["--cycles", "two"])
    assert check_argv(build_parser(), ["--cycles", "2"]) == ""


def test_exit_codes_come_from_the_cli():
    names = exit_code_names()
    assert names[0] == "ok" and names[3] == "connection error" and names[5] == "safety refused"
    assert describe_exit(2, names) == "exit 2: fault"
    assert describe_exit(None, names) == "stopped"
    assert describe_exit(42, names) == "exit 42: unknown exit code"


def test_positional_and_plain_parsers_work():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    (spec,) = option_specs(parser)
    assert spec.flag == "" and build_argv("run", [spec], {"target": "home"}) == ["home"]
