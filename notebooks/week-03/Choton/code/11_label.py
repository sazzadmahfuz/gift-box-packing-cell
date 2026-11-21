"""
STEP 11 - Label the training pictures (draw a box around every object and say
what it is). Works offline - same idea as Roboflow Annotate from the lecture.

    python 11_label.py                      (all sessions, starts at the first unlabelled picture)
    python 11_label.py --session home_nicla_1

The tool DRAWS THE BOXES FOR YOU (it compares the picture with the empty
background.jpg of the session) and guesses the class from the shape.
You only CHECK and CORRECT, then press n.

Mouse:
    drag            = draw a new box (with the current class)
    click in a box  = select it (thick box)
Keys:
    1 / 2 / ...     = class of the selected box (1 = card, 2 = candy, see settings.json "yolo" -> "classes")
    d               = delete the selected box
    TAB             = select the next box
    r               = redo the automatic boxes
    n or SPACE      = SAVE and go to the next picture
    b               = back to the previous picture
    s               = skip this picture (not used for training)
    q               = quit (the current picture is NOT saved - press n first)

Rules for good labels:
  - every card and candy fully or partly visible gets a box, tight around it
  - nothing else gets a box (hands, cables, belt marks)
  - a picture with NO objects is fine too: press n with no boxes
Labels are saved next to each picture as a .txt file in YOLO format:
    class  x_centre  y_centre  width  height     (all 0..1)
"""

import argparse
import glob
import os

import cv2
import numpy as np

import vision_lib as vl
import yolo_lib as yl

WIN = "11 label"


# ---------------------------------------------------------------------------
# automatic box proposals
# ---------------------------------------------------------------------------
def propose(img, background, names):
    h, w = img.shape[:2]
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    if background is not None and background.shape == img.shape:
        bg = cv2.GaussianBlur(background, (5, 5), 0)
        diff = cv2.absdiff(blur, bg).max(axis=2)
        mask = (diff > 35).astype(np.uint8) * 255
    else:
        # no background picture: take the COLOURFUL pixels (wrappers and cards are
        # colourful, the black belt and the grey aluminium are not)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 50)).astype(np.uint8) * 255
    k = max(3, int(round(w / 160)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    # fill the holes inside each object (dark print on a wrapper)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(mask)
    cv2.drawContours(mask, cnts, -1, 255, -1)
    # cut thin bridges between objects that almost touch
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3 * k, 3 * k)))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 60, 150)
    boxes = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.003 * w * h or area > 0.5 * w * h:
            continue
        (cx, cy), (rw, rh), _ = cv2.minAreaRect(c)
        aspect = max(rw, rh) / max(1.0, min(rw, rh))
        x, y, bw, bh = cv2.boundingRect(c)
        # guess the class: long thin = candy; otherwise a printed wrapper has many
        # edges inside, a plain card almost none (YOU still check every guess)
        inner = edges[y + bh // 5:y + bh - bh // 5, x + bw // 5:x + bw - bw // 5]
        printed = inner.size and inner.mean() / 255 > 0.045
        guess = "candy" if aspect >= 2.2 or printed else "card"
        cls = names.index(guess) if guess in names else 0
        boxes.append([cls, x, y, x + bw, y + bh])
    return boxes


# ---------------------------------------------------------------------------
# YOLO txt files
# ---------------------------------------------------------------------------
def label_path(img_path):
    return os.path.splitext(img_path)[0] + ".txt"


def read_labels(path, w, h):
    boxes = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) != 5:
                continue
            c, xc, yc, bw, bh = int(p[0]), *[float(v) for v in p[1:]]
            boxes.append([c, (xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h])
    return boxes


def write_labels(path, boxes, w, h):
    with open(path, "w", encoding="utf-8") as f:
        for c, x1, y1, x2, y2 in boxes:
            x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
            y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
            if x2 - x1 < 3 or y2 - y1 < 3:
                continue
            f.write(f"{c} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                    f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}\n")


# ---------------------------------------------------------------------------
class Labeler:
    def __init__(self, images, names):
        self.images, self.names = images, names
        self.i = 0
        self.cur_cls = 0
        self.drag = None
        self.load_first_unlabelled()

    def load_first_unlabelled(self):
        for k, p in enumerate(self.images):
            if not os.path.exists(label_path(p)) and not os.path.exists(p + ".skip"):
                self.i = k
                break
        self.load()

    def load(self):
        p = self.images[self.i]
        self.img = cv2.imread(p)
        h, w = self.img.shape[:2]
        bg_path = os.path.join(os.path.dirname(p), "background.jpg")
        self.bg = cv2.imread(bg_path) if os.path.exists(bg_path) else None
        if os.path.exists(label_path(p)):
            self.boxes, self.auto = read_labels(label_path(p), w, h), False
        else:
            self.boxes, self.auto = propose(self.img, self.bg, self.names), True
        self.sel = 0 if self.boxes else -1

    def mouse(self, event, x, y, flags, _):
        x, y = vl.to_image_xy(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drag = [x, y, x, y]
        elif event == cv2.EVENT_MOUSEMOVE and self.drag:
            self.drag[2], self.drag[3] = x, y
        elif event == cv2.EVENT_LBUTTONUP and self.drag:
            x1, y1, x2, y2 = self.drag
            self.drag = None
            if abs(x2 - x1) > 8 and abs(y2 - y1) > 8:
                self.boxes.append([self.cur_cls, min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
                self.sel = len(self.boxes) - 1
            else:  # click: select the smallest box under the mouse
                inside = [(abs((b[3] - b[1]) * (b[4] - b[2])), k) for k, b in enumerate(self.boxes)
                          if b[1] <= x <= b[3] and b[2] <= y <= b[4]]
                if inside:
                    self.sel = min(inside)[1]

    def view(self):
        out = self.img.copy()
        for k, (c, x1, y1, x2, y2) in enumerate(self.boxes):
            col = yl.CLASS_COLORS[c % len(yl.CLASS_COLORS)]
            cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), col, 4 if k == self.sel else 2)
            name = self.names[c] if c < len(self.names) else str(c)
            vl._put_label(out, f"{k + 1}:{name}", (int(x1) + 3, int(y1) + 18), col)
        if self.drag:
            x1, y1, x2, y2 = self.drag
            cv2.rectangle(out, (x1, y1), (x2, y2), (255, 255, 255), 1)
        done = sum(os.path.exists(label_path(p)) for p in self.images)
        p = self.images[self.i]
        state = "AUTO boxes - check them!" if self.auto else "saved labels"
        vl._put_label(out, f"{self.i + 1}/{len(self.images)}  labelled {done}  "
                           f"{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)}  [{state}]",
                      (8, 20), (255, 255, 255))
        keys = "  ".join(f"{k + 1}={n}" for k, n in enumerate(self.names))
        vl._put_label(out, f"{keys}  new box: {self.names[self.cur_cls]} | d=del TAB=next box "
                           "n=save+next b=back s=skip r=auto q=quit",
                      (8, out.shape[0] - 10), (0, 255, 255))
        return out

    def save(self):
        h, w = self.img.shape[:2]
        p = self.images[self.i]
        write_labels(label_path(p), self.boxes, w, h)
        if os.path.exists(p + ".skip"):
            os.remove(p + ".skip")
        print(f"[saved] {os.path.basename(label_path(p))}: {len(self.boxes)} boxes")

    def run(self):
        cv2.namedWindow(WIN)
        cv2.setMouseCallback(WIN, self.mouse)
        while True:
            vl.show(WIN, self.view())
            key = cv2.waitKey(20) & 0xFF
            if key == 255:
                continue
            if key == ord("q"):
                break
            if ord("1") <= key <= ord("9"):
                c = key - ord("1")
                if c < len(self.names):
                    self.cur_cls = c
                    if 0 <= self.sel < len(self.boxes):
                        self.boxes[self.sel][0] = c
            elif key == ord("d") and 0 <= self.sel < len(self.boxes):
                self.boxes.pop(self.sel)
                self.sel = min(self.sel, len(self.boxes) - 1)
            elif key == 9 and self.boxes:  # TAB
                self.sel = (self.sel + 1) % len(self.boxes)
            elif key == ord("r"):
                self.boxes, self.auto = propose(self.img, self.bg, self.names), True
                self.sel = 0 if self.boxes else -1
            elif key in (ord("n"), ord(" ")):
                self.save()
                if self.i == len(self.images) - 1:
                    print("That was the last picture. Next: python 12_train.py")
                    break
                self.i += 1
                self.load()
            elif key == ord("b") and self.i > 0:
                self.i -= 1
                self.load()
            elif key == ord("s"):
                p = self.images[self.i]
                open(p + ".skip", "w").close()
                if os.path.exists(label_path(p)):
                    os.remove(label_path(p))
                print(f"[skipped] {os.path.basename(p)}")
                if self.i < len(self.images) - 1:
                    self.i += 1
                    self.load()
        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="only this folder in dataset/raw/")
    args = ap.parse_args()
    names = yl.class_names()
    pattern = os.path.join(yl.DATASET_DIR, "raw", args.session or "*", "*.jpg")
    images = sorted(p for p in glob.glob(pattern) if os.path.basename(p) != "background.jpg")
    if not images:
        raise SystemExit(f"No pictures found ({pattern}). Take some with 10_collect_images.py first.")
    print(f"{len(images)} pictures. Classes: " + ", ".join(f"{k + 1}={n}" for k, n in enumerate(names)))
    Labeler(images, names).run()


if __name__ == "__main__":
    main()
