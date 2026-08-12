import io
import math

import ezdxf
import shapely.geometry as sg

from core.dxf_io import parse_dxf_bytes, export_result_dxf
from core.packing import optimize_polygons


def build_sample_dxf():
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    # L-shape
    msp.add_lwpolyline([(1000, 0), (1600, 0), (1600, 300), (1300, 300), (1300, 600), (1000, 600)],
                       close=True, dxfattribs={"layer": "ESCALERA"})
    # Trapezoid
    msp.add_lwpolyline([(0, 500), (800, 500), (900, 1000), (100, 1000)], close=True,
                       dxfattribs={"layer": "MESADA"})
    # Circle with a hole (donut)
    msp.add_circle((2200, 900), radius=400, dxfattribs={"layer": "TAPA"})
    msp.add_circle((2200, 900), radius=100, dxfattribs={"layer": "TAPA"})
    # Open lines that form a rectangle contour
    for pts in [((0, 0), (400, 0)), ((400, 0), (400, 400)),
                ((400, 400), (0, 400)), ((0, 400), (0, 0))]:
        msp.add_line(*pts, dxfattribs={"layer": "REPISA"})

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


data = build_sample_dxf()
parsed = parse_dxf_bytes(data)
print("pieces:", len(parsed["pieces"]), "| total area:", parsed["stats"]["total_area"], "mm2")
for p in parsed["pieces"]:
    print(f"  {p['name']:10s} bbox {p['width']}x{p['height']}  area {p['area']}  n={len(p['polygon'])}")

assert len(parsed["pieces"]) >= 4, "deberian detectarse al menos 4 piezas"

pieces = parsed["pieces"]
slabs = [{"name": "Plancha", "width": 3000, "height": 1500, "quantity": 1}]
res = optimize_polygons(pieces, slabs, kerf=4, allow_rotation=True)
print("\nplaced:", res["pieces_placed"], "unplaced:", res["pieces_unplaced"],
      "util:", res["global_utilization"], "%")

# check no overlaps among placed polygons (shapely)
placed_geo = []
for s in res["slabs_used"]:
    for p in s["pieces"]:
        g = sg.Polygon([(x + p["x"], y + p["y"]) for x, y in p["polygon"]])
        assert g.is_valid, f"poligono invalido {p['name']}"
        for other in placed_geo:
            assert not g.intersects(other.buffer(-1e-6)), f"solapamiento: {p['name']}"
        placed_geo.append(g)
print("sin solapamientos OK")

dxf_out = export_result_dxf(res["slabs_used"], kerf=4)
print("export dxf bytes:", len(dxf_out))
back = parse_dxf_bytes(dxf_out)
print("re-parse pieces:", len(back["pieces"]))
