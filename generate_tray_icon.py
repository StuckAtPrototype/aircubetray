"""
Generate the branded AirCube app icons for all supported platforms.

Outputs (all written next to this script):
  - aircube_tray.ico   Windows multi-size icon
  - aircube_tray.icns  macOS multi-size icon (used in .app bundle)
  - aircube_tray.png   1024x1024 source PNG (used for Linux .desktop + AppImage)

Run once (or whenever the design changes):
    pip install Pillow>=10.0
    python generate_tray_icon.py
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ICO = os.path.join(HERE, "aircube_tray.ico")
OUT_ICNS = os.path.join(HERE, "aircube_tray.icns")
OUT_PNG = os.path.join(HERE, "aircube_tray.png")
BASE = 1024  # Source size; downscaled for each icon variant
SCALE = BASE / 256.0  # Original design was tuned at 256x256
RADIUS = int(44 * SCALE)

# VOC Level "good" palette: green -> blue
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

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    draw_cube(
        od,
        cx=BASE / 2,
        cy=BASE / 2 + 6 * SCALE,
        size=int(132 * SCALE),
        stroke_color=(255, 255, 255, 235),
        stroke_width=max(1, int(10 * SCALE)),
    )

    shadow = overlay.filter(ImageFilter.GaussianBlur(6 * SCALE))
    img = Image.alpha_composite(img, Image.eval(shadow, lambda v: v // 3 if v else v) if shadow.mode == "L" else shadow)
    img = Image.alpha_composite(img, overlay)

    text = "A"
    font = load_bold_font(int(150 * SCALE))
    td = ImageDraw.Draw(img)
    text_stroke = max(1, int(4 * SCALE))
    bbox = td.textbbox((0, 0), text, font=font, stroke_width=text_stroke)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (BASE - tw) // 2 - bbox[0]
    ty = (BASE - th) // 2 - bbox[1] - int(4 * SCALE)

    shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).text(
        (tx + int(2 * SCALE), ty + int(4 * SCALE)),
        text, font=font, fill=(0, 0, 0, 120),
        stroke_width=text_stroke, stroke_fill=(0, 0, 0, 120),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(3 * SCALE))
    img = Image.alpha_composite(img, shadow_layer)

    td = ImageDraw.Draw(img)
    td.text(
        (tx, ty), text, font=font, fill=(255, 255, 255, 255),
        stroke_width=text_stroke, stroke_fill=(40, 90, 120, 200),
    )

    # Re-apply the rounded mask to the alpha so nothing bleeds outside
    alpha = img.split()[3]
    alpha = Image.composite(alpha, Image.new("L", size, 0), mask)
    img.putalpha(alpha)

    return img


def main():
    print("Generating AirCube tray icon (Windows .ico + macOS .icns + Linux .png)...")
    base = build_base_image()

    # -- Windows .ico (multi-resolution) --
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    base.save(OUT_ICO, format="ICO", sizes=ico_sizes)
    print(f"  wrote {OUT_ICO}  ({os.path.getsize(OUT_ICO)} bytes, sizes={ico_sizes})")

    # -- macOS .icns (multi-resolution) --
    # Apple's Icon Composer formats: 16, 32, 128, 256, 512, 1024.
    # Pillow accepts a size list and produces an ICNS bundle with those variants.
    icns_sizes = [(1024, 1024), (512, 512), (256, 256), (128, 128), (32, 32), (16, 16)]
    try:
        base.save(OUT_ICNS, format="ICNS", sizes=icns_sizes)
        print(f"  wrote {OUT_ICNS}  ({os.path.getsize(OUT_ICNS)} bytes, sizes={icns_sizes})")
    except (OSError, ValueError) as exc:
        print(f"  SKIPPED {OUT_ICNS}: {exc}")
        print("           (Pillow's ICNS writer may require an up-to-date Pillow; run `pip install --upgrade Pillow`.)")

    # -- Cross-platform master PNG (for Linux AppImage / .desktop icon) --
    base.save(OUT_PNG, format="PNG", optimize=True)
    print(f"  wrote {OUT_PNG}  ({os.path.getsize(OUT_PNG)} bytes, {BASE}x{BASE})")


if __name__ == "__main__":
    main()
