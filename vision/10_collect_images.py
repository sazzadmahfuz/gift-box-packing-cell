"""
STEP 10 - Take training pictures for YOLO.

    python 10_collect_images.py --session home_nicla_1
    python 10_collect_images.py --session belt_usb_1

Every run is one "session" (one folder in dataset/raw/). Use a NEW session
name every time you change place, light or camera. Later the sessions are
split into train / validation / test (the teacher: different capture sessions
in different sets, not neighbouring frames).

Keys (click the video window first):
    b      = save the EMPTY background (do this FIRST, with nothing on the belt/table).
             The labelling tool uses it to draw the boxes for you.
    SPACE  = save one picture
    a      = auto mode on/off (saves a picture every 2 s while you move objects)
    q      = quit

Good training pictures:
  - 50-100 pictures per session, 2-3 sessions to start
  - move, rotate and flip the objects between pictures, mix cards and candies,
    let them touch, put some near the edge, use DIFFERENT candies
  - keep your hands OUT of the picture when it saves
"""

import argparse
import os
import time

import cv2

import vision_lib as vl
import yolo_lib as yl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None, help="folder name, e.g. home_nicla_1")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between pictures in auto mode")
    args = ap.parse_args()

    settings = vl.load_settings()
    session = args.session or f'{settings.get("camera", "cam")}_{vl.timestamp()}'
    folder = os.path.join(yl.DATASET_DIR, "raw", session)
    os.makedirs(folder, exist_ok=True)
    print(f"Saving to {folder}")
    print("b = background (empty!)   SPACE = save   a = auto on/off   q = quit")

    src = vl.FrameSource(None, settings)
    saved = len([f for f in os.listdir(folder) if f.startswith("img_")])
    auto, last = False, 0.0
    while True:
        frame = src.read()
        view = frame.copy()
        has_bg = os.path.exists(os.path.join(folder, "background.jpg"))
        status = (f"{session} | saved {saved} | background {'OK' if has_bg else 'MISSING (press b)'}"
                  f" | auto {'ON' if auto else 'off'}")
        vl._put_label(view, status, (10, 22), (0, 255, 0) if has_bg else (0, 200, 255))
        vl.show("10 collect images", view)
        key = cv2.waitKey(30) & 0xFF

        now = time.time()
        if key == ord("q"):
            break
        if key == ord("b"):
            cv2.imwrite(os.path.join(folder, "background.jpg"), frame)
            print("[saved] background.jpg")
        elif key == ord("a"):
            auto = not auto
            last = now
        elif key == ord(" ") or (auto and now - last >= args.every):
            last = now
            saved += 1
            path = os.path.join(folder, f"img_{saved:04d}_{vl.timestamp()}.jpg")
            cv2.imwrite(path, frame)
            print(f"[saved] {os.path.basename(path)}")
            flash = view.copy()
            cv2.rectangle(flash, (0, 0), (flash.shape[1] - 1, flash.shape[0] - 1), (255, 255, 255), 12)
            vl.show("10 collect images", flash)
            cv2.waitKey(80)

    src.release()
    cv2.destroyAllWindows()
    print(f"{saved} pictures in {folder}\nNext: python 11_label.py")


if __name__ == "__main__":
    main()
