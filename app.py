from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.models import OptimizeRequest
from core.packing import optimize

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Corte de Marmol", description="Optimizacion de corte de marmol en planchas")


@app.post("/api/optimize")
def run_optimize(req: OptimizeRequest):
    pieces = [
        {"name": p.name, "width": p.width, "height": p.height, "quantity": p.quantity}
        for p in req.pieces
    ]
    slabs = [
        {"name": s.name, "width": s.width, "height": s.height, "quantity": s.quantity}
        for s in req.slabs
    ]
    return optimize(pieces, slabs, kerf=req.kerf, allow_rotation=req.allow_rotation)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
