from typing import List, Tuple, Optional, Literal
from pydantic import BaseModel, Field


class Rectangle2D(BaseModel):
    origine: Tuple[float, float] = Field(..., description="Coin Sud-Ouest (x, y) en metres")
    largeur: float = Field(..., ge=0, description="Largeur en metres")
    hauteur: float = Field(..., ge=0, description="Hauteur en metres")


class Maison(Rectangle2D):
    hauteur_batiment: float = Field(6.0, ge=0, description="Hauteur du batiment en metres")


class Trou(BaseModel):
    forme: Literal["rectangle", "cercle"]
    position: Tuple[float, float] = Field(..., description="Position (x, y) en metres")
    dimensions: Optional[Tuple[float, float]] = Field(None, description="(largeur, hauteur) si rectangle")
    rayon: Optional[float] = Field(None, ge=0, description="Rayon si cercle")


class TerrainInput(BaseModel):
    parcelle: Rectangle2D
    maison: Maison
    terrasse: Rectangle2D
    trous_terrasse: List[Trou] = Field(default_factory=list)

    orientation_nord_deg: float = Field(0.0, description="Orientation du nord en degres (0 = nord en haut)")
    latitude: float = Field(48.8566, description="Latitude du terrain (ex: Paris = 48.8566)")
    pas_grille_m: float = Field(1.0, gt=0, description="Pas de discretisation de la grille en metres")


class SurfacesOutput(BaseModel):
    surfaces_m2: dict


class CellExposition(BaseModel):
    x: float
    y: float
    score: int
    classe: Literal["ombre", "mi_ombre", "plein_soleil"]


class ExpositionOutput(BaseModel):
    pas_grille_m: float
    largeur: float
    hauteur: float
    cells: List[CellExposition]
    resume: dict


class Shape2D(BaseModel):
    type: Literal["rectangle", "cercle"]
    label: str
    x: float
    y: float
    w: Optional[float] = None
    h: Optional[float] = None
    r: Optional[float] = None


class Plan2DOutput(BaseModel):
    shapes: List[Shape2D]
