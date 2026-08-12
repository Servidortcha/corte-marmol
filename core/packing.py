"""Optimizacion de corte 2D: empaquetado en planchas variables con hoja de sierra.

Estrategia: colocacion "bottom-left" (posicion mas baja, luego mas a la izquierda)
probando ambas orientaciones, sobre varias planchas de tamaños distintos.
La hoja de sierra (kerf) se modela como una separacion obligatoria entre piezas.
"""

from dataclasses import dataclass, field


@dataclass
class PlacedPiece:
    name: str
    width: float
    height: float
    x: float
    y: float
    rotated: bool = False


@dataclass
class BinResult:
    name: str
    width: float
    height: float
    pieces: list = field(default_factory=list)
    used_area: float = 0.0
    waste_area: float = 0.0
    utilization: float = 0.0
    unplaced_after: int = 0


def _find_position(width, height, kerf, bin_w, bin_h, placed):
    """Posicion bottom-left (menor y, luego menor x) libre para un rectangulo."""
    xs = {0.0}
    ys = {0.0}
    for p in placed:
        xs.add(p.x + p.width + kerf)
        ys.add(p.y + p.height + kerf)
    if width > bin_w or height > bin_h:
        return None
    best = None
    for x in xs:
        for y in ys:
            if x + width > bin_w + 1e-9 or y + height > bin_h + 1e-9:
                continue
            ok = True
            for p in placed:
                if (x < p.x + p.width + kerf and p.x < x + width + kerf and
                        y < p.y + p.height + kerf and p.y < y + height + kerf):
                    ok = False
                    break
            if ok and (best is None or (y, x) < (best[1], best[0])):
                best = (x, y)
    return best


def _place_in_bin(bin_w, bin_h, kerf, allow_rotation, items):
    placed = []
    remaining = []
    for it in items:
        options = [(it["w"], it["h"], False)]
        if allow_rotation:
            options.append((it["h"], it["w"], True))
        best_pos = None
        best_w = best_h = None
        best_rot = False
        for w, h, rot in options:
            pos = _find_position(w, h, kerf, bin_w, bin_h, placed)
            if pos is not None and (best_pos is None or (pos[1], pos[0]) < (best_pos[1], best_pos[0])):
                best_pos = pos
                best_w, best_h, best_rot = w, h, rot
        if best_pos is None:
            remaining.append(it)
            continue
        placed.append(PlacedPiece(
            name=it["name"],
            width=best_w,
            height=best_h,
            x=best_pos[0],
            y=best_pos[1],
            rotated=best_rot,
        ))
    return placed, remaining


def optimize(pieces, slabs, kerf=0.0, allow_rotation=True):
    """Empaqueta las piezas en las planchas disponibles.

    pieces: lista de dicts {"name", "width", "height", "quantity"}
    slabs:  lista de dicts {"name", "width", "height", "quantity"}
    kerf:   ancho de la hoja de sierra en la misma unidad.
    Devuelve dict con planchas usadas, piezas no colocadas y estadisticas.
    """
    kerf = max(0.0, float(kerf))

    items = []
    for p in pieces:
        for _ in range(int(p.get("quantity", 1))):
            items.append({"name": p["name"], "w": p["width"], "h": p["height"]})

    bins = []
    for s in slabs:
        for _ in range(int(s.get("quantity", 1))):
            bins.append({"name": s["name"], "w": s["width"], "h": s["height"]})

    if not items:
        return {
            "slabs_used": [], "unplaced": [], "total_pieces": 0,
            "pieces_placed": 0, "pieces_unplaced": 0,
            "total_area_pieces": 0.0, "total_area_slabs": 0.0,
            "total_waste": 0.0, "global_utilization": 0.0, "kerf": kerf,
        }

    # Probar varias estrategias de orden y rotacion, quedarse con la mejor.
    def sorters(items):
        return [
            sorted(items, key=lambda i: i["w"] * i["h"], reverse=True),      # por area
            sorted(items, key=lambda i: max(i["w"], i["h"]), reverse=True),  # por lado mayor
            sorted(items, key=lambda i: i["w"], reverse=True),               # por ancho
            sorted(items, key=lambda i: i["w"] * i["h"]),                    # por area asc
        ]

    rotation_modes = [allow_rotation, False] if allow_rotation else [False]

    best = None
    for rotation in rotation_modes:
        for items_sorted in sorters(items):
            pool = list(items_sorted)
            results = []
            for b in bins:
                placed, pool = _place_in_bin(b["w"], b["h"], kerf, rotation, pool)
                if placed:
                    used = sum(pp.width * pp.height for pp in placed)
                    area = b["w"] * b["h"]
                    results.append(BinResult(
                        name=b["name"], width=b["w"], height=b["h"], pieces=placed,
                        used_area=used, waste_area=max(0.0, area - used),
                        utilization=used / area, unplaced_after=len(pool),
                    ))
            used_slabs_area = sum(b.width * b.height for b in results)
            placed_count = sum(len(b.pieces) for b in results)
            score = (placed_count, -used_slabs_area)
            if best is None or score > best[0]:
                best = (score, results, pool)

    _, results, unplaced = best

    total_piece_area = sum(i["w"] * i["h"] for i in items)
    total_slab_area = sum(b["w"] * b["h"] for b in bins)
    placed_area = sum(b.used_area for b in results)
    unplaced_area = sum(i["w"] * i["h"] for i in unplaced)
    used_slabs_area = sum(b.width * b.height for b in results)

    def _bin_json(b):
        return {
            "name": b.name,
            "width": b.width,
            "height": b.height,
            "used_area": round(b.used_area, 4),
            "waste_area": round(b.waste_area, 4),
            "utilization": round(b.utilization * 100, 2),
            "pieces": [
                {
                    "name": p.name, "width": p.width, "height": p.height,
                    "x": round(p.x, 4), "y": round(p.y, 4), "rotated": p.rotated,
                }
                for p in b.pieces
            ],
        }

    return {
        "slabs_used": [_bin_json(b) for b in results],
        "unplaced": [
            {"name": i["name"], "width": i["w"], "height": i["h"], "quantity": 1}
            for i in unplaced
        ],
        "total_pieces": len(items),
        "pieces_placed": sum(len(b.pieces) for b in results),
        "pieces_unplaced": len(unplaced),
        "total_area_pieces": round(total_piece_area, 4),
        "total_area_slabs": round(total_slab_area, 4),
        "used_slabs_area": round(used_slabs_area, 4),
        "placed_area": round(placed_area, 4),
        "unplaced_area": round(unplaced_area, 4),
        "total_waste": round(used_slabs_area - placed_area, 4),
        "global_utilization": round(
            placed_area / used_slabs_area * 100, 2) if used_slabs_area else 0.0,
        "kerf": kerf,
    }


# --------------------------------------------------------------------------
# Empaquetado de formas libres (poligonos) con shapely
# --------------------------------------------------------------------------

import shapely.geometry as sg
from shapely import affinity, make_valid, prepare, simplify


def _clean_polygon(poly):
    poly = make_valid(poly)
    if poly.geom_type == "MultiPolygon":
        parts = sorted(list(poly.geoms), key=lambda g: g.area, reverse=True)
        poly = parts[0] if parts else poly
    if poly.geom_type != "Polygon" or poly.area <= 0:
        return None
    poly = simplify(poly, tolerance=0.5)
    return poly if poly.geom_type == "Polygon" else None


def _normalize_poly(poly):
    minx, miny, maxx, maxy = poly.bounds
    return affinity.translate(poly, -minx, -miny)


def _polygon_points(poly):
    def ring(linear):
        pts = list(linear.coords)
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return [[round(x, 3), round(y, 3)] for x, y in pts]

    return {
        "polygon": ring(poly.exterior),
        "holes": [ring(r) for r in poly.interiors],
    }


def _place_polygon(shape, placed, slab_w, slab_h):
    """Posicion bottom-left para un poligono (normalizado en origen) sobre los colocados."""
    sw, sh = shape.bounds[2], shape.bounds[3]
    if sw > slab_w + 1e-6 or sh > slab_h + 1e-6:
        return None
    candidates = {0.0}
    for p in placed:
        candidates.add(p.bounds[2])
        candidates.add(p.bounds[0])
    candidates = [c for c in candidates
                  if -1e-6 <= c <= slab_w - sw + 1e-6]
    candidates.sort()
    best = None
    for x in candidates:
        moved = affinity.translate(shape, x, 0.0)
        y = 0.0
        guard = 0
        while guard < 400:
            if moved.bounds[3] > slab_h + 1e-6:
                break
            hit = None
            for p in placed:
                if moved.intersects(p):
                    hit = p
                    break
            if hit is None:
                if best is None or (y, x) < (best[1], best[0]):
                    best = (x, y)
                break
            dy = hit.bounds[3] - moved.bounds[1]
            dy = max(dy, 0.01)
            moved = affinity.translate(moved, 0.0, dy)
            y += dy
            guard += 1
    return best


def optimize_polygons(polygon_pieces, slabs, kerf=0.0, allow_rotation=True):
    """Empaqueta poligonos (formas libres) en las planchas disponibles.

    polygon_pieces: lista de {"name", "polygon": [[x, y], ...], "quantity"}
    Devuelve el mismo formato que optimize() con 'polygon' en cada pieza.
    """
    kerf = max(0.0, float(kerf))

    items = []
    for p in polygon_pieces:
        for _ in range(int(p.get("quantity", 1))):
            poly = sg.Polygon(p["polygon"], [h for h in p.get("holes") or []])
            poly = _clean_polygon(poly)
            if poly is None:
                continue
            items.append({"name": p["name"], "poly": poly, "area": poly.area})

    bins = []
    for s in slabs:
        for _ in range(int(s.get("quantity", 1))):
            bins.append({"name": s["name"], "w": s["width"], "h": s["height"]})
    bins.sort(key=lambda b: b["w"] * b["h"], reverse=True)

    if not items:
        return {
            "slabs_used": [], "unplaced": [], "total_pieces": 0,
            "pieces_placed": 0, "pieces_unplaced": 0,
            "total_area_pieces": 0.0, "total_area_slabs": 0.0,
            "used_slabs_area": 0.0, "placed_area": 0.0,
            "unplaced_area": 0.0, "total_waste": 0.0,
            "global_utilization": 0.0, "kerf": kerf,
        }

    def sorters(items):
        return [
            sorted(items, key=lambda i: i["area"], reverse=True),
            sorted(items, key=lambda i: max(i["poly"].bounds[2], i["poly"].bounds[3]), reverse=True),
            sorted(items, key=lambda i: i["area"]),
            sorted(items, key=lambda i: i["poly"].bounds[2], reverse=True),
        ]

    rotation_modes = [allow_rotation, False] if allow_rotation else [False]

    best = None
    for rotation in rotation_modes:
        for items_sorted in sorters(items):
            pool = list(items_sorted)
            results = []
            for b in bins:
                placed_polys = []  # (shapely placed)
                placed_infos = []  # (name, draw_poly, x, y, rotated, area)
                remaining = []
                for it in pool:
                    shape = it["poly"]
                    if kerf:
                        shape = shape.buffer(kerf / 2.0, join_style=2)
                        shape = _clean_polygon(shape)
                        if shape is None:
                            remaining.append(it)
                            continue
                    shape = _normalize_poly(shape)
                    options = [shape]
                    if rotation:
                        options.append(_normalize_poly(affinity.rotate(shape, 90, origin=(0, 0))))
                    best_pos = None
                    best_shape = None
                    best_rot = False
                    for idx, opt in enumerate(options):
                        pos = _place_polygon(opt, placed_polys, b["w"], b["h"])
                        if pos is not None and (best_pos is None or (pos[1], pos[0]) < (best_pos[1], best_pos[0])):
                            best_pos = pos
                            best_shape = opt
                            best_rot = (idx == 1)
                    if best_pos is None:
                        remaining.append(it)
                        continue
                    draw = _normalize_poly(it["poly"])
                    if best_rot:
                        draw = _normalize_poly(affinity.rotate(draw, 90, origin=(0, 0)))
                    placed_polys.append(
                        affinity.translate(best_shape, best_pos[0], best_pos[1]))
                    prepare(placed_polys[-1])
                    placed_infos.append((it["name"], draw, best_pos[0], best_pos[1], best_rot, it["area"]))
                if placed_infos:
                    used = sum(info[5] for info in placed_infos)
                    area = b["w"] * b["h"]
                    results.append({
                        "name": b["name"], "width": b["w"], "height": b["h"],
                        "pieces": placed_infos, "used_area": used,
                        "waste_area": max(0.0, area - used), "utilization": used / area,
                    })
                pool = remaining
            used_slabs_area = sum(r["width"] * r["height"] for r in results)
            placed_count = sum(len(r["pieces"]) for r in results)
            score = (placed_count, -used_slabs_area)
            if best is None or score > best[0]:
                best = (score, results, pool)

    _, results, unplaced = best

    total_piece_area = sum(i["area"] for i in items)
    total_slab_area = sum(b["w"] * b["h"] for b in bins)
    placed_area = sum(r["used_area"] for r in results)
    used_slabs_area = sum(r["width"] * r["height"] for r in results)
    unplaced_area = sum(i["area"] for i in unplaced)

    def _bin_json(b):
        return {
            "name": b["name"],
            "width": b["width"],
            "height": b["height"],
            "used_area": round(b["used_area"], 4),
            "waste_area": round(b["waste_area"], 4),
            "utilization": round(b["utilization"] * 100, 2),
            "pieces": [
                {
                    "name": name, "width": round(poly.bounds[2], 3),
                    "height": round(poly.bounds[3], 3),
                    "x": round(x, 3), "y": round(y, 3),
                    "rotated": rot, **_polygon_points(poly),
                }
                for name, poly, x, y, rot, _area in b["pieces"]
            ],
        }

    return {
        "slabs_used": [_bin_json(b) for b in results],
        "unplaced": [
            {"name": i["name"], "width": round(i["poly"].bounds[2], 3),
             "height": round(i["poly"].bounds[3], 3), "quantity": 1}
            for i in unplaced
        ],
        "total_pieces": len(items),
        "pieces_placed": sum(len(b["pieces"]) for b in results),
        "pieces_unplaced": len(unplaced),
        "total_area_pieces": round(total_piece_area, 4),
        "total_area_slabs": round(total_slab_area, 4),
        "used_slabs_area": round(used_slabs_area, 4),
        "placed_area": round(placed_area, 4),
        "unplaced_area": round(unplaced_area, 4),
        "total_waste": round(used_slabs_area - placed_area, 4),
        "global_utilization": round(
            placed_area / used_slabs_area * 100, 2) if used_slabs_area else 0.0,
        "kerf": kerf,
    }
