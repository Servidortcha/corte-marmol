from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from core.dxf_io import export_result_dxf, parse_dxf_bytes
from core.models import ExportRequest, OptimizeRequest
from core.packing import optimize, optimize_polygons

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Corte de Marmol", description="Optimizacion de corte de marmol en planchas")


@app.post("/api/optimize")
def run_optimize(req: OptimizeRequest):
    has_polygons = any(p.polygon for p in req.pieces)
    if has_polygons:
        polygon_pieces = [
            {"name": p.name, "polygon": p.polygon, "holes": p.holes, "quantity": p.quantity}
            for p in req.pieces if p.polygon
        ]
        slabs = [
            {"name": s.name, "width": s.width, "height": s.height, "quantity": s.quantity}
            for s in req.slabs
        ]
        return optimize_polygons(polygon_pieces, slabs, kerf=req.kerf,
                                 allow_rotation=req.allow_rotation)
    pieces = [
        {"name": p.name, "width": p.width, "height": p.height, "quantity": p.quantity}
        for p in req.pieces
    ]
    slabs = [
        {"name": s.name, "width": s.width, "height": s.height, "quantity": s.quantity}
        for s in req.slabs
    ]
    return optimize(pieces, slabs, kerf=req.kerf, allow_rotation=req.allow_rotation)


@app.post("/api/dxf-parse")
async def dxf_parse(file: UploadFile):
    data = await file.read()
    return parse_dxf_bytes(data)


@app.post("/api/export-dxf")
def dxf_export(req: ExportRequest):
    content = export_result_dxf(
        [s.model_dump() for s in req.slabs_used], kerf=req.kerf)
    return Response(
        content=content,
        media_type="application/dxf",
        headers={"Content-Disposition": 'attachment; filename="corte_optimizado.dxf"'},
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
