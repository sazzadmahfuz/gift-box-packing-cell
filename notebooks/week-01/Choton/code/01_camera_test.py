"""
STEP 1 - Camera test.

Opens the camera and shows the live picture.

    python 01_camera_test.py

Keys (click on the video window first):
    s  = save a photo to Choton/images/
    q  = quit

If the window stays black or you get an error, change "camera_index"
in config/settings.json to 1 (or 2) and try again.
"""

import os

import cv2

import vision_lib as vl


def main():
    settings = vl.load_settings()
    cap = vl.open_camera(settings)
    os.makedirs(vl.IMAGES_DIR, exist_ok=True)

    ok, frame = cap.read()
    if not ok:
        print("Camera opened but gave no picture. Try another camera_index.")
        return
    h, w = frame.shape[:2]
    print(f"Camera works. Resolution: {w} x {h}")
    print("Press 's' to save a photo, 'q' to quit.")

    saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Lost the camera picture.")
            break
        view = frame.copy()
        cv2.putText(view, f"{w}x{h}  saved: {saved}   [s]=save  [q]=quit", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        vl.show("01 camera test", view)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            path = os.path.join(vl.IMAGES_DIR, f"photo_{vl.timestamp()}.jpg")
            cv2.imwrite(path, frame)  # save the clean frame, without the text
            saved += 1
            print(f"[saved] {path}")
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
