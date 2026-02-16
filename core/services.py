from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.geometry import rect_to_poly, poly_area, circle_area
from core.schemas import (
    TerrainInput,
    Shape2D,
    PlantesFiltrerInput,
    PlantesFiltrerOutput,
    Plante,
    PlantationRequest,
    PlantationPlanOutput,
    PlantPlacement,
)

import csv
from pathlib import Path
import pandas as pd
from pvlib.solarposition import get_solarposition
import reverse_geocoder as rg


def _classe_from_minutes(minutes: int, max_minutes: int) -> str:
    if max_minutes <= 0:
        return "ombre"
    ratio = minutes / max_minutes
    if ratio <= 0.25:
        return "ombre"
    if ratio <= 0.60:
        return "mi_ombre"
    return "plein_soleil"


def proposer_plantation(req: PlantationRequest) -> PlantationPlanOutput:
    terrain = req.terrain

    expo = compute_exposition_precise(terrain)
    cells = expo["cells"]
    max_minutes = int(expo["resume"].get("max_minutes_theorique", 0))

    plantes = load_plantes()

    if req.sol:
        plantes = [p for p in plantes if p.sol == req.sol]
    if req.climat:
        plantes = [p for p in plantes if p.climat == req.climat]

    plantes_par_expo = {
        "plein_soleil": [p for p in plantes if p.exposition == "plein_soleil"],
        "mi_ombre": [p for p in plantes if p.exposition == "mi_ombre"],
        "ombre": [p for p in plantes if p.exposition == "ombre"],
    }

    placements: List[PlantPlacement] = []
    used = set()

    for c in cells:
        x, y = float(c["x"]), float(c["y"])
        minutes = int(c["score"])
        classe = _classe_from_minutes(minutes, max_minutes)

        candidates = plantes_par_expo.get(classe, [])
        if not candidates:
            continue

        idx = len(placements) % len(candidates)
        p = candidates[idx]

        step = max(1, int(round(p.distance_m / terrain.pas_grille_m)))
        key = (int(x / terrain.pas_grille_m), int(y / terrain.pas_grille_m))

        if (key[0] % step != 0) or (key[1] % step != 0):
            continue

        if key in used:
            continue
        used.add(key)

        placements.append(
            PlantPlacement(
                x=x,
                y=y,
                nom=p.nom,
                type=p.type,
                exposition=p.exposition,
                distance_m=p.distance_m,
            )
        )

    resume = expo["resume"].copy()
    resume["nb_placements"] = len(placements)
    resume["sol_filtre"] = req.sol
    resume["climat_filtre"] = req.climat

    return PlantationPlanOutput(resume=resume, placements=placements)



def compute_surfaces(terrain: TerrainInput) -> Dict[str, float]:
    poly_parcelle = rect_to_poly(
        *terrain.parcelle.origine, terrain.parcelle.largeur, terrain.parcelle.hauteur
    )
    surface_parcelle = poly_area(poly_parcelle)

    poly_maison = rect_to_poly(
        *terrain.maison.origine, terrain.maison.largeur, terrain.maison.hauteur
    )
    surface_maison = poly_area(poly_maison)

    poly_terrasse = rect_to_poly(
        *terrain.terrasse.origine, terrain.terrasse.largeur, terrain.terrasse.hauteur
    )
    surface_terrasse = poly_area(poly_terrasse)

    surface_trous = 0.0
    for t in terrain.trous_terrasse:
        if t.forme == "rectangle" and t.dimensions:
            surface_trous += float(t.dimensions[0]) * float(t.dimensions[1])
        elif t.forme == "cercle" and t.rayon is not None:
            surface_trous += circle_area(float(t.rayon))

    surface_terrasse_utile = max(surface_terrasse - surface_trous, 0.0)
    surface_jardin_approx = max(surface_parcelle - surface_maison - surface_terrasse_utile, 0.0)

    return {
        "Surface totale de la parcelle": round(surface_parcelle, 2),
        "Surface de la maison": round(surface_maison, 2),
        "Surface totale de la terrasse": round(surface_terrasse, 2),
        "Surface des trous/massifs": round(surface_trous, 2),
        "Surface utile de la terrasse": round(surface_terrasse_utile, 2),
        "Surface approximative du jardin": round(surface_jardin_approx, 2),
    }


def build_plan_2d(terrain: TerrainInput) -> List[Shape2D]:
    shapes: List[Shape2D] = []

    shapes.append(
        Shape2D(
            type="rectangle",
            label="Parcelle",
            x=float(terrain.parcelle.origine[0]),
            y=float(terrain.parcelle.origine[1]),
            w=float(terrain.parcelle.largeur),
            h=float(terrain.parcelle.hauteur),
        )
    )

    shapes.append(
        Shape2D(
            type="rectangle",
            label="Maison",
            x=float(terrain.maison.origine[0]),
            y=float(terrain.maison.origine[1]),
            w=float(terrain.maison.largeur),
            h=float(terrain.maison.hauteur),
        )
    )

    shapes.append(
        Shape2D(
            type="rectangle",
            label="Terrasse",
            x=float(terrain.terrasse.origine[0]),
            y=float(terrain.terrasse.origine[1]),
            w=float(terrain.terrasse.largeur),
            h=float(terrain.terrasse.hauteur),
        )
    )

    for i, t in enumerate(terrain.trous_terrasse, start=1):
        if t.forme == "rectangle" and t.dimensions:
            shapes.append(
                Shape2D(
                    type="rectangle",
                    label=f"Trou {i}",
                    x=float(t.position[0]),
                    y=float(t.position[1]),
                    w=float(t.dimensions[0]),
                    h=float(t.dimensions[1]),
                )
            )
        elif t.forme == "cercle" and t.rayon is not None:
            shapes.append(
                Shape2D(
                    type="cercle",
                    label=f"Trou {i}",
                    x=float(t.position[0]),
                    y=float(t.position[1]),
                    r=float(t.rayon),
                )
            )

    return shapes


@dataclass(frozen=True)
class SunCase:
    name: str
    altitude_deg: float
    azimuth_deg: float


def _build_sun_cases(latitude: float) -> List[SunCase]:
    lat = abs(latitude)

    alt_winter = max(8.0, 90.0 - lat - 23.5)
    alt_equinox = max(12.0, 90.0 - lat)
    alt_summer = max(15.0, 90.0 - lat + 23.5)

    def trio(alt_mid: float) -> Tuple[float, float, float]:
        return (max(5.0, alt_mid - 15.0), alt_mid, max(5.0, alt_mid - 15.0))

    w_m, w_noon, w_a = trio(alt_winter)
    e_m, e_noon, e_a = trio(alt_equinox)
    s_m, s_noon, s_a = trio(alt_summer)

    az_morning = 135.0
    az_noon = 180.0
    az_afternoon = 225.0

    return [
        SunCase("hiver_matin", w_m, az_morning),
        SunCase("hiver_midi", w_noon, az_noon),
        SunCase("hiver_aprem", w_a, az_afternoon),
        SunCase("equinoxe_matin", e_m, az_morning),
        SunCase("equinoxe_midi", e_noon, az_noon),
        SunCase("equinoxe_aprem", e_a, az_afternoon),
        SunCase("ete_matin", s_m, az_morning),
        SunCase("ete_midi", s_noon, az_noon),
        SunCase("ete_aprem", s_a, az_afternoon),
    ]


def _rotate_point(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca)


def _is_in_shadow_by_house(
    cell: Tuple[float, float],
    house_origin: Tuple[float, float],
    house_w: float,
    house_h: float,
    house_height: float,
    sun_altitude_deg: float,
    sun_azimuth_deg: float,
    orientation_nord_deg: float,
) -> bool:
    alt = math.radians(max(1.0, sun_altitude_deg))
    L = house_height / math.tan(alt)

    az = math.radians(sun_azimuth_deg)
    dx = -math.sin(az)
    dy = -math.cos(az)

    cx, cy = cell
    hx, hy = house_origin

    cx2, cy2 = _rotate_point(cx, cy, -orientation_nord_deg)
    hx2, hy2 = _rotate_point(hx, hy, -orientation_nord_deg)

    x0, y0 = hx2, hy2
    x1, y1 = hx2 + house_w, hy2 + house_h

    if x0 <= cx2 <= x1 and y0 <= cy2 <= y1:
        return True

    house_cx = (x0 + x1) / 2.0
    house_cy = (y0 + y1) / 2.0

    vx = cx2 - house_cx
    vy = cy2 - house_cy
    t = vx * dx + vy * dy

    if t <= 0:
        return False
    if t > L:
        return False

    house_radius = 0.5 * math.hypot(house_w, house_h)

    px = vx - t * dx
    py = vy - t * dy
    dist_perp = math.hypot(px, py)

    return dist_perp <= house_radius


def compute_exposition(terrain: TerrainInput) -> Dict:
    sun_cases = _build_sun_cases(terrain.latitude)

    pas = float(terrain.pas_grille_m)
    W = float(terrain.parcelle.largeur)
    H = float(terrain.parcelle.hauteur)

    hx, hy = terrain.maison.origine
    hw = float(terrain.maison.largeur)
    hh = float(terrain.maison.hauteur)
    hZ = float(terrain.maison.hauteur_batiment)

    orientation = float(terrain.orientation_nord_deg)

    cells = []
    counts = {"ombre": 0, "mi_ombre": 0, "plein_soleil": 0}

    nx = int(math.ceil(W / pas))
    ny = int(math.ceil(H / pas))

    for iy in range(ny):
        for ix in range(nx):
            x = (ix + 0.5) * pas
            y = (iy + 0.5) * pas

            score = 0
            for sc in sun_cases:
                if not _is_in_shadow_by_house(
                    (x, y),
                    (hx, hy),
                    hw,
                    hh,
                    hZ,
                    sc.altitude_deg,
                    sc.azimuth_deg,
                    orientation,
                ):
                    score += 1

            if score <= 2:
                classe = "ombre"
            elif score <= 6:
                classe = "mi_ombre"
            else:
                classe = "plein_soleil"

            counts[classe] += 1
            cells.append({"x": round(x, 3), "y": round(y, 3), "score": score, "classe": classe})

    total = max(1, len(cells))
    resume = {
        "total_cells": total,
        "pct_ombre": round(100 * counts["ombre"] / total, 1),
        "pct_mi_ombre": round(100 * counts["mi_ombre"] / total, 1),
        "pct_plein_soleil": round(100 * counts["plein_soleil"] / total, 1),
        "sun_cases": [
            {"name": s.name, "altitude_deg": round(s.altitude_deg, 1), "azimuth_deg": s.azimuth_deg}
            for s in sun_cases
        ],
    }

    return {
        "pas_grille_m": pas,
        "largeur": W,
        "hauteur": H,
        "cells": cells,
        "resume": resume,
    }

def _plantes_csv_path() -> Path:
    # core/services.py -> remonte au dossier racine du projet -> data/plantes.csv
    return Path(__file__).resolve().parents[1] / "data" / "plantes.csv"


def load_plantes() -> List[Plante]:
    path = _plantes_csv_path()
    plantes: List[Plante] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plantes.append(
                Plante(
                    nom=row["nom"],
                    type=row["type"],
                    exposition=row["exposition"],
                    sol=row["sol"],
                    climat=row["climat"],
                    hauteur_m=float(row["hauteur_m"]),
                    largeur_m=float(row["largeur_m"]),
                    distance_m=float(row["distance_m"]),
                    floraison=row["floraison"],
                    feuillage=row["feuillage"],
                    couleur=row["couleur"],
                    notes=row["notes"],
                )
            )
    return plantes


def filtrer_plantes(filtres: PlantesFiltrerInput) -> PlantesFiltrerOutput:
    plantes = load_plantes()

    def match(p: Plante) -> bool:
        if filtres.exposition and p.exposition != filtres.exposition:
            return False
        if filtres.sol and p.sol != filtres.sol:
            return False
        if filtres.climat and p.climat != filtres.climat:
            return False
        if filtres.type and p.type != filtres.type:
            return False
        return True

    res = [p for p in plantes if match(p)]
    return PlantesFiltrerOutput(nb=len(res), plantes=res)

def reverse_city(latitude: float, longitude: float) -> dict:
    res = rg.search((latitude, longitude), mode=1)[0]
    # res contient: name, admin1, admin2, cc, lat, lon
    return {
        "city": res.get("name"),
        "region": res.get("admin1"),
        "country_code": res.get("cc"),
    }


def compute_exposition_precise(terrain: TerrainInput) -> Dict:
    pas_grille = float(terrain.pas_grille_m)
    W = float(terrain.parcelle.largeur)
    H = float(terrain.parcelle.hauteur)

    hx, hy = terrain.maison.origine
    hw = float(terrain.maison.largeur)
    hh = float(terrain.maison.hauteur)
    hZ = float(terrain.maison.hauteur_batiment)

    orientation = float(terrain.orientation_nord_deg)

    date = terrain.date_ref  # "YYYY-MM-DD"
    tz = terrain.timezone
    pas_min = int(terrain.pas_minutes)

    if terrain.heure_fin < terrain.heure_debut:
        raise ValueError("heure_fin doit etre >= heure_debut")

    start = pd.Timestamp(f"{date} {terrain.heure_debut:02d}:00:00", tz=tz)
    end = pd.Timestamp(f"{date} {terrain.heure_fin:02d}:00:00", tz=tz)
    times = pd.date_range(start=start, end=end, freq=f"{pas_min}min", inclusive="left")

    solpos = get_solarposition(times, latitude=float(terrain.latitude), longitude=float(terrain.longitude))
    altitudes = solpos["apparent_elevation"].to_numpy()
    azimuths = solpos["azimuth"].to_numpy()

    nx = int(math.ceil(W / pas_grille))
    ny = int(math.ceil(H / pas_grille))

    cells = []
    counts = {"ombre": 0, "mi_ombre": 0, "plein_soleil": 0}

    valid_sun = [(alt, az) for alt, az in zip(altitudes, azimuths) if alt > 0]
    max_steps = len(valid_sun)
    max_minutes = max_steps * pas_min

    for iy in range(ny):
        for ix in range(nx):
            x = (ix + 0.5) * pas_grille
            y = (iy + 0.5) * pas_grille

            sunny_steps = 0
            for alt, az in valid_sun:
                if not _is_in_shadow_by_house(
                    (x, y),
                    (float(hx), float(hy)),
                    hw,
                    hh,
                    hZ,
                    float(alt),
                    float(az),
                    orientation,
                ):
                    sunny_steps += 1

            minutes_soleil = sunny_steps * pas_min

            ratio = 0.0 if max_minutes == 0 else minutes_soleil / max_minutes
            if ratio <= 0.25:
                classe = "ombre"
            elif ratio <= 0.60:
                classe = "mi_ombre"
            else:
                classe = "plein_soleil"

            counts[classe] += 1
            cells.append({"x": round(x, 3), "y": round(y, 3), "score": int(minutes_soleil), "classe": classe})

    total = max(1, len(cells))
    resume = {
        "date_ref": terrain.date_ref,
        "timezone": terrain.timezone,
        "pas_minutes": pas_min,
        "plage": f"{terrain.heure_debut:02d}:00-{terrain.heure_fin:02d}:00",
        "max_minutes_theorique": int(max_minutes),
        "pct_ombre": round(100 * counts["ombre"] / total, 1),
        "pct_mi_ombre": round(100 * counts["mi_ombre"] / total, 1),
        "pct_plein_soleil": round(100 * counts["plein_soleil"] / total, 1),
    }

    loc = reverse_city(float(terrain.latitude), float(terrain.longitude))
    resume["location"] = loc

    return {"pas_grille_m": pas_grille, "largeur": W, "hauteur": H, "cells": cells, "resume": resume}
