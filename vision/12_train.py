"""
STEP 12 - Train our own YOLO model (fine-tune the small pretrained YOLO11n,
like in the week 3 lecture, but with OUR classes: card and candy).

    python 12_train.py                          (sessions split automatically)
    python 12_train.py --val belt_usb_2 --test belt_usb_3
    python 12_train.py --epochs 3 --imgsz 320   (very quick test, like the classroom run)

What it does:
  1. Collects every labelled picture from dataset/raw/<session>/ (picture + .txt).
  2. Splits them BY SESSION into train / val (/ test), as in the lecture:
     different capture sessions in different sets - not neighbouring frames.
       --val / --test   choose the sessions yourself
       otherwise: the newest session = val (if there are 2 or more sessions),
                  with only 1 session every 5th picture goes to val (warning).
  3. Writes dataset/yolo/ and dataset/yolo/data.yaml.
  4. Trains on the CPU (no graphics card needed). 50 epochs on ~200 pictures
     takes roughly 15-40 min on a laptop.
  5. Copies the best weights to  models/best.pt  (used by 13 and 14),
     and prints precision / recall / mAP on the validation set.
     Training curves and example predictions: models/runs/<name>/
"""

import argparse
import glob
import os
import shutil

import vision_lib as vl
import yolo_lib as yl


def labelled_by_session():
    sessions = {}
    for img in sorted(glob.glob(os.path.join(yl.DATASET_DIR, "raw", "*", "*.jpg"))):
        if os.path.basename(img) == "background.jpg":
            continue
        if os.path.exists(os.path.splitext(img)[0] + ".txt"):
            sessions.setdefault(os.path.basename(os.path.dirname(img)), []).append(img)
    return sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val", nargs="*", default=None, help="session name(s) for validation")
    ap.add_argument("--test", nargs="*", default=None, help="session name(s) kept for the final test")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=None, help="picture size for training (default settings.json)")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--base", default="yolo11n.pt", help="pretrained model to start from")
    ap.add_argument("--repeat", nargs="*", default=[], metavar="SESSION=N",
                    help="use the training pictures of a session N times, e.g. belt_usb_1=3")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("YOLO is not installed. Run:  pip install ultralytics")

    settings = vl.load_settings()
    names = yl.class_names(settings)
    imgsz = args.imgsz or settings.get("yolo", {}).get("imgsz", 640)

    sessions = labelled_by_session()
    if not sessions:
        raise SystemExit("No labelled pictures. Run 10_collect_images.py and 11_label.py first.")
    order = sorted(sessions)          # session names; the newest is usually last
    test = set(args.test or [])
    if args.val is not None:
        val = set(args.val)
    elif len(order) - len(test) >= 2:
        val = {[s for s in order if s not in test][-1]}
    else:
        val = set()

    split = {"train": [], "val": [], "test": []}
    for s in order:
        for k, img in enumerate(sessions[s]):
            if s in test:
                split["test"].append(img)
            elif s in val:
                split["val"].append(img)
            elif not val and k % 5 == 4:
                split["val"].append(img)   # only one session: every 5th picture
            else:
                split["train"].append(img)
    if not val:
        print("WARNING: only one session -> validation pictures are neighbours of training pictures.\n"
              "         The scores will look better than reality. Take a second session soon.")
    if not split["train"] or not split["val"]:
        raise SystemExit("Need pictures in both train and val. Take more sessions.")

    for s in order:
        part = "test" if s in test else "val" if s in val else "train" if val else "train+val"
        print(f"  {s:30s} {len(sessions[s]):4d} pictures -> {part}")
    print(f"train {len(split['train'])}  val {len(split['val'])}  test {len(split['test'])}")

    repeat = {r.split("=")[0]: int(r.split("=")[1]) for r in args.repeat if "=" in r}
    # ---- build dataset/yolo/<part>/images + labels (copies, raw stays untouched)
    out = os.path.join(yl.DATASET_DIR, "yolo")
    shutil.rmtree(out, ignore_errors=True)
    for part, imgs in split.items():
        for d in ("images", "labels"):
            os.makedirs(os.path.join(out, part, d), exist_ok=True)
        for img in imgs:
            session = os.path.basename(os.path.dirname(img))
            stem = session + "__" + os.path.splitext(os.path.basename(img))[0]
            times = repeat.get(session, 1) if part == "train" else 1
            for k in range(times):      # repeat = more weight for the real setup pictures
                name = stem + (f"__r{k}" if k else "")
                shutil.copy(img, os.path.join(out, part, "images", name + ".jpg"))
                shutil.copy(os.path.splitext(img)[0] + ".txt", os.path.join(out, part, "labels", name + ".txt"))
    yaml_path = os.path.join(out, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(f"path: {out.replace(os.sep, '/')}\ntrain: train/images\nval: val/images\n")
        if split["test"]:
            f.write("test: test/images\n")
        f.write("names:\n" + "".join(f"  {k}: {n}\n" for k, n in enumerate(names)))
    print(f"[saved] {yaml_path}")

    # ---- train
    os.makedirs(yl.MODELS_DIR, exist_ok=True)
    run_name = f"train_{vl.timestamp()}"
    model = YOLO(args.base)
    model.train(
        data=yaml_path, epochs=args.epochs, imgsz=imgsz, batch=args.batch, device="cpu",
        project=os.path.join(yl.MODELS_DIR, "runs"), name=run_name, patience=15,
        workers=0,                 # Windows: avoids multiprocessing problems
        fliplr=0.5, flipud=0.5,    # camera looks straight down: flipped pictures are still realistic
        degrees=10, plots=True, verbose=False,
    )
    best = os.path.join(yl.MODELS_DIR, "runs", run_name, "weights", "best.pt")
    if not os.path.exists(best):
        raise SystemExit("Training finished without best.pt - see the messages above.")
    shutil.copy(best, os.path.join(yl.MODELS_DIR, "best.pt"))
    print(f"\n[saved] {os.path.join(yl.MODELS_DIR, 'best.pt')}")

    # ---- results on validation (and test, if there is one)
    m = YOLO(os.path.join(yl.MODELS_DIR, "best.pt"))
    lines = [f"model {run_name}  base {args.base}  epochs {args.epochs}  imgsz {imgsz}",
             f"train {len(split['train'])}  val {len(split['val'])}  test {len(split['test'])}"]
    for part in ("val", "test"):
        if not split[part]:
            continue
        r = m.val(data=yaml_path, split=part, imgsz=imgsz, device="cpu", workers=0,
                  project=os.path.join(yl.MODELS_DIR, "runs"), name=f"{run_name}_{part}", verbose=False)
        lines.append(f"{part:5s}: precision {r.box.mp:.2f}  recall {r.box.mr:.2f}  "
                     f"mAP50 {r.box.map50:.2f}  mAP50-95 {r.box.map:.2f}")
    text = "\n".join(lines)
    print("\n" + text)
    with open(os.path.join(yl.MODELS_DIR, "training_log.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n\n")
    print("\nNext: python 13_yolo_detect.py")


if __name__ == "__main__":
    main()
