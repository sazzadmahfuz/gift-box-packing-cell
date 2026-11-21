# Nicla Vision - Wi-Fi MJPEG camera stream for our vision code.
# Copy this file to the Nicla drive (D:) and name it  main.py
# Then unplug/plug the Nicla (OpenMV IDE closed). It starts by itself.
#
# LED:  RED = connecting to Wi-Fi   GREEN = connected, waiting   BLUE = sending video
# Open in browser / Python:  http://<IP>:8080   (IP is usually 172.20.10.3 on an iPhone hotspot)

import csi
import time
import network
import socket
import gc

SSID = "Enamul"      # hotspot name (exactly as on the phone)
KEY = "12345678"     # hotspot password
PORT = 8080
QUALITY = 90         # JPEG quality 10-95 (higher = sharper picture, more Wi-Fi load)
RESOLUTION = "VGA_CROP"  # "VGA_CROP" = 560 x 400 from the 640 x 480 sensor mode (best that fits, ~25 fps)
                         # "HVGA" = 480 x 320 (8 fps)   "QVGA" = 320 x 240
                         # Full 640 x 480 colour does NOT fit in the Nicla's memory (tested 6 Nov).


# ---------- LED helper (works on different firmware versions) ----------
def _make_leds():
    try:
        from machine import LED
        return {"r": LED("LED_RED"), "g": LED("LED_GREEN"), "b": LED("LED_BLUE")}
    except Exception:
        pass
    try:
        import pyb
        return {"r": pyb.LED(1), "g": pyb.LED(2), "b": pyb.LED(3)}
    except Exception:
        return {}


LEDS = _make_leds()


def led(colour):
    for k, l in LEDS.items():
        try:
            l.on() if k == colour else l.off()
        except Exception:
            pass


# ---------- camera ----------
cam = csi.CSI()
cam.reset()
cam.pixformat(csi.RGB565)
if RESOLUTION == "VGA_CROP":
    cam.framesize(csi.VGA)
    cam.window((560, 400))    # keep the middle 560 x 400 (the full 640 x 480 is too big for the memory)
    cam.framebuffers(1)       # one picture buffer only -> leaves memory for the bigger picture
elif RESOLUTION == "HVGA":
    cam.framesize(csi.HVGA)
else:
    cam.framesize(csi.QVGA)
cam.snapshot(time=2000)       # let exposure and white balance settle
print("picture size:", cam.snapshot().width(), "x", cam.snapshot().height())

# Lock the white balance so the colours stay the same in every picture
# (otherwise the camera keeps re-adjusting and the picture turns greenish on white paper).
# Put the cards and candies under the camera BEFORE starting, so it adjusts to them.
try:
    cam.auto_whitebal(False)
    print("white balance locked")
except Exception as e:
    print("could not lock white balance:", e)


# ---------- Wi-Fi ----------
wlan = network.WLAN(network.STA_IF)


def connect_wifi():
    led("r")
    wlan.active(True)
    try:
        wlan.config(pm=0xA11140)   # turn OFF Wi-Fi power saving (fixes CYW43 errors on many boards)
    except Exception as e:
        print("pm config not supported:", e)
    if not wlan.isconnected():
        wlan.connect(SSID, KEY)
        t0 = time.ticks_ms()
        while not wlan.isconnected():
            print('Trying to connect to "{}"...'.format(SSID))
            time.sleep_ms(1000)
            if time.ticks_diff(time.ticks_ms(), t0) > 30000:   # retry after 30 s
                wlan.disconnect()
                wlan.connect(SSID, KEY)
                t0 = time.ticks_ms()
    print("WiFi Connected ", wlan.ifconfig())


_q = [QUALITY]   # current JPEG quality (lowered automatically if memory runs out)


def compress(frame):
    """Compress the picture to JPEG in place. If memory runs out, lower the
    quality by 10 and try again (down to 40), and remember the working value."""
    while True:
        try:
            gc.collect()
            return frame.to_jpeg(quality=_q[0])
        except MemoryError:
            if _q[0] <= 40:
                raise
            _q[0] -= 10
            print("JPEG out of memory -> quality", _q[0])


def make_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    s.bind(["", PORT])
    s.listen(1)
    s.setblocking(True)
    return s


def stream(s):
    led("g")
    print("Waiting for connections..")
    client, addr = s.accept()
    client.settimeout(5.0)
    print("Connected to", addr[0])
    client.recv(1024)
    client.sendall(
        "HTTP/1.1 200 OK\r\n"
        "Server: OpenMV\r\n"
        "Content-Type: multipart/x-mixed-replace;boundary=openmv\r\n"
        "Cache-Control: no-cache\r\n"
        "Pragma: no-cache\r\n\r\n"
    )
    led("b")
    try:
        while True:
            frame = cam.snapshot()
            jpg = compress(frame)
            client.sendall(
                "\r\n--openmv\r\nContent-Type: image/jpeg\r\n"
                "Content-Length:" + str(jpg.size()) + "\r\n\r\n"
            )
            client.sendall(jpg)
    finally:
        client.close()


connect_wifi()
server = make_server()
while True:
    try:
        if not wlan.isconnected():
            connect_wifi()
        stream(server)
    except OSError as e:
        print("socket error:", e)   # viewer closed or Wi-Fi hiccup -> wait for the next viewer
        time.sleep_ms(200)
