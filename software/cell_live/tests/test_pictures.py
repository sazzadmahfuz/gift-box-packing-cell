"""The pictures of a run are saved next to its log (control/pictures.py), and never stop the run."""

import dataclasses
from pathlib import Path

from cell_live.control.pictures import RunPictures, pictures_folder
from cell_live.tests.control_fakes import objects_come_with_the_belt, wait_for
from cell_live.tests.test_cycle import make_run


def test_pictures_are_numbered_in_the_order_they_were_taken(tmp_path):
    pictures = RunPictures(tmp_path / "run_pictures", lambda frame: f"jpeg of {frame}".encode())
    assert pictures.save("box", "frame 1") == "0001_box.jpg" and pictures.save("look", "frame 9") == "0002_look.jpg"
    assert (tmp_path / "run_pictures" / "0002_look.jpg").read_bytes() == b"jpeg of frame 9"
    assert pictures.saved == 2 and pictures.failed == 0


def test_a_failed_save_is_counted_and_does_not_raise(tmp_path):
    def broken(frame):
        raise ValueError("not a picture")

    pictures = RunPictures(tmp_path / "run_pictures", broken)
    assert pictures.save("look", "frame 1") is None and pictures.failed == 1 and pictures.saved == 0
    assert RunPictures(tmp_path / "x", lambda frame: None).save("look", "frame 1") is None  # the encoder gave nothing
    assert RunPictures(tmp_path / "y", lambda frame: b"jpeg").save("look", None) is None  # no frame
    assert not (tmp_path / "run_pictures").exists()


def test_the_number_of_pictures_per_run_is_limited(tmp_path):
    pictures = RunPictures(tmp_path / "p", lambda frame: b"jpeg", limit=2)
    assert [pictures.save("belt", n) for n in range(3)] == ["0001_belt.jpg", "0002_belt.jpg", None]


def test_the_folder_is_named_after_the_run_log():
    assert pictures_folder(Path("testing/live_runs/20261117_195652.csv")) == Path("testing/live_runs/20261117_195652_pictures")


def test_a_run_saves_the_picture_of_each_decision_and_the_log_names_the_file(tmp_path):
    controller, session, vision, log = make_run()
    objects_come_with_the_belt(vision, session)
    pictures = RunPictures(tmp_path / "run_pictures", lambda frame: str(frame).encode())
    controller.context = dataclasses.replace(controller.context, pictures=pictures)
    controller.start()
    wait_for(lambda: controller.finished)
    saved = sorted(path.name for path in (tmp_path / "run_pictures").iterdir())
    labels = [name[5:-4] for name in saved]
    assert labels[0] == "box" and labels[-1] == "closed_box" and "look" in labels and "belt" in labels
    events = [row["event"] for row in log.rows]
    assert f"box is here and standing still (picture {saved[0]})" in events
    assert any(event.startswith("pictures taken (picture ") for event in events)
    assert any(event.startswith("take the closed box away") and event.endswith(f"(picture {saved[-1]})") for event in events)
