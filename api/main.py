from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Tuple, Optional, Literal

from core.geometry import rect_to_poly, poly_area, circle_area


# --- Initialisation ---
app = FastAPI(title="IA Paysagiste - Prototype de calcul de surfaces")


# --- Modèles d’entrée ---
class Trou(BaseModel):
    forme: Literal["rectangle", "cercle"]
    position: Tuple[float, float]
    dimensions: Optional[Tuple[float, float]] = None  # si rectangle
    rayon: Optional[float] = None  # si cercle


class Rectangle(BaseModel):
    origine: Tuple[float, float]  # coin Sud-Ouest (x, y)
    largeur: float
    hauteur: float


class AnalyseEntree(BaseModel):
    parcelle: Rectangle
    maison: Rectangle
    terrasse: Rectangle
    trous_terrasse: List[Trou] = []


# --- Modèle de sortie ---
class AnalyseSortie(BaseModel):
    surfaces_m2: dict


# --- Routes API ---
@app.get("/")
def root():
    # Quand on va sur http://127.0.0.1:8000/ ça renvoie automatiquement vers /docs
    return RedirectResponse(url="/docs")


@app.get("/ping")
def ping():
    return {"statut": "ok", "message": "IA Paysagiste opérationnelle en français 🇫🇷"}


@app.post("/analyser", response_model=AnalyseSortie)
def analyser(donnees: AnalyseEntree):
    """Calcule les surfaces totales et utiles à partir des données d’entrée"""

    # Parcelle
    poly_parcelle = rect_to_poly(*donnees.parcelle.origine, donnees.parcelle.largeur, donnees.parcelle.hauteur)
    surface_parcelle = poly_area(poly_parcelle)

    # Maison
    poly_maison = rect_to_poly(*donnees.maison.origine, donnees.maison.largeur, donnees.maison.hauteur)
    surface_maison = poly_area(poly_maison)

    # Terrasse
    poly_terrasse = rect_to_poly(*donnees.terrasse.origine, donnees.terrasse.largeur, donnees.terrasse.hauteur)
    surface_terrasse = poly_area(poly_terrasse)

    # Trous dans la terrasse (massifs, arbres, etc.)
    surface_trous = 0.0
    for t in donnees.trous_terrasse:
        if t.forme == "rectangle" and t.dimensions:
            surface_trous += t.dimensions[0] * t.dimensions[1]
        elif t.forme == "cercle" and t.rayon:
            surface_trous += circle_area(t.rayon)

    surface_terrasse_utile = max(surface_terrasse - surface_trous, 0.0)

    # Jardin = surface restante
    surface_jardin_approx = max(surface_parcelle - surface_maison - surface_terrasse_utile, 0.0)

    return AnalyseSortie(surfaces_m2={
        "Surface totale de la parcelle": round(surface_parcelle, 2),
        "Surface de la maison": round(surface_maison, 2),
        "Surface totale de la terrasse": round(surface_terrasse, 2),
        "Surface des trous/massifs": round(surface_trous, 2),
        "Surface utile de la terrasse": round(surface_terrasse_utile, 2),
        "Surface approximative du jardin": round(surface_jardin_approx, 2),
    })
