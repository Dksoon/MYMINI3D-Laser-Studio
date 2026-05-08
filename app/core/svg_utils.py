"""SVG / DXF thumbnail generation with graceful fallbacks."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Optional

from app.core.config import get_thumbnails_dir

THUMB_SIZE = (200, 200)


def _thumb_path(source_path: str) -> Path:
    h = hashlib.md5(source_path.encode()).hexdigest()[:12]
    return get_thumbnails_dir() / f"{h}.png"


def get_thumbnail(file_path: str, force: bool = False) -> Optional[str]:
    """Return path to a PNG thumbnail for the given SVG/DXF file.
    Returns None if generation fails completely."""
    if not file_path or not Path(file_path).exists():
        return None

    out = _thumb_path(file_path)
    if out.exists() and not force:
        return str(out)

    ext = Path(file_path).suffix.lower()
    if ext == ".svg":
        return _thumb_svg(file_path, out)
    elif ext == ".dxf":
        return _thumb_dxf(file_path, out)
    return None


def _thumb_svg(src: str, out: Path) -> Optional[str]:
    # Try cairosvg first (best quality)
    try:
        import cairosvg
        cairosvg.svg2png(
            url=src,
            write_to=str(out),
            output_width=THUMB_SIZE[0],
            output_height=THUMB_SIZE[1],
        )
        return str(out)
    except Exception:
        pass

    # Try Pillow + wand (ImageMagick)
    try:
        from wand.image import Image as WandImage
        with WandImage(filename=src) as img:
            img.resize(*THUMB_SIZE)
            img.save(filename=str(out))
        return str(out)
    except Exception:
        pass

    # Fallback: render SVG outline placeholder with Pillow
    return _placeholder_thumb(src, out, color="#58a6ff", label="SVG")


def _thumb_dxf(src: str, out: Path) -> Optional[str]:
    try:
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        doc = ezdxf.readfile(src)
        msp = doc.modelspace()
        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        out_backend = MatplotlibBackend(ax)
        Frontend(ctx, out_backend).draw_layout(msp)
        fig.savefig(str(out), dpi=100, bbox_inches="tight",
                    facecolor="#161b22")
        plt.close(fig)
        return str(out)
    except Exception:
        pass

    return _placeholder_thumb(src, out, color="#d29922", label="DXF")


def _placeholder_thumb(src: str, out: Path, color: str, label: str) -> Optional[str]:
    """Generate a simple colored placeholder image with the filename."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", THUMB_SIZE, color="#161b22")
        draw = ImageDraw.Draw(img)

        # Colored border
        r, g, b = _hex_to_rgb(color)
        draw.rectangle([4, 4, THUMB_SIZE[0]-5, THUMB_SIZE[1]-5],
                       outline=(r, g, b), width=2)

        # Label badge
        draw.rectangle([60, 70, 140, 100], fill=(r, g, b, 80))
        try:
            font = ImageFont.truetype("arial.ttf", 18)
            small = ImageFont.truetype("arial.ttf", 11)
        except Exception:
            font = ImageFont.load_default()
            small = font

        draw.text((100, 85), label, fill=(255, 255, 255),
                  font=font, anchor="mm")

        # Filename (truncated)
        fname = Path(src).name
        if len(fname) > 22:
            fname = fname[:19] + "…"
        draw.text((100, 120), fname, fill="#8b949e",
                  font=small, anchor="mm")

        img.save(str(out), "PNG")
        return str(out)
    except Exception:
        return None


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def invalidate_thumbnail(file_path: str):
    """Delete cached thumbnail so it regenerates on next access."""
    if not file_path:
        return
    p = _thumb_path(file_path)
    if p.exists():
        p.unlink(missing_ok=True)
