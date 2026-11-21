"""
STEP 2 - Find the colour ranges (HSV) for your cards and candies.

Live camera:          python 02_hsv_tuner.py
From a saved photo:   python 02_hsv_tuner.py --image ../images/xxx.png

How to use:
  1. CLICK on an object in the "image" window -> its HSV value is printed
     in the terminal. Click a few spots on the same object.
  2. Move the sliders until ONLY that object is white in the "mask" window
     and everything else is black.
       H = hue (the colour itself, 0..180)
       S = saturation (how strong the colour is; grey/white table = low S)
       V = value (brightness)
  3. Press 's' and type the colour name (e.g. red) in the terminal.
     The range is saved to config/colors.json (or the "colors_file" in settings.json).
  4. Repeat for every colour. Press 'q' to quit.

Red is special: it sits at BOTH ends of the hue scale (0-10 and 170-180).
Save red twice and answer 'a' (add) the second time.
"""

import argparse

import cv2
import numpy as np

import vision_lib as vl

WIN_IMG = "image (click = show HSV)"
WIN_MASK = "mask (white = selected)"
WIN_BARS = "sliders"


def nothing(_):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use a saved photo instead of the live camera")
    args = ap.parse_args()

    settings = vl.load_settings()
    src = vl.FrameSource(args.image, settings)
    state = {"hsv": None}

    def on_click(event, x, y, flags, param):
        x, y = vl.to_image_xy(x, y)
        if event == cv2.EVENT_LBUTTONDOWN and state["hsv"] is not None:
            h, s, v = state["hsv"][y, x]
            print(f"pixel ({x},{y})  ->  H={h}  S={s}  V={v}")

    cv2.namedWindow(WIN_IMG)
    cv2.namedWindow(WIN_MASK)
    cv2.namedWindow(WIN_BARS)
    cv2.resizeWindow(WIN_BARS, 400, 250)
    cv2.setMouseCallback(WIN_IMG, on_click)
    for name, start, maximum in [("H min", 0, 180), ("H max", 180, 180),
                                 ("S min", 100, 255), ("S max", 255, 255),
                                 ("V min", 70, 255), ("V max", 255, 255)]:
        cv2.createTrackbar(name, WIN_BARS, start, maximum, nothing)

    print(__doc__)
    while True:
        frame = src.read()
        frame, _ = vl.crop_roi(frame, settings)
        blur = settings.get("blur", 5)
        if blur and blur > 1:
            frame = cv2.GaussianBlur(frame, (blur | 1, blur | 1), 0)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        state["hsv"] = hsv

        lo = [cv2.getTrackbarPos(n, WIN_BARS) for n in ("H min", "S min", "V min")]
        hi = [cv2.getTrackbarPos(n, WIN_BARS) for n in ("H max", "S max", "V max")]
        mask = vl.color_mask(hsv, [(lo, hi)], settings)

        vl.show(WIN_IMG, frame)
        vl.show(WIN_MASK, mask)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            name = input("Colour name to save (e.g. red, green): ").strip().lower()
            if not name:
                print("Nothing saved.")
                continue
            colors = vl.load_colors()
            new_range = [lo, hi]
            if name in colors:
                ans = input(f"'{name}' exists. [r]eplace or [a]dd this range? ").strip().lower()
                if ans == "a":
                    colors[name]["ranges"].append(new_range)
                else:
                    colors[name]["ranges"] = [new_range]
            else:
                # draw colour for the boxes in 03_detect = average colour of the selected pixels
                mean_bgr = cv2.mean(frame, mask=mask)[:3] if mask.any() else (255, 255, 255)
                colors[name] = {"ranges": [new_range], "draw": [int(c) for c in mean_bgr]}
            vl.save_json(vl.colors_file(), colors)
            print(f"{name}: {colors[name]['ranges']}")

    src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
