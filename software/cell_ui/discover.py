"""Discover commands, options and exit codes from the cell_sim CLI itself (no tkinter here).

Nothing about the CLI is hard-coded: a new option, mode or exit code shows up in the UI.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
RUN_COMMAND = "run"  # the command without a command word: python -m cell_sim --mode ...

KIND_CHOICE, KIND_FLAG, KIND_VALUE, KIND_OPTIONAL_VALUE = "choice", "flag", "value", "optional_value"


@dataclass(frozen=True)
class OptionSpec:
    dest: str
    flag: str  # e.g. "--cycles"; "" for a positional argument
    kind: str
    default: str  # shown in the form; "" when there is none
    help: str
    choices: tuple[str, ...] = field(default_factory=tuple)
    const: str = ""  # nargs="?" options: the value used when the flag is given alone


def cli_module() -> ModuleType:
    from cell_sim import __main__ as cli

    return cli


def commands(cli: ModuleType | None = None) -> dict[str, Callable[[], argparse.ArgumentParser]]:
    return dict((cli or cli_module()).COMMANDS)


def option_specs(parser: argparse.ArgumentParser) -> list[OptionSpec]:
    specs = []
    for action in parser._actions:  # argparse has no public list of actions
        if isinstance(action, argparse._HelpAction):
            continue
        flag = max(action.option_strings, key=len) if action.option_strings else ""
        default = "" if action.default in (None, argparse.SUPPRESS) else str(action.default)
        help_text = (action.help or "").replace("%(default)s", default)
        if isinstance(action, argparse._StoreTrueAction):
            kind = KIND_FLAG
        elif action.choices:
            kind = KIND_CHOICE
        elif action.nargs == "?":
            kind = KIND_OPTIONAL_VALUE
        else:
            kind = KIND_VALUE
        choices = tuple(str(choice) for choice in action.choices or ())
        const = "" if action.const is None else str(action.const)
        specs.append(OptionSpec(action.dest, flag, kind, default, help_text, choices, const))
    return specs


def build_argv(command: str, specs: list[OptionSpec], values: dict[str, Any]) -> list[str]:
    """Form values -> CLI arguments. Values equal to the default are left out.

    values: flag -> bool; choice/value -> str; optional_value -> (enabled: bool, text: str).
    """
    argv = [] if command == RUN_COMMAND else [command]
    for spec in specs:
        value = values.get(spec.dest)
        if spec.kind == KIND_FLAG:
            if value:
                argv.append(spec.flag)
        elif spec.kind == KIND_OPTIONAL_VALUE:
            enabled, text = value if value else (False, "")
            if enabled:
                argv.append(spec.flag)
                if str(text).strip() and str(text).strip() != spec.const:
                    argv.append(str(text).strip())
        else:
            text = "" if value is None else str(value).strip()
            if text and text != spec.default:
                argv.extend([spec.flag, text] if spec.flag else [text])
    return argv


def check_argv(parser: argparse.ArgumentParser, argv: list[str], command: str = RUN_COMMAND) -> str:
    """Return argparse's error message for these arguments, or "" if they parse."""
    own_args = argv[1:] if command != RUN_COMMAND else argv
    errors = io.StringIO()
    try:
        with contextlib.redirect_stderr(errors):
            parser.parse_args(own_args)
    except SystemExit:
        lines = [line for line in errors.getvalue().splitlines() if line.strip()]
        return lines[-1] if lines else "invalid arguments"
    return ""


def full_command(argv: list[str]) -> list[str]:
    return [sys.executable, "-m", "cell_sim", *argv]


def exit_code_names(cli: ModuleType | None = None) -> dict[int, str]:
    """EXIT_CONNECTION_ERROR = 3 -> {3: "connection error"}."""
    module = cli or cli_module()
    names: dict[int, str] = {}
    for name in dir(module):
        value = getattr(module, name)
        if name.startswith("EXIT_") and isinstance(value, int) and not isinstance(value, bool):
            label = name[len("EXIT_"):].replace("_", " ").lower()
            names[value] = f"{names[value]} / {label}" if value in names else label
    return names


def describe_exit(code: int | None, names: dict[int, str]) -> str:
    if code is None:
        return "stopped"
    return f"exit {code}: {names.get(code, 'unknown exit code')}"
