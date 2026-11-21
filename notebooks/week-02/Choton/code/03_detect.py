"""
STEP 3 - Detect cards and candies.

Live camera:          python 03_detect.py
From a saved photo:   python 03_detect.py --image photo.png
Without windows:      python 03_detect.py --image xxx.png --no-window

Keys:
    p  = print the list of detected objects (JSON) in the terminal
    s  = save a screenshot with the boxes into Choton/images/
    q  = quit

Every object gets a box, a label "colour type" and a cross at its centre.
How it decides card or candy (see vision_lib.classify):
  long and thin (aspect >= candy_min_aspect, e.g. the 3D-printed bars) -> candy
  card-shaped and big (area >= card_min_area)                          -> card
Press 'p' to see the 'area' and 'aspect' of every object, and change
candy_min_aspect / card_min_area in config/settings.json if needed.
"""

import argparse
import os

import cv2

import vision_lib as vl


def print_objects(objects):
    print(vl.summarize(objects))
    for i, o in enumerate(objects):
        pos = f"pixel=({o['u']:.0f},{o['v']:.0f})"
        if "x_mm" in o:
            pos += f"  mm=({o['x_mm']:.1f},{o['y_mm']:.1f})"
        if "x_robot" in o:
            pos += f"  robot=({o['x_robot']:.1f},{o['y_robot']:.1f})" + ("" if o["reachable"] else " OUT OF REACH")
        size = f"  size={o['length_mm']:.0f}x{o['width_mm']:.0f}mm" if "length_mm" in o else ""
        print(f"  {i}: {o['color']:<7} {o['type']:<6} {pos}{size}  angle={o['angle']}  area={o['area']}  aspect={o.get('aspect')}")


def save_result(annotated):
    os.makedirs(vl.RESULTS_DIR, exist_ok=True)
    path = os.path.join(vl.RESULTS_DIR, f"detect_{vl.timestamp()}.jpg")
    cv2.imwrite(path, annotated)
    print(f"[saved] {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use a saved photo instead of the live camera")
    ap.add_argument("--no-window", action="store_true", help="just print + save, no window")
    args = ap.parse_args()

    settings = vl.load_settings()
    colors = vl.load_colors()
    H = vl.load_homography()
    if not colors:
        print("No colours in config/" + vl.colors_file() + " - run 02_hsv_tuner.py first.")
        return
    print("Colours:", ", ".join(colors), "| calibration:", "yes" if H is not None else "no (pixels only)")

    src = vl.FrameSource(args.image, settings)

    if args.no_window:
        frame = src.read()
        objects = vl.detect_objects(frame, colors, settings, H)
        print_objects(objects)
        save_result(vl.draw_objects(frame, objects, colors, settings, H))
        src.release()
        return

    print("Keys: [p]=print objects  [s]=save screenshot  [q]=quit")
    while True:
        frame = src.read()
        objects = vl.detect_objects(frame, colors, settings, H)
        annotated = vl.draw_objects(frame, objects, colors, settings, H)
        vl.show("03 detect", annotated)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("p"):
            print_objects(objects)
        elif key == ord("s"):
            print_objects(objects)
            save_result(annotated)
        elif key == ord("q"):
            break

    src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
