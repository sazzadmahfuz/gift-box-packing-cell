"""
STEP 5 - Plan which objects go into which box.

What goes into one box is set in config/settings.json -> "box_contents",
for example {"card": 2, "candy": 2} or {"card": 1, "candy": 2}.
All cards in a box have different colours, all candies too.

    python 05_box_planner.py                 (live camera, one snapshot)
    python 05_box_planner.py --image photo.png
    python 05_box_planner.py --boxes 2

Prints the pick list and saves a picture with B1, B2 ... on each object.
"""

import argparse
import os

import cv2

import vision_lib as vl


def describe(o):
    if "x_robot" in o:
        pos = f"robot ({o['x_robot']:.1f}, {o['y_robot']:.1f}) mm"
        if not o["reachable"]:
            pos += " OUT OF REACH"
    elif "x_mm" in o:
        pos = f"table ({o['x_mm']:.1f}, {o['y_mm']:.1f}) mm"
    else:
        pos = f"pixel ({o['u']:.0f}, {o['v']:.0f})"
    return f"{o['color']} {o['type']} at {pos}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use a saved photo instead of the live camera")
    ap.add_argument("--boxes", type=int, help="number of boxes (default from settings.json)")
    ap.add_argument("--no-window", action="store_true")
    args = ap.parse_args()

    settings = vl.load_settings()
    colors = vl.load_colors()
    H = vl.load_homography()
    n_boxes = args.boxes or settings.get("boxes", 1)

    src = vl.FrameSource(args.image, settings)
    frame, objects, _ = vl.detect_stable(src, colors, settings, H)   # 15 frames, median position
    src.release()

    print(vl.summarize(objects))
    print("Box contents:", settings.get("box_contents", {"card": 2, "candy": 2}))
    boxes, problems = vl.plan_boxes(objects, n_boxes, settings)

    print("\n=== PICK LIST ===")
    step = 1
    annotated = vl.draw_objects(frame, objects, colors, settings, H)
    for b in boxes:
        for o in b["items"]:
            print(f"{step:2d}. pick {describe(o):<50} -> BOX {b['box']}")
            vl._put_label(annotated, f"B{b['box']}", (int(o["u"]) - 10, int(o["v"]) + 30), (255, 255, 255))
            step += 1
    print(f"\nBoxes complete: {len(boxes)} of {n_boxes}")
    for p in problems:
        print("WARNING:", p)

    os.makedirs(vl.RESULTS_DIR, exist_ok=True)
    path = os.path.join(vl.RESULTS_DIR, f"plan_{vl.timestamp()}.jpg")
    cv2.imwrite(path, annotated)
    print(f"[saved] {path}")

    if not args.no_window:
        vl.show("05 box plan (any key = close)", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
