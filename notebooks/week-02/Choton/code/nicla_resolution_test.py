# Nicla Vision - resolution test  (version 3)
# Run in OpenMV IDE (USB cable, no Wi-Fi needed). Click Play and wait ~40 s.
# It tries bigger picture sizes and prints which ones work.
# Send the Serial Terminal output to Claude.

import csi
import time

print("=== resolution test v3 ===")

TESTS = [
    # name,                       pixformat,   framesize,  crop (w, h), one buffer?
    ("HVGA 480x320 (now)",        csi.RGB565,  csi.HVGA,   None,        False),
    ("HVGA 480x320 1 buffer",     csi.RGB565,  csi.HVGA,   None,        True),
    ("VGA 640x480 1 buffer",      csi.RGB565,  csi.VGA,    None,        True),
    ("VGA crop 560x400 1 buffer", csi.RGB565,  csi.VGA,    (560, 400),  True),
    ("SVGA crop 480x320 (zoom)",  csi.RGB565,  csi.SVGA,   (480, 320),  True),
    ("SVGA crop 640x400 (zoom)",  csi.RGB565,  csi.SVGA,   (640, 400),  True),
    ("VGA BAYER (raw)",           csi.BAYER,   csi.VGA,    None,        True),
]

for name, pf, fs, crop, one_buf in TESTS:
    step = "start"
    try:
        step = "CSI()"
        cam = csi.CSI()              # new camera object for every test
        step = "reset"
        cam.reset()
        step = "pixformat"
        cam.pixformat(pf)
        step = "framesize"
        cam.framesize(fs)
        if crop:
            step = "window"
            cam.window(crop)
        if one_buf:
            step = "framebuffers(1)"
            cam.framebuffers(1)
        step = "snapshot"
        img = cam.snapshot(time=1500)
        t0 = time.ticks_ms()
        n = 0
        while time.ticks_diff(time.ticks_ms(), t0) < 2000:
            img = cam.snapshot()
            n += 1
        print("OK   {:28s} -> {} x {}  {:.1f} fps".format(name, img.width(), img.height(), n / 2))
        try:
            j = img.to_jpeg(quality=90, copy=True)
            print("       JPEG q90 OK, {} kB".format(j.size() // 1024))
        except Exception as e:
            print("       JPEG q90 (copy) FAILED:", e)
    except Exception as e:
        print("FAIL {:28s} at step '{}': {}".format(name, step, e))
    time.sleep_ms(300)

print("DONE")
