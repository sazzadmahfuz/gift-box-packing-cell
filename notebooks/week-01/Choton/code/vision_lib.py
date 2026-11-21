"""
vision_lib.py - shared functions used by all the vision scripts.

You normally do NOT run this file directly. The numbered scripts
(01_camera_test.py, 02_hsv_tuner.py, ...) import it.
"""

import json
import os
import time

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Paths (everything is relative to this file, so it works from any folder)
# ---------------------------------------------------------------------------
VISION_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(VISION_DIR, "config")
# Screenshots go straight into the notebook's picture folder (Choton/images), so they can be used in the report
RESULTS_DIR = os.path.abspath(os.path.join(VISION_DIR, "..", "images"))
IMAGES_DIR = RESULTS_DIR  # photos from 01_camera_test.py


# ---------------------------------------------------------------------------
# Config files (simple JSON so you can open and edit them in any editor)
# ---------------------------------------------------------------------------
def load_json(name, default=None):
    path = os.path.join(CONFIG_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(name, data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[saved] {path}")


def load_settings():
    return load_json("settings.json", {})


def colors_file():
    """Each camera can have its own colour file (settings.json -> "colors_file")."""
    return load_settings().get("colors_file", "colors.json")


def homography_file():
    """Each camera needs its own calibration (settings.json -> "homography_file")."""
    return load_settings().get("homography_file", "homography.json")


def load_colors():
    return load_json(colors_file(), {})


def load_homography():
    data = load_json(homography_file())
    if data is None:
        return None
    return np.array(data["H"], dtype=np.float64)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
def open_camera(settings):
    """Open the camera given in settings.json (camera_index)."""
    index = settings.get("camera_index", 0)

    # Wi-Fi camera (e.g. ESP32 / XIAO ESP32S3 Sense running CameraWebServer):
    # put the stream address in settings.json, e.g. "camera_index": "http://192.168.1.50:81/stream"
    if isinstance(index, str):
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open the stream {index}. Check that the address opens in your "
                "web browser first, and that the laptop and camera are on the same Wi-Fi."
            )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep only the newest frame (less delay)
        return cap

    # On Windows the DirectShow backend opens USB cameras faster and more reliably.
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)  # try the default backend
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {index}. "
            "Try camera_index 1 or 2 in config/settings.json, "
            "and check the cable / that no other program (Teams, Camera app) uses it."
        )
    w, h = settings.get("frame_width"), settings.get("frame_height")
    if w and h:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    return cap


class FrameSource:
    """Gives frames either from the live camera or from a still image file.

    Using an image file lets you develop and test at home without the camera.
    """

    def __init__(self, image_path=None, settings=None):
        self.image = None
        self.cap = None
        if image_path:
            self.image = cv2.imread(image_path)
            if self.image is None:
                raise FileNotFoundError(f"Could not read image: {image_path}")
        else:
            self.settings = settings or load_settings()
            self.cap = open_camera(self.settings)
            # USB cameras give dark/blank pictures for the first moment after opening
            # (auto exposure is still adjusting), so throw those frames away.
            for _ in range(30):
                self.cap.read()

    def read(self):
        if self.image is not None:
            return self.image.copy()
        ok, frame = self.cap.read()
        if ok:
            return frame
        # Wi-Fi stream (Nicla): the camera closes the connection if we stop reading
        # for a few seconds (e.g. while typing in the terminal) -> just reconnect.
        if isinstance(self.settings.get("camera_index"), str):
            for attempt in range(5):
                print("Stream lost - reconnecting...")
                self.cap.release()
                time.sleep(1.0)
                try:
                    self.cap = open_camera(self.settings)
                except RuntimeError:
                    continue
                ok, frame = self.cap.read()
                if ok:
                    return frame
        raise RuntimeError("Camera returned no frame (cable unplugged / Wi-Fi lost?)")

    def release(self):
        if self.cap is not None:
            self.cap.release()


def crop_roi(frame, settings):
    """Cut the image down to the work area, if 'roi' is set in settings.json.

    roi = [x, y, width, height] in pixels, or null for the full image.
    Returns the cropped image and the (x, y) offset of the crop.
    """
    roi = settings.get("roi")
    if not roi:
        return frame, (0, 0)
    x, y, w, h = roi
    return frame[y:y + h, x:x + w], (x, y)


# ---------------------------------------------------------------------------
# Colour masks
# ---------------------------------------------------------------------------
def color_mask(hsv, ranges, settings):
    """Black/white image: white where the pixel colour is inside one of the HSV ranges."""
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
    k = settings.get("morph_kernel", 5)
    if k and k > 1:
        kernel = np.ones((k, k), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # remove small noise dots
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # fill small holes
    return mask


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def classify(area, aspect, settings, color_info=None):
    """Decide 'card' or 'candy'.

    1. If the colour in colors.json has "type": "card" / "candy", use that.
    2. Long and thin (long side / short side >= candy_min_aspect) -> candy.
       Your 3D-printed candies are bars (about 4-5 : 1), cards are about 1.4 : 1.
    3. Big and card-shaped -> card, small -> candy.
    Tune the numbers in settings.json (press 'p' in 03_detect.py to see area and aspect).
    """
    if color_info and color_info.get("type") in ("card", "candy"):
        return color_info["type"]
    if aspect >= settings.get("candy_min_aspect", 2.5):
        return "candy"
    if area >= settings.get("card_min_area", 15000):
        return "card"
    return "candy"


def pixel_to_robot(H, u, v):
    """Convert an image pixel (u, v) to robot (x, y) in millimetres using the homography."""
    pt = np.array([[[u, v]]], dtype=np.float64)
    x, y = cv2.perspectiveTransform(pt, H)[0][0]
    return float(x), float(y)


def solid_mask(mask, settings):
    """Turn a colour mask into solid object shapes.

    The pictures printed on the cards make holes in the card's colour mask.
    'close' joins small gaps, then every outline is filled completely,
    so a card with a printed Santa becomes ONE solid shape.
    """
    k = settings.get("close_kernel", 7)
    if k and k > 1:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled, contours


def merge_fragments(cands, settings):
    """Join pieces of ONE object that a glare line cut in two.

    Two shapes of the same colour are joined when they are close together
    (gap <= merge_gap pixels) AND they line up like one straight bar:
    the joined shape is not wider than the pieces and fills its rectangle well.
    Two separate cards lying side by side are NOT joined (the joined shape
    would be much wider than each card).
    """
    gap = settings.get("merge_gap", 30)
    if gap <= 0:
        return cands
    merged = True
    while merged:
        merged = False
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                a, b = cands[i], cands[j]
                # quick distance check between the two outlines
                pa = a["contour"].reshape(-1, 2).astype(np.float32)
                pb = b["contour"].reshape(-1, 2).astype(np.float32)
                d = np.min(np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2))
                if d > gap:
                    continue
                pts = np.vstack([pa, pb])
                hull = cv2.convexHull(pts.astype(np.int32))
                (_, (w, h), _) = cv2.minAreaRect(hull)
                short_joined = min(w, h)
                short_a = min(a["rect"][1])
                short_b = min(b["rect"][1])
                fill = (a["area"] + b["area"]) / max(w * h, 1)
                if short_joined <= 1.25 * max(short_a, short_b) and fill >= 0.75:
                    rect = cv2.minAreaRect(hull)
                    cands[i] = {"name": a["name"], "info": a["info"], "contour": hull,
                                "area": cv2.contourArea(hull), "rect": rect}
                    del cands[j]
                    merged = True
                    break
            if merged:
                break
    return cands


def scaled_settings(settings, frame):
    """The size limits in settings.json were tuned for a 1280 x 720 picture
    ("reference_size"). For another camera size (e.g. Nicla Vision 320 x 240)
    scale them, so the same settings work for every camera."""
    ref_w, ref_h = settings.get("reference_size", [1280, 720])
    h, w = frame.shape[:2]
    f_area = (w * h) / float(ref_w * ref_h)
    if abs(f_area - 1.0) < 0.05:
        return settings
    f_len = f_area ** 0.5
    s = dict(settings)
    for k in ("min_object_area", "card_min_area"):
        if k in s:
            s[k] = s[k] * f_area
    if "merge_gap" in s:
        s["merge_gap"] = s["merge_gap"] * f_len
    for k in ("blur", "morph_kernel", "close_kernel"):
        if k in s and s[k]:
            s[k] = max(3, int(round(s[k] * f_len)) | 1)
    return s


def detect_objects(frame, colors, settings, H=None):
    """Find all cards and candies in the frame.

    Returns a list of dicts, for example:
      {"type": "card", "color": "red", "u": 320, "v": 240, "angle": 12.5,
       "area": 24000, "aspect": 1.4, "x_mm": 123.4, "y_mm": -56.7, "box": [[..], ..]}
    (u, v) are pixel coordinates in the full image; x_mm/y_mm only appear
    after calibration (04_calibrate.py).
    """
    settings = scaled_settings(settings, frame)
    work, (ox, oy) = crop_roi(frame, settings)
    blur = settings.get("blur", 5)
    if blur and blur > 1:
        work = cv2.GaussianBlur(work, (blur | 1, blur | 1), 0)
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    min_area = settings.get("min_object_area", 3000)

    # 1) candidate shapes for every colour
    candidates = []
    for name, info in colors.items():
        mask = color_mask(hsv, info["ranges"], settings)
        _, contours = solid_mask(mask, settings)
        pieces = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue  # too small = noise
            (rc, (rw, rh), angle) = cv2.minAreaRect(c)
            if min(rw, rh) < 1:
                continue
            pieces.append({"name": name, "info": info, "contour": c, "area": area,
                           "rect": (rc, (rw, rh), angle)})
        candidates += merge_fragments(pieces, settings)

    # 2) drop shapes that lie INSIDE a bigger object
    #    (e.g. the red Santa printed on the green card)
    candidates.sort(key=lambda d: d["area"], reverse=True)
    kept = []
    for cand in candidates:
        (cx, cy), _, _ = cand["rect"]
        inside = False
        for big in kept:
            hull = cv2.convexHull(big["contour"])
            if cv2.pointPolygonTest(hull, (float(cx), float(cy)), False) >= 0:
                inside = True
                break
        if not inside:
            kept.append(cand)

    # 3) describe each object
    objects = []
    for cand in kept:
        c = cand["contour"]
        (rc, (rw, rh), angle) = cand["rect"]
        aspect = max(rw, rh) / min(rw, rh)
        kind = classify(cand["area"], aspect, settings, cand["info"])
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        u = M["m10"] / M["m00"] + ox
        v = M["m01"] / M["m00"] + oy
        box = cv2.boxPoints(((rc[0] + ox, rc[1] + oy), (rw, rh), angle))
        if rw < rh:  # make the angle describe the long side of the object
            angle += 90
        obj = {
            "type": kind,
            "color": cand["name"],
            "u": round(u, 1),
            "v": round(v, 1),
            "angle": round(angle % 180, 1),
            "area": int(cand["area"]),
            "aspect": round(aspect, 2),
            "box": np.round(box).astype(int).tolist(),
        }
        if H is not None:
            x, y = pixel_to_robot(H, u, v)
            obj["x_mm"], obj["y_mm"] = round(x, 1), round(y, 1)
            if settings.get("robot"):
                xr, yr = table_to_robot(x, y, settings)
                obj["x_robot"], obj["y_robot"] = round(xr, 1), round(yr, 1)
                obj["reachable"] = in_reach(xr, yr, settings)
        objects.append(obj)

    # Sort top-to-bottom, left-to-right so the list order is stable between frames
    objects.sort(key=lambda o: (round(o["v"] / 40), o["u"]))
    return objects


def draw_objects(frame, objects, colors, settings=None, H=None):
    """Draw boxes and labels on the image so you can see what was detected.
    If H (calibration) is given, the robot's reach area is drawn in yellow."""
    out = frame.copy()
    if H is not None and settings and settings.get("robot"):
        draw_reach(out, H, settings)
    if settings and settings.get("roi"):
        x, y, w, h = settings["roi"]
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 255), 1)
    for i, o in enumerate(objects):
        bgr = tuple(int(c) for c in colors.get(o["color"], {}).get("draw", [255, 255, 255]))
        pts = np.array(o["box"], dtype=np.int32)
        thickness = 3 if o["type"] == "card" else 2
        cv2.polylines(out, [pts], True, bgr, thickness)
        cu, cv_ = int(o["u"]), int(o["v"])
        cv2.drawMarker(out, (cu, cv_), (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
        bgr = tuple(min(255, c + 60) for c in bgr)  # lighter colour for text on dark label
        label = f"{i}:{o['color']} {o['type']}"
        if "x_robot" in o:
            label += f" robot({o['x_robot']:.0f},{o['y_robot']:.0f})"
            if not o["reachable"]:
                label += " OUT OF REACH"
        elif "x_mm" in o:
            label += f" ({o['x_mm']:.0f},{o['y_mm']:.0f})mm"
        _put_label(out, label, (cu + 8, cv_ - 8), bgr)
    summary = summarize(objects)
    _put_label(out, summary, (10, 25), (255, 255, 255))
    return out


# ---------------------------------------------------------------------------
# Robot (settings.json -> "robot")
# ---------------------------------------------------------------------------
def table_to_robot(x_mm, y_mm, settings):
    """Table mm (from 04_calibrate.py) -> robot X/Y in mm.

    TEMPORARY until we calibrate with the robot tip: the robot's (0, 0) is
    assumed to be at 'origin_on_table_mm' on the paper, with the same axis
    directions (use flip_x / flip_y if an axis points the other way).
    After calibrating with the robot tip, set origin to [0, 0] and no flips.
    """
    r = settings.get("robot", {})
    ox, oy = r.get("origin_on_table_mm", [0, 0])
    sx = -1 if r.get("flip_x") else 1
    sy = -1 if r.get("flip_y") else 1
    return sx * (x_mm - ox), sy * (y_mm - oy)


def robot_to_table(xr, yr, settings):
    r = settings.get("robot", {})
    ox, oy = r.get("origin_on_table_mm", [0, 0])
    sx = -1 if r.get("flip_x") else 1
    sy = -1 if r.get("flip_y") else 1
    return ox + sx * xr, oy + sy * yr


def in_reach(xr, yr, settings):
    """Delta robot working area is a circle: reach_radius_mm around the robot's (0, 0)."""
    r = settings.get("robot", {})
    return (xr ** 2 + yr ** 2) ** 0.5 <= r.get("reach_radius_mm", 180)


def draw_reach(img, H, settings):
    """Draw the circle the robot can reach (yellow) on the camera image."""
    r = settings["robot"]
    R = r.get("reach_radius_mm", 180)
    Hinv = np.linalg.inv(H)
    pts = []
    for a in np.linspace(0, 2 * np.pi, 120, endpoint=False):
        x, y = robot_to_table(R * np.cos(a), R * np.sin(a), settings)
        pts.append(cv2.perspectiveTransform(np.array([[[x, y]]], dtype=np.float64), Hinv)[0][0])
    pts = np.round(np.array(pts)).astype(np.int32)
    cv2.polylines(img, [pts], True, (0, 255, 255), 2)
    x0, y0 = robot_to_table(0, 0, settings)
    c = cv2.perspectiveTransform(np.array([[[x0, y0]]], dtype=np.float64), Hinv)[0][0]
    cv2.drawMarker(img, (int(c[0]), int(c[1])), (0, 255, 255), cv2.MARKER_TILTED_CROSS, 18, 2)
    _put_label(img, f"robot reach R={R:.0f} mm", (int(c[0]) + 10, int(c[1]) + 25), (0, 255, 255))


# ---------------------------------------------------------------------------
# Box planning (settings.json -> "box_contents")
# ---------------------------------------------------------------------------
def _take_colours(pool, n):
    """Take one object from each of n DIFFERENT colours (most plentiful first)."""
    available = [c for c in pool if pool[c]]
    if len(available) < n:
        return None
    available.sort(key=lambda c: len(pool[c]), reverse=True)
    return [pool[c].pop(0) for c in available[:n]]


def plan_boxes(objects, n_boxes, settings):
    """Every box gets box_contents["card"] cards and box_contents["candy"]
    candies, each of a different colour. Returns (boxes, problems)."""
    from collections import defaultdict
    want = settings.get("box_contents", {"card": 2, "candy": 2})
    pools = {"card": defaultdict(list), "candy": defaultdict(list)}
    for o in objects:
        pools[o["type"]][o["color"]].append(o)

    boxes, problems = [], []
    for b in range(1, n_boxes + 1):
        taken, missing = {}, []
        for kind in ("card", "candy"):
            n = want.get(kind, 0)
            got = _take_colours(pools[kind], n) if n else []
            if got is None:
                missing.append(f"{n} {'candies' if kind == 'candy' else 'cards'} of different colours")
            taken[kind] = got or []
        if missing:
            problems.append(f"Box {b}: not enough objects - missing {' and '.join(missing)}")
            for kind in ("card", "candy"):  # put back
                for o in taken[kind]:
                    pools[kind][o["color"]].insert(0, o)
            break
        boxes.append({"box": b, "items": taken["card"] + taken["candy"]})
    return boxes, problems


def best_snapshot(src, colors, settings, H=None, tries=10):
    """Look at several camera pictures and keep the one where the most objects
    are found (one single picture can be dark or blurred)."""
    best_frame, best_objs = None, None
    for _ in range(tries if src.image is None else 1):
        frame = src.read()
        objs = detect_objects(frame, colors, settings, H)
        if best_objs is None or len(objs) > len(best_objs):
            best_frame, best_objs = frame, objs
    return best_frame, best_objs


# ---------------------------------------------------------------------------
# Showing windows (small camera pictures are enlarged on screen)
# ---------------------------------------------------------------------------
DISPLAY_SCALE = 1.0   # last scale used by show(); mouse clicks are divided by it


def show(win, img):
    """Like cv2.imshow, but enlarges small pictures (e.g. Nicla 320 x 240)
    to about "display_width" pixels (settings.json, default 960) for viewing."""
    global DISPLAY_SCALE
    target = load_settings().get("display_width", 960)
    s = max(1.0, target / float(img.shape[1]))
    DISPLAY_SCALE = s
    if s != 1.0:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
    cv2.imshow(win, img)


def to_image_xy(x, y):
    """Convert a mouse click in an enlarged window back to picture pixels."""
    return int(x / DISPLAY_SCALE), int(y / DISPLAY_SCALE)


def summarize(objects):
    cards = [o["color"] for o in objects if o["type"] == "card"]
    candies = [o["color"] for o in objects if o["type"] == "candy"]
    return f"cards: {len(cards)} {sorted(cards)}   candies: {len(candies)} {sorted(candies)}"


def _put_label(img, text, org, color):
    """Text on a dark box so it is readable on any background."""
    font, thick = cv2.FONT_HERSHEY_SIMPLEX, 1
    scale = 0.55 if img.shape[1] >= 900 else 0.35   # smaller text on small pictures
    (tw, th), base = cv2.getTextSize(text, font, scale, thick)
    x, y = org
    cv2.rectangle(img, (x - 3, y - th - 4), (x + tw + 3, y + base + 2), (30, 30, 30), -1)
    cv2.putText(img, text, (x, y), font, scale, color, thick, cv2.LINE_AA)


def timestamp():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
