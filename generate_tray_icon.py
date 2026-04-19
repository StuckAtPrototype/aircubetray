"""
Generate a branded AirCube icon (aircube_tray.ico).

Produces a multi-size Windows .ico file with sizes suitable for the
taskbar, window chrome, Explorer, and the large icon shown in
installers and the "About" dialog.

Run once (or whenever the design changes):
    python generate_tray_icon.py
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aircube_tray.ico")
BASE = 256
RADIUS = 44

# AQI "good" palette: green -> blue
TOP_COLOR = (76, 175, 80)      # #4CAF50
BOTTOM_COLOR = (33, 150, 243)  # #2196F3


def linear_gradient(size, top, bottom):
    """Vertical linear gradient image."""
    w, h = size
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        grad.putpixel((0, y), (r, g, b))
    return grad.resize((w, h), Image.BILINEAR)


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def load_bold_font(px):
    """Try to find a bold system font; fall back to default."""
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\seguibl.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_cube(draw, cx, cy, size, stroke_color, stroke_width):
    """Draw a stylized isometric cube outline centered at (cx, cy)."""
    # Isometric unit vectors (30 degrees)
    s = size / 2
    # 8 cube corners projected to 2D
    # Back bottom
    p_bbl = (cx - s, cy + s * 0.5)
    p_bbr = (cx + s, cy + s * 0.5)
    # Front bottom
    p_fbl = (cx - s, cy + s)
    p_fbr = (cx + s, cy + s)
    # Top back
    p_tbl = (cx - s, cy - s * 0.5)
    p_tbr = (cx + s, cy - s * 0.5)
    # Top front
    p_tfl = (cx - s, cy - s)
    p_tfr = (cx + s, cy - s)

    # Simpler isometric representation: three visible faces.
    # Top face (rhombus)
    top = [
        (cx, cy - s),
        (cx + s, cy - s * 0.5),
        (cx, cy),
        (cx - s, cy - s * 0.5),
    ]
    # Left face
    left = [
        (cx - s, cy - s * 0.5),
        (cx, cy),
        (cx, cy + s),
        (cx - s, cy + s * 0.5),
    ]
    # Right face
    right = [
        (cx, cy),
        (cx + s, cy - s * 0.5),
        (cx + s, cy + s * 0.5),
        (cx, cy + s),
    ]

    for poly in (top, left, right):
        draw.polygon(poly, outline=stroke_color, width=stroke_width)


def build_base_image():
    size = (BASE, BASE)

    # Background: rounded-square with vertical gradient
    gradient = linear_gradient(size, TOP_COLOR, BOTTOM_COLOR)
    mask = rounded_mask(size, RADIUS)

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    # Subtle inner highlight (top half slightly lighter)
    highlight = Image.new("RGBA", size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle((0, 0, BASE - 1, BASE // 2), radius=RADIUS, fill=(255, 255, 255, 30))
    img = Image.alpha_composite(img, Image.composite(highlight, Image.new("RGBA", size, (0, 0, 0, 0)), mask))

    # Draw cube in a translucent white
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    draw_cube(od, cx=BASE / 2, cy=BASE / 2 + 6, size=132, stroke_color=(255, 255, 255, 235), stroke_width=10)

    # Soft shadow behind cube for depth
    shadow = overlay.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, Image.eval(shadow, lambda v: v // 3 if v else v) if shadow.mode == "L" else shadow)
    img = Image.alpha_composite(img, overlay)

    # Bold "A" in the center
    text = "A"
    font = load_bold_font(150)
    td = ImageDraw.Draw(img)
    # Use textbbox for accurate centering
    bbox = td.textbbox((0, 0), text, font=font, stroke_width=4)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (BASE - tw) // 2 - bbox[0]
    ty = (BASE - th) // 2 - bbox[1] - 4

    # Drop shadow
    shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).text(
        (tx + 2, ty + 4), text, font=font, fill=(0, 0, 0, 120), stroke_width=4, stroke_fill=(0, 0, 0, 120)
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(3))
    img = Image.alpha_composite(img, shadow_layer)

    td = ImageDraw.Draw(img)
    td.text(
        (tx, ty), text, font=font, fill=(255, 255, 255, 255),
        stroke_width=4, stroke_fill=(40, 90, 120, 200),
    )

    # Re-apply the rounded mask to the alpha so nothing bleeds outside
    alpha = img.split()[3]
    alpha = Image.composite(alpha, Image.new("L", size, 0), mask)
    img.putalpha(alpha)

    return img


def main():
    print("Generating AirCube tray icon...")
    base = build_base_image()

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]

    # Pillow's ICO writer needs the base image large enough to downscale for each size.
    base.save(OUT_PATH, format="ICO", sizes=sizes)

    print(f"  wrote {OUT_PATH}")
    print(f"  sizes: {sizes}")
    print(f"  {os.path.getsize(OUT_PATH)} bytes")


if __name__ == "__main__":
    main()
