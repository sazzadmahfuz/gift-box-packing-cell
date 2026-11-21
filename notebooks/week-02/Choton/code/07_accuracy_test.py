"""
STEP 7 - Accuracy and robustness test (gives numbers for the report).

    python 07_accuracy_test.py --condition "normal light"
    python 07_accuracy_test.py --condition "lamp from the side" --cards 2 --candies 2

How to use:
  1. Put the objects on the table in a new layout.
  2. Click the window and press SPACE. The program looks at 20 frames and checks:
       - how many of the 20 frames were detected 100 % correctly
       - whether the final (stable) result is correct
       - how much each position moves between frames (jitter, in mm)
  3. Change the layout (move / rotate objects) and press SPACE again.
     Do about 10 layouts per condition.
  4. Press q. A summary is printed and saved.

"Correct" = exactly the expected number of cards and candies, all with different
colours, and no extra objects. Only objects the robot can use are counted:
objects partly outside the picture (EDGE) or ignored ones (wrong size) are not.
Keep the cards and candies fully inside the picture and keep hands out of it.

Results are added to   Choton/test_results/accuracy_log.csv
and a picture of every run is saved in   Choton/test_results/
"""

import argparse
import csv
import os

import cv2
import numpy as np

import vision_lib as vl

RESULT_DIR = os.path.abspath(os.path.join(vl.VISION_DIR, "..", "test_results"))
LOG = os.path.join(RESULT_DIR, "accuracy_log.csv")


def is_correct(objects, want_cards, want_candies):
    # count only objects the robot can use (same rule as the robot program):
    # card / candy of the right size, not partly outside the picture
    usable = [o for o in objects if o["type"] in ("card", "candy") and not o.get("edge")]
    cards = [o["color"] for o in usable if o["type"] == "card"]
    candies = [o["color"] for o in usable if o["type"] == "candy"]
    return (len(cards) == want_cards and len(candies) == want_candies
            and len(set(cards)) == len(cards) and len(set(candies)) == len(candies))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="normal", help='test condition, e.g. "normal light"')
    ap.add_argument("--cards", type=int, default=2, help="cards on the table")
    ap.add_argument("--candies", type=int, default=2, help="candies on the table")
    ap.add_argument("--frames", type=int, default=20, help="frames per run")
    args = ap.parse_args()

    settings = vl.load_settings()
    colors = vl.load_colors()
    H = vl.load_homography()
    os.makedirs(RESULT_DIR, exist_ok=True)
    new_file = not os.path.exists(LOG)

    src = vl.FrameSource(None, settings)
    print(f'Condition: "{args.condition}"  expected: {args.cards} cards + {args.candies} candies')
    print("SPACE = test this layout   q = finish")

    runs = []
    while True:
        frame = src.read()
        objs = vl.detect_objects(frame, colors, settings, H)
        view = vl.draw_objects(frame, objs, colors, settings, H)
        vl._put_label(view, f'{args.condition} | runs: {len(runs)} | SPACE = test, q = quit',
                      (10, view.shape[0] - 15), (0, 255, 255))
        vl.show("07 accuracy test", view)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key != ord(" "):
            continue

        # ---- one test run ----
        last, stable, stats = vl.detect_stable(src, colors, settings, H, frames=args.frames)
        ok_frames = sum(is_correct(f, args.cards, args.candies) for f in stats["per_frame"])
        ok_stable = is_correct(stable, args.cards, args.candies)
        jit = [o["jitter_mm"] for o in stable if "jitter_mm" in o]
        max_jit = max(jit) if jit else None
        covered = sum(1 for o in stable if o.get("covered"))
        found = vl.summarize(stable)

        n = len(runs) + 1
        img_name = f"{vl.timestamp()}_run{n}.jpg"
        cv2.imwrite(os.path.join(RESULT_DIR, img_name), vl.draw_objects(last, stable, colors, settings, H))

        row = {
            "time": vl.timestamp(), "condition": args.condition, "run": n,
            "frames": stats["frames"], "frames_correct": ok_frames,
            "frame_accuracy_%": round(100.0 * ok_frames / stats["frames"], 1),
            "stable_result_correct": "yes" if ok_stable else "NO",
            "max_jitter_mm": max_jit if max_jit is not None else "",
            "covered_objects": covered, "found": found, "image": img_name,
        }
        runs.append(row)
        with open(LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if new_file:
                w.writeheader()
                new_file = False
            w.writerow(row)

        print(f"run {n}: {ok_frames}/{stats['frames']} frames correct, stable result "
              f"{'OK' if ok_stable else 'WRONG'}, max jitter "
              f"{max_jit if max_jit is not None else '-'} mm | {found}")

    src.release()
    cv2.destroyAllWindows()

    if not runs:
        print("No runs.")
        return
    total = len(runs)
    stable_ok = sum(r["stable_result_correct"] == "yes" for r in runs)
    frame_acc = np.mean([r["frame_accuracy_%"] for r in runs])
    jits = [r["max_jitter_mm"] for r in runs if r["max_jitter_mm"] != ""]
    summary = (
        f'\n=== SUMMARY: "{args.condition}" ===\n'
        f"layouts tested:          {total}\n"
        f"stable result correct:   {stable_ok}/{total} ({100.0 * stable_ok / total:.0f} %)\n"
        f"single frames correct:   {frame_acc:.1f} % (average)\n"
        + (f"position jitter:         mean {np.mean(jits):.2f} mm, max {np.max(jits):.2f} mm\n" if jits else
           "position jitter:         - (not calibrated)\n")
    )
    print(summary)
    with open(os.path.join(RESULT_DIR, "summary.txt"), "a", encoding="utf-8") as f:
        f.write(summary)
    print(f"[saved] {LOG}")


if __name__ == "__main__":
    main()
