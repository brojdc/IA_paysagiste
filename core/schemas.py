# core/schemas.py
from typing import List, Tuple, Optional, Literal

from pydantic import BaseModel, Field


class ExpositionV2Input(BaseModel):
    lat: float
    lon: float
    date: str
    timezone: str
    north_offset: float
    step_minutes: int = 30


# -------------------------
# Géométrie de base
# -------------------------
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


class ObstacleSegment(BaseModel):
    type: Literal["haie", "mur"]
    a: Tuple[float, float] = Field(..., description="Point A (x, y)")
    b: Tuple[float, float] = Field(..., description="Point B (x, y)")
    hauteur: float = Field(2.0, ge=0, description="Hauteur (m)")


class HaieAuto(BaseModel):
    """Haïe auto-générée basée sur les côtés de la maison."""
    cote: Literal["nord", "sud", "est", "ouest"] = Field(..., description="Côté de la maison")
    hauteur: float = Field(2.0, ge=0, description="Hauteur de la haïe (m)")
    epaisseur: float = Field(0.3, ge=0.1, description="Largeur/épaisseur haïe (m)")


# -------------------------
# Entrée principale terrain
# -------------------------
class TerrainInput(BaseModel):
    parcelle: Rectangle2D
    zone_analyse: Optional[dict] = None

    # plusieurs blocs maison (maison principale + extensions)
    maisons: List[Maison] = Field(
        default_factory=list,
        description="Liste des blocs de maison (maison principale + extensions).",
    )

    # compat: ancienne version (une seule maison)
    maison: Optional[Maison] = Field(
        default=None,
        description="(Compat) Ancienne version: une seule maison. Si renseigné, à convertir en 'maisons'.",
    )

    terrasse: Rectangle2D
    trous_terrasse: List[Trou] = Field(default_factory=list)

    # Haies auto-générées basées sur les côtés de la maison
    haies_auto: List[HaieAuto] = Field(
        default_factory=list,
        description="Haïes auto-générées sur les côtés de la maison (nord/sud/est/ouest)",
    )

    # Haies/murs sous forme de segments (ancien système, pour compatibilité)
    obstacles: List[ObstacleSegment] = Field(
        default_factory=list,
        description="Haies/murs sous forme de segments",
    )

    orientation_nord_deg: float = Field(0.0, description="Orientation du nord en degres (0 = nord en haut)")
    latitude: float = Field(48.8566, description="Latitude du terrain (ex: Paris = 48.8566)")
    longitude: float = Field(2.3522, description="Longitude du terrain (ex: Paris = 2.3522)")

    pas_grille_m: float = Field(1.0, gt=0, description="Pas de discretisation de la grille en metres")

    timezone: str = Field("Europe/Paris", description="Timezone IANA (ex: Europe/Paris)")
    date_ref: str = Field("2026-06-21", description="Date de reference YYYY-MM-DD")
    pas_minutes: int = Field(10, gt=0, description="Pas de temps en minutes pour l'ensoleillement")
    heure_debut: int = Field(6, ge=0, le=23, description="Heure de debut (0-23)")
    heure_fin: int = Field(21, ge=0, le=23, description="Heure de fin (0-23)")

    haie_position: str = Field("À la lisière de la parcelle (recommandé)", description="Positionnement des haies: lisière ou maison")

    def get_blocs_maison(self) -> List[Maison]:
        """
        Helper pratique (optionnel).
        Utilise 'maisons' si fourni, sinon fallback sur 'maison' (ancienne version).
        """
        if self.maisons:
            return self.maisons
        if self.maison is not None:
            return [self.maison]
        return []


# -------------------------
# Outputs
# -------------------------
class SurfacesOutput(BaseModel):
    surfaces_m2: dict
    # résumé et méta-informations générées par l'API (zones, obstacles, etc.)
    resume: Optional[dict] = None


class CellExposition(BaseModel):
    x: float
    y: float
    score: int
    classe: Literal["ombre", "mi_ombre", "plein_soleil"]


class CellExpositionProgressive(BaseModel):
    """Cellule d'exposition avec valeur continue (0-100%)."""
    x: float
    y: float
    percentage: float = Field(..., ge=0, le=100, description="Pourcentage d'ensoleillement (0-100%)")


class ExpositionOutput(BaseModel):
    pas_grille_m: float
    largeur: float
    hauteur: float
    cells: List[CellExposition]
    resume: dict


class ExpositionPreciseOutput(BaseModel):
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
    # optionally include plants placements (coordonnées et infos) pour affichage sur le plan
    plants: Optional[List["PlantPlacement"]] = None


class Plante(BaseModel):
    nom: str
    type: str
    exposition: Literal["plein_soleil", "mi_ombre", "ombre"]
    sol: Literal["drainant", "normal", "argileux", "humide"]
    climat: Literal["oceanique", "continental", "mediterraneen", "montagnard"]

    hauteur_m: float = Field(..., ge=0)
    largeur_m: float = Field(..., ge=0)
    distance_m: float = Field(..., ge=0)

    floraison: str
    feuillage: str
    couleur: str
    notes: str

    # nouveaux champs pour enrichir la base de plantes
    photo_url: Optional[str] = None
    exigences: Optional[str] = None


class PlantesFiltrerInput(BaseModel):
    exposition: Optional[Literal["plein_soleil", "mi_ombre", "ombre"]] = None
    sol: Optional[Literal["drainant", "normal", "argileux", "humide"]] = None
    climat: Optional[Literal["oceanique", "continental", "mediterraneen", "montagnard"]] = None
    type: Optional[str] = None


class PlantesFiltrerOutput(BaseModel):
    nb: int
    plantes: List[Plante]


class PlantationRequest(BaseModel):
    terrain: TerrainInput
    sol: Optional[Literal["drainant", "normal", "argileux", "humide"]] = None
    climat: Optional[Literal["oceanique", "continental", "mediterraneen", "montagnard"]] = None


class PlantPlacement(BaseModel):
    x: float
    y: float
    nom: str
    type: str
    exposition: Literal["plein_soleil", "mi_ombre", "ombre"]
    distance_m: float


class PlantationPlanOutput(BaseModel):
    resume: dict
    placements: List[PlantPlacement]