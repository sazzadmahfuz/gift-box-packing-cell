"""Command line:
python -m cell_sim --cycles 5 [--mode sim|robodk|dobot-dry|dobot-real]
python -m cell_sim connect-check [--ip IP]   (read-only Dobot connection check)
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .controller import State
from .hardware_config import DEFAULT_HARDWARE_PATH, HardwareConfigError, dobot_settings, load_hardware_raw
from .modes import (
    MODES,
    ModeSetup,
    RealMotionNotImplemented,
    setup_dobot_dry,
    setup_dobot_real,
    setup_robodk,
    setup_sim,
)
from .recorder import summary_line, write_csv
from .safety_gate import SafetyGateRefused
from .simulation import SimResult, Simulation

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "testing" / "sim_runs"

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_FAULT = 2
EXIT_CONNECTION_ERROR = 3
EXIT_ROBOT_REPORTS_ERROR = 4  # connect-check only
EXIT_SAFETY_REFUSED = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cell_sim",
        description="Packing cell simulation (SIMULATION or ROBODK SIMULATION, assumed parameters).",
    )
    parser.add_argument("--cycles", type=int, default=1, help="number of boxes to finish (default 1)")
    parser.add_argument("--mode", choices=MODES, default="sim", help="sim (default), robodk, dobot-dry, dobot-real")
    parser.add_argument(
        "--teacher-approved",
        action="store_true",
        help="dobot-real only: the teacher approved this real-robot run (also needs dobot.teacher_approval)",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to config.json")
    parser.add_argument("--hardware", type=Path, default=DEFAULT_HARDWARE_PATH, help="path to hardware.json")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="folder for the CSV log")
    parser.add_argument(
        "--realtime",
        type=float,
        nargs="?",
        const=1.0,
        default=None,
        metavar="FACTOR",
        help="sim mode only: sleep between events; FACTOR 1.0 = real speed, 10 = ten times faster",
    )
    return parser


def exit_code_for(result: SimResult) -> int:
    return EXIT_FAULT if result.final_state is State.FAULT else EXIT_OK


def _setup_mode(args: argparse.Namespace) -> ModeSetup:
    if args.mode == "robodk":
        return setup_robodk(args.hardware)
    if args.mode == "dobot-dry":
        return setup_dobot_dry(args.hardware)
    if args.mode == "dobot-real":
        return setup_dobot_real(args.hardware, args.teacher_approved)
    return setup_sim()


def build_connect_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cell_sim connect-check",
        description="Read-only Dobot check: error ID, robot mode and pose. Never enables or moves the robot.",
    )
    parser.add_argument("--hardware", type=Path, default=DEFAULT_HARDWARE_PATH, help="path to hardware.json")
    parser.add_argument("--ip", help="robot IP (default: hardware.json dobot.robot_ip)")
    parser.add_argument("--timeout-s", type=float, help="socket timeout in s (default: dobot.connect_timeout_s)")
    return parser


def connect_check_main(argv: list[str]) -> int:
    args = build_connect_check_parser().parse_args(argv)
    from .drivers.dobot_connect_check import connect_check
    from .drivers.dobot_tcp_robot import DobotUnavailable

    try:
        settings = dobot_settings(load_hardware_raw(args.hardware), args.hardware)
        if args.ip:
            settings = dataclasses.replace(settings, robot_ip=args.ip)
        if args.timeout_s:
            settings = dataclasses.replace(settings, connect_timeout_s=args.timeout_s)
        return connect_check(settings)
    except HardwareConfigError as error:
        print(f"hardware.json error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except DobotUnavailable as error:
        print(f"[CONNECT-CHECK] cannot start: {error}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["connect-check"]:
        return connect_check_main(argv[1:])
    args = build_parser().parse_args(argv)
    if args.teacher_approved and args.mode != "dobot-real":
        print("--teacher-approved works with --mode dobot-real only", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    if args.cycles < 1:
        print("--cycles must be at least 1", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    if args.realtime is not None and (args.realtime <= 0 or args.mode != "sim"):
        print("--realtime FACTOR must be positive and works in sim mode only", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    from .drivers.dobot_tcp_robot import DobotUnavailable
    from .drivers.robodk_robot import RoboDKUnavailable

    try:
        mode = _setup_mode(args)
    except HardwareConfigError as error:
        print(f"hardware.json error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except RoboDKUnavailable as error:
        print(f"[ROBODK SIMULATION] cannot start: {error}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR
    except DobotUnavailable as error:
        print(f"[DOBOT] cannot start: {error}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR
    except (SafetyGateRefused, RealMotionNotImplemented) as error:
        print(f"[DOBOT REAL] {error}", file=sys.stderr)
        return EXIT_SAFETY_REFUSED

    label = mode.label
    print(f"[{label}] assumed parameters, not hardware results")
    try:
        result = Simulation(
            config,
            args.cycles,
            realtime_factor=args.realtime,
            on_cycle=lambda record: print(summary_line(record, args.cycles, label), flush=True),
            cell_factory=mode.cell_factory,
        ).run()
    finally:
        mode.close()
    if result.fault_reason is not None:
        print(f"[{label}] {result.fault_reason}")
    csv_path = write_csv(result, args.out_dir, banner=mode.banner)
    print(f"[{label}] log written to {csv_path}")
    return exit_code_for(result)


# Command name -> parser builder. "run" has no command word; others are the first argument.
# The operator UI (software/cell_ui) builds its forms from these parsers.
COMMANDS = {"run": build_parser, "connect-check": build_connect_check_parser}


if __name__ == "__main__":
    sys.exit(main())
