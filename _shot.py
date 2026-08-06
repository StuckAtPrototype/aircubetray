"""Dev helper: maximize and screenshot the AirCube window via PrintWindow."""
import ctypes
import sys
import time
from ctypes import wintypes

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

title = sys.argv[1] if len(sys.argv) > 1 else "AirCube"
out = sys.argv[2] if len(sys.argv) > 2 else "window.png"
maximize = len(sys.argv) > 3 and sys.argv[3] == "max"

hwnd = user32.FindWindowW(None, title)
if not hwnd:
    print(f"window '{title}' not found")
    sys.exit(1)

if maximize:
    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    time.sleep(1.0)

rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top

hdc = user32.GetWindowDC(hwnd)
mem = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
gdi32.SelectObject(mem, bmp)
user32.PrintWindow(hwnd, mem, 2)


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


bmi = BMIH(biSize=ctypes.sizeof(BMIH), biWidth=w, biHeight=-h, biPlanes=1,
           biBitCount=32, biCompression=0)
buf = ctypes.create_string_buffer(w * h * 4)
gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).save(out)
print(f"saved {out} ({w}x{h})")

gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mem)
user32.ReleaseDC(hwnd, hdc)
