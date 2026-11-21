"""
STEP 13 - Live detection with the trained YOLO model.

    python 13_yolo_detect.py                       (live camera)
    python 13_yolo_detect.py --image photo.jpg     (one saved picture)
    python 13_yolo_detect.py --folder ../dataset/raw/belt_usb_3   (check many pictures, any key = next)

Shows for every object: class, confidence, main colour and - when the camera
is calibrated (04 + 09) - the robot X/Y of its centre.

Keys (live):
    + / -  = confidence threshold up / down (lecture: a higher threshold can hide real objects)
    p      = print all objects in the terminal
    s      = save a screenshot to Choton/images/
    q      = quit
"""

import argparse
import glob
import os

import cv2

import vision_lib as vl
import yolo_lib as yl


def print_objects(objects):
    print(yl.summarize(objects))
    for o in objects:
        pos = f'robot ({o["x_robot"]:.1f}, {o["y_robot"]:.1f})' if "x_robot" in o else f'pixel ({o["u"]}, {o["v"]})'
        flags = (" EDGE" if o.get("edge") else "") + ("" if o.get("reachable", True) else " OUT OF REACH")
        print(f'  {o["type"]:6s} {o["conf"]:.2f}  {o["color"]:7s} {pos}{flags}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--folder")
    args = ap.parse_args()

    settings = vl.load_settings()
    model = yl.load_model(settings)
    H = vl.load_homography()
    if H is None:
        print("(not calibrated - positions in pixels only)")
    conf = settings.get("yolo", {}).get("conf", 0.5)
    os.makedirs(vl.RESULTS_DIR, exist_ok=True)

    if args.folder:
        H = None   # saved pictures (other cameras/sizes): no robot X/Y, the calibration does not fit them
        files = sorted(p for p in glob.glob(os.path.join(args.folder, "*.jpg")) if not p.endswith("background.jpg"))
        for p in files:
            img = cv2.imread(p)
            objs = yl.detect(img, model, settings, H, conf)
            for o in objs:
                yl.add_angle(img, o, H)            # how crooked each object lies
            print(os.path.basename(p), "->", yl.summarize(objs))
            vl.show("13 yolo detect (any key = next, q = quit)", yl.draw(img, objs, settings, H))
            if cv2.waitKey(0) & 0xFF == ord("q"):
                break
        cv2.destroyAllWindows()
        return

    src = vl.FrameSource(args.image, settings)
    while True:
        frame = src.read()
        objs = yl.detect(frame, model, settings, H, conf)
        for o in objs:
            yl.add_angle(frame, o, H)              # how crooked each object lies
        view = yl.draw(frame, objs, settings, H)
        vl._put_label(view, f"conf >= {conf:.2f}  (+/-)   p=print  s=save  q=quit",
                      (10, view.shape[0] - 12), (0, 255, 255))
        vl.show("13 yolo detect", view)
        key = cv2.waitKey(0 if args.image else 1) & 0xFF
        if key == ord("q") or (args.image and key not in (ord("+"), ord("-"), ord("p"), ord("s"))):
            break
        if key in (ord("+"), ord("=")):
            conf = min(0.95, conf + 0.05)
        elif key == ord("-"):
            conf = max(0.05, conf - 0.05)
        elif key == ord("p"):
            print_objects(objs)
        elif key == ord("s"):
            path = os.path.join(vl.RESULTS_DIR, f"yolo_{vl.timestamp()}.jpg")
            cv2.imwrite(path, view)
            print(f"[saved] {path}")
    src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
