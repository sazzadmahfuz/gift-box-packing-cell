"""
STEP 4 - Calibrate: convert camera pixels to millimetres on the table.

Because the table is flat, 4 known points are enough (a "homography").

What you need under the camera:
  A sheet of paper with 4 crosses drawn with a ruler, as far apart as
  possible (near the corners of what the camera sees). Measure each cross
  from ONE corner of the paper: X to the right, Y down, in mm.
  Example: (0, 0)  (200, 0)  (200, 150)  (0, 150)
  Do NOT move the camera after this.

How to use:
  1. python 04_calibrate.py
  2. CLICK the centre of each cross. 'u' = undo last click. ENTER = done.
  3. Type the X and Y (mm) of each cross in the terminal.
  4. Saved to config/homography.json. Test mode starts: click anywhere,
     it prints X/Y in mm. Check against the ruler. 'q' = quit.

After this, 03_detect.py shows every object's position in mm.
Later (robot working): repeat with the robot tip on the crosses and type
the robot's X/Y instead, then positions are in robot coordinates.
"""

import argparse

import cv2
import numpy as np

import vision_lib as vl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use a saved photo instead of the live camera")
    ap.add_argument("--test", action="store_true", help="only test the saved calibration (click = X/Y in mm)")
    args = ap.parse_args()

    settings = vl.load_settings()
    src = vl.FrameSource(args.image, settings)
    frame = src.read()

    if args.test:
        H = vl.load_homography()
        if H is None:
            print("No calibration saved yet - run without --test first.")
            return
        test_mode(src, H, args.image is None)
        return

    clicks = []

    def on_click(event, x, y, flags, param):
        x, y = vl.to_image_xy(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
            print(f"point {len(clicks)}: pixel ({x}, {y})")

    win = "04 calibrate - click markers, ENTER = done, u = undo"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    print(__doc__)

    while True:
        if args.image is None:
            frame = src.read()
        view = frame.copy()
        for i, (x, y) in enumerate(clicks):
            cv2.drawMarker(view, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
            cv2.putText(view, str(i + 1), (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        vl.show(win, view)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("u") and clicks:
            print(f"removed point {len(clicks)}")
            clicks.pop()
        elif key in (13, 10):  # ENTER
            if len(clicks) < 4:
                print("Need at least 4 points.")
            else:
                break
        elif key == ord("q"):
            src.release()
            cv2.destroyAllWindows()
            return

    robot_pts = []
    for i, (x, y) in enumerate(clicks):
        while True:
            txt = input(f"Point {i + 1} at pixel ({x},{y}) - X Y in mm (e.g. 200 150): ")
            try:
                rx, ry = [float(t) for t in txt.replace(",", " ").split()]
                robot_pts.append((rx, ry))
                break
            except ValueError:
                print("Type two numbers separated by a space.")

    px = np.array(clicks, dtype=np.float64)
    rb = np.array(robot_pts, dtype=np.float64)
    H, _ = cv2.findHomography(px, rb)
    if H is None:
        print("Calibration failed - points may be in a straight line. Spread them out.")
        return

    # Error at the calibration points (should be small, around 1-2 mm)
    proj = cv2.perspectiveTransform(px.reshape(-1, 1, 2), H).reshape(-1, 2)
    errors = np.linalg.norm(proj - rb, axis=1)
    for i, e in enumerate(errors):
        print(f"point {i + 1}: error {e:.2f} mm")
    print(f"mean error {errors.mean():.2f} mm, max {errors.max():.2f} mm")

    vl.save_json(vl.homography_file(), {
        "H": H.tolist(),
        "pixel_points": px.tolist(),
        "mm_points": rb.tolist(),
        "mean_error_mm": float(errors.mean()),
        "created": vl.timestamp(),
    })

    test_mode(src, H, args.image is None)


def test_mode(src, H, live):
    win = "04 calibrate - TEST: click a point, q = quit"
    cv2.namedWindow(win)
    print("\nTEST MODE: click anywhere to see X/Y in mm. Press q to quit.")

    def on_test_click(event, x, y, flags, param):
        x, y = vl.to_image_xy(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            rx, ry = vl.pixel_to_robot(H, x, y)
            print(f"pixel ({x},{y}) -> X={rx:.1f} mm  Y={ry:.1f} mm")

    cv2.setMouseCallback(win, on_test_click)
    frame = src.read()
    while True:
        if live:
            frame = src.read()
        vl.show(win, frame)
        if (cv2.waitKey(30) & 0xFF) == ord("q"):
            break
    src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
