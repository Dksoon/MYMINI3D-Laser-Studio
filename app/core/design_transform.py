"""
Design transforms applied before sending to laser.
Mirror X/Y, rotate 90°, scale — all per-machine settings.
Coordinates in mm.
"""
from __future__ import annotations
import math

Polylines = list[list[tuple[float, float]]]


def apply_transforms(
    polylines: Polylines,
    bed_w: float,
    bed_h: float,
    mirror_x: bool = False,
    mirror_y: bool = False,
    rotate_90: bool = False,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
) -> Polylines:
    """Apply all transforms in order: scale → mirror → rotate."""
    if not polylines:
        return polylines

    result = polylines

    # 1. Scale
    if x_scale != 1.0 or y_scale != 1.0:
        result = _scale(result, x_scale, y_scale)

    # 2. Mirror X (flip horizontally around bed centre)
    if mirror_x:
        result = _mirror_x(result, bed_w)

    # 3. Mirror Y (flip vertically around bed centre)
    if mirror_y:
        result = _mirror_y(result, bed_h)

    # 4. Rotate 90° clockwise around bed centre
    if rotate_90:
        result = _rotate_90(result, bed_w, bed_h)

    return result


# ── Transform primitives ──────────────────────────────────────────────

def _scale(polys: Polylines, sx: float, sy: float) -> Polylines:
    return [[(x * sx, y * sy) for x, y in poly] for poly in polys]


def _mirror_x(polys: Polylines, bed_w: float) -> Polylines:
    """Flip design horizontally: x → bed_w - x"""
    return [[(bed_w - x, y) for x, y in poly] for poly in polys]


def _mirror_y(polys: Polylines, bed_h: float) -> Polylines:
    """Flip design vertically: y → bed_h - y"""
    return [[(x, bed_h - y) for x, y in poly] for poly in polys]


def _rotate_90(polys: Polylines, bed_w: float, bed_h: float) -> Polylines:
    """Rotate 90° clockwise around bed centre.
    (x, y) → (bed_h - y, x)  after centering on new bed dimensions.
    """
    # After 90° CW: new_x = y, new_y = bed_w - x
    # New bed dimensions swap (w↔h)
    return [[(y, bed_w - x) for x, y in poly] for poly in polys]


def bbox(polys: Polylines) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) bounding box."""
    all_pts = [pt for poly in polys for pt in poly]
    if not all_pts:
        return 0.0, 0.0, 0.0, 0.0
    return (
        min(p[0] for p in all_pts),
        min(p[1] for p in all_pts),
        max(p[0] for p in all_pts),
        max(p[1] for p in all_pts),
    )


def translate_to_origin(polys: Polylines) -> Polylines:
    """Shift design so its top-left corner is at (0, 0)."""
    if not polys:
        return polys
    min_x, min_y, _, _ = bbox(polys)
    if min_x == 0.0 and min_y == 0.0:
        return polys
    return [[(x - min_x, y - min_y) for x, y in poly] for poly in polys]
