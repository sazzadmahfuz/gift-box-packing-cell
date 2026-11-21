"""Static rules for real control, checked in the source."""

import ast
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONTROL_DIR = PACKAGE_DIR / "control"


def _sources(folder=PACKAGE_DIR):
    return [path for path in folder.rglob("*.py") if "tests" not in path.parts]


def _calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(tree) if isinstance(node, ast.Call)]


def test_no_input_and_no_windows_anywhere_in_cell_live():
    for path in _sources():
        found = set(_calls(path)) & {"input", "imshow", "waitKey", "namedWindow", "show"}
        assert not found, f"{path.name} calls {found}"


def test_chotons_robot_is_created_only_in_robot_session():
    for path in _sources():
        if "Robot" in _calls(path):
            assert path.name == "robot_session.py", f"{path.name} creates a robot_lib.Robot"


def test_the_gate_is_standard_library_only_and_has_no_network_code():
    gate = CONTROL_DIR / "gate.py"
    tree = ast.parse(gate.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0}
    assert imported <= set(sys.stdlib_module_names) and not imported & {"socket", "http", "urllib", "ssl"}


def test_software_estop_is_named_as_software_everywhere():
    text = "".join(path.read_text(encoding="utf-8") for path in _sources(CONTROL_DIR))
    assert "software e-stop (not the physical emergency stop)" in text
    assert "def software_estop" in text and "def emergency_stop" not in text


def test_every_cell_live_file_is_under_300_lines():
    for path in PACKAGE_DIR.rglob("*.py"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 300, path.name
