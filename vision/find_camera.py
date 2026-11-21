"""
Find the number of the USB camera.

    python find_camera.py

Opens camera 0, 1, 2, 3 and shows them side by side with their number.
Type the number of the USB camera (the one looking at the belt) and press ENTER:
it is saved in config/settings.json (cameras -> usb -> camera_index).
"""

import cv2
import numpy as np

import vision_lib as vl

tiles, found = [], []
for i in range(4):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    ok, frame = (cap.read() if cap.isOpened() else (False, None))
    for _ in range(10):                      # let the picture settle
        if ok:
            ok, f2 = cap.read()
            frame = f2 if ok else frame
    cap.release()
    if frame is None:
        continue
    found.append(i)
    t = cv2.resize(frame, (480, 270))
    cv2.rectangle(t, (0, 0), (150, 50), (0, 0, 0), -1)
    cv2.putText(t, f"camera {i}", (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    tiles.append(t)

if not tiles:
    raise SystemExit("No camera found - is the USB camera plugged in?")
print("Cameras found:", found)
cv2.imshow("cameras (press any key)", np.hstack(tiles))
cv2.waitKey(0)
cv2.destroyAllWindows()

num = input(f"Number of the USB camera {found}: ").strip()
if num.isdigit() and int(num) in found:
    raw = vl.load_json("settings.json", {})
    raw["cameras"]["usb"]["camera_index"] = int(num)
    vl.save_json("settings.json", raw)
    print(f"Saved: USB camera = {num}. Now run  python 13_yolo_detect.py")
else:
    print("Nothing changed.")
