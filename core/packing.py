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
