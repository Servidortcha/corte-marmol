from pydantic import BaseModel, Field


class PieceIn(BaseModel):
    name: str = "Pieza"
    width: float = Field(gt=0, description="Ancho en mm")
    height: float = Field(gt=0, description="Alto en mm")
    quantity: int = Field(1, ge=1)
    priority: int = Field(
        0, ge=0, description="Prioridad de corte: 1 primero, 2 despues... 0 = sin prioridad")
    allow_rotation: bool | None = Field(
        None, description="Permite rotar esta pieza. None = usar la opcion general")
    polygon: list[list[float]] | None = Field(
        None, description="Forma libre como lista de puntos [x, y] (opcional)")
    holes: list[list[list[float]]] | None = Field(
        None, description="Agujeros como listas de puntos (opcional)")
    lines: list[list] | None = Field(
        None, description="Segmentos originales de color: [capa, x1, y1, x2, y2]")


class SlabIn(BaseModel):
    name: str = "Plancha"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(1, ge=1)
    priority: int = Field(
        0, ge=0, description="Prioridad de uso: 1 se usa primero, 0 = normal")
    holes: list[list[list[float]]] | None = Field(
        None, description="Obstaculos internos de la chapa como contornos cerrados")


class OptimizeRequest(BaseModel):
    pieces: list[PieceIn] = Field(min_length=1)
    slabs: list[SlabIn] = Field(min_length=1)
    kerf: float = Field(0.0, ge=0, description="Ancho de hoja de sierra")
    allow_rotation: bool = True
    intensive: bool = Field(
        False, description="Busqueda exhaustiva: mas ordenamientos, mas lenta")
    layers_colors: dict[str, int] | None = Field(
        None, description="Colores ACI de las capas originales del DXF")
    edge_distances: dict[str, float] | None = Field(
        None, description="Separacion total (mm) por capa de linea, p.ej. {'ROJO_INGLETE': 10}")


class PieceOut(BaseModel):
    name: str
    width: float
    height: float
    x: float
    y: float
    rotated: bool = False
    polygon: list[list[float]] | None = None
    holes: list[list[list[float]]] | None = None
    lines: list[list] | None = Field(
        None, description="Segmentos de color originales: [capa, x1, y1, x2, y2]")


class SlabOut(BaseModel):
    name: str
    width: float
    height: float
    used_area: float = 0.0
    waste_area: float = 0.0
    utilization: float = 0.0
    pieces: list[PieceOut]
    holes: list[list[list[float]]] | None = None


class ExportRequest(BaseModel):
    slabs_used: list[SlabOut]
    kerf: float = Field(0.0, ge=0)
    layers_colors: dict[str, int] | None = Field(
        None, description="Colores ACI de las capas originales del DXF")


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: dict
    job_id: int | None = Field(None, gt=0)


class LicenseIn(BaseModel):
    key: str = Field(min_length=4, max_length=120)
