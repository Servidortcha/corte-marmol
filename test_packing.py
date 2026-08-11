from core.packing import optimize

pieces = [
    {"name": "Mesa", "width": 800, "height": 1200, "quantity": 1},
    {"name": "Mesita", "width": 500, "height": 500, "quantity": 2},
    {"name": "Mesada", "width": 900, "height": 600, "quantity": 1},
    {"name": "Repisa", "width": 300, "height": 1500, "quantity": 3},
]
slabs = [
    {"name": "Blanco", "width": 3200, "height": 1600, "quantity": 1},
    {"name": "Gris", "width": 2800, "height": 1400, "quantity": 1},
]

r = optimize(pieces, slabs, kerf=4, allow_rotation=True)
for k in ("pieces_placed", "pieces_unplaced", "global_utilization", "total_waste"):
    print(k, "=", r[k])
for s in r["slabs_used"]:
    print(s["name"], s["width"], "x", s["height"], "util=", s["utilization"], "%")
    for p in s["pieces"]:
        print("   ", p["name"], p["width"], "x", p["height"], "at", p["x"], p["y"], "rot=", p["rotated"])
