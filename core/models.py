from pydantic import BaseModel, Field


class PieceIn(BaseModel):
    name: str = "Pieza"
    width: float = Field(gt=0, description="Ancho en mm")
    height: float = Field(gt=0, description="Alto en mm")
    quantity: int = Field(1, ge=1)


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
