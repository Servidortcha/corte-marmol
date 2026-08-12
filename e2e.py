import json
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1. parse dxf
fd = open("muestra.dxf", "rb").read()
boundary = "----b"
body = b""
body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"muestra.dxf\"\r\n"
         "Content-Type: application/octet-stream\r\n\r\n").encode()
body += fd + b"\r\n"
body += f"--{boundary}--\r\n".encode()

req = urllib.request.Request(f"{BASE}/api/dxf-parse", data=body,
                             headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
parsed = json.loads(urllib.request.urlopen(req).read())

pieces = []
for p in parsed["pieces"]:
    pieces.append({"name": p["name"], "width": p["width"], "height": p["height"],
                   "quantity": 1, "polygon": p["polygon"], "holes": p["holes"]})
slabs = [{"name": "Plancha", "width": 3200, "height": 1600, "quantity": 2}]

req = urllib.request.Request(f"{BASE}/api/optimize",
                             data=json.dumps({"pieces": pieces, "slabs": slabs,
                                              "kerf": 4, "allow_rotation": True}).encode(),
                             headers={"Content-Type": "application/json"})
res = json.loads(urllib.request.urlopen(req).read())
print("placed:", res["pieces_placed"], "unplaced:", res["pieces_unplaced"],
      "util:", res["global_utilization"], "slabs used:", len(res["slabs_used"]))
for s in res["slabs_used"]:
    for p in s["pieces"]:
        print("  ", p["name"], "at", p["x"], p["y"], "rot", p["rotated"],
              "holes:", len(p.get("holes", [])), "polypts:", len(p["polygon"]))

req = urllib.request.Request(f"{BASE}/api/export-dxf",
                             data=json.dumps({"slabs_used": res["slabs_used"],
                                              "kerf": res["kerf"]}).encode(),
                             headers={"Content-Type": "application/json"})
dxf = urllib.request.urlopen(req).read()
open("corte_optimizado.dxf", "wb").write(dxf)
print("export dxf:", len(dxf), "bytes")

# verify re-parse of exported file
from core.dxf_io import parse_dxf_bytes
back = parse_dxf_bytes(dxf)
print("re-parse:", back["stats"]["piece_count"], "pieces")
