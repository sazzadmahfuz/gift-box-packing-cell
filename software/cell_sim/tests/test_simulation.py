import ast
import csv
import sys
from pathlib import Path

import pytest

from cell_sim import SIMULATION_BANNER
from cell_sim.__main__ import EXIT_FAULT, exit_code_for, main
from cell_sim.config import config_from_dict, load_config, load_raw_config
from cell_sim.controller import State
from cell_sim.recorder import write_csv
from cell_sim.simulation import run_simulation

PACKAGE_DIR = Path(__file__).resolve().parents[1]
FOUR_ITEMS = ["card", "card", "candy", "candy"]


def _config(items=None):
    raw = load_raw_config()
    if items is not None:
        raw["items_per_box"]["value"] = items
        raw["pick_area_length_mm"]["value"] = 300.0  # a set of 4 needs a longer pick area
    return config_from_dict(raw)


def _read_csv(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return lines[0], list(csv.DictReader(lines[1:]))


# AC1: five complete cycles, exit code 0


def test_cli_five_cycles_exits_zero(tmp_path, capsys):
    assert main(["--cycles", "5", "--out-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert output.count("[SIMULATION] cycle ") == 5

    (csv_path,) = tmp_path.glob("*.csv")
    banner, rows = _read_csv(csv_path)
    assert banner == SIMULATION_BANNER
    cycle_rows = [row for row in rows if row["record_type"] == "cycle"]
    item_rows = [row for row in rows if row["record_type"] == "item"]
    assert [row["cycle"] for row in cycle_rows] == ["1", "2", "3", "4", "5"]
    assert len(item_rows) == 5 * 3
    assert all(float(row["cycle_time_s"]) > 0 for row in cycle_rows)


def test_run_result_has_five_cycles():
    result = run_simulation(load_config(), 5)
    assert result.final_state is State.READY
    assert result.fault_reason is None
    assert len(result.cycles) == 5
    assert exit_code_for(result) == 0


# AC2: every box gets all configured items, in order, then the lid


@pytest.mark.parametrize("items", [None, FOUR_ITEMS])
def test_every_box_gets_items_in_order_then_the_lid(items):
    config = _config(items)
    result = run_simulation(config, 5)
    for cycle in result.cycles:
        assert cycle.items == config.items_per_box
        placed = [r for r in result.items if r.cycle == cycle.cycle]
        assert [r.item_type for r in placed] == list(config.items_per_box)
        assert [r.item_index for r in placed] == list(range(1, len(config.items_per_box) + 1))
    kinds = [a.action if a.action != "place" else a.item_type for a in result.actions if a.action != "pick"]
    assert kinds == (list(config.items_per_box) + ["lid"]) * 5


def test_unneeded_items_pass_the_pick_area_and_are_logged():
    result = run_simulation(load_config(), 5)
    assert result.skipped, "the seeded random feed should send some items past the pick area"
    assert sum(c.skipped_count for c in result.cycles) == len(result.skipped)
    assert all(r.left_area_s > r.entered_area_s for r in result.skipped)


# AC3: no pick while belt A moves; no place or lid without a box at S1


@pytest.mark.parametrize("items", [None, FOUR_ITEMS])
def test_safety_rules_hold_for_every_action(items):
    result = run_simulation(_config(items), 5)
    picks = [a for a in result.actions if a.action == "pick"]
    places = [a for a in result.actions if a.action in ("place", "lid")]
    assert picks and len(places) == len(picks) + 5
    assert not any(a.belt_a_running for a in picks)
    assert all(a.s1_active for a in places)


def test_cycle_follows_the_team_set_up():
    config = load_config()
    result = run_simulation(config, 5)
    entered = [t.to_state for t in result.transitions]
    assert entered.count(State.FEED_SET) == entered.count(State.DETECT) == entered.count(State.CLOSE_LID) == 5
    for cycle in result.cycles:
        assert cycle.cycle_start_s < cycle.box_seen_s < cycle.set_ready_s < cycle.pictures_done_s
        assert cycle.pictures_done_s < cycle.lid_done_s < cycle.box_removed_s == cycle.cycle_done_s
        assert cycle.box_removed_s - cycle.lid_done_s == pytest.approx(config.box_removal_time_s)


# AC4: same config gives identical CSV files


def test_two_runs_give_identical_csv(tmp_path):
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"
    assert main(["--cycles", "5", "--out-dir", str(first_dir)]) == 0
    assert main(["--cycles", "5", "--out-dir", str(second_dir)]) == 0
    (first,) = first_dir.glob("*.csv")
    (second,) = second_dir.glob("*.csv")
    assert first.read_bytes() == second.read_bytes()


# AC5: no box ever reaches S1 -> FAULT via the timeout hook


def test_no_box_at_s1_ends_in_fault(tmp_path):
    config = load_config()
    result = run_simulation(config, 5, s1_working=False)

    assert result.final_state is State.FAULT
    last = result.transitions[-1]
    assert (last.from_state, last.to_state) == (State.WAIT_BOX, State.FAULT)
    entered_wait_s = result.transitions[-2].time_s
    assert last.time_s == pytest.approx(entered_wait_s + config.timeouts_s[State.WAIT_BOX])
    assert "S1" in result.fault_reason
    assert not any(a.action in ("place", "lid") for a in result.actions)
    assert result.cycles == []
    assert exit_code_for(result) == EXIT_FAULT != 0

    banner, rows = _read_csv(write_csv(result, tmp_path))
    assert banner == SIMULATION_BANNER
    assert rows[-1]["record_type"] == "fault"


# AC6: standard library only, files under 300 lines


def _package_python_files():
    return sorted(PACKAGE_DIR.rglob("*.py"))


def test_files_are_under_300_lines():
    for path in _package_python_files():
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count < 300, f"{path.name} has {line_count} lines"


def test_only_standard_library_imports():
    allowed = set(sys.stdlib_module_names) | {"cell_sim"}
    for path in _package_python_files():
        if path.parent.name == "tests":
            allowed_here = allowed | {"pytest"}
        else:
            allowed_here = allowed
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                assert name.split(".")[0] in allowed_here, f"{path.name} imports {name}"
