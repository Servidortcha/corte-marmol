"""Lectura de piezas desde archivos DXF y exportacion del plano optimizado a DXF.

Unidades de entrada: se leen del encabezado ($INSUNITS) y se convierten a mm.
Soporta polilneas cerradas, lineas cosidas en contornos cerrados, circulos,
arcos y bloques (INSERT). Los contornos interiores (agujeros) se detectan por
contencion y se aplican como huecos del contorno exterior.
"""

import io

import ezdxf
import shapely.geometry as sg
from ezdxf.path import make_path

from .packing import _clean_polygon

_UNIT_SCALE = {0: 1.0, 1: 25.4, 2: 304.8, 3: 914.4, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 25.4}
_SKIP_LAYER = ("texto", "text", "dim", "cota", "título", "titulo", "rotulo", "title", "center", "aux")

_SUPPORTED = {
    "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "SPLINE", "ELLIPSE",
}


def _pt_close(a, b, tol=0.05):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _pt_dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _dedup_pts(pts):
    out = []
    for p in pts:
        if not out or not _pt_close(out[-1], p, 1e-6):
            out.append(p)
    if len(out) > 1 and _pt_close(out[0], out[-1], 1e-6):
        out = out[:-1]
    return out


def _contains(outer, inner):
    try:
        return outer.contains(inner.representative_point()) and inner.area < outer.area * 0.98
    except Exception:
        return False


def _stitch_loops(segments, tol=0.5):
    edges = []
    for layer, seg in segments:
        for a, b in zip(seg[:-1], seg[1:]):
            if _pt_dist(a, b) > tol:
                edges.append((layer, a, b))
    loops = []
    used = [False] * len(edges)
    for i in range(len(edges)):
        if used[i]:
            continue
        used[i] = True
        layer, a, b = edges[i]
        chain = [a, b]
        while True:
            last = chain[-1]
            found = False
            for j in range(len(edges)):
                if used[j]:
                    continue
                lj, x, y = edges[j]
                if _pt_dist(x, last) < tol:
                    nxt = y
                elif _pt_dist(y, last) < tol:
                    nxt = x
                else:
                    continue
                chain.append(nxt)
                used[j] = True
                found = True
                break
            if not found:
                break
        if len(chain) >= 3 and _pt_close(chain[0], chain[-1], tol):
            loops.append((layer, chain[:-1]))
    return loops


def _polygons_with_holes(loops, scale):
    polys = []
    for layer, pts in loops:
        poly = _clean_polygon(sg.Polygon([(x * scale, y * scale) for x, y in pts]))
        if poly is not None and poly.area >= 1.0:
            polys.append({"layer": layer, "poly": poly})

    # Procesar de mayor a menor: los contenedores ya estan en 'result'
    # cuando llega el turno de sus agujeros.
    polys.sort(key=lambda e: e["poly"].area, reverse=True)
    result = []
    for e in polys:
        p = e["poly"]
        container = None
        for o in result:
            if _contains(o["poly"], p):
                if container is None or o["poly"].area < container["poly"].area:
                    container = o
        if container is None:
            result.append({"layer": e["layer"], "poly": p})
        else:
            container["poly"] = container["poly"].difference(p)

    out = []
    for e in result:
        if e["poly"].is_empty:
            continue
        poly = _clean_polygon(e["poly"])
        if poly is not None:
            out.append((e["layer"], poly))
    return out


def parse_dxf_bytes(data: bytes):
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".dxf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            doc = ezdxf.readfile(path)
        except ezdxf.DXFStructureError:
            doc, _auditor = ezdxf.recover.readfile(path)
    finally:
        if os.path.exists(path):
            os.remove(path)

    scale = _UNIT_SCALE.get(doc.header.get("$INSUNITS", 0), 1.0)
    msp = doc.modelspace()

    loops = []
    segments = []

    def visit(e):
        if e.dxftype() == "INSERT":
            for v in e.virtual_entities():
                visit(v)
            return
        if e.dxftype() not in _SUPPORTED:
            return
        layer = (e.dxf.layer or "").strip()
        if any(k in layer.lower() for k in _SKIP_LAYER):
            return
        try:
            path = make_path(e)
        except Exception:
            return
        pts = _dedup_pts([(round(v.x, 3), round(v.y, 3)) for v in path.flattening(distance=1.0)])
        if len(pts) < 2:
            return
        if path.is_closed or _pt_close(pts[0], pts[-1]):
            if _pt_close(pts[0], pts[-1]):
                pts = pts[:-1]
            if len(pts) >= 3:
                loops.append((layer, pts))
        else:
            segments.append((layer, pts))

    for e in msp:
        visit(e)

    loops.extend(_stitch_loops(segments))
    polys = _polygons_with_holes(loops, scale)

    pieces = []
    counts = {}
    total_area = 0.0
    for layer, poly in polys:
        counts[layer or "0"] = counts.get(layer or "0", 0) + 1
        minx, miny, maxx, maxy = poly.bounds
        pieces.append({
            "name": layer or f"Pieza {counts[layer or '0']}",
            "width": round(maxx - minx, 3),
            "height": round(maxy - miny, 3),
            "area": round(poly.area, 3),
            "polygon": [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords[:-1]],
            "holes": [
                [[round(x, 3), round(y, 3)] for x, y in r.coords[:-1]]
                for r in poly.interiors
            ],
        })
        total_area += poly.area

    pieces.sort(key=lambda p: p["area"], reverse=True)
    return {
        "pieces": pieces,
        "stats": {
            "piece_count": len(pieces),
            "total_area": round(total_area, 3),
            "units": "mm",
        },
    }


def _offset_outline(pts, dist):
    try:
        poly = sg.Polygon(pts)
        if not poly.is_valid:
            return None
        cut = poly.buffer(dist, join_style=2)
        if cut.is_empty:
            return None
        if cut.geom_type == "MultiPolygon":
            cut = max(cut.geoms, key=lambda g: g.area)
        return [(round(x, 3), round(y, 3)) for x, y in cut.exterior.coords[:-1]]
    except Exception:
        return None


def export_result_dxf(slabs_used, kerf=0.0):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    doc.layers.add("PLANCHAS", color=8)
    doc.layers.add("PIEZAS", color=1)
    if kerf:
        doc.layers.add("CORTES", color=3)

    for slab in slabs_used:
        w, h = slab["width"], slab["height"]
        msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True,
                           dxfattribs={"layer": "PLANCHAS"})
        for p in slab["pieces"]:
            pts = p.get("polygon") or [
                (0, 0), (p["width"], 0),
                (p["width"], p["height"]), (0, p["height"]),
            ]
            pts = [(x + p["x"], y + p["y"]) for x, y in pts]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "PIEZAS"})
            for hole in p.get("holes") or []:
                hole_pts = [(x + p["x"], y + p["y"]) for x, y in hole]
                msp.add_lwpolyline(hole_pts, close=True,
                                   dxfattribs={"layer": "PIEZAS"})
            if kerf:
                cut = _offset_outline(pts, kerf / 2.0)
                if cut:
                    msp.add_lwpolyline(cut, close=True, dxfattribs={"layer": "CORTES"})

    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")
