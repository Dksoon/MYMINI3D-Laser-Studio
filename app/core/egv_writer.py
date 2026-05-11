"""
Lhymicro-GL (EGV) encoder for K40 M2 Nano controller.
Converts polylines (mm) → EGV byte stream ready to send via USB.

Protocol reference: K40 Whisperer (GPL v3), reverse-engineered Lhymicro-GL spec.
1 step = 1/1000 inch = 0.0254 mm
"""
from __future__ import annotations
import math

MM_PER_STEP  = 0.0254          # 1 step = 1/1000 inch
STEPS_PER_MM = 1.0 / MM_PER_STEP   # ≈ 39.37 steps/mm

# ── Direction encoding ────────────────────────────────────────────────
# Single-axis
DIR_TOP    = ord("T")   # Y-
DIR_BOTTOM = ord("B")   # Y+
DIR_LEFT   = ord("L")   # X-
DIR_RIGHT  = ord("R")   # X+
# Diagonal prefix
DIR_DIAG   = ord("M")

# Laser on/off
LASER_ON   = ord("D")
LASER_OFF  = ord("U")

# Packet markers
HEADER     = b"I"
FOOTER     = b"FNSE"

# ── Speed table for M2 Nano (mm/s → encoded byte) ────────────────────
# Values derived from K40 Whisperer's speed table
# Format: speed_mm_s → (speed_byte, step_byte)
_SPEED_TABLE = [
    (200, 0x09), (150, 0x0B), (100, 0x0E), (80, 0x10),
    (60,  0x12), (40,  0x15), (30,  0x17), (20,  0x1A),
    (15,  0x1C), (10,  0x1F), (8,   0x21), (5,   0x25),
    (3,   0x29), (2,   0x2C), (1,   0x31),
]


def speed_to_byte(speed_mm_s: float) -> int:
    """Return the closest speed byte for a given speed in mm/s."""
    best_byte = _SPEED_TABLE[-1][1]
    best_diff = float("inf")
    for spd, byte in _SPEED_TABLE:
        diff = abs(spd - speed_mm_s)
        if diff < best_diff:
            best_diff = diff
            best_byte = byte
    return best_byte


# ── EGV builder ───────────────────────────────────────────────────────

class EGVWriter:
    """
    Build an EGV byte stream from a list of polylines.

    Usage:
        writer = EGVWriter(speed_mm_s=20.0)
        for polyline in polylines:
            writer.cut_polyline(polyline)
        data = writer.build()
    """

    def __init__(self, speed_mm_s: float = 20.0, trace_only: bool = False):
        self._speed    = speed_mm_s
        self._trace    = trace_only   # if True: move without firing laser
        self._buf: list[int] = []
        self._x = 0   # current position in steps
        self._y = 0

    # ------------------------------------------------------------------ public

    def cut_polylines(self, polylines: list[list[tuple[float, float]]]) -> "EGVWriter":
        """Add all polylines. Call build() when done."""
        self._write_header()
        for poly in polylines:
            if len(poly) < 2:
                continue
            self._move_to(*poly[0])   # travel to start (laser off)
            if not self._trace:
                self._buf.append(LASER_ON)
            for pt in poly[1:]:
                self._line_to(*pt)
            if not self._trace:
                self._buf.append(LASER_OFF)
        self._write_footer()
        return self

    def trace_bounding_box(self, polylines: list[list[tuple[float, float]]]) -> "EGVWriter":
        """Trace the bounding box of all polylines without firing laser."""
        all_pts = [pt for poly in polylines for pt in poly]
        if not all_pts:
            return self
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)

        # Trace the rectangle
        box = [
            (min_x, min_y), (max_x, min_y),
            (max_x, max_y), (min_x, max_y),
            (min_x, min_y),
        ]
        self._write_header()
        self._move_to(*box[0])
        for pt in box[1:]:
            self._line_to(*pt)
        self._write_footer()
        return self

    def build(self) -> bytes:
        return bytes(self._buf)

    def estimate_steps(self, polylines: list[list[tuple[float, float]]]) -> int:
        """Estimate total steps (for progress tracking)."""
        total = 0
        prev = None
        for poly in polylines:
            for pt in poly:
                if prev:
                    dx = abs(pt[0] - prev[0]) * STEPS_PER_MM
                    dy = abs(pt[1] - prev[1]) * STEPS_PER_MM
                    total += int(max(dx, dy))
                prev = pt
        return max(1, total)

    # ------------------------------------------------------------------ internal

    def _write_header(self):
        spd = speed_to_byte(self._speed)
        # IS1V{spd}L1a$N — K40 Whisperer M2 Nano format
        self._buf += [ord("I"), ord("S"), ord("1"), ord("V"), spd,
                      ord("L"), ord("1"), ord("a"), ord("$"), ord("N")]

    def _write_footer(self):
        for c in b"FNSE":
            self._buf.append(c)

    def _move_to(self, x_mm: float, y_mm: float):
        """Travel to (x_mm, y_mm) with laser off."""
        tx = int(round(x_mm * STEPS_PER_MM))
        ty = int(round(y_mm * STEPS_PER_MM))
        self._encode_move(tx - self._x, ty - self._y, laser=False)
        self._x, self._y = tx, ty

    def _line_to(self, x_mm: float, y_mm: float):
        """Cut to (x_mm, y_mm) — laser already on."""
        tx = int(round(x_mm * STEPS_PER_MM))
        ty = int(round(y_mm * STEPS_PER_MM))
        self._encode_move(tx - self._x, ty - self._y, laser=True)
        self._x, self._y = tx, ty

    def _encode_move(self, dx: int, dy: int, laser: bool):
        """Encode a relative move as Lhymicro-GL direction bytes using Bresenham."""
        if dx == 0 and dy == 0:
            return

        # For travel moves, turn laser off first
        if not laser:
            self._buf.append(LASER_OFF)

        ax, ay = abs(dx), abs(dy)
        sx = DIR_RIGHT if dx >= 0 else DIR_LEFT
        sy = DIR_BOTTOM if dy >= 0 else DIR_TOP

        # Bresenham line algorithm → direction sequence
        if ax == 0:
            for _ in range(ay):
                self._buf.append(sy)
        elif ay == 0:
            for _ in range(ax):
                self._buf.append(sx)
        else:
            # Diagonal + remainder
            diag = min(ax, ay)
            for _ in range(diag):
                self._buf += [DIR_DIAG, sx, sy]
            rem_x = ax - diag
            rem_y = ay - diag
            for _ in range(rem_x):
                self._buf.append(sx)
            for _ in range(rem_y):
                self._buf.append(sy)


# ── Convenience function ──────────────────────────────────────────────

def polylines_to_egv(
    polylines: list[list[tuple[float, float]]],
    speed_mm_s: float = 20.0,
    trace_only: bool  = False,
) -> bytes:
    return EGVWriter(speed_mm_s, trace_only).cut_polylines(polylines).build()


def bounding_box_egv(
    polylines: list[list[tuple[float, float]]],
    speed_mm_s: float = 30.0,
) -> bytes:
    return EGVWriter(speed_mm_s, trace_only=True).trace_bounding_box(polylines).build()


# ── Raster (scanline) engrave ─────────────────────────────────────────

def _scanline_intersections(polylines: list, y: float) -> list[float]:
    """
    Ray-casting: find all X positions where horizontal line Y
    crosses the boundaries of the given closed polylines.
    """
    xs: list[float] = []
    for poly in polylines:
        n = len(poly)
        for i in range(n - 1):
            x1, y1 = poly[i]
            x2, y2 = poly[i + 1]
            if y1 == y2:
                continue                    # horizontal edge — skip
            if (y1 <= y < y2) or (y2 <= y < y1):
                t  = (y - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
    xs.sort()
    return xs


def raster_to_egv(
    polylines:        list[list[tuple[float, float]]],
    speed_mm_s:       float = 200.0,
    scanline_step_mm: float = 0.127,    # 0.005 inch — K40W default
    bottom_up:        bool  = False,
) -> bytes:
    """
    Generate raster engrave EGV from filled/closed shape polylines.
    Uses horizontal boustrophedon scan (alternates L→R / R→L per row).
    K40 Whisperer compatible scanline fill algorithm.
    """
    all_pts = [pt for poly in polylines for pt in poly]
    if not all_pts:
        return b""

    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)

    # Build Y scan positions
    y_vals: list[float] = []
    y = min_y
    while y <= max_y + scanline_step_mm * 0.5:
        y_vals.append(y)
        y += scanline_step_mm
    if bottom_up:
        y_vals = list(reversed(y_vals))

    writer  = EGVWriter(speed_mm_s=speed_mm_s)
    writer._write_header()
    has_any = False
    ltr     = True      # left-to-right flag; alternates each row

    for y in y_vals:
        xs = _scanline_intersections(polylines, y)
        if len(xs) < 2:
            continue

        # Build fill segments from intersection pairs
        segs: list[tuple[float, float]] = []
        for i in range(0, len(xs) - 1, 2):
            x0 = max(min_x, xs[i])
            x1 = min(max_x, xs[i + 1])
            if x1 > x0 + 1e-4:
                segs.append((x0, x1))

        if not segs:
            continue

        has_any = True
        if not ltr:
            segs = [(b, a) for a, b in reversed(segs)]

        for x_start, x_end in segs:
            writer._move_to(x_start, y)
            writer._buf.append(LASER_ON)
            writer._line_to(x_end, y)
            writer._buf.append(LASER_OFF)

        ltr = not ltr   # flip direction for next row

    if not has_any:
        return b""

    writer._write_footer()
    return writer.build()
