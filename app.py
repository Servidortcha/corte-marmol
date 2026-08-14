from pathlib import Path
import io
import sys
import threading
import time
import uuid
import zipfile

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from core.dxf_io import export_result_dxf, parse_dxf_bytes
from core.licencia import activate as licencia_activate
from core.licencia import status as licencia_status
from core.models import ExportRequest, JobIn, LicenseIn, OptimizeRequest
from core.packing import optimize, optimize_polygons, validate_result
from core.storage import get_job, init_db, list_jobs, save_job


def _resource_path(name):
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / name
    return Path(__file__).resolve().parent / name


STATIC_DIR = _resource_path("static")


def _require_licencia():
    estado = licencia_status()
    if estado["status"] == "expired":
        raise HTTPException(
            status_code=403,
            detail=(
                "La licencia de prueba vencio. Ingresa una clave de "
                "activacion en la app o solicitala al proveedor."
            ),
        )
    return estado

app = FastAPI(title="La Puntual Marmolería",
              description="Optimización de corte de mármol en planchas")
init_db()

_JOBS: dict[str, dict] = {}


def _run_optimize_job(job_id: str, req_dict: dict):
    try:
        request = OptimizeRequest(**req_dict)
        result = run_optimize(request)
        _JOBS[job_id] = {"status": "done", "result": result}
    except Exception as exc:
        _JOBS[job_id] = {"status": "error", "error": str(exc)}


@app.get("/api/license/status")
def license_status():
    return licencia_status()


@app.post("/api/license/activate")
def license_activate(req: LicenseIn):
    ok, message = licencia_activate(req.key)
    return {"ok": ok, "message": message, "status": licencia_status()}


@app.post("/api/optimize-async")
def optimize_async(req: OptimizeRequest):
    _require_licencia()
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "started": time.time()}
    thread = threading.Thread(
        target=_run_optimize_job, args=(job_id, req.model_dump()),
        daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "running"}


@app.get("/api/optimize-async/{job_id}")
def optimize_status(job_id: str):
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job


@app.post("/api/optimize")
def run_optimize(req: OptimizeRequest):
    _require_licencia()
    has_polygons = any(p.polygon for p in req.pieces)
    if has_polygons:
        polygon_pieces = [
            {
                "name": p.name,
                "polygon": p.polygon or [[0, 0], [p.width, 0],
                                           [p.width, p.height], [0, p.height]],
                "holes": p.holes,
                "quantity": p.quantity,
                "lines": p.lines,
            }
            for p in req.pieces
        ]
        slabs = [
            {"name": s.name, "width": s.width, "height": s.height,
             "quantity": s.quantity, "holes": s.holes}
            for s in req.slabs
        ]
        result = optimize_polygons(polygon_pieces, slabs, kerf=req.kerf,
                                   allow_rotation=req.allow_rotation,
                                   intensive=req.intensive,
                                   edge_distances=req.edge_distances)
        result["layers_colors"] = req.layers_colors or {}
        result["validation"] = validate_result(result)
        return result
    pieces = [
        {"name": p.name, "width": p.width, "height": p.height, "quantity": p.quantity}
        for p in req.pieces
    ]
    slabs = [
        {"name": s.name, "width": s.width, "height": s.height,
         "quantity": s.quantity, "holes": s.holes}
        for s in req.slabs
    ]
    result = optimize(pieces, slabs, kerf=req.kerf, allow_rotation=req.allow_rotation,
                      intensive=req.intensive)
    result["layers_colors"] = req.layers_colors or {}
    result["validation"] = validate_result(result)
    return result


@app.post("/api/dxf-parse")
async def dxf_parse(file: UploadFile):
    _require_licencia()
    data = await file.read()
    return parse_dxf_bytes(data)


@app.post("/api/slab-parse")
async def slab_parse(file: UploadFile):
    _require_licencia()
    data = await file.read()
    parsed = parse_dxf_bytes(data)
    if not parsed["pieces"]:
        return {"error": "No se encontraron contornos cerrados."}
    outer = max(parsed["pieces"], key=lambda piece: piece["area"])
    minx = min(point[0] for point in outer["polygon"])
    miny = min(point[1] for point in outer["polygon"])
    holes = [
        [[round(x - minx, 3), round(y - miny, 3)] for x, y in ring]
        for ring in outer.get("holes") or []
    ]
    return {
        "name": file.filename or "Chapa DXF",
        "width": outer["width"],
        "height": outer["height"],
        "holes": holes,
        "hole_count": len(holes),
    }


@app.post("/api/export-dxf")
def dxf_export(req: ExportRequest):
    _require_licencia()
    slabs = [s.model_dump() for s in req.slabs_used]
    if len(slabs) > 1:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for index, slab in enumerate(slabs, start=1):
                output.writestr(
                    f"plancha_{index:03d}.dxf",
                    export_result_dxf([slab], kerf=req.kerf,
                                      layer_colors=req.layers_colors),
                )
        content = archive.getvalue()
        media_type = "application/zip"
        filename = "cortes_optimizado.zip"
    else:
        content = export_result_dxf(slabs, kerf=req.kerf,
                                    layer_colors=req.layers_colors)
        media_type = "application/dxf"
        filename = "corte_optimizado.dxf"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs")
def jobs_list():
    return list_jobs()


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job


@app.post("/api/jobs")
def job_save(req: JobIn):
    if req.job_id is not None and get_job(req.job_id) is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return save_job(req.name, req.payload, req.job_id)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
