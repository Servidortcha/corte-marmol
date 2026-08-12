from pydantic import BaseModel, Field


class PieceIn(BaseModel):
    name: str = "Pieza"
    width: float = Field(gt=0, description="Ancho en mm")
    height: float = Field(gt=0, description="Alto en mm")
    quantity: int = Field(1, ge=1)
    polygon: list[list[float]] | None = Field(
        None, description="Forma libre como lista de puntos [x, y] (opcional)")
    holes: list[list[list[float]]] | None = Field(
        None, description="Agujeros como listas de puntos (opcional)")


class SlabIn(BaseModel):
    name: str = "Plancha"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(1, ge=1)


class OptimizeRequest(BaseModel):
    pieces: list[PieceIn] = Field(min_length=1)
    slabs: list[SlabIn] = Field(min_length=1)
    kerf: float = Field(0.0, ge=0, description="Ancho de hoja de sierra")
    allow_rotation: bool = True


class PieceOut(BaseModel):
    name: str
    width: float
    height: float
    x: float
    y: float
    rotated: bool = False
    polygon: list[list[float]] | None = None
    holes: list[list[list[float]]] | None = None


class SlabOut(BaseModel):
    name: str
    width: float
    height: float
    used_area: float = 0.0
    waste_area: float = 0.0
    utilization: float = 0.0
    pieces: list[PieceOut]


class ExportRequest(BaseModel):
    slabs_used: list[SlabOut]
    kerf: float = Field(0.0, ge=0)
