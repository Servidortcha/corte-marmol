"""Optimizacion de corte 2D: empaquetado en planchas variables con hoja de sierra.

Estrategia: colocacion "bottom-left" (posicion mas baja, luego mas a la izquierda)
probando ambas orientaciones, sobre varias planchas de tamaños distintos.
La hoja de sierra (kerf) se modela como una separacion obligatoria entre piezas.

Incluye soporte para cortes guillotina (cortes de borde a borde) y ejecucion en
paralelo con ThreadPoolExecutor para aprovechar multiples nucleos.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import random

import shapely.geometry as sg
from shapely import affinity, make_valid, prepare, simplify
from shapely.ops import unary_union


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
    holes: list = field(default_factory=list)
    priority: int = 0
    polygon: list | None = None


def _layout_metrics(geometries, kerf=0.0):
    """Mide si las piezas forman un bloque compacto o varios grupos separados."""
    if not geometries:
        return {
            "clusters": 0,
            "cluster_bbox_area": 0.0,
            "hull_area": 0.0,
            "bbox_area": 0.0,
            "occupied_area": 0.0,
        }

    occupied = unary_union(geometries)
    gap = max(0.05, float(kerf) * 1.05)
    clustered = unary_union([
        geometry.buffer(gap / 2.0, join_style=2) for geometry in geometries
    ])
    if clustered.geom_type == "MultiPolygon":
        clusters = list(clustered.geoms)
    elif clustered.geom_type == "Polygon":
        clusters = [clustered]
    else:
        clusters = [part for part in getattr(clustered, "geoms", [])
                    if part.geom_type == "Polygon"]

    cluster_bbox_area = 0.0
    for cluster in clusters:
        minx, miny, maxx, maxy = cluster.bounds
        cluster_bbox_area += (maxx - minx) * (maxy - miny)

    minx, miny, maxx, maxy = occupied.bounds
    return {
        "clusters": len(clusters),
        "cluster_bbox_area": cluster_bbox_area,
        "hull_area": occupied.convex_hull.area,
        "bbox_area": (maxx - minx) * (maxy - miny),
        "occupied_area": sum(geometry.area for geometry in geometries),
    }


def _compactness_terms(geometries, reference_area, kerf=0.0):
    """Devuelve penalizaciones normalizadas para comparar layouts."""
    metrics = _layout_metrics(geometries, kerf)
    scale = max(float(reference_area), 1.0)
    return (
        -metrics["clusters"],
        -max(0.0, metrics["cluster_bbox_area"] - metrics["occupied_area"]) / scale,
        -max(0.0, metrics["hull_area"] - metrics["occupied_area"]) / scale,
        -max(0.0, metrics["bbox_area"] - metrics["occupied_area"]) / scale,
    )


def _find_position(width, height, kerf, bin_w, bin_h, placed, blocked=None,
                   placement_mode="bottomleft"):
    """Posicion bottom-left (menor y, luego menor x) libre para un rectangulo."""
    xs = {0.0}
    ys = {0.0}
    for p in placed:
        xs.add(p.x)
        xs.add(p.x + p.width + kerf)
        ys.add(p.y)
        ys.add(p.y + p.height + kerf)
        xs.add(max(0.0, p.x - width - kerf))
        ys.add(max(0.0, p.y - height - kerf))
    for obstacle in blocked or []:
        minx, miny, maxx, maxy = obstacle.bounds
        xs.update((max(0.0, minx - width - kerf), max(0.0, maxx + kerf + 0.01)))
        ys.update((max(0.0, miny - height - kerf), max(0.0, maxy + kerf + 0.01)))
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
            if ok:
                candidate = sg.box(x, y, x + width, y + height)
                if any(candidate.intersects(obstacle) for obstacle in blocked or []):
                    ok = False
            if ok:
                if placement_mode == "compact":
                    max_x = max([x + width] + [p.x + p.width for p in placed])
                    max_y = max([y + height] + [p.y + p.height for p in placed])
                    key = (max_x * max_y, y, x)
                else:
                    key = (y, x)
                if best is None or key < best[2]:
                    best = (x, y, key)
    return best[:2] if best is not None else None


def _rectangle_position_key(x, y, width, height, placed, placement_mode):
    if placement_mode == "compact":
        max_x = max([x + width] + [p.x + p.width for p in placed])
        max_y = max([y + height] + [p.y + p.height for p in placed])
        return (max_x * max_y, max_x + max_y, y, x)
    return (y, x)


def _place_in_bin(bin_w, bin_h, kerf, allow_rotation, items, blocked=None,
                  placement_mode="bottomleft"):
    placed = []
    remaining = []
    for it in items:
        options = [(it["w"], it["h"], False)]
        if allow_rotation and not it.get("no_rotate"):
            options.append((it["h"], it["w"], True))
        best_pos = None
        best_w = best_h = None
        best_rot = False
        for w, h, rot in options:
            pos = _find_position(
                w, h, kerf, bin_w, bin_h, placed, blocked, placement_mode)
            if pos is not None and (
                best_pos is None or
                _rectangle_position_key(
                    pos[0], pos[1], w, h, placed, placement_mode
                ) < _rectangle_position_key(
                    best_pos[0], best_pos[1], best_w, best_h, placed,
                    placement_mode
                )
            ):
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


def _maxrects_place_in_bin(bin_w, bin_h, kerf, allow_rotation, items):
    """Empaquetado MaxRects para rectangulos sin obstaculos internos."""
    free = [(0.0, 0.0, float(bin_w), float(bin_h))]
    placed = []
    remaining = []

    def prune(rectangles):
        result = []
        for index, rect in enumerate(rectangles):
            x, y, w, h = rect
            contained = False
            for other_index, other in enumerate(rectangles):
                if index == other_index:
                    continue
                ox, oy, ow, oh = other
                if (x >= ox and y >= oy and x + w <= ox + ow and
                        y + h <= oy + oh):
                    contained = True
                    break
            if not contained and w > 1e-6 and h > 1e-6:
                result.append(rect)
        return result

    for item in items:
        options = [(item["w"], item["h"], False)]
        if allow_rotation and item["w"] != item["h"] and not item.get("no_rotate"):
            options.append((item["h"], item["w"], True))
        best = None
        for w, h, rotated in options:
            rw, rh = w + kerf, h + kerf
            for fx, fy, fw, fh in free:
                if rw > fw + 1e-9 or rh > fh + 1e-9:
                    continue
                leftover_w = fw - rw
                leftover_h = fh - rh
                short_fit = min(leftover_w, leftover_h)
                long_fit = max(leftover_w, leftover_h)
                key = (short_fit, long_fit, fy, fx)
                if best is None or key < best[0]:
                    best = (key, fx, fy, w, h, rw, rh, rotated)
        if best is None:
            remaining.append(item)
            continue

        _, x, y, w, h, rw, rh, rotated = best
        used = (x, y, rw, rh)
        next_free = []
        for fx, fy, fw, fh in free:
            if (used[0] >= fx + fw or used[0] + used[2] <= fx or
                    used[1] >= fy + fh or used[1] + used[3] <= fy):
                next_free.append((fx, fy, fw, fh))
                continue
            if used[0] > fx:
                next_free.append((fx, fy, used[0] - fx, fh))
            if used[0] + used[2] < fx + fw:
                next_free.append((used[0] + used[2], fy,
                                  fx + fw - used[0] - used[2], fh))
            overlap_w = min(used[0] + used[2], fx + fw) - max(used[0], fx)
            if used[1] > fy and overlap_w > 0:
                next_free.append((max(used[0], fx), fy, overlap_w, used[1] - fy))
            if used[1] + used[3] < fy + fh and overlap_w > 0:
                next_free.append((max(used[0], fx), used[1] + used[3],
                                  overlap_w, fy + fh - used[1] - used[3]))
        free = prune(next_free)
        placed.append(PlacedPiece(
            name=item["name"], width=w, height=h, x=x, y=y, rotated=rotated,
        ))
    return placed, remaining


def _guillotine_place_in_bin(bin_w, bin_h, kerf, allow_rotation, items):
    """Empaquetado por cortes guillotina: el espacio se divide secuencialmente
    con cortes de borde a borde, apropiado para aserraderos de marmol."""
    shelves = [(0.0, 0.0, float(bin_w), float(bin_h))]
    placed = []
    remaining = []

    for item in items:
        options = [(item["w"], item["h"], False)]
        if allow_rotation and item["w"] != item["h"] and not item.get("no_rotate"):
            options.append((item["h"], item["w"], True))
        best = None
        best_shelf_idx = None
        for w, h, rot in options:
            rw, rh = w + kerf, h + kerf
            for idx, (sx, sy, sw, sh) in enumerate(shelves):
                if rw > sw + 1e-9 or rh > sh + 1e-9:
                    continue
                leftover_w = sw - rw
                leftover_h = sh - rh
                score = (min(leftover_w, leftover_h), max(leftover_w, leftover_h), sy, sx, idx)
                if best is None or score < best[0]:
                    best = (score, sx, sy, w, h, rw, rh, rot, idx)
        if best is None:
            remaining.append(item)
            continue
        _, x, y, w, h, rw, rh, rotated, idx = best

        placed.append(PlacedPiece(
            name=item["name"], width=w, height=h, x=x, y=y, rotated=rotated,
        ))
        sx, sy, sw, sh = shelves.pop(idx)
        if rw < sw - 1e-6:
            shelves.append((x + rw, sy, sw - rw, rh))
        if rh < sh - 1e-6:
            shelves.append((x, y + rh, sw, sh - rh))
    return placed, remaining


def _guillotine_place_polygons(bin_w, bin_h, kerf, allow_rotation, items, blocked):
    """Guillotina para poligonos usando su bounding box."""
    placed_polys = []
    placed_infos = []
    remaining = []

    shelves = [(0.0, 0.0, float(bin_w), float(bin_h))]

    for item in items:
        options = [_normalize_poly(item["collision"])]
        if allow_rotation and not item.get("no_rotate"):
            options.append(_normalize_poly(item["collision_rot"]))
        best = None
        for option_index, option in enumerate(options):
            ow, oh = option.bounds[2], option.bounds[3]
            rw, rh = ow + kerf, oh + kerf
            for idx, (sx, sy, sw, sh) in enumerate(shelves):
                if rw > sw + 1e-9 or rh > sh + 1e-9:
                    continue
                candidate = affinity.translate(option, sx, sy)
                if any(candidate.intersects(other) for other in placed_polys + (blocked or [])):
                    continue
                score = (min(sw - rw, sh - rh), max(sw - rw, sh - rh), sy, sx, idx)
                if best is None or score < best[0]:
                    best = (score, sx, sy, option, rw, rh, option_index == 1)
        if best is None:
            remaining.append(item)
            continue
        _, x, y, option, rw, rh, rotated = best
        filled_collision = _filled_polygon(option)
        placed_polys.append(affinity.translate(filled_collision, x, y))
        sx, sy, sw, sh = shelves.pop(idx)
        if rw < sw - 1e-6:
            shelves.append((x + rw, sy, sw - rw, rh))
        if rh < sh - 1e-6:
            shelves.append((x, y + rh, sw, sh - rh))
        draw, piece_lines = _piece_geometry(
            item["poly"], item.get("lines") or [], rotated)
        placed_infos.append((item["name"], draw, x, y, rotated,
                             item["area"], piece_lines, filled_collision,
                             item["offset_rot"] if rotated else item["offset"]))
    return placed_infos, remaining


def _try_strategy(strategy):
    placement_mode, rotation, items_sorted, bins_sorted, kerf = strategy
    pool = list(items_sorted)
    results = []
    for b in bins_sorted:
        blocked = [sg.Polygon(hole).buffer(kerf / 2, join_style=2)
                   for hole in b.get("holes") or []]
        if placement_mode == "maxrects" and not blocked:
            placed, pool = _maxrects_place_in_bin(
                b["w"], b["h"], kerf, rotation, pool)
        elif placement_mode == "guillotine" and not blocked:
            placed, pool = _guillotine_place_in_bin(
                b["w"], b["h"], kerf, rotation, pool)
        else:
            placed, pool = _place_in_bin(
                b["w"], b["h"], kerf, rotation, pool, blocked,
                "compact" if placement_mode == "compact" else "bottomleft")
        if placed:
            placed, pool = _fill_gaps(
                b["w"], b["h"], kerf, rotation, placed, pool, blocked
            )
            used = sum(pp.width * pp.height for pp in placed)
            area = b["w"] * b["h"]
            results.append(BinResult(
                name=b["name"], width=b["w"], height=b["h"], pieces=placed,
                used_area=used, waste_area=max(0.0, area - used),
                utilization=used / area, unplaced_after=len(pool),
                holes=b.get("holes") or [],
                priority=b.get("priority", 0),
                polygon=b.get("polygon"),
            ))
    used_slabs_area = sum(b.width * b.height for b in results)
    placed_count = sum(len(b.pieces) for b in results)
    placed_area = sum(b.used_area for b in results)
    priority_sum = sum(b.priority for b in results)
    min_utilization = min((b.utilization for b in results), default=0.0)
    global_util = placed_area / used_slabs_area if used_slabs_area else 0.0
    compact_terms = [0.0, 0.0, 0.0, 0.0]
    for b in results:
        geometries = [sg.box(p.x, p.y, p.x + p.width, p.y + p.height)
                      for p in b.pieces]
        terms = _compactness_terms(geometries, b.width * b.height, kerf)
        compact_terms = [current + value
                         for current, value in zip(compact_terms, terms)]
    score = (placed_count, -priority_sum, -used_slabs_area, global_util,
             min_utilization, *compact_terms)
    return (score, results, pool)


def _try_polygon_strategy(strategy):
    placement_mode, rotation, items_sorted, bins_sorted, kerf = strategy
    pool = list(items_sorted)
    results = []
    for b in bins_sorted:
        placed_polys = []
        blocked = []
        for hole in b.get("holes") or []:
            obstacle = sg.Polygon(hole).buffer(kerf / 2, join_style=2)
            prepare(obstacle)
            blocked.append(obstacle)
        if placement_mode == "maxrects":
            placed_infos, pool = _maxrects_place_polygons(
                b["w"], b["h"], kerf, rotation, pool, blocked)
            if placed_infos:
                used = sum(info[5] for info in placed_infos)
                area = b["w"] * b["h"]
                results.append({
                    "name": b["name"], "width": b["w"], "height": b["h"],
                    "holes": b.get("holes") or [],
                    "pieces": placed_infos, "used_area": used,
                    "waste_area": max(0.0, area - used),
                    "utilization": used / area,
                    "priority": b.get("priority", 0),
                "polygon": b.get("polygon"),
                })
            continue
        if placement_mode == "guillotine":
            placed_infos, pool = _guillotine_place_polygons(
                b["w"], b["h"], kerf, rotation, pool, blocked)
            if placed_infos:
                used = sum(info[5] for info in placed_infos)
                area = b["w"] * b["h"]
                results.append({
                    "name": b["name"], "width": b["w"], "height": b["h"],
                    "holes": b.get("holes") or [],
                    "pieces": placed_infos, "used_area": used,
                    "waste_area": max(0.0, area - used),
                    "utilization": used / area,
                    "priority": b.get("priority", 0),
                "polygon": b.get("polygon"),
                })
            continue
        placed_infos = []
        remaining = []
        for it in pool:
            shape = it["collision"]
            shape = _normalize_poly(shape)
            options = [shape]
            if rotation and not it.get("no_rotate"):
                options.append(_normalize_poly(it["collision_rot"]))
            best_pos = None
            best_shape = None
            best_rot = False
            for idx_opt, opt in enumerate(options):
                pos = _place_polygon(
                    opt, placed_polys, b["w"], b["h"], blocked,
                    "compact" if placement_mode == "compact" else "bottomleft")
                if pos is not None and (
                    best_pos is None or
                    _polygon_position_key(
                        opt, pos[0], pos[1], placed_polys, placement_mode
                    ) < _polygon_position_key(
                        best_shape, best_pos[0], best_pos[1], placed_polys,
                        placement_mode
                    )
                ):
                    best_pos = pos
                    best_shape = opt
                    best_rot = (idx_opt == 1)
            if best_pos is None:
                remaining.append(it)
                continue
            draw, piece_lines = _piece_geometry(
                it["poly"], it.get("lines") or [], best_rot)
            filled_collision = _filled_polygon(best_shape)
            placed_polys.append(
                affinity.translate(filled_collision, best_pos[0], best_pos[1]))
            prepare(placed_polys[-1])
            placed_infos.append((it["name"], draw, best_pos[0], best_pos[1],
                                 best_rot, it["area"], piece_lines,
                                 filled_collision,
                                 it["offset_rot"] if best_rot else it["offset"]))
        if placed_infos:
            used = sum(info[5] for info in placed_infos)
            area = b["w"] * b["h"]
            results.append({
                "name": b["name"], "width": b["w"], "height": b["h"],
                "holes": b.get("holes") or [],
                "pieces": placed_infos, "used_area": used,
                "waste_area": max(0.0, area - used), "utilization": used / area,
                "priority": b.get("priority", 0),
                "polygon": b.get("polygon"),
            })
        pool = remaining
    used_slabs_area = sum(r["width"] * r["height"] for r in results)
    placed_count = sum(len(r["pieces"]) for r in results)
    placed_area = sum(r["used_area"] for r in results)
    priority_sum = sum(r.get("priority", 0) for r in results)
    global_util = placed_area / used_slabs_area if used_slabs_area else 0.0
    min_utilization = min((r["utilization"] for r in results), default=0.0)
    compact_terms = [0.0, 0.0, 0.0, 0.0]
    for r in results:
        geometries = [affinity.translate(collision, x, y)
                      for _name, _p, x, y, _rot, _area, _lines, collision,
                      _offset in r["pieces"]]
        terms = _compactness_terms(geometries, r["width"] * r["height"], kerf)
        compact_terms = [current + value
                         for current, value in zip(compact_terms, terms)]
    if not _polygon_infos_valid(results):
        return ((-1, float("-inf"), float("-inf"), float("-inf"),
                 float("-inf"), float("-inf"), float("-inf"), float("-inf"),
                 float("-inf")),
                results, pool)
    score = (placed_count, -priority_sum, -used_slabs_area, global_util,
             min_utilization, *compact_terms)
    return (score, results, pool)


def _fill_gaps(bin_w, bin_h, kerf, allow_rotation, placed, remaining,
               blocked=None):
    """Intenta colocar piezas sobrantes en los huecos entre piezas ya colocadas."""
    if not remaining:
        return placed, remaining

    placed_geoms = []
    for p in placed:
        placed_geoms.append(sg.box(p.x, p.y, p.x + p.width, p.y + p.height))
    blocked_geoms = list(blocked or [])

    still_remaining = []
    for item in remaining:
        options = [(item["w"], item["h"], False)]
        if allow_rotation and item["w"] != item["h"] and not item.get("no_rotate"):
            options.append((item["h"], item["w"], True))
        best_pos = None
        best_w = best_h = None
        best_rot = False
        for w, h, rot in options:
            rw, rh = w + kerf, h + kerf
            candidates_x = {0.0}
            candidates_y = {0.0}
            for pg in placed_geoms:
                candidates_x.add(pg.bounds[0])
                candidates_x.add(pg.bounds[2] + kerf)
                candidates_y.add(pg.bounds[1])
                candidates_y.add(pg.bounds[3] + kerf)
            for cx in sorted(candidates_x):
                if cx + rw > bin_w + 1e-9:
                    break
                for cy in sorted(candidates_y):
                    if cy + rh > bin_h + 1e-9:
                        break
                    rect = sg.box(cx, cy, cx + rw, cy + rh)
                    if any(rect.intersects(other)
                           for other in placed_geoms + blocked_geoms):
                        continue
                    key = (cy, cx)
                    if best_pos is None or key < best_pos[0]:
                        best_pos = (key, cx, cy)
                        best_w, best_h, best_rot = w, h, rot
        if best_pos is None:
            still_remaining.append(item)
            continue
        _, x, y = best_pos
        placed.append(PlacedPiece(
            name=item["name"], width=best_w, height=best_h,
            x=x, y=y, rotated=best_rot,
        ))
        placed_geoms.append(sg.box(x, y, x + best_w, y + best_h))
    return placed, still_remaining


def _rects_bbox(pieces):
    max_x = max((p.x + p.width for p in pieces), default=0.0)
    max_y = max((p.y + p.height for p in pieces), default=0.0)
    return max_x * max_y


def _recompact_rectangles(placed, bin_w, bin_h, kerf, blocked=None,
                          rounds=8):
    """Empuja las piezas hacia abajo-izquierda para compactar el bloque."""
    if len(placed) < 2:
        return placed
    pieces = [PlacedPiece(p.name, p.width, p.height, p.x, p.y, p.rotated)
              for p in placed]
    for round_index in range(rounds):
        improved = False
        order = (lambda q: (q.y, q.x)) if round_index % 2 == 0 else (
            lambda q: (q.x, q.y))
        for p in sorted(pieces, key=order):
            others = [q for q in pieces if q is not p]
            pos = _find_position(p.width, p.height, kerf, bin_w, bin_h,
                                 others, blocked, "compact")
            if pos is None:
                continue
            if (pos[0], pos[1]) == (p.x, p.y):
                continue
            moved_piece = PlacedPiece(p.name, p.width, p.height,
                                      pos[0], pos[1], p.rotated)
            old_bbox = _rects_bbox(others + [p])
            new_bbox = _rects_bbox(others + [moved_piece])
            if (new_bbox < old_bbox - 1e-6 or
                    (new_bbox <= old_bbox + 1e-6 and pos[1] < p.y - 1e-6)):
                p.x, p.y = pos
                improved = True
        if not improved:
            break
    return pieces


def _fill_gaps_polygons(bin_w, bin_h, kerf, allow_rotation, placed_polys,
                         placed_infos, remaining, blocked=None):
    """Intenta colocar poligonos sobrantes en los huecos."""
    if not remaining:
        return placed_polys, placed_infos, remaining

    still_remaining = []
    for item in remaining:
        shape = item["poly"]
        if kerf:
            shape = shape.buffer(kerf / 2, join_style=2)
        options = [_normalize_poly(shape)]
        if allow_rotation and not item.get("no_rotate"):
            options.append(_normalize_poly(affinity.rotate(shape, 90, origin=(0, 0))))
        best_pos = None
        best_option = None
        best_rot = False
        for idx, opt in enumerate(options):
            ow, oh = opt.bounds[2], opt.bounds[3]
            rw, rh = ow + kerf, oh + kerf
            if rw > bin_w + 1e-9 or rh > bin_h + 1e-9:
                continue
            candidates_x = {0.0}
            for p in placed_polys:
                candidates_x.add(p.bounds[0])
                candidates_x.add(p.bounds[2])
                candidates_x.add(max(0.0, p.bounds[2] + kerf))
            for cx in sorted(candidates_x):
                if cx + rw > bin_w + 1e-9:
                    break
                moved = affinity.translate(opt, cx, 0.0)
                y = 0.0
                guard = 0
                while guard < 300:
                    if moved.bounds[3] > bin_h + 1e-9:
                        break
                    if not any(moved.intersects(other)
                               for other in placed_polys + list(blocked or [])):
                        key = (y, cx)
                        if best_pos is None or key < best_pos[0]:
                            best_pos = (key, cx, y)
                            best_option = opt
                            best_rot = (idx == 1)
                        break
                    hit = None
                    for p in placed_polys + list(blocked or []):
                        if moved.intersects(p):
                            hit = p
                            break
                    if hit is None:
                        y += 0.1
                    else:
                        dy = hit.bounds[3] - moved.bounds[1]
                        dy = max(dy, 0.5)
                        moved = affinity.translate(moved, 0.0, dy)
                        y += dy
                    guard += 1
        if best_pos is None:
            still_remaining.append(item)
            continue
        _, cx, cy = best_pos
        placed_shape = affinity.translate(best_option, cx, cy)
        placed_polys.append(placed_shape)
        prepare(placed_polys[-1])
        draw, piece_lines = _piece_geometry(
            item["poly"], item.get("lines") or [], best_rot)
        placed_infos.append((item["name"], draw, cx, cy, best_rot,
                             item["area"], piece_lines))
    return placed_polys, placed_infos, still_remaining


def _polygon_infos_bbox(infos):
    max_x = max((x + collision.bounds[2]
                 for _n, _p, x, _y, _r, _a, _l, collision, _o in infos),
                default=0.0)
    max_y = max((y + collision.bounds[3]
                 for _n, _p, _x, y, _r, _a, _l, collision, _o in infos),
                default=0.0)
    return max_x * max_y


def _recompact_polygon_infos(infos, bin_w, bin_h, kerf, blocked=None,
                             rounds=5):
    """Reubica cada poligono en su posicion mas compacta, iterativamente."""
    if len(infos) < 2:
        return infos
    pieces = [list(info) for info in infos]
    for round_index in range(rounds):
        improved = False
        order = (lambda q: (q[3], q[2])) if round_index % 2 == 0 else (
            lambda q: (q[2], q[3]))
        for info in sorted(pieces, key=order):
            name, poly, x, y, rot, area, lines, collision, offset = info
            others = [o for o in pieces if o is not info]
            other_geoms = [affinity.translate(o[7], o[2], o[3])
                           for o in others]
            pos = _place_polygon(collision, other_geoms, bin_w, bin_h,
                                 blocked, "compact")
            if pos is None:
                continue
            if (pos[0], pos[1]) == (x, y):
                continue
            old_bbox = _polygon_infos_bbox(
                others + [[name, poly, x, y, rot, area, lines, collision,
                           offset]])
            new_bbox = _polygon_infos_bbox(
                others + [[name, poly, pos[0], pos[1], rot, area, lines,
                           collision, offset]])
            if new_bbox < old_bbox - 1e-6:
                index = next(i for i, piece in enumerate(pieces)
                             if piece is info)
                pieces[index] = [name, poly, pos[0], pos[1], rot, area,
                                 lines, collision, offset]
                improved = True
        if not improved:
            break
    return [tuple(piece) for piece in pieces]


def optimize(pieces, slabs, kerf=0.0, allow_rotation=True, intensive=False):
    """Empaqueta las piezas en las planchas disponibles.

    pieces: lista de dicts {"name", "width", "height", "quantity"}
    slabs:  lista de dicts {"name", "width", "height", "quantity"}
    kerf:   ancho de la hoja de sierra en la misma unidad.
    intensive: si True, proba muchas mas estrategias de ordenamiento.
    Devuelve dict con planchas usadas, piezas no colocadas y estadisticas.
    """
    kerf = max(0.0, float(kerf))

    items = []
    for p in pieces:
        for _ in range(int(p.get("quantity", 1))):
            items.append({"name": p["name"], "w": p["width"], "h": p["height"],
                          "priority": int(p.get("priority", 0)),
                          "no_rotate": p.get("allow_rotation") is False})

    priority_map = {p["name"]: int(p.get("priority", 0)) for p in pieces}

    bins = []
    for s in slabs:
        for _ in range(int(s.get("quantity", 1))):
            holes = s.get("holes") or []
            bins.append({"name": s["name"], "w": s["width"], "h": s["height"],
                         "holes": holes,
                         "priority": int(s.get("priority", 0)),
                         "polygon": s.get("polygon")})

    if not items:
        return {
            "slabs_used": [], "unplaced": [], "total_pieces": 0,
            "pieces_placed": 0, "pieces_unplaced": 0,
            "total_area_pieces": 0.0, "total_area_slabs": 0.0,
            "total_waste": 0.0, "global_utilization": 0.0, "kerf": kerf,
        }

    def sorters(items):
        strategies = [
            sorted(items, key=lambda i: i["w"] * i["h"], reverse=True),
            sorted(items, key=lambda i: max(i["w"], i["h"]), reverse=True),
            sorted(items, key=lambda i: i["w"], reverse=True),
            sorted(items, key=lambda i: i["h"], reverse=True),
            sorted(items, key=lambda i: min(i["w"], i["h"]), reverse=True),
            sorted(items, key=lambda i: i["w"] * i["h"]),
            sorted(items, key=lambda i: (i["name"], -(i["w"] * i["h"]))),
            sorted(items, key=lambda i: (i["name"], -max(i["w"], i["h"]))),
            sorted(items, key=lambda i: (i["name"], max(i["w"], i["h"]))),
            sorted(items, key=lambda i: (i["w"] * i["h"], i["name"])),
            sorted(items, key=lambda i: (max(i["w"], i["h"]), min(i["w"], i["h"]))),
            # por prioridad: las prioritarias primero, luego por area
            sorted(items, key=lambda i: (
                1 if i.get("priority", 0) <= 0 else 0,
                i.get("priority", 0), -(i["w"] * i["h"]))),
        ]
        rng = random.Random(20260812)
        shuffle_count = 80 if intensive else 15
        for _ in range(shuffle_count):
            shuffled = list(items)
            rng.shuffle(shuffled)
            strategies.append(shuffled)
        return strategies

    rotation_modes = [allow_rotation, False] if allow_rotation else [False]
    placement_modes = ["maxrects", "guillotine", "bottomleft", "compact"]
    if any(b.get("priority", 0) > 0 for b in bins):
        bin_orders = [sorted(bins, key=lambda b: (
            1 if b.get("priority", 0) <= 0 else 0,
            b.get("priority", 0), -(b["w"] * b["h"])))]
    else:
        bin_areas = [b["w"] * b["h"] for b in bins]
        if len(bin_areas) > 1 and min(bin_areas) != max(bin_areas):
            bin_orders = [
                bins,
                sorted(bins, key=lambda b: b["w"] * b["h"], reverse=True),
                sorted(bins, key=lambda b: b["w"] * b["h"]),
            ]
        else:
            bin_orders = [bins]

    strategies = []
    for rotation in rotation_modes:
        for placement_mode in placement_modes:
            for items_sorted in sorters(items):
                for bins_sorted in bin_orders:
                    strategies.append((placement_mode, rotation, items_sorted,
                                       bins_sorted, kerf))

    best = None
    with ThreadPoolExecutor(max_workers=min(4, len(strategies))) as executor:
        futures = {executor.submit(_try_strategy, st): st for st in strategies}
        for future in as_completed(futures):
            try:
                score, results, pool = future.result()
                if best is None or score > best[0]:
                    best = (score, results, pool)
            except Exception:
                pass

    _, results, unplaced = best

    for result in results:
        blocked = [sg.Polygon(hole).buffer(kerf / 2, join_style=2)
                   for hole in result.holes or []]
        result.pieces = _recompact_rectangles(
            result.pieces, result.width, result.height, kerf, blocked)
        result.used_area = sum(p.width * p.height for p in result.pieces)
        area = result.width * result.height
        result.utilization = result.used_area / area
        result.waste_area = max(0.0, area - result.used_area)

    total_piece_area = sum(i["w"] * i["h"] for i in items)
    total_slab_area = sum(b["w"] * b["h"] for b in bins)
    placed_area = sum(b.used_area for b in results)
    unplaced_area = sum(i["w"] * i["h"] for i in unplaced)
    used_slabs_area = sum(b.width * b.height for b in results)

    def _bin_json(b):
        piece_json = [
            {
                "name": p.name, "width": p.width, "height": p.height,
                "x": round(p.x, 4), "y": round(p.y, 4), "rotated": p.rotated,
                "priority": priority_map.get(p.name, 0),
            }
            for p in b.pieces
        ]
        piece_json.sort(key=lambda p: (
            1 if p["priority"] <= 0 else 0, p["priority"]))
        return {
            "name": b.name,
            "width": b.width,
            "height": b.height,
            "holes": b.holes if hasattr(b, "holes") else None,
            "polygon": b.polygon,
            "used_area": round(b.used_area, 4),
            "waste_area": round(b.waste_area, 4),
            "utilization": round(b.utilization * 100, 2),
            "pieces": piece_json,
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


def _clean_polygon(poly):
    poly = make_valid(poly)
    if poly.geom_type == "MultiPolygon":
        parts = sorted(list(poly.geoms), key=lambda g: g.area, reverse=True)
        poly = parts[0] if parts else poly
    if poly.geom_type != "Polygon" or poly.area <= 0:
        return None
    poly = simplify(poly, tolerance=0.5)
    return poly if poly.geom_type == "Polygon" else None


def _filled_polygon(poly):
    """Version rellena (sin huecos) para usar como obstaculo de colision:
    los interiores quedan ocupados porque el disco no puede entrar a cortar."""
    if poly.interiors:
        return sg.Polygon(poly.exterior)
    return poly


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


def _rotate_segments(segments):
    out = []
    for segment in segments:
        layer, x1, y1, x2, y2 = segment
        out.append([layer, -y1, x1, -y2, x2])
    return out


def _normalize_segments(segments, minx, miny):
    out = []
    for segment in segments:
        layer, x1, y1, x2, y2 = segment
        out.append([layer, x1 - minx, y1 - miny, x2 - minx, y2 - miny])
    return out


def _piece_geometry(poly, lines, rotated):
    """Devuelve (draw_poly, lineas_en_frame_local) con la rotacion aplicada.

    Las lineas son [capa, x1, y1, x2, y2] en coordenadas locales de la pieza.
    """
    draw = _normalize_poly(poly)
    if not rotated:
        return draw, [list(segment) for segment in lines]
    draw = affinity.rotate(draw, 90, origin=(0, 0))
    minx, miny, _, _ = draw.bounds
    draw = affinity.translate(draw, -minx, -miny)
    return draw, _normalize_segments(_rotate_segments(lines), minx, miny)


def _polygon_candidate_values(geometry, width, height):
    """Obtiene coordenadas de bordes exteriores, huecos y concavidades."""
    xs = set()
    ys = set()
    geometries = [geometry]
    if geometry.geom_type == "GeometryCollection":
        geometries = list(geometry.geoms)
    for current in geometries:
        if current.geom_type == "MultiPolygon":
            for part in current.geoms:
                part_xs, part_ys = _polygon_candidate_values(part, width, height)
                xs.update(part_xs)
                ys.update(part_ys)
            continue
        if current.geom_type != "Polygon":
            continue
        rings = [current.exterior, *current.interiors]
        for ring in rings:
            minx, miny, maxx, maxy = ring.bounds
            xs.update((minx, maxx, minx - width, maxx - width))
            ys.update((miny, maxy, miny - height, maxy - height))
        minx, miny, maxx, maxy = current.bounds
        xs.update((minx, maxx, minx - width, maxx - width))
        ys.update((miny, maxy, miny - height, maxy - height))
    return xs, ys


def _place_polygon(shape, placed, slab_w, slab_h, blocked=None,
                   placement_mode="bottomleft"):
    """Coloca un poligono usando bordes reales, incluidos huecos y concavidades."""
    sw, sh = shape.bounds[2], shape.bounds[3]
    if sw > slab_w + 1e-6 or sh > slab_h + 1e-6:
        return None

    obstacles = list(placed) + list(blocked or [])
    obstacle_bounds = [obstacle.bounds for obstacle in obstacles]
    max_x = slab_w - sw
    max_y = slab_h - sh

    xs = {0.0}
    ys = {0.0}
    for obstacle in obstacles:
        obstacle_xs, obstacle_ys = _polygon_candidate_values(obstacle, sw, sh)
        xs.update(x for x in obstacle_xs if -1e-6 <= x <= max_x + 1e-6)
        ys.update(y for y in obstacle_ys if -1e-6 <= y <= max_y + 1e-6)
    xs = sorted(xs)
    ys = sorted(ys)

    best = None
    for x in xs:
        for y in ys:
            moved = affinity.translate(shape, x, y)
            moved_bounds = moved.bounds
            hit = False
            for obstacle, ob_bounds in zip(obstacles, obstacle_bounds):
                if (moved_bounds[0] < ob_bounds[2] - 0.01 and
                        moved_bounds[2] > ob_bounds[0] + 0.01 and
                        moved_bounds[1] < ob_bounds[3] - 0.01 and
                        moved_bounds[3] > ob_bounds[1] + 0.01):
                    if moved.intersects(obstacle) and not moved.touches(obstacle):
                        hit = True
                        break
            if hit:
                continue
            if placement_mode == "compact":
                max_xx = max([x + sw] + [p.bounds[2] for p in placed])
                max_yy = max([y + sh] + [p.bounds[3] for p in placed])
                key = (max_xx * max_yy, max_xx + max_yy, y, x)
            else:
                key = (y, x)
            if best is None or key < best[2]:
                best = (x, y, key)
            break
    return best[:2] if best is not None else None


def _polygon_position_key(shape, x, y, placed, placement_mode):
    if placement_mode == "compact":
        max_x = max([x + shape.bounds[2]] + [p.bounds[2] for p in placed])
        max_y = max([y + shape.bounds[3]] + [p.bounds[3] for p in placed])
        return (max_x * max_y, max_x + max_y, y, x)
    return (y, x)


def _polygon_infos_valid(results):
    """Descarta estrategias que producen solapamientos en la salida."""
    for result in results:
        slab_box = sg.box(0, 0, result["width"], result["height"])
        obstacles = [sg.Polygon(hole) for hole in result.get("holes") or []]
        geometries = []
        for _name, polygon, x, y, _rotated, _area, _lines, _collision, offset in result["pieces"]:
            geometry = affinity.translate(polygon, x + offset[0], y + offset[1])
            if not geometry.is_valid or not slab_box.covers(geometry):
                return False
            minx, miny, maxx, maxy = geometry.bounds
            for obstacle in obstacles:
                ominx, ominy, omaxx, omaxy = obstacle.bounds
                if (minx < omaxx and maxx > ominx and
                        miny < omaxy and maxy > ominy and
                        geometry.intersection(obstacle).area > 1e-6):
                    return False
            for other in geometries:
                ominx, ominy, omaxx, omaxy = other.bounds
                if (minx < omaxx and maxx > ominx and
                        miny < omaxy and maxy > ominy and
                        geometry.intersection(other).area > 1e-6):
                    return False
            geometries.append(geometry)
    return True


def _maxrects_place_polygons(bin_w, bin_h, kerf, allow_rotation, items, blocked):
    """MaxRects por caja envolvente, validando cada forma con Shapely."""
    free = [(0.0, 0.0, float(bin_w), float(bin_h))]
    placed = []
    infos = []
    remaining = []

    def prune(rectangles):
        output = []
        for index, rect in enumerate(rectangles):
            x, y, w, h = rect
            if w <= 1e-6 or h <= 1e-6:
                continue
            if any(index != other_index and
                   x >= ox and y >= oy and x + w <= ox + ow and y + h <= oy + oh
                   for other_index, (ox, oy, ow, oh) in enumerate(rectangles)):
                continue
            output.append(rect)
        return output

    for item in items:
        options = [_normalize_poly(item["collision"])]
        if allow_rotation and not item.get("no_rotate"):
            options.append(_normalize_poly(item["collision_rot"]))
        best = None
        for option_index, option in enumerate(options):
            ow, oh = option.bounds[2], option.bounds[3]
            rw, rh = ow + kerf, oh + kerf
            for fx, fy, fw, fh in free:
                if rw > fw + 1e-9 or rh > fh + 1e-9:
                    continue
                candidate = affinity.translate(option, fx, fy)
                if any(candidate.intersects(other) for other in placed + (blocked or [])):
                    continue
                key = (min(fw - rw, fh - rh), max(fw - rw, fh - rh), fy, fx)
                if best is None or key < best[0]:
                    best = (key, fx, fy, option, rw, rh, option_index == 1)
        if best is None:
            remaining.append(item)
            continue

        _, x, y, option, rw, rh, rotated = best
        filled_collision = _filled_polygon(option)
        placed.append(affinity.translate(filled_collision, x, y))
        next_free = []
        for fx, fy, fw, fh in free:
            if (x >= fx + fw or x + rw <= fx or y >= fy + fh or y + rh <= fy):
                next_free.append((fx, fy, fw, fh))
                continue
            if x > fx:
                next_free.append((fx, fy, x - fx, fh))
            if x + rw < fx + fw:
                next_free.append((x + rw, fy, fx + fw - x - rw, fh))
            overlap_w = min(x + rw, fx + fw) - max(x, fx)
            if y > fy and overlap_w > 0:
                next_free.append((max(x, fx), fy, overlap_w, y - fy))
            if y + rh < fy + fh and overlap_w > 0:
                next_free.append((max(x, fx), y + rh, overlap_w, fy + fh - y - rh))
        free = prune(next_free)
        draw, piece_lines = _piece_geometry(
            item["poly"], item.get("lines") or [], rotated)
        infos.append((item["name"], draw, x, y, rotated, item["area"],
                      piece_lines, filled_collision,
                      item["offset_rot"] if rotated else item["offset"]))
    return infos, remaining


def _order_by_priority(pieces):
    pieces.sort(key=lambda p: (1 if p["priority"] <= 0 else 0,
                               p["priority"]))
    return pieces


def _build_collision_shape(poly, kerf, lines, edge_distances):
    """Forma de colision: contorno con buffer de kerf + engrosado en bordes
    con distancia personalizada por capa (p.ej. ingletes en lineas rojas).

    La distancia configurada es la separacion total entre ese borde y la
    pieza vecina; el buffer base aporta kerf/2 y el resto lo agrega la tira.
    """
    collision = poly.buffer(kerf / 2.0, join_style=2) if kerf else poly
    extra_parts = []
    for segment in lines or []:
        layer = segment[0]
        distance = (edge_distances or {}).get(layer)
        if not distance or distance <= kerf / 2.0 + 1e-9:
            continue
        x1, y1, x2, y2 = segment[1], segment[2], segment[3], segment[4]
        if (x1, y1) == (x2, y2):
            continue
        strip = sg.LineString([(x1, y1), (x2, y2)]).buffer(
            distance - kerf / 2.0, join_style=2)
        extra_parts.append(strip)
    if extra_parts:
        collision = unary_union([collision, *extra_parts])
    return _clean_polygon(collision)


def optimize_polygons(polygon_pieces, slabs, kerf=0.0, allow_rotation=True,
                      intensive=False, edge_distances=None):
    """Empaqueta poligonos (formas libres) en las planchas disponibles.

    polygon_pieces: lista de {"name", "polygon": [[x, y], ...], "quantity"}
    intensive: si True, proba muchas mas estrategias de ordenamiento.
    Devuelve el mismo formato que optimize() con 'polygon' en cada pieza.
    """
    kerf = max(0.0, float(kerf))

    items = []
    priority_map = {}
    for p in polygon_pieces:
        priority_map[p["name"]] = int(p.get("priority", 0))
        for _ in range(int(p.get("quantity", 1))):
            poly = sg.Polygon(p["polygon"], [h for h in p.get("holes") or []])
            poly = _clean_polygon(poly)
            if poly is None:
                continue
            lines = p.get("lines") or []
            collision = _build_collision_shape(poly, kerf, lines, edge_distances)
            if collision is None:
                continue
            collision_rot = affinity.rotate(collision, 90, origin=(0, 0))
            poly_rot = affinity.rotate(poly, 90, origin=(0, 0))
            items.append({
                "name": p["name"], "poly": poly, "area": poly.area,
                "lines": lines,
                "priority": int(p.get("priority", 0)),
                "no_rotate": p.get("allow_rotation") is False,
                "collision": collision,
                "collision_rot": collision_rot,
                "offset": (poly.bounds[0] - collision.bounds[0],
                           poly.bounds[1] - collision.bounds[1]),
                "offset_rot": (poly_rot.bounds[0] - collision_rot.bounds[0],
                               poly_rot.bounds[1] - collision_rot.bounds[1]),
            })

    bins = []
    for s in slabs:
        for _ in range(int(s.get("quantity", 1))):
            bins.append({"name": s["name"], "w": s["width"], "h": s["height"],
                         "holes": s.get("holes") or [],
                         "priority": int(s.get("priority", 0)),
                         "polygon": s.get("polygon")})
    bins.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    if any(b.get("priority", 0) > 0 for b in bins):
        bin_orders = [sorted(bins, key=lambda b: (
            1 if b.get("priority", 0) <= 0 else 0,
            b.get("priority", 0), -(b["w"] * b["h"])))]
    else:
        bin_areas = [b["w"] * b["h"] for b in bins]
        if len(bin_areas) > 1 and min(bin_areas) != max(bin_areas):
            bin_orders = [
                bins,
                sorted(bins, key=lambda b: b["w"] * b["h"]),
            ]
        else:
            bin_orders = [bins]

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
        strategies = [
            sorted(items, key=lambda i: i["area"], reverse=True),
            sorted(items, key=lambda i: max(i["poly"].bounds[2], i["poly"].bounds[3]), reverse=True),
            sorted(items, key=lambda i: i["area"]),
            sorted(items, key=lambda i: i["poly"].bounds[2], reverse=True),
            sorted(items, key=lambda i: i["poly"].bounds[3], reverse=True),
            sorted(items, key=lambda i: min(i["poly"].bounds[2], i["poly"].bounds[3]), reverse=True),
            # agrupado por nombre - piezas del mismo tipo juntas
            sorted(items, key=lambda i: (i["name"], -i["area"])),
            sorted(items, key=lambda i: (i["name"], -max(i["poly"].bounds[2], i["poly"].bounds[3]))),
            sorted(items, key=lambda i: (i["name"], i["area"])),
            # agrupado por bounding box - similares juntas
            sorted(items, key=lambda i: (i["area"], i["name"])),
            sorted(items, key=lambda i: (max(i["poly"].bounds[2], i["poly"].bounds[3]), min(i["poly"].bounds[2], i["poly"].bounds[3]))),
            # por prioridad: las prioritarias primero, luego por area
            sorted(items, key=lambda i: (
                1 if i.get("priority", 0) <= 0 else 0,
                i.get("priority", 0), -i["area"])),
        ]
        rng = random.Random(20260812)
        shuffle_count = 60 if intensive else 10
        for _ in range(shuffle_count):
            shuffled = list(items)
            rng.shuffle(shuffled)
            strategies.append(shuffled)
        return strategies

    rotation_modes = [allow_rotation, False] if allow_rotation else [False]
    placement_modes = ["maxrects", "guillotine", "bottomleft", "compact"]

    all_strategies = []
    for rotation in rotation_modes:
        for placement_mode in placement_modes:
            for items_sorted in sorters(items):
                for bins_sorted in bin_orders:
                    all_strategies.append((placement_mode, rotation, items_sorted,
                                           bins_sorted, kerf))

    best = None
    with ThreadPoolExecutor(max_workers=min(4, len(all_strategies))) as executor:
        futures = {executor.submit(_try_polygon_strategy, st): st for st in all_strategies}
        for future in as_completed(futures):
            try:
                score, results, pool = future.result()
                if best is None or score > best[0]:
                    best = (score, results, pool)
            except Exception:
                pass

    _, results, unplaced = best

    for result in results:
        blocked = []
        for hole in result.get("holes") or []:
            obstacle = sg.Polygon(hole).buffer(kerf / 2, join_style=2)
            prepare(obstacle)
            blocked.append(obstacle)
        result["pieces"] = _recompact_polygon_infos(
            result["pieces"], result["width"], result["height"], kerf, blocked)
        result["used_area"] = sum(info[5] for info in result["pieces"])
        area = result["width"] * result["height"]
        result["utilization"] = result["used_area"] / area
        result["waste_area"] = max(0.0, area - result["used_area"])

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
            "holes": b.get("holes") or [],
            "polygon": b.get("polygon"),
            "used_area": round(b["used_area"], 4),
            "waste_area": round(b["waste_area"], 4),
            "utilization": round(b["utilization"] * 100, 2),
            "pieces": _order_by_priority([
                {
                    "name": name, "width": round(poly.bounds[2], 3),
                    "height": round(poly.bounds[3], 3),
                    "x": round(x + offset[0], 3),
                    "y": round(y + offset[1], 3),
                    "rotated": rot, **_polygon_points(poly),
                    "priority": priority_map.get(name, 0),
                    "lines": [
                        [line_layer, round(x1, 3), round(y1, 3),
                         round(x2, 3), round(y2, 3)]
                        for line_layer, x1, y1, x2, y2 in lines
                    ],
                }
                for name, poly, x, y, rot, _area, lines, _collision, offset
                in b["pieces"]
            ]),
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


def validate_result(result):
    """Comprueba limites y solapamientos del resultado antes de fabricarlo."""
    errors = []
    for slab in result.get("slabs_used", []):
        slab_box = sg.box(0, 0, slab["width"], slab["height"])
        obstacles = [sg.Polygon(hole) for hole in slab.get("holes") or []]
        geometries = []
        for piece in slab.get("pieces", []):
            if piece.get("polygon"):
                geometry = sg.Polygon(
                    [(x + piece["x"], y + piece["y"]) for x, y in piece["polygon"]],
                    [[(x + piece["x"], y + piece["y"]) for x, y in hole]
                     for hole in piece.get("holes") or []],
                )
            else:
                geometry = sg.box(
                    piece["x"], piece["y"],
                    piece["x"] + piece["width"], piece["y"] + piece["height"],
                )
            if not geometry.is_valid:
                errors.append(f"Geometria invalida: {piece.get('name', 'Pieza')}")
            if not slab_box.covers(geometry):
                errors.append(f"Fuera de plancha: {piece.get('name', 'Pieza')}")
            if any(geometry.intersection(obstacle).area > 1e-6 for obstacle in obstacles):
                errors.append(f"Sobre perforacion: {piece.get('name', 'Pieza')}")
            for other_name, other in geometries:
                if geometry.intersection(other).area > 1e-6:
                    errors.append(
                        f"Solapamiento: {piece.get('name', 'Pieza')} con {other_name}"
                    )
            geometries.append((piece.get("name", "Pieza"), geometry))
    return {"valid": not errors, "errors": errors}
