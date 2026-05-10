"""
SVG / DXF → list of polylines (mm coordinates), with laser operation classification.

K40 Whisperer color rules (matched exactly):
  Red stroke   #FF0000 ±tolerance  → Vector Cut
  Blue stroke  #0000FF ±tolerance  → Vector Engrave
  Non-white fill (any dark fill)   → Raster Engrave
  Default (no recognised colour)   → Vector Cut
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from typing import Iterator, Optional
from xml.etree import ElementTree as ET


# ─────────────────────────────────────────────────────────────────────
# Layered path — polyline + laser operation type
# ─────────────────────────────────────────────────────────────────────

@dataclass
class LayeredPath:
    """A polyline with its classified laser operation."""
    operation: str                               # "cut" | "engrave" | "raster"
    polyline:  list[tuple[float, float]]
    stroke:    Optional[tuple] = None            # (r,g,b) or None
    fill:      Optional[tuple] = None            # (r,g,b) or None

# SVG namespace
_NS = {"svg": "http://www.w3.org/2000/svg"}

CURVE_TOLERANCE = 0.1   # mm — max deviation when flattening curves
MM_PER_PX       = 0.264583   # 1 px = 0.264583 mm (96 dpi standard)


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

def file_to_polylines(file_path: str) -> list[list[tuple[float, float]]]:
    """Return all polylines from an SVG or DXF file (coordinates in mm)."""
    ext = file_path.lower().rsplit(".", 1)[-1]
    if ext == "svg":
        return svg_to_polylines(file_path)
    elif ext == "dxf":
        return dxf_to_polylines(file_path)
    return []


# ─────────────────────────────────────────────────────────────────────
# SVG parsing
# ─────────────────────────────────────────────────────────────────────

def svg_to_polylines(svg_path: str) -> list[list[tuple[float, float]]]:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    tag = root.tag
    ns  = ""
    if tag.startswith("{"):
        ns = tag.split("}")[0] + "}"

    scale = _svg_scale(root, ns)
    polylines: list[list[tuple[float, float]]] = []
    _walk(root, ns, scale, _IDENTITY, polylines)
    return [p for p in polylines if len(p) >= 2]


# ── Transform helpers ─────────────────────────────────────────────────
# Affine matrix as (a, b, c, d, e, f) matching SVG matrix(a,b,c,d,e,f)
# point (x,y) → (a*x + c*y + e,  b*x + d*y + f)

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mat_mul(m1, m2):
    a1,b1,c1,d1,e1,f1 = m1
    a2,b2,c2,d2,e2,f2 = m2
    return (
        a1*a2 + c1*b2,  b1*a2 + d1*b2,
        a1*c2 + c1*d2,  b1*c2 + d1*d2,
        a1*e2 + c1*f2 + e1,  b1*e2 + d1*f2 + f1,
    )


def _apply_m(m, x, y):
    a,b,c,d,e,f = m
    return (a*x + c*y + e,  b*x + d*y + f)


def _parse_transform(t: str) -> tuple:
    """Parse SVG transform string → affine matrix tuple."""
    t = t.strip()
    m = _IDENTITY
    # Handle chained transforms (applied right-to-left per SVG spec)
    for part in re.findall(r'\w+\s*\([^)]*\)', t):
        name = re.match(r'\w+', part).group()
        nums = [float(x) for x in re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', part)]
        if name == 'translate':
            tx = nums[0]; ty = nums[1] if len(nums) > 1 else 0.0
            local = (1,0,0,1,tx,ty)
        elif name == 'scale':
            sx = nums[0]; sy = nums[1] if len(nums) > 1 else nums[0]
            local = (sx,0,0,sy,0,0)
        elif name == 'matrix' and len(nums) == 6:
            local = tuple(nums)
        elif name == 'rotate':
            a = math.radians(nums[0])
            ca, sa = math.cos(a), math.sin(a)
            if len(nums) == 3:  # rotate(angle, cx, cy)
                cx2, cy2 = nums[1], nums[2]
                local = _mat_mul((ca,sa,-sa,ca,0,0),
                                 (1,0,0,1,-cx2,-cy2))
                local = _mat_mul((1,0,0,1,cx2,cy2), local)
            else:
                local = (ca,sa,-sa,ca,0,0)
        else:
            continue
        m = _mat_mul(m, local)
    return m


def _walk(elem, ns: str, scale: float, ctm: tuple, polylines: list):
    """Recursively walk SVG tree, accumulating transforms, collecting polylines."""
    local = elem.tag.replace(ns, "")

    # Accumulate this element's own transform
    t_str = elem.get("transform", "")
    m = _mat_mul(ctm, _parse_transform(t_str)) if t_str else ctm

    if local in ("g", "svg", "a", "symbol"):
        for child in elem:
            _walk(child, ns, scale, m, polylines)
        return

    # Skip non-drawing elements
    if local in ("defs", "namedview", "desc", "title",
                 "metadata", "marker", "pattern", "style"):
        return

    pts_raw = _elem_points_raw(elem, local)
    if pts_raw and len(pts_raw) > 1:
        # Apply CTM then convert to mm
        pts_mm = [(_apply_m(m, x, y)[0] * scale,
                   _apply_m(m, x, y)[1] * scale) for x, y in pts_raw]
        polylines.append(pts_mm)


def _svg_scale(root, ns: str) -> float:
    """Return mm-per-user-unit scale factor."""
    vb = root.get("viewBox", "")
    w  = root.get("width",  "")
    h  = root.get("height", "")

    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            vb_w = float(parts[2])
            vb_h = float(parts[3])
            if w and vb_w > 0:
                w_mm = _svg_length_to_mm(w)
                return w_mm / vb_w
    if w:
        return _svg_length_to_mm(w) / 744.09   # A4 default fallback
    return MM_PER_PX   # 1px = 0.2646mm


def _svg_length_to_mm(val: str) -> float:
    val = val.strip()
    units_map = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 0.352778,
                 "pc": 4.2333, "px": MM_PER_PX}
    for unit, factor in units_map.items():
        if val.endswith(unit):
            return float(val[:-len(unit)]) * factor
    try:
        return float(val) * MM_PER_PX
    except ValueError:
        return 0.0


def _elem_points_raw(elem, local: str) -> list[tuple[float, float]]:
    """Return element coordinates in raw SVG user units (no scaling, no transform)."""
    def f(v, d=0.0):
        try: return float(v or d)
        except: return d

    if local == "path":
        return _parse_path_d(elem.get("d", ""))

    if local == "line":
        return [(f(elem.get("x1")), f(elem.get("y1"))),
                (f(elem.get("x2")), f(elem.get("y2")))]

    if local in ("polyline", "polygon"):
        nums = [float(n) for n in re.split(r"[\s,]+", elem.get("points","").strip()) if n]
        pts  = [(nums[i], nums[i+1]) for i in range(0, len(nums)-1, 2)]
        if local == "polygon" and pts:
            pts.append(pts[0])
        return pts

    if local == "rect":
        x = f(elem.get("x",0));  y = f(elem.get("y",0))
        w = f(elem.get("width",0)); h = f(elem.get("height",0))
        rx = f(elem.get("rx",0)); ry = f(elem.get("ry",0))
        if rx == 0 and ry == 0:
            return [(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
        # Rounded rect — approximate as straight lines for laser
        return [(x+rx,y),(x+w-rx,y),(x+w,y+ry),(x+w,y+h-ry),
                (x+w-rx,y+h),(x+rx,y+h),(x,y+h-ry),(x,y+ry),(x+rx,y)]

    if local == "circle":
        return _circle_pts(f(elem.get("cx",0)), f(elem.get("cy",0)), f(elem.get("r",0)))

    if local == "ellipse":
        return _ellipse_pts(f(elem.get("cx",0)), f(elem.get("cy",0)),
                            f(elem.get("rx",0)), f(elem.get("ry",0)))
    return []


def _elem_to_polyline(elem, local: str, scale: float) -> list[tuple[float, float]]:
    """Legacy helper kept for any callers outside the walk."""
    pts = _elem_points_raw(elem, local)
    return [(x*scale, y*scale) for x, y in pts]


def _circle_pts(cx, cy, r, steps=64):
    return [(cx + r*math.cos(2*math.pi*i/steps),
             cy + r*math.sin(2*math.pi*i/steps)) for i in range(steps+1)]


def _ellipse_pts(cx, cy, rx, ry, steps=64):
    return [(cx + rx*math.cos(2*math.pi*i/steps),
             cy + ry*math.sin(2*math.pi*i/steps)) for i in range(steps+1)]


# ─────────────────────────────────────────────────────────────────────
# SVG path `d` attribute parser
# ─────────────────────────────────────────────────────────────────────

def _parse_path_d(d: str) -> list[tuple[float, float]]:
    """Parse SVG path d attribute → list of (x,y) points."""
    pts: list[tuple[float, float]] = []
    tokens = _tokenize_path(d)
    idx = 0
    cx, cy = 0.0, 0.0   # current position
    sx, sy = 0.0, 0.0   # last cubic bezier control point (for S)
    qx, qy = 0.0, 0.0   # last quadratic control point (for T)
    start_x, start_y = 0.0, 0.0
    cmd = "M"

    def n():
        nonlocal idx
        v = float(tokens[idx]); idx += 1; return v

    while idx < len(tokens):
        t = tokens[idx]
        if t and t[0].isalpha():
            cmd = t; idx += 1
        else:
            if cmd in "Mm": cmd = "Ll" if cmd == "M" else "ll"

        rel = cmd.islower()

        try:
            if cmd in "Mm":
                x = (cx if rel else 0) + n()
                y = (cy if rel else 0) + n()
                cx, cy = x, y; start_x, start_y = x, y
                pts.append((cx, cy))
                cmd = "l" if rel else "L"

            elif cmd in "Ll":
                x = (cx if rel else 0) + n()
                y = (cy if rel else 0) + n()
                cx, cy = x, y; pts.append((cx, cy))

            elif cmd in "Hh":
                x = (cx if rel else 0) + n()
                cx = x; pts.append((cx, cy))

            elif cmd in "Vv":
                y = (cy if rel else 0) + n()
                cy = y; pts.append((cx, cy))

            elif cmd in "Cc":
                x1=(cx if rel else 0)+n(); y1=(cy if rel else 0)+n()
                x2=(cx if rel else 0)+n(); y2=(cy if rel else 0)+n()
                ex=(cx if rel else 0)+n(); ey=(cy if rel else 0)+n()
                seg = _cubic_bezier(cx,cy,x1,y1,x2,y2,ex,ey)
                pts.extend(seg[1:]); sx,sy=x2,y2; cx,cy=ex,ey

            elif cmd in "Ss":
                x1=2*cx-sx; y1=2*cy-sy
                x2=(cx if rel else 0)+n(); y2=(cy if rel else 0)+n()
                ex=(cx if rel else 0)+n(); ey=(cy if rel else 0)+n()
                seg=_cubic_bezier(cx,cy,x1,y1,x2,y2,ex,ey)
                pts.extend(seg[1:]); sx,sy=x2,y2; cx,cy=ex,ey

            elif cmd in "Qq":
                x1=(cx if rel else 0)+n(); y1=(cy if rel else 0)+n()
                ex=(cx if rel else 0)+n(); ey=(cy if rel else 0)+n()
                seg=_quadratic_bezier(cx,cy,x1,y1,ex,ey)
                pts.extend(seg[1:]); qx,qy=x1,y1; cx,cy=ex,ey

            elif cmd in "Tt":
                x1=2*cx-qx; y1=2*cy-qy
                ex=(cx if rel else 0)+n(); ey=(cy if rel else 0)+n()
                seg=_quadratic_bezier(cx,cy,x1,y1,ex,ey)
                pts.extend(seg[1:]); qx,qy=x1,y1; cx,cy=ex,ey

            elif cmd in "Aa":
                rx_a=abs(n()); ry_a=abs(n())
                x_rot=n(); laf=int(n()); sf=int(n())
                ex=(cx if rel else 0)+n(); ey=(cy if rel else 0)+n()
                arc_pts = _arc_to_pts(cx, cy, rx_a, ry_a, x_rot, laf, sf, ex, ey)
                pts.extend(arc_pts[1:])
                cx, cy = ex, ey

            elif cmd in "Zz":
                pts.append((start_x, start_y)); cx,cy=start_x,start_y

        except (IndexError, ValueError):
            break

    return pts


def _arc_to_pts(x1, y1, rx, ry, phi_deg, large_arc, sweep, x2, y2) -> list[tuple]:
    """SVG endpoint arc → polyline using the standard W3C centre-parameterisation."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    # Step 1 — midpoint
    dx, dy = (x1-x2)/2, (y1-y2)/2
    x1p =  cp*dx + sp*dy
    y1p = -sp*dx + cp*dy
    # Ensure radii are large enough
    rx, ry = abs(rx), abs(ry)
    lam = (x1p/rx)**2 + (y1p/ry)**2
    if lam > 1:
        s = math.sqrt(lam); rx *= s; ry *= s
    # Step 2 — centre in rotated frame
    num = max(0.0, (rx*ry)**2 - (rx*y1p)**2 - (ry*x1p)**2)
    den = (rx*y1p)**2 + (ry*x1p)**2
    sq  = math.sqrt(num/den) if den > 0 else 0.0
    if large_arc == sweep: sq = -sq
    cxp =  sq * rx * y1p / ry
    cyp = -sq * ry * x1p / rx
    # Step 3 — centre in original frame
    cx = cp*cxp - sp*cyp + (x1+x2)/2
    cy = sp*cxp + cp*cyp + (y1+y2)/2
    # Step 4 — angles
    def _ang(ux, uy, vx, vy):
        n = math.hypot(ux,uy)*math.hypot(vx,vy)
        if n == 0: return 0.0
        c = max(-1.0, min(1.0, (ux*vx+uy*vy)/n))
        a = math.acos(c)
        return -a if ux*vy-uy*vx < 0 else a
    theta1 = _ang(1,0, (x1p-cxp)/rx, (y1p-cyp)/ry)
    dtheta = _ang((x1p-cxp)/rx,(y1p-cyp)/ry, (-x1p-cxp)/rx,(-y1p-cyp)/ry)
    if not sweep and dtheta > 0: dtheta -= 2*math.pi
    if sweep  and dtheta < 0: dtheta += 2*math.pi
    # Sample — number of steps from arc length vs tolerance
    steps = max(4, int(abs(dtheta) * max(rx,ry) / CURVE_TOLERANCE))
    result = []
    for i in range(steps+1):
        t  = theta1 + dtheta*i/steps
        ct, st = math.cos(t), math.sin(t)
        result.append((cp*rx*ct - sp*ry*st + cx,
                       sp*rx*ct + cp*ry*st + cy))
    return result


def _tokenize_path(d: str) -> list[str]:
    return re.findall(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", d)


def _cubic_bezier(x0,y0,x1,y1,x2,y2,x3,y3,tol=CURVE_TOLERANCE):
    pts = [(x0,y0)]
    _subdivide_cubic(x0,y0,x1,y1,x2,y2,x3,y3,pts,tol)
    return pts

def _subdivide_cubic(x0,y0,x1,y1,x2,y2,x3,y3,pts,tol):
    # Check flatness
    dx=x3-x0; dy=y3-y0
    d1=abs((x1-x0)*dy-(y1-y0)*dx)
    d2=abs((x2-x0)*dy-(y2-y0)*dx)
    l2=dx*dx+dy*dy
    if l2 > 0 and (d1*d1+d2*d2) <= tol*tol*l2:
        pts.append((x3,y3)); return
    # Split at t=0.5
    mx01=(x0+x1)/2; my01=(y0+y1)/2
    mx12=(x1+x2)/2; my12=(y1+y2)/2
    mx23=(x2+x3)/2; my23=(y2+y3)/2
    mx012=(mx01+mx12)/2; my012=(my01+my12)/2
    mx123=(mx12+mx23)/2; my123=(my12+my23)/2
    mx=(mx012+mx123)/2; my=(my012+my123)/2
    _subdivide_cubic(x0,y0,mx01,my01,mx012,my012,mx,my,pts,tol)
    _subdivide_cubic(mx,my,mx123,my123,mx23,my23,x3,y3,pts,tol)

def _quadratic_bezier(x0,y0,x1,y1,x2,y2,tol=CURVE_TOLERANCE):
    pts=[(x0,y0)]
    _subdivide_quad(x0,y0,x1,y1,x2,y2,pts,tol)
    return pts

def _subdivide_quad(x0,y0,x1,y1,x2,y2,pts,tol):
    dx=x2-x0; dy=y2-y0
    d=abs((x1-x0)*dy-(y1-y0)*dx)
    l2=dx*dx+dy*dy
    if l2>0 and d*d<=tol*tol*l2:
        pts.append((x2,y2)); return
    mx01=(x0+x1)/2; my01=(y0+y1)/2
    mx12=(x1+x2)/2; my12=(y1+y2)/2
    mx=(mx01+mx12)/2; my=(my01+my12)/2
    _subdivide_quad(x0,y0,mx01,my01,mx,my,pts,tol)
    _subdivide_quad(mx,my,mx12,my12,x2,y2,pts,tol)


# ─────────────────────────────────────────────────────────────────────
# DXF parsing
# ─────────────────────────────────────────────────────────────────────

def dxf_to_polylines(dxf_path: str) -> list[list[tuple[float, float]]]:
    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        polys = []
        for entity in msp:
            pts = _dxf_entity_to_pts(entity)
            if pts and len(pts) >= 2:
                polys.append(pts)
        return polys
    except Exception:
        return []


def _dxf_entity_to_pts(e) -> list[tuple[float, float]]:
    t = e.dxftype()
    try:
        if t == "LINE":
            s = e.dxf.start; en = e.dxf.end
            return [(s.x, s.y), (en.x, en.y)]

        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if e.is_closed and pts:
                pts.append(pts[0])
            return pts

        if t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if e.is_closed and pts:
                pts.append(pts[0])
            return pts

        if t == "CIRCLE":
            cx,cy=e.dxf.center.x,e.dxf.center.y; r=e.dxf.radius
            return _circle_pts(cx,cy,r)

        if t == "ARC":
            cx,cy=e.dxf.center.x,e.dxf.center.y; r=e.dxf.radius
            sa=math.radians(e.dxf.start_angle); ea=math.radians(e.dxf.end_angle)
            if ea < sa: ea += 2*math.pi
            steps = max(8, int((ea-sa)*r/0.5))
            return [(cx+r*math.cos(sa+(ea-sa)*i/steps),
                     cy+r*math.sin(sa+(ea-sa)*i/steps))
                    for i in range(steps+1)]

        if t == "ELLIPSE":
            cx,cy=e.dxf.center.x,e.dxf.center.y
            mx,my=e.dxf.major_axis.x,e.dxf.major_axis.y
            rx=math.hypot(mx,my); ry=rx*e.dxf.ratio
            angle=math.atan2(my,mx)
            return [(cx+rx*math.cos(angle+2*math.pi*i/64)*math.cos(0)
                       -ry*math.sin(angle+2*math.pi*i/64)*math.sin(0),
                     cy+rx*math.cos(angle+2*math.pi*i/64)*math.sin(0)
                       +ry*math.sin(angle+2*math.pi*i/64)*math.cos(0))
                    for i in range(65)]

        if t == "SPLINE":
            pts = list(e.flattening(0.1))
            return [(p.x, p.y) for p in pts]

    except Exception:
        pass
    return []


# ═════════════════════════════════════════════════════════════════════
# LAYER CLASSIFICATION  (K40 Whisperer colour rules)
# ═════════════════════════════════════════════════════════════════════

_NAMED_COLORS: dict[str, Optional[tuple]] = {
    "red":         (255,   0,   0),
    "lime":        (  0, 255,   0),
    "green":       (  0, 128,   0),
    "blue":        (  0,   0, 255),
    "black":       (  0,   0,   0),
    "white":       (255, 255, 255),
    "none":        None,
    "transparent": None,
}


def _parse_svg_color(s: str) -> Optional[tuple[int, int, int]]:
    """Parse any SVG colour string → (r,g,b) or None."""
    if not s:
        return None
    s = s.strip().lower()
    if s in _NAMED_COLORS:
        return _NAMED_COLORS[s]
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                pass
    m = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_style(style: str) -> dict[str, str]:
    """Parse a CSS-style attribute string → {property: value}."""
    result: dict[str, str] = {}
    for part in style.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip().lower()] = v.strip()
    return result


def _elem_colors(elem, parent_stroke=None, parent_fill=None):
    """Return effective (stroke_rgb, fill_rgb) for an element."""
    stroke_str = elem.get("stroke") or ""
    fill_str   = elem.get("fill")   or ""

    style_str = elem.get("style") or ""
    if style_str:
        smap = _parse_style(style_str)
        if "stroke" in smap:
            stroke_str = smap["stroke"]
        if "fill" in smap:
            fill_str   = smap["fill"]

    stroke = _parse_svg_color(stroke_str) if stroke_str else parent_stroke
    fill   = _parse_svg_color(fill_str)   if fill_str   else parent_fill
    return stroke, fill


def _classify(stroke, fill) -> str:
    """
    K40 Whisperer colour classification:
      Red stroke (#FF0000 ±tol)  → cut
      Blue stroke (#0000FF ±tol) → engrave
      Dark/non-white fill        → raster
      White fill + no stroke     → ignore  (invisible mask, skip it)
      Default                    → cut
    """
    if stroke:
        r, g, b = stroke
        if r > 200 and g < 50 and b < 50:
            return "cut"
        if r < 50 and g < 50 and b > 200:
            return "engrave"

    if fill:
        r, g, b = fill
        if r > 200 and g > 200 and b > 200:
            return "ignore"   # white/near-white, no stroke → invisible
        return "raster"       # any dark fill → raster engrave

    return "cut"   # default: uncoloured path → vector cut


def _walk_layered(elem, ns, scale, ctm, par_stroke, par_fill, results):
    """Recursively walk SVG tree, collecting LayeredPath objects."""
    local = elem.tag.replace(ns, "")

    # Skip hidden elements (display:none)
    style_str = elem.get("style") or ""
    if style_str:
        smap_check = _parse_style(style_str)
        if smap_check.get("display") == "none":
            return

    t_str = elem.get("transform", "")
    m = _mat_mul(ctm, _parse_transform(t_str)) if t_str else ctm

    stroke, fill = _elem_colors(elem, par_stroke, par_fill)

    if local in ("g", "svg", "a", "symbol"):
        for child in elem:
            _walk_layered(child, ns, scale, m, stroke, fill, results)
        return

    if local in ("defs", "namedview", "desc", "title",
                 "metadata", "marker", "pattern", "style"):
        return

    pts_raw = _elem_points_raw(elem, local)
    if pts_raw and len(pts_raw) > 1:
        pts_mm = [
            (_apply_m(m, x, y)[0] * scale, _apply_m(m, x, y)[1] * scale)
            for x, y in pts_raw
        ]
        op = _classify(stroke, fill)
        results.append(LayeredPath(
            operation=op, polyline=pts_mm,
            stroke=stroke, fill=fill,
        ))


# ─────────────────────────────────────────────────────────────────────
# Public: file → classified paths
# ─────────────────────────────────────────────────────────────────────

def file_to_layered_paths(file_path: str) -> list[LayeredPath]:
    """
    Parse SVG or DXF → list of LayeredPath objects, each classified as:
      'cut'     – red stroke  – Vector Cut
      'engrave' – blue stroke – Vector Engrave
      'raster'  – filled shape – Raster Engrave
    """
    ext = file_path.lower().rsplit(".", 1)[-1]
    if ext == "svg":
        return _svg_layered(file_path)
    elif ext == "dxf":
        return _dxf_layered(file_path)
    return []


def _svg_layered(svg_path: str) -> list[LayeredPath]:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    ns = ""
    tag = root.tag
    if tag.startswith("{"):
        ns = tag.split("}")[0] + "}"

    scale   = _svg_scale(root, ns)
    results: list[LayeredPath] = []
    _walk_layered(root, ns, scale, _IDENTITY, None, None, results)

    # Ensure raster paths are closed (required by scanline fill algorithm)
    for lp in results:
        if lp.operation == "raster" and len(lp.polyline) >= 2:
            if lp.polyline[0] != lp.polyline[-1]:
                lp.polyline = lp.polyline + [lp.polyline[0]]

    return [lp for lp in results
            if len(lp.polyline) >= 2 and lp.operation != "ignore"]


def _dxf_layered(dxf_path: str) -> list[LayeredPath]:
    """
    DXF classification (K40 Whisperer rules):
      ACI colour 5 (blue) → engrave
      Layer name contains 'engrave' → engrave
      Everything else → cut
    """
    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        results: list[LayeredPath] = []
        for entity in msp:
            pts = _dxf_entity_to_pts(entity)
            if not pts or len(pts) < 2:
                continue
            op = "cut"
            try:
                if entity.dxf.color == 5:
                    op = "engrave"
            except Exception:
                pass
            try:
                if "engrave" in entity.dxf.layer.lower():
                    op = "engrave"
            except Exception:
                pass
            results.append(LayeredPath(operation=op, polyline=pts))
        return results
    except Exception:
        return []
