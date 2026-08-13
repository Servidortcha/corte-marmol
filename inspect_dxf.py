import sys
from core.dxf_io import parse_dxf_bytes

for path in sys.argv[1:]:
    data = open(path, "rb").read()
    try:
        r = parse_dxf_bytes(data)
    except Exception as e:
        print(f"== {path} ERROR: {e}")
        continue
    print(f"== {path}")
    print(f"   piezas: {r['stats']['piece_count']} | area total: {r['stats']['total_area']} mm2 "
          f"({r['stats']['total_area']/1e6:.3f} m2) | unidades: {r['stats']['units']}")
    for p in r["pieces"][:40]:
        print(f"   - {p['name']:25s} {p['width']:8.1f} x {p['height']:8.1f}  area {p['area']:10.0f} mm2"
              f"  holes={len(p['holes'])} n={len(p['polygon'])}")
    if len(r["pieces"]) > 40:
        print(f"   ... y {len(r['pieces'])-40} mas")
    print()
