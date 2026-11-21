from pathlib import Path

from cell_ui.results import list_logs, read_banner, read_log
from cell_ui.runner import STDERR, CellRun

REFERENCE_CYCLE_TIMES_S = [61.1, 58.7, 60.1, 60.1, 58.7]  # cell_sim/tests/test_reference.py


def test_sim_run_from_the_ui_matches_the_cli_reference(tmp_path):
    run = CellRun(["--cycles", "5", "--out-dir", str(tmp_path)])
    run.start()
    assert run.wait(timeout_s=60) == 0
    output = [line.text for line in run.new_lines()]
    assert any("cycle 5/5" in line and "cycle_time_s=58.700" in line for line in output)
    (csv_path,) = run.csv_paths
    log = read_log(csv_path)
    assert log.label == "SIMULATION, assumed parameters"
    assert [time_s for _cycle, time_s in log.cycle_times_s()] == REFERENCE_CYCLE_TIMES_S
    assert round(log.mean_cycle_time_s(), 3) == 59.74
    assert list_logs(tmp_path) == [csv_path] and read_banner(csv_path).startswith("SIMULATION")


def test_errors_arrive_on_stderr_with_the_exit_code(tmp_path):
    run = CellRun(["--mode", "dobot-real", "--out-dir", str(tmp_path)])
    run.start()
    assert run.wait(timeout_s=60) == 5
    errors = [line.text for line in run.new_lines() if line.stream == STDERR]
    assert any("dobot-real refused to start" in line for line in errors)


def test_stop_ends_a_long_run(tmp_path):
    run = CellRun(["--cycles", "5", "--realtime", "1", "--out-dir", str(tmp_path)])  # about 256 s
    run.start()
    run.stop()
    assert run.wait(timeout_s=30) is None  # None = stopped by the operator
    assert not run.is_running()


def test_logs_without_cycle_columns_still_show(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    log = read_log(path)
    assert log.banner == "" and log.columns == ("a", "b") and log.rows == ({"a": "1", "b": "2"},)
    assert log.cycle_times_s() == [] and log.mean_cycle_time_s() is None


def test_committed_reference_log_reads():
    runs = Path(__file__).resolve().parents[3] / "testing" / "sim_runs"
    reference, old_reference = runs / "20261116_203549.csv", runs / "20261109_022312.csv"
    if reference.is_file():
        assert [t for _c, t in read_log(reference).cycle_times_s()] == REFERENCE_CYCLE_TIMES_S
    if old_reference.is_file():  # logs in the old column layout still read
        assert [t for _c, t in read_log(old_reference).cycle_times_s()] == [57.875, 54.875, 45.875, 54.875, 42.875]
