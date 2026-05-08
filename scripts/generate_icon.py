"""
Run once before building to generate installer/icon.ico
Usage:  python scripts/generate_icon.py
Requires: pip install Pillow
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT   = Path(__file__).parent.parent / "installer" / "icon.ico"
OUT.parent.mkdir(exist_ok=True)

BG      = "#0d1117"
ACCENT  = "#58a6ff"
TEXT_C  = "#e6edf3"


def make_frame(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(2, size // 12)
    r   = max(3, size // 8)

    # Background rounded rect
    draw.rounded_rectangle([pad, pad, size-pad, size-pad],
                            radius=r, fill=BG)

    # Blue accent bar (left edge)
    bar_w = max(2, size // 10)
    draw.rounded_rectangle([pad, pad, pad + bar_w, size - pad],
                            radius=r, fill=ACCENT)

    # Text "M3D" for large sizes, "M" for small
    label = "M3D" if size >= 48 else ("M3" if size >= 32 else "M")
    fs    = max(6, int(size * 0.30))
    try:
        font = ImageFont.truetype("arialbd.ttf", fs)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", fs)
        except Exception:
            font = ImageFont.load_default()

    cx = (pad + bar_w + size) // 2
    cy = size // 2
    draw.text((cx, cy), label, fill=TEXT_C, font=font, anchor="mm")

    return img


frames = [make_frame(s) for s in SIZES]
frames[0].save(
    OUT, format="ICO",
    sizes=[(s, s) for s in SIZES],
    append_images=frames[1:]
)
print(f"Icon saved: {OUT}")
