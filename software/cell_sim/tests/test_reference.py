"""The sim result with the current config.json must not change (SIMULATION, assumed parameters).

Reference since 2026-11-16: the team's cycle (Choton_Week3_Notebook.md). The earlier
one-item-at-a-time reference (testing/sim_runs/20261109_022312.csv) is kept as history.
"""

from pathlib import Path

import pytest

from cell_sim.__main__ import main
from cell_sim.config import load_config
from cell_sim.simulation import run_simulation

REFERENCE_CYCLE_TIMES_S = [61.1, 58.7, 60.1, 60.1, 58.7]
REFERENCE_CSV = Path(__file__).resolve().parents[3] / "testing" / "sim_runs" / "20261116_203549.csv"


def test_five_cycle_times_match_reference():
    result = run_simulation(load_config(), 5)
    times_s = [round(cycle.cycle_time_s, 3) for cycle in result.cycles]
    assert times_s == REFERENCE_CYCLE_TIMES_S
    assert round(sum(times_s), 3) == 298.7
    assert round(sum(times_s) / len(times_s), 3) == 59.74


def test_csv_rows_match_committed_reference_run(tmp_path):
    if not REFERENCE_CSV.exists():
        pytest.skip(f"reference run {REFERENCE_CSV} not checked out")
    assert main(["--cycles", "5", "--out-dir", str(tmp_path)]) == 0
    (new_csv,) = tmp_path.glob("*.csv")
    reference_lines = REFERENCE_CSV.read_text(encoding="utf-8").splitlines()
    new_lines = new_csv.read_text(encoding="utf-8").splitlines()
    assert new_lines[0] == reference_lines[0]
    assert new_lines[1:] == reference_lines[1:]
