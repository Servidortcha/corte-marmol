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

_UNIT_SCALE = {
    0: 1.0, 1: 25.4, 2: 304.8, 3: 1609344.0, 4: 1.0,
    5: 10.0, 6: 1000.0, 7: 1000000.0, 8: 0.0000254,
    9: 0.001, 10: 914.4, 11: 0.0000001, 12: 0.000001,
    13: 0.001, 14: 100.0, 15: 10000.0, 16: 100000.0,
    17: 1000000000.0, 18: 149597870700000.0, 19: 3.085677581e19,
}
_SKIP_LAYER = (
    "texto", "text", "dim", "cota", "título", "titulo", "rotulo", "title",
    "center", "aux", "planchas", "cortes",
)

_NON_CUT_LINETYPES = {
    "DASHED", "DASHDOT", "DASHDOT2", "DASHDOTX2", "DASHED2",
    "DASHEDX2", "DIVIDE", "DOT", "DOT2", "DOTX2", "CENTER",
    "HIDDEN", "HIDDEN2", "HIDDENX2", "PHANTOM", "PHANTOM2",
    "PHANTOMX2", "BORDER", "BORDER2", "BORDERX2",
}

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
    """Cose segmentos en contornos cerrados conservando la capa de cada borde.

    Devuelve tuplas (layer, pts, edge_layers) donde edge_layers[i] es la capa
    del borde entre pts[i] y pts[(i+1) % len(pts)].
    """
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
        chain = [(layer, a), (layer, b)]
        while True:
            last = chain[-1]
            found = False
            for j in range(len(edges)):
                if used[j]:
                    continue
                lj, x, y = edges[j]
                if _pt_dist(x, last[1]) < tol:
                    nxt = (lj, y)
                elif _pt_dist(y, last[1]) < tol:
                    nxt = (lj, x)
                else:
                    continue
                chain.append(nxt)
                used[j] = True
                found = True
                break
            if not found:
                break
        if len(chain) >= 3 and _pt_close(chain[0][1], chain[-1][1], tol):
            pts = [p for _, p in chain[:-1]]
            edge_layers = [l for l, _ in chain[1:]] + [chain[0][0]]
            loops.append((layer, pts, edge_layers))
    return loops


def _polygons_with_holes(loops, scale):
    polys = []
    for layer, pts, edge_layers in loops:
        poly = _clean_polygon(sg.Polygon([(x * scale, y * scale) for x, y in pts]))
        if poly is not None and poly.area >= 1.0:
            lines = []
            for i, pt in enumerate(pts):
                nxt = pts[(i + 1) % len(pts)]
                lines.append((
                    edge_layers[i],
                    (pt[0] * scale, pt[1] * scale),
                    (nxt[0] * scale, nxt[1] * scale),
                ))
            polys.append({"layer": layer, "poly": poly, "lines": lines})

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
            result.append({"layer": e["layer"], "poly": p, "lines": e["lines"]})
        else:
            container["poly"] = container["poly"].difference(p)

    out = []
    for e in result:
        if e["poly"].is_empty:
            continue
        poly = _clean_polygon(e["poly"])
        if poly is not None:
            out.append((e["layer"], poly, e["lines"]))
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

    dashed_layers = set()
    for layer_entry in doc.layers:
        layer_name = layer_entry.dxf.name.strip()
        linetype = (layer_entry.dxf.linetype or "").strip().upper()
        if linetype in _NON_CUT_LINETYPES:
            dashed_layers.add(layer_name)

    loops = []
    segments = []
    seen_layers = set()
    ignored_layers = set()

    def visit(e):
        if e.dxftype() == "INSERT":
            for v in e.virtual_entities():
                visit(v)
            return
        if e.dxftype() not in _SUPPORTED:
            return
        layer = (e.dxf.layer or "").strip()
        if any(k in layer.lower() for k in _SKIP_LAYER):
            ignored_layers.add(layer)
            return
        if layer in dashed_layers:
            return
        entity_lt = e.dxf.get("linetype", "")
        if isinstance(entity_lt, str) and entity_lt.strip().upper() in _NON_CUT_LINETYPES:
            return
        seen_layers.add(layer)
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
                loops.append((layer, pts, [layer] * len(pts)))
        else:
            segments.append((layer, pts))

    for e in msp:
        visit(e)

    loops.extend(_stitch_loops(segments))
    polys = _polygons_with_holes(loops, scale)

    layers_colors = {
        layer_entry.dxf.name.strip(): layer_entry.dxf.color
        for layer_entry in doc.layers
    }

    pieces = []
    counts = {}
    total_area = 0.0
    for layer, poly, piece_lines in polys:
        counts[layer or "0"] = counts.get(layer or "0", 0) + 1
        minx, miny, maxx, maxy = poly.bounds
        pieces.append({
            "name": f"{layer or 'Pieza'} {counts[layer or '0']}",
            "width": round(maxx - minx, 3),
            "height": round(maxy - miny, 3),
            "area": round(poly.area, 3),
            "quantity": 1,
            "polygon": [[round(x - minx, 3), round(y - miny, 3)]
                        for x, y in poly.exterior.coords[:-1]],
            "holes": [
                [[round(x - minx, 3), round(y - miny, 3)]
                 for x, y in r.coords[:-1]]
                for r in poly.interiors
            ],
            "lines": [
                [line_layer, round(x1 - minx, 3), round(y1 - miny, 3),
                 round(x2 - minx, 3), round(y2 - miny, 3)]
                for line_layer, (x1, y1), (x2, y2) in piece_lines
            ],
        })
        total_area += poly.area

    pieces.sort(key=lambda p: p["area"], reverse=True)
    return {
        "pieces": pieces,
        "stats": {
            "piece_count": len(pieces),
            "total_quantity": len(pieces),
            "total_area": round(total_area, 3),
            "units": "mm",
            "layers": sorted(layer for layer in seen_layers if layer),
            "ignored_layers": sorted(layer for layer in ignored_layers if layer),
            "layers_colors": layers_colors,
        },
    }


def export_result_dxf(slabs_used, kerf=0.0, layer_colors=None):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    doc.layers.add("PLANCHAS", color=8)
    doc.layers.add("PIEZAS", color=1)
    doc.layers.add("AGUJEROS", color=5)
    doc.layers.add("OBSTACULOS", color=6)
    doc.layers.add("ETIQUETAS", color=2)
    for name, color in (layer_colors or {}).items():
        clean = (name or "").strip()
        if clean and clean not in doc.layers:
            doc.layers.add(clean, color=color)

    gap = 250.0
    offset_x = 0.0
    for slab_index, slab in enumerate(slabs_used, start=1):
        w, h = slab["width"], slab["height"]
        msp.add_lwpolyline([(offset_x, 0), (offset_x + w, 0),
                            (offset_x + w, h), (offset_x, h)], close=True,
                           dxfattribs={"layer": "PLANCHAS"})
        msp.add_text(
            f"PLANCHA {slab_index}: {slab.get('name', 'Plancha')}",
            dxfattribs={"layer": "ETIQUETAS", "height": 40},
        ).set_placement((offset_x, h + 60))
        for hole in slab.get("holes") or []:
            hole_pts = [(x + offset_x, y) for x, y in hole]
            msp.add_lwpolyline(hole_pts, close=True,
                               dxfattribs={"layer": "OBSTACULOS"})
        for piece_index, p in enumerate(slab["pieces"], start=1):
            pts = p.get("polygon") or [
                (0, 0), (p["width"], 0),
                (p["width"], p["height"]), (0, p["height"]),
            ]
            lines = p.get("lines") or []
            if lines:
                for line in lines:
                    line_layer, x1, y1, x2, y2 = line
                    msp.add_line(
                        (x1 + p["x"] + offset_x, y1 + p["y"]),
                        (x2 + p["x"] + offset_x, y2 + p["y"]),
                        dxfattribs={"layer": line_layer or "PIEZAS"},
                    )
            else:
                outline = [(x + p["x"] + offset_x, y + p["y"]) for x, y in pts]
                msp.add_lwpolyline(outline, close=True,
                                   dxfattribs={"layer": "PIEZAS"})
            for hole in p.get("holes") or []:
                hole_pts = [(x + p["x"] + offset_x, y + p["y"]) for x, y in hole]
                msp.add_lwpolyline(hole_pts, close=True,
                                   dxfattribs={"layer": "AGUJEROS"})
            label_x = offset_x + p["x"] + p["width"] / 2
            label_y = p["y"] + p["height"] / 2
            msp.add_text(
                f"{piece_index}: {p.get('name', 'Pieza')}",
                dxfattribs={"layer": "ETIQUETAS", "height": 25},
            ).set_placement((label_x, label_y), align=ezdxf.enums.TextEntityAlignment.CENTER)
        offset_x += w + gap

    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")
