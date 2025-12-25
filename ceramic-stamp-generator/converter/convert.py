
"""
converter/convert.py
Minimal SVG -> STL ceramic stamp converter engine.

Design goal: robust-enough MVP for clean, vector-only SVGs (paths/rect/circle/ellipse/polygon/polyline).
- Rejects embedded raster (<image> tags or href=data:... to bitmap).
- Ensures minimum line thickness by buffering geometry.
- Extrudes a stamp base + raised/engraved relief.
- Writes a watertight STL.

NOTE: This is a practical MVP, not a perfect CAD kernel.
"""

from __future__ import annotations

import math
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import numpy as np

# Geometry stack
from shapely.geometry import Polygon, MultiPolygon, LineString, GeometryCollection, Point
from shapely.ops import unary_union
from shapely.affinity import translate, scale as shp_scale
from shapely import make_valid

# SVG parsing
from lxml import etree

# Meshing
import trimesh
from trimesh.creation import extrude_polygon, box

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

_ALLOWED_SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}

@dataclass
class DimensionReport:
    size_mm: float
    base_mm: float
    relief_mm: float
    mode: str
    bbox_mm: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy) in model units (mm)
    approx_area_mm2: float
    warnings: List[str]

class ConvertError(Exception):
    pass

def _has_raster_images(svg_root: etree._Element) -> bool:
    # <image> tags or href/data URLs pointing to common raster formats
    for el in svg_root.iter():
        tag = etree.QName(el).localname.lower()
        if tag == "image":
            return True
        # also check hrefs
        for attr in ("href", f"{{{XLINK_NS}}}href"):
            if attr in el.attrib:
                href = el.attrib.get(attr, "")
                if href.startswith("data:"):
                    # could be svg+xml (vector) OR raster. be conservative:
                    if "image/svg+xml" not in href:
                        return True
                if re.search(r"\.(png|jpg|jpeg|gif|bmp|webp)(\?|#|$)", href, re.I):
                    return True
    return False

def _parse_points(points: str) -> List[Tuple[float, float]]:
    pts = []
    if not points:
        return pts
    # split by spaces or commas
    raw = re.split(r"[\s,]+", points.strip())
    nums = [float(x) for x in raw if x]
    for i in range(0, len(nums) - 1, 2):
        pts.append((nums[i], nums[i+1]))
    return pts

def _path_to_linestring(d: str) -> Optional[LineString]:
    """
    MVP path parser: handles M/L/H/V/Z (absolute or relative).
    Curves are not supported in this MVP converter; they should be converted to paths with segments in design tool.
    """
    if not d:
        return None
    # tokenize commands/numbers
    tokens = re.findall(r"[MmLlHhVvZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    if not tokens:
        return None

    i = 0
    cmd = None
    x = y = 0.0
    start = None
    pts = []
    def read_num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[MmLlHhVvZz]$", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if start is not None:
                    pts.append(start)
                continue
        else:
            # implicit command repeat
            if cmd is None:
                raise ConvertError("SVG path has numbers before any command.")

        if cmd in "Mm":
            dx = read_num(); dy = read_num()
            if cmd == "m":
                x += dx; y += dy
            else:
                x, y = dx, dy
            start = (x, y)
            pts.append((x, y))
            # subsequent pairs treated as lineto
            cmd = "l" if cmd == "m" else "L"
        elif cmd in "Ll":
            dx = read_num(); dy = read_num()
            if cmd == "l":
                x += dx; y += dy
            else:
                x, y = dx, dy
            pts.append((x, y))
        elif cmd in "Hh":
            dx = read_num()
            if cmd == "h":
                x += dx
            else:
                x = dx
            pts.append((x, y))
        elif cmd in "Vv":
            dy = read_num()
            if cmd == "v":
                y += dy
            else:
                y = dy
            pts.append((x, y))
        elif cmd in "Zz":
            if start is not None:
                pts.append(start)
        else:
            raise ConvertError("Unsupported SVG path command. Please convert curves to line segments (no C/Q/A).")

    if len(pts) < 3:
        return None
    return LineString(pts)

def _extract_geometry(svg_bytes: bytes) -> Tuple[etree._Element, List[Any]]:
    try:
        root = etree.fromstring(svg_bytes)
    except Exception as e:
        raise ConvertError(f"Invalid SVG file: {e}")

    if _has_raster_images(root):
        raise ConvertError("The SVG contains embedded raster images. Please upload a vector-only SVG (no <image> tags).")

    geoms = []
    for el in root.iter():
        tag = etree.QName(el).localname.lower()
        if tag not in _ALLOWED_SHAPES:
            continue

        if tag == "path":
            d = el.attrib.get("d", "")
            ls = _path_to_linestring(d)
            if ls is not None:
                geoms.append(ls)
        elif tag == "rect":
            x = float(el.attrib.get("x", 0))
            y = float(el.attrib.get("y", 0))
            w = float(el.attrib.get("width", 0))
            h = float(el.attrib.get("height", 0))
            if w > 0 and h > 0:
                geoms.append(Polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)]))
        elif tag == "circle":
            cx = float(el.attrib.get("cx", 0))
            cy = float(el.attrib.get("cy", 0))
            r = float(el.attrib.get("r", 0))
            if r > 0:
                geoms.append(Point(cx, cy).buffer(r, resolution=64))
        elif tag == "ellipse":
            cx = float(el.attrib.get("cx", 0))
            cy = float(el.attrib.get("cy", 0))
            rx = float(el.attrib.get("rx", 0))
            ry = float(el.attrib.get("ry", 0))
            if rx > 0 and ry > 0:
                g = Point(cx, cy).buffer(1.0, resolution=64)
                geoms.append(shp_scale(g, xfact=rx, yfact=ry, origin=(cx, cy)))
        elif tag in ("polygon", "polyline"):
            pts = _parse_points(el.attrib.get("points", ""))
            if len(pts) >= 3:
                if tag == "polyline":
                    geoms.append(LineString(pts))
                else:
                    geoms.append(Polygon(pts))

    if not geoms:
        raise ConvertError("No vector paths/shapes found. Please export SVG with paths (not text/raster).")

    return root, geoms

def _normalize_to_size(geom, target_size_mm: float, warnings: List[str]) -> Any:
    # Fit geometry within target_size_mm square, preserving aspect ratio, centered at origin.
    minx, miny, maxx, maxy = geom.bounds
    w = maxx - minx
    h = maxy - miny
    if w <= 0 or h <= 0:
        raise ConvertError("SVG has invalid geometry bounds (zero area).")
    scale_factor = target_size_mm / max(w, h)
    if scale_factor <= 0:
        raise ConvertError("Could not compute scale factor from SVG bounds.")
    geom_s = shp_scale(geom, xfact=scale_factor, yfact=scale_factor, origin=(0,0))
    # translate to center at origin
    minx2, miny2, maxx2, maxy2 = geom_s.bounds
    cx = (minx2 + maxx2) / 2.0
    cy = (miny2 + maxy2) / 2.0
    geom_c = translate(geom_s, xoff=-cx, yoff=-cy)
    if scale_factor < 0.5:
        warnings.append("The SVG was scaled down significantly; very fine details may be lost in printing.")
    return geom_c

def _buffer_to_min_line(geom, min_line_mm: float, warnings: List[str]) -> Any:
    # Convert lines to polygons by buffering. Polygons are buffered slightly to ensure minimum wall.
    half = max(min_line_mm/2.0, 0.01)
    polys = []
    if isinstance(geom, (LineString,)):
        polys.append(geom.buffer(half, cap_style=2, join_style=2))
    elif isinstance(geom, (Polygon, MultiPolygon)):
        polys.append(geom.buffer(0))
    else:
        # attempt to buffer everything
        try:
            polys.append(geom.buffer(0))
        except Exception:
            pass

    u = unary_union(polys) if polys else geom
    # Ensure minimum thickness by buffering outward if geometry includes thin strokes (lines)
    try:
        u2 = u.buffer(0)  # clean
    except Exception:
        u2 = u
    if u2.is_empty:
        raise ConvertError("After processing, geometry became empty. Try increasing minimum line thickness.")
    if half > 1.0:
        warnings.append("Minimum line thickness is large; small details may be merged.")
    return u2

def _remove_small_holes(poly: Polygon, min_hole_area_mm2: float, warnings: List[str]) -> Polygon:
    if not poly.interiors:
        return poly
    keep = []
    removed = 0
    for ring in poly.interiors:
        hole = Polygon(ring)
        if hole.area >= min_hole_area_mm2:
            keep.append(ring)
        else:
            removed += 1
    if removed:
        warnings.append(f"Removed {removed} small hole(s) to improve printability.")
    return Polygon(poly.exterior, keep)

def _clean_geometry(geom, warnings: List[str]) -> MultiPolygon:
    # make valid, union, drop tiny fragments
    try:
        geom = make_valid(geom)
    except Exception:
        pass
    geom = unary_union(geom)
    # Ensure MultiPolygon
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    elif isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, Polygon)]
        geom = MultiPolygon(polys) if polys else MultiPolygon([])
    if geom.is_empty:
        raise ConvertError("Geometry is empty after union/cleanup. Ensure your SVG has closed shapes.")
    # remove small holes (heuristic)
    polys2 = []
    for p in geom.geoms:
        p2 = _remove_small_holes(p, min_hole_area_mm2= (0.35 * 0.35), warnings=warnings)  # ~0.12mm2
        polys2.append(p2)
    return MultiPolygon(polys2)

def convert_svg_to_stl(
    svg_bytes: bytes,
    out_stl_path: str | Path,
    *,
    size_mm: float = 30.0,
    mode: str = "raised",
    base_mm: float = 7.0,
    relief_mm: float = 2.2,
    min_line_mm: float = 1.4,
) -> DimensionReport:
    warnings: List[str] = []

    root, raw_geoms = _extract_geometry(svg_bytes)

    # unify to polygons: buffer lines, union all
    converted = []
    for g in raw_geoms:
        if isinstance(g, LineString):
            converted.append(g.buffer(max(min_line_mm/2.0, 0.01), cap_style=2, join_style=2))
        elif isinstance(g, Polygon):
            converted.append(g)
        else:
            try:
                converted.append(g.buffer(0))
            except Exception:
                pass

    geom = unary_union(converted)
    geom = _clean_geometry(geom, warnings)
    geom = _normalize_to_size(geom, float(size_mm), warnings)
    geom = _buffer_to_min_line(geom, float(min_line_mm), warnings)
    geom = _clean_geometry(geom, warnings)

    # mesh creation
    base = box(extents=(float(size_mm), float(size_mm), float(base_mm)))
    base.apply_translation((0, 0, float(base_mm)/2.0))

    # relief geometry union (may be multipolygon)
    relief_meshes = []
    for p in geom.geoms if isinstance(geom, MultiPolygon) else [geom]:
        if p.is_empty or p.area <= 0:
            continue
        try:
            m = extrude_polygon(p, height=float(relief_mm))
            # place on top of base
            m.apply_translation((0, 0, float(base_mm)))
            relief_meshes.append(m)
        except Exception as e:
            raise ConvertError(f"Could not extrude polygon: {e}")

    if not relief_meshes:
        raise ConvertError("No printable geometry after processing. Try increasing min line thickness or simplifying the SVG.")

    relief = trimesh.util.concatenate(relief_meshes)

    mode = (mode or "raised").lower()
    if mode not in ("raised", "engraved"):
        raise ConvertError("Mode must be 'raised' or 'engraved'.")

    if mode == "raised":
        stamp = trimesh.boolean.union([base, relief], engine="scad") if trimesh.interfaces.scad.exists else trimesh.util.concatenate([base, relief])
        if not trimesh.interfaces.scad.exists:
            warnings.append("OpenSCAD not found in container; exported as multi-solid STL (still printable).")
    else:
        # engraved: subtract relief volume from base (cut into base)
        cutter = relief.copy()
        cutter.apply_translation((0, 0, -float(relief_mm)))  # sink cutter down a bit
        if trimesh.interfaces.scad.exists:
            stamp = trimesh.boolean.difference([base, cutter], engine="scad")
        else:
            warnings.append("OpenSCAD not found in container; engraved mode approximated (no boolean).")
            stamp = base

    # validate mesh
    if stamp.is_empty:
        raise ConvertError("Mesh generation failed (empty).")
    stamp = stamp.process(validate=True)
    out_stl_path = Path(out_stl_path)
    out_stl_path.parent.mkdir(parents=True, exist_ok=True)
    stamp.export(out_stl_path)

    minx, miny, minz = stamp.bounds[0]
    maxx, maxy, maxz = stamp.bounds[1]
    report = DimensionReport(
        size_mm=float(size_mm),
        base_mm=float(base_mm),
        relief_mm=float(relief_mm),
        mode=mode,
        bbox_mm=(float(minx), float(miny), float(maxx), float(maxy)),
        approx_area_mm2=float(sum([p.area for p in geom.geoms])) if isinstance(geom, MultiPolygon) else float(geom.area),
        warnings=warnings,
    )
    return report

def cli():
    import argparse
    ap = argparse.ArgumentParser(description="Convert SVG to STL ceramic stamp.")
    ap.add_argument("svg", help="Input SVG file")
    ap.add_argument("out", help="Output STL file")
    ap.add_argument("--size-mm", type=float, default=30.0, choices=[25.0, 30.0, 40.0])
    ap.add_argument("--mode", type=str, default="raised", choices=["raised", "engraved"])
    ap.add_argument("--base-mm", type=float, default=7.0)
    ap.add_argument("--relief-mm", type=float, default=2.2)
    ap.add_argument("--min-line-mm", type=float, default=1.4)
    args = ap.parse_args()

    svg_bytes = Path(args.svg).read_bytes()
    rep = convert_svg_to_stl(
        svg_bytes, args.out,
        size_mm=args.size_mm, mode=args.mode, base_mm=args.base_mm,
        relief_mm=args.relief_mm, min_line_mm=args.min_line_mm
    )
    print(json.dumps(asdict(rep), indent=2))

if __name__ == "__main__":
    cli()
