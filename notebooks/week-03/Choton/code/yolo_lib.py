"""
yolo_lib.py - week 3: the trained YOLO model finds cards and candies.

Used by 13_yolo_detect.py and 14_pick_and_place.py (you do not run it directly).

Pipeline:  camera picture -> YOLO (class + box + score) -> centre of the box
           -> calibration (pixels -> robot X/Y) -> choose what goes in the box.

Each detected object is a dict:
    type   "card" / "candy"         (class name from the model)
    conf   0..1                      (model confidence)
    box    (x1, y1, x2, y2) pixels
    u, v   centre in pixels
    color  main colour of the object (e.g. "red") - used for "different colours"
    edge   True if the box touches the picture border (maybe cut off -> not picked)
    x_robot, y_robot, reachable      (only when calibrated)
"""

import os

import cv2
import numpy as np

import vision_lib as vl

CODE_DIR = vl.VISION_DIR
DATASET_DIR = os.path.abspath(os.path.join(CODE_DIR, "..", "dataset"))
MODELS_DIR = os.path.abspath(os.path.join(CODE_DIR, "..", "models"))

# colours used to draw each class (BGR)
CLASS_COLORS = [(0, 200, 255), (255, 120, 0), (0, 220, 0), (200, 0, 200), (0, 0, 255), (255, 255, 0)]


def class_names(settings=None):
    settings = settings or vl.load_settings()
    return settings.get("yolo", {}).get("classes", ["card", "candy"])


def model_path(settings=None):
    settings = settings or vl.load_settings()
    p = settings.get("yolo", {}).get("model", "models/best.pt")
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(CODE_DIR, "..", p))
    return p


def load_model(settings=None):
    """Load the trained model (models/best.pt). Needs:  pip install ultralytics"""
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("YOLO is not installed. Run:  pip install ultralytics")
    p = model_path(settings)
    if not os.path.exists(p):
        raise SystemExit(f"No trained model at {p}\nTrain one first:  python 12_train.py")
    return YOLO(p)


# ---------------------------------------------------------------------------
# Main colour of an object (for the "different colours in one box" rule)
# ---------------------------------------------------------------------------
HUE_NAMES = [(8, "red"), (22, "orange"), (35, "yellow"), (85, "green"),
             (100, "cyan"), (130, "blue"), (150, "purple"), (172, "pink"), (180, "red")]


def dominant_color(frame, box):
    """Name of the most common colour inside the middle of the box.
    Dark pixels (the black belt) are ignored."""
    x1, y1, x2, y2 = [int(round(c)) for c in box]
    w, h = x2 - x1, y2 - y1
    # middle 60 % of the box: less belt, less shadow
    crop = frame[max(0, y1 + int(0.2 * h)):max(0, y2 - int(0.2 * h)),
                 max(0, x1 + int(0.2 * w)):max(0, x2 - int(0.2 * w))]
    if crop.size == 0:
        return "unknown"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    bright = hsv[hsv[:, 2] > 60]
    if len(bright) < 20:
        return "black"
    colourful = bright[bright[:, 1] > 50]
    if len(colourful) < 0.25 * len(bright):
        return "white"
    hist = np.bincount(colourful[:, 0], minlength=180)
    hue = int(np.argmax(np.convolve(hist, np.ones(7), mode="same")))
    for limit, name in HUE_NAMES:
        if hue < limit:
            return name
    return "red"


# ---------------------------------------------------------------------------
# Angle of an object (how crooked it lies)
# ---------------------------------------------------------------------------
def object_angle(frame, box, pad=12):
    """Angle of the object's LONG side in the picture, degrees (-90..90], 0 = along the
    picture's x axis. YOLO only gives a straight box, so inside that box GrabCut separates
    the object from the belt, and cv2.minAreaRect fits a turned rectangle around it.
    Returns (angle_deg, corner_points) or None. About 70 ms per object."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = [int(round(c)) for c in box]
    X1, Y1, X2, Y2 = max(0, x1 - pad), max(0, y1 - pad), min(W, x2 + pad), min(H, y2 + pad)
    crop = frame[Y1:Y2, X1:X2]
    if crop.size == 0:
        return None
    s = min(1.0, 200.0 / max(crop.shape[:2]))          # small picture = fast
    small = cv2.resize(crop, None, fx=s, fy=s) if s < 1 else crop.copy()
    rect = (int((x1 - X1) * s), int((y1 - Y1) * s),
            max(2, int((x2 - x1) * s)), max(2, int((y2 - y1) * s)))
    mask = np.zeros(small.shape[:2], np.uint8)
    bgm, fgm = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(small, mask, rect, bgm, fgm, 4, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    m = ((mask == 1) | (mask == 3)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    (cx, cy), (w, h), a = cv2.minAreaRect(max(cnts, key=cv2.contourArea))
    pts = cv2.boxPoints(((cx, cy), (w, h), a)) / s + [X1, Y1]
    e1, e2 = pts[1] - pts[0], pts[2] - pts[1]
    long_side = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    ang = float(np.degrees(np.arctan2(long_side[1], long_side[0])))
    return wrap90(ang), pts


def wrap90(a):
    """Angle of a LINE: a and a+180 are the same, so keep it in (-90, 90]."""
    while a <= -90:
        a += 180
    while a > 90:
        a -= 180
    return a


def add_angle(frame, o, H=None):
    """Adds o["angle_img"] (picture) and, when calibrated, o["angle_robot"]
    (direction of the long side in robot X/Y, degrees)."""
    r = object_angle(frame, o["box"])
    if r is None:
        return
    o["angle_img"], o["corners"] = round(r[0], 1), r[1]
    if H is not None:
        a = np.radians(r[0])
        x0, y0 = vl.pixel_to_robot(H, o["u"], o["v"])
        x1, y1 = vl.pixel_to_robot(H, o["u"] + 50 * np.cos(a), o["v"] + 50 * np.sin(a))
        o["angle_robot"] = round(wrap90(float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))), 1)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def detect(frame, model, settings, H=None, conf=None):
    """Run YOLO on one picture and return a list of object dicts."""
    y = settings.get("yolo", {})
    conf = y.get("conf", 0.5) if conf is None else conf
    res = model.predict(frame, conf=conf, imgsz=y.get("imgsz", 640), verbose=False)[0]
    names = res.names
    hgt, wid = frame.shape[:2]
    margin = 3
    objects = []
    for b in res.boxes:
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
        o = {
            "type": names[int(b.cls)],
            "conf": round(float(b.conf), 2),
            "box": (x1, y1, x2, y2),
            "u": round((x1 + x2) / 2, 1),
            "v": round((y1 + y2) / 2, 1),
            "edge": x1 < margin or y1 < margin or x2 > wid - margin or y2 > hgt - margin,
        }
        o["color"] = dominant_color(frame, o["box"])
        add_robot_xy(o, settings, H)
        objects.append(o)
    return objects


def add_robot_xy(o, settings, H):
    if H is None:
        return
    x, y = vl.pixel_to_robot(H, o["u"], o["v"])
    o["x_mm"], o["y_mm"] = round(x, 1), round(y, 1)
    if settings.get("robot"):
        xr, yr = vl.table_to_robot(x, y, settings)
        o["x_robot"], o["y_robot"] = round(xr, 1), round(yr, 1)
        o["reachable"] = vl.in_reach(xr, yr, settings)
        zone = _belt_zone()
        if zone and not (zone[0] <= xr <= zone[1] and zone[2] <= yr <= zone[3]):
            o["reachable"] = False       # not on the belt (e.g. the box on the other conveyor)
            o["off_belt"] = True


_ZONE = {}


def _belt_zone(margin=20):
    """Pick area = the area of the calibration crosses + margin (mm), in robot X/Y.
    Objects outside it (the box, things on the other conveyor) are never picked."""
    if "z" not in _ZONE:
        cal = vl.load_json(vl.homography_file(), {})
        pts = cal.get("robot_points") if cal.get("frame") == "robot" else None
        if pts and len(pts) >= 4:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            _ZONE["z"] = (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)
        else:
            _ZONE["z"] = None
    return _ZONE["z"]


def detect_stable(src, model, settings, H=None, frames=8, min_seen=0.6, angles=True):
    """Detect on several pictures; keep objects found in most of them and use
    the MEDIAN centre (removes flicker). Returns (last_frame, objects)."""
    n = frames if src.image is None else 1
    per_frame, frame = [], None
    for _ in range(n):
        frame = src.read()
        per_frame.append(detect(frame, model, settings, H))
    tracks = []
    max_dist = 0.05 * frame.shape[1]
    for objs in per_frame:
        for o in objs:
            best = None
            for t in tracks:
                r = t[-1]
                if r["type"] == o["type"]:
                    d = np.hypot(r["u"] - o["u"], r["v"] - o["v"])
                    if d < max_dist and (best is None or d < best[0]):
                        best = (d, t)
            if best:
                best[1].append(o)
            else:
                tracks.append([o])
    objects = []
    for t in tracks:
        seen = len(t) / float(n)
        if seen < min_seen:
            continue
        u = float(np.median([o["u"] for o in t]))
        v = float(np.median([o["v"] for o in t]))
        o = dict(min(t, key=lambda k: (k["u"] - u) ** 2 + (k["v"] - v) ** 2))
        o["u"], o["v"], o["seen"] = round(u, 1), round(v, 1), round(seen, 2)
        o["conf"] = round(float(np.median([k["conf"] for k in t])), 2)
        add_robot_xy(o, settings, H)
        if angles:
            add_angle(frame, o, H)
        objects.append(o)
    objects.sort(key=lambda o: (round(o["v"] / 40), o["u"]))
    return frame, objects


# ---------------------------------------------------------------------------
# What goes into the box
# ---------------------------------------------------------------------------
def usable(o):
    return not o.get("edge") and o.get("reachable", True)


def next_pick(objects, placed, settings):
    """Choose the next object to pick.
    placed = list of objects already put in the box (dicts with type/color).
    Returns (object or None, message)."""
    want = settings.get("box_contents", {"card": 2, "candy": 2})
    diff = settings.get("require_different_colors", True)
    missing = []
    for kind, n in want.items():
        done = [p for p in placed if p["type"] == kind]
        if len(done) >= n:
            continue
        used_colors = {p["color"] for p in done}
        cands = [o for o in objects if o["type"] == kind and usable(o)]
        if diff:
            cands = [o for o in cands if o["color"] not in used_colors]
        if cands:
            return max(cands, key=lambda o: o["conf"]), f"{kind} {len(done) + 1}/{n}"
        missing.append(f"{n - len(done)} more {kind}(s)"
                       + (f" (colour not {sorted(used_colors)})" if diff and used_colors else ""))
    if not missing:
        return None, "box complete"
    return None, "need " + " and ".join(missing) + " - put them in the camera view, inside the robot reach"


def box_complete(placed, settings):
    want = settings.get("box_contents", {"card": 2, "candy": 2})
    return all(sum(p["type"] == k for p in placed) >= n for k, n in want.items())


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def summarize(objects):
    from collections import Counter
    c = Counter(o["type"] for o in objects if not o.get("edge"))
    text = "   ".join(f"{k}: {v}" for k, v in sorted(c.items())) or "nothing found"
    e = sum(1 for o in objects if o.get("edge"))
    if e:
        text += f"   at edge: {e}"
    return text


def draw(frame, objects, settings, H=None, highlight=None):
    out = frame.copy()
    names = class_names(settings)
    if H is not None and settings.get("robot"):
        try:
            vl.draw_reach(out, H, settings)
        except Exception:
            pass
    for o in objects:
        idx = names.index(o["type"]) if o["type"] in names else len(names)
        col = CLASS_COLORS[idx % len(CLASS_COLORS)]
        if o.get("edge") or not o.get("reachable", True):
            col = (140, 140, 140)
        x1, y1, x2, y2 = [int(c) for c in o["box"]]
        th = (4 if o is highlight else 2) * max(1, out.shape[0] // 700)   # thicker on big photos
        cv2.rectangle(out, (x1, y1), (x2, y2), col, th)
        cv2.drawMarker(out, (int(o["u"]), int(o["v"])), col, cv2.MARKER_CROSS, 14, 2)
        label = f'{o["type"]} {o["conf"]:.2f} {o["color"]}'
        if "corners" in o:                       # the turned rectangle and its angle
            cv2.polylines(out, [np.int32(o["corners"])], True, (0, 255, 255), max(1, th // 2))
            label += f' {o["angle_img"]:.0f}deg'
        if "x_robot" in o:
            label += f' ({o["x_robot"]:.0f},{o["y_robot"]:.0f})'
            if o.get("off_belt"):
                label += " NOT ON BELT"
            elif not o["reachable"]:
                label += " OUT OF REACH"
        if o.get("edge"):
            label += " EDGE"
        vl._put_label(out, label, (x1 + 2, max(15, y1 - 6)), col)
    vl._put_label(out, summarize(objects), (10, 22), (255, 255, 255))
    return out
