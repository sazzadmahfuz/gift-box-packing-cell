"""The calibration fitted to a camera view that has turned (control/camera_view.py). 17 Nov: the camera turned
6.3 deg in its holder between 21:50 and 21:58, half an hour after the calibration of 21:26."""

from types import SimpleNamespace

from cell_live.control.camera_view import describe, view_correction
from cell_live.control.vision_session import VisionSession
from cell_live.tests.control_fakes import CHOTON

CREATED = "2026-11-17_21-26-54"
TURNED = [[0.99494, -0.109689, 40.876979], [0.109689, 0.99494, -72.347958], [0.0, 0.0, 1.0]]  # as worked out on 17 Nov
ENTRY = {"for_calibration": CREATED, "why": "the camera turned 6.3 deg in its holder", "pixel_to_calibration_pixel": TURNED}
CALIBRATION = [[-0.020743267205752335, 0.41890105665891864, 135.37448911870504],
               [0.41391036981722307, 0.02368291536141527, -179.25358252822642],
               [-4.533996512327276e-06, 3.460968962911686e-05, 1.0]]  # homography.json of 21:26


def test_the_correction_is_used_only_with_the_calibration_it_was_made_for():
    assert view_correction(ENTRY, CREATED) == TURNED
    assert view_correction(ENTRY, "2026-11-18_09-00-00") is None  # a new calibration: the old correction is not used
    assert view_correction(None, CREATED) is None and view_correction(ENTRY, None) is None
    assert view_correction({**ENTRY, "pixel_to_calibration_pixel": [[1, 0], [0, 1]]}, CREATED) is None


def test_the_note_says_what_is_in_use():
    assert describe(None, CREATED) == ""
    assert describe(ENTRY, CREATED).startswith(
        "the calibration of 2026-11-17_21-26-54 is used with a correction for the camera view (the camera turned 6.3 deg in its holder)")
    assert "it is not used" in describe(ENTRY, "2026-11-18_09-00-00")


def _session(correction):
    np = CHOTON.vision_lib.np
    vision_lib = SimpleNamespace(load_homography=lambda: np.array(CALIBRATION), np=np, pixel_to_robot=CHOTON.vision_lib.pixel_to_robot,
                                 table_to_robot=lambda x, y, settings: (x, y), robot_to_table=lambda x, y, settings: (x, y))
    session = VisionSession(SimpleNamespace(vision_lib=vision_lib, yolo_lib=SimpleNamespace()), {"camera_index": 0}, 1, 0.5,
                            make_source=lambda s: SimpleNamespace(read=lambda: None, release=lambda: None), load_model=lambda s: object())
    session.view_correction = correction
    session.start()
    session.stop()
    return session


def test_the_two_crosses_seen_after_the_turn_get_their_robot_positions_back():
    # after the turn the crosses of marks 1 and 4 were found at these pixels; the robot touched them at these positions
    session = _session(TURNED)
    for pixel, robot in (((93.0, 167.0), (175.5, -128.52)), ((114.0, 602.0), (352.37, -128.1))):
        x_mm, y_mm = session.pixel_robot(*pixel)
        assert abs(x_mm - robot[0]) < 1.0 and abs(y_mm - robot[1]) < 1.0, (x_mm, y_mm)
        u, v = session.robot_pixel(*robot)
        assert abs(u - pixel[0]) < 2.0 and abs(v - pixel[1]) < 2.0, (u, v)


def test_without_the_correction_the_same_pixels_are_two_centimetres_off():
    session = _session(None)
    x_mm, y_mm = session.pixel_robot(93.0, 167.0)
    assert ((x_mm - 175.5) ** 2 + (y_mm + 128.52) ** 2) ** 0.5 > 20.0
