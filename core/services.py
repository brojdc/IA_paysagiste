# -*- coding: utf-8 -*-
# core/services.py
from __future__ import annotations

import math
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import reverse_geocoder as rg
from pvlib.solarposition import get_solarposition
from shapely.geometry import box as shapely_box

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
from core.shadow_engine import sun_hours_grid, terrain_to_obstacles


# -------------------------------------------------------------------
# Génération automatique des haies
# -------------------------------------------------------------------
def generate_obstacles_from_haies_auto(terrain: TerrainInput) -> List[dict]:
    """
    Génère les obstacles (segments) à partir de la liste des haies auto.
    Peut être positionné à la lisière de la parcelle ou autour de la maison.
    """
    if not terrain.haies_auto:
        return []
    
    obstacles = []
    maisons = terrain.get_blocs_maison()
    if not maisons:
        return obstacles
    
    # on prend la maison principale (première)
    maison = maisons[0]
    mx, my = float(maison.origine[0]), float(maison.origine[1])
    mw, mh = float(maison.largeur), float(maison.hauteur)
    
    # Récupère le positionnement
    haie_position = terrain.haie_position.lower()
    is_lisiere = "lisière" in haie_position
    
    # Dimensions de la parcelle
    px, py = float(terrain.parcelle.origine[0]), float(terrain.parcelle.origine[1])
    pw, ph = float(terrain.parcelle.largeur), float(terrain.parcelle.hauteur)
    
    for haie in terrain.haies_auto:
        cote = haie.cote
        hauteur = float(haie.hauteur)
        
        if is_lisiere:
            # Haies À LA LISIÈRE DE LA PARCELLE
            if cote == "nord":
                a = (px, py + ph)
                b = (px + pw, py + ph)
            elif cote == "sud":
                a = (px, py)
                b = (px + pw, py)
            elif cote == "est":
                a = (px + pw, py)
                b = (px + pw, py + ph)
            elif cote == "ouest":
                a = (px, py)
                b = (px, py + ph)
            else:
                continue
        else:
            # Haies AUTOUR DE LA MAISON
            if cote == "nord":
                a = (mx, my + mh)
                b = (mx + mw, my + mh)
            elif cote == "sud":
                a = (mx, my)
                b = (mx + mw, my)
            elif cote == "est":
                a = (mx + mw, my)
                b = (mx + mw, my + mh)
            elif cote == "ouest":
                a = (mx, my)
                b = (mx, my + mh)
            else:
                continue
        
        obstacles.append({
            "type": "haie",
            "a": list(a),
            "b": list(b),
            "hauteur": hauteur,
        })
    
    return obstacles


# -------------------------------------------------------------------
# Utils classes exposition (minute -> classe)
# -------------------------------------------------------------------
def _cell_in_zone(x: float, y: float, terrain: TerrainInput) -> bool:
    zone = terrain.zone_analyse
    if not zone:
        return True

    ztype = zone.get("type")

    W = float(terrain.parcelle.largeur)
    H = float(terrain.parcelle.hauteur)

    if ztype == "tout":
        return True

    if ztype == "fond":
        return y > H * 0.66

    if ztype == "cote_maison":
        return y < H * 0.33

    if ztype == "rectangle":
        zx = float(zone.get("x", 0.0))
        zy = float(zone.get("y", 0.0))
        zw = float(zone.get("w", 0.0))
        zh = float(zone.get("h", 0.0))
        return zx <= x <= zx + zw and zy <= y <= zy + zh

    return True   # ← IMPORTANT


def _classe_from_minutes(minutes: int, max_minutes: int) -> str:
    if max_minutes <= 0:
        return "ombre"

    ratio = minutes / max_minutes

    if ratio <= 0.25:
        return "ombre"
    if ratio <= 0.60:
        return "mi_ombre"

    return "plein_soleil"


# -------------------------------------------------------------------
# Plantation (utilise exposition précise)
# -------------------------------------------------------------------
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

        # échantillonnage selon distance plante
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


# -------------------------------------------------------------------
# Surfaces (parcelle / maison(s) / terrasse / trous)
# -------------------------------------------------------------------
def compute_surfaces(terrain: TerrainInput) -> Dict[str, float]:
    poly_parcelle = rect_to_poly(
        *terrain.parcelle.origine, terrain.parcelle.largeur, terrain.parcelle.hauteur
    )
    surface_parcelle = poly_area(poly_parcelle)

    # Plusieurs blocs maison (maison + extensions)
    blocs = terrain.get_blocs_maison()
    surface_maison = 0.0
    for m in blocs:
        poly_m = rect_to_poly(*m.origine, m.largeur, m.hauteur)
        surface_maison += poly_area(poly_m)

    surface_terrasse = 0.0
    if terrain.terrasse is not None:
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


# -------------------------------------------------------------------
# Plan 2D
# -------------------------------------------------------------------
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

    blocs = terrain.get_blocs_maison()
    for i, m in enumerate(blocs, start=1):
        label = "Maison" if i == 1 else f"Extension {i-1}"
        shapes.append(
            Shape2D(
                type="rectangle",
                label=label,
                x=float(m.origine[0]),
                y=float(m.origine[1]),
                w=float(m.largeur),
                h=float(m.hauteur),
            )
        )

    if terrain.terrasse is not None:
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


# -------------------------------------------------------------------
# Exposition (simplifiée)
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Segments (haies / murs)  ✅ DOIT ÊTRE AVANT _is_in_shadow_by_any_obstacle
# -------------------------------------------------------------------
def _dot(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay

    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-12:
        return math.hypot(px - ax, py - ay)

    t = max(0.0, min(1.0, _dot(apx, apy, abx, aby) / ab2))
    cx = ax + t * abx
    cy = ay + t * aby
    return math.hypot(px - cx, py - cy)


def _is_in_shadow_by_segment(
    cell: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    height: float,
    sun_altitude_deg: float,
    sun_azimuth_deg: float,
    orientation_nord_deg: float,
    thickness: float,
) -> bool:
    # Shadow of a hedge/wall modeled as a vertical segment
    # Approximation: band around segment + shadow length L = height/tan(alt)
    alt_deg = float(sun_altitude_deg)
    if alt_deg <= 0.0:
        return False  # (on ne devrait pas appeler avec alt<=0 si on filtre déjà)

    alt = math.radians(max(1.0, alt_deg))
    L = float(height) / math.tan(alt)

    # azimut dans repère du plan
    az_plan = (float(sun_azimuth_deg) - float(orientation_nord_deg)) % 360.0
    az = math.radians(az_plan)
    dx = -math.sin(az)
    dy = -math.cos(az)

    cx, cy = cell
    ax0, ay0 = a
    bx0, by0 = b

    # Rotate tout dans le repère "plan" (comme maison)
    cx2, cy2 = _rotate_point(float(cx), float(cy), -orientation_nord_deg)
    ax2, ay2 = _rotate_point(float(ax0), float(ay0), -orientation_nord_deg)
    bx2, by2 = _rotate_point(float(bx0), float(by0), -orientation_nord_deg)

    # proche du segment ?
    d = _dist_point_to_segment(cx2, cy2, ax2, ay2, bx2, by2)
    if d > float(thickness):
        return False

    # derrière le segment dans la direction de l'ombre ?
    mx = 0.5 * (ax2 + bx2)
    my = 0.5 * (ay2 + by2)

    vx = cx2 - mx
    vy = cy2 - my

    t = vx * dx + vy * dy
    if t <= 0.0:
        return False
    if t > L:
        return False

    return True


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
    # Test approximate shadow of a rectangular block.
    # Simplified model (but sufficient for prototype).
    alt = math.radians(max(1.0, sun_altitude_deg))
    L = house_height / math.tan(alt)

    # ✅ BUGFIX : corrige l'azimut du soleil dans le repère du plan
    az_plan = (float(sun_azimuth_deg) - float(orientation_nord_deg)) % 360.0

    az = math.radians(az_plan)
    dx = -math.sin(az)
    dy = -math.cos(az)

    cx, cy = cell
    hx, hy = house_origin

    cx2, cy2 = _rotate_point(cx, cy, -orientation_nord_deg)
    hx2, hy2 = _rotate_point(hx, hy, -orientation_nord_deg)

    x0, y0 = hx2, hy2
    x1, y1 = hx2 + house_w, hy2 + house_h

    # à l'intérieur du bâti => ombre
    if x0 <= cx2 <= x1 and y0 <= cy2 <= y1:
        return True

    # centre du bâtiment
    house_cx = (x0 + x1) / 2.0
    house_cy = (y0 + y1) / 2.0

    vx = cx2 - house_cx
    vy = cy2 - house_cy
    t = vx * dx + vy * dy

    if t <= 0:
        return False
    if t > L:
        return False

    # approximation "disque" autour du rectangle
    house_radius = 0.5 * math.hypot(house_w, house_h)

    px = vx - t * dx
    py = vy - t * dy
    dist_perp = math.hypot(px, py)

    return dist_perp <= house_radius


def _is_in_shadow_by_any_obstacle(
    cell: Tuple[float, float],
    terrain: TerrainInput,
    sun_altitude_deg: float,
    sun_azimuth_deg: float,
) -> bool:
    orientation = float(terrain.orientation_nord_deg)

    # 1) maisons/extensions
    for m in terrain.get_blocs_maison():
        hx, hy = m.origine
        hw = float(m.largeur)
        hh = float(m.hauteur)
        hZ = float(m.hauteur_batiment)

        if _is_in_shadow_by_house(
            cell,
            (float(hx), float(hy)),
            hw,
            hh,
            hZ,
            float(sun_altitude_deg),
            float(sun_azimuth_deg),
            orientation,
        ):
            return True

    # 2) haies / murs (segments)
    thickness = float(getattr(terrain, "pas_grille_m", 1.0)) * 0.75
    
    # obstacles manuels
    all_obstacles = list(getattr(terrain, "obstacles", []) or [])
    
    # obstacles auto-générés à partir des haies
    auto_obstacles = generate_obstacles_from_haies_auto(terrain)
    for auto_obs in auto_obstacles:
        from core.schemas import ObstacleSegment
        all_obstacles.append(
            ObstacleSegment(
                type=auto_obs["type"],
                a=tuple(auto_obs["a"]),
                b=tuple(auto_obs["b"]),
                hauteur=auto_obs["hauteur"],
            )
        )
    
    for obs in all_obstacles:
        if _is_in_shadow_by_segment(
            cell,
            (float(obs.a[0]), float(obs.a[1])),
            (float(obs.b[0]), float(obs.b[1])),
            float(obs.hauteur),
            float(sun_altitude_deg),
            float(sun_azimuth_deg),
            orientation,
            thickness=thickness,
        ):
            return True

    return False


def compute_exposition(terrain: TerrainInput) -> Dict:
    """Calcule l'exposition solaire simplifiée via le moteur shadow_engine."""
    pas = float(terrain.pas_grille_m)
    W = float(terrain.parcelle.largeur)
    H = float(terrain.parcelle.hauteur)

    parcel_geom = shapely_box(0, 0, W, H)
    obstacles = terrain_to_obstacles(terrain)
    grid, meta = sun_hours_grid(
        parcel=parcel_geom,
        obstacles=obstacles,
        date=terrain.date_ref,
        lat=float(terrain.latitude),
        lon=float(terrain.longitude),
        parcel_rotation=float(terrain.orientation_nord_deg),
        resolution_m=pas,
        time_step_min=int(terrain.pas_minutes),
        tz=terrain.timezone,
        slope_pct=float(terrain.slope_pct),
        slope_orientation_deg=float(terrain.slope_orientation_deg),
        start_hour=int(terrain.heure_debut),
        end_hour=int(terrain.heure_fin),
    )

    cells = []
    counts = {"ombre": 0, "mi_ombre": 0, "plein_soleil": 0}
    max_minutes = int(round(meta.get("max_hours", 0) * 60))

    ny, nx = grid.shape
    for iy in range(ny):
        for ix in range(nx):
            x = (ix + 0.5) * pas
            y = (iy + 0.5) * pas
            if not _cell_in_zone(x, y, terrain):
                continue

            hours = float(grid[iy, ix])
            minutes_soleil = int(round(hours * 60.0))
            ratio = 0.0 if max_minutes == 0 else minutes_soleil / max_minutes
            if ratio <= 0.25:
                classe = "ombre"
            elif ratio <= 0.60:
                classe = "mi_ombre"
            else:
                classe = "plein_soleil"

            counts[classe] += 1
            cells.append({
                "x": round(x, 3),
                "y": round(y, 3),
                "score": minutes_soleil,
                "classe": classe,
            })

    total = len(cells)
    resume = {
        "date_ref": terrain.date_ref,
        "timezone": terrain.timezone,
        "pas_minutes": int(terrain.pas_minutes),
        "max_minutes_theorique": max_minutes,
        "pct_ombre": round(100 * counts["ombre"] / total, 1) if total else 0.0,
        "pct_mi_ombre": round(100 * counts["mi_ombre"] / total, 1) if total else 0.0,
        "pct_plein_soleil": round(100 * counts["plein_soleil"] / total, 1) if total else 0.0,
        "zone_analyse": terrain.zone_analyse,
        "cells_zone": total,
    }

    if total == 0:
        resume["warning"] = "Zone vide : aucune cellule dans la zone_analyse."

    return {"pas_grille_m": pas, "largeur": W, "hauteur": H, "cells": cells, "resume": resume}


# -------------------------------------------------------------------
# Plantes : CSV + filtres
# -------------------------------------------------------------------
def _plantes_csv_path() -> Path:
    # core/services.py -> remonte au dossier racine du projet -> data/plantes.csv
    return Path(__file__).resolve().parents[1] / "data" / "plantes.csv"


def load_plantes() -> List[Plante]:
    path = _plantes_csv_path()
    plantes: List[Plante] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            normalized_names = [name.strip().lower().lstrip("\ufeff") for name in reader.fieldnames]
            reader.fieldnames = normalized_names

        for row in reader:
            normalized_row = {
                key.strip().lower().lstrip("\ufeff"): value
                for key, value in row.items()
            }

            def _f(k, default=0.0):
                v = normalized_row.get(k, "").strip()
                try: return float(v) if v else default
                except (ValueError, TypeError): return default

            def _s(k): return normalized_row.get(k, "").strip() or None

            plantes.append(
                Plante(
                    nom=normalized_row.get("nom", ""),
                    type=normalized_row.get("type", ""),
                    exposition=normalized_row.get("exposition", ""),
                    sol=normalized_row.get("sol", ""),
                    climat=normalized_row.get("climat", ""),
                    hauteur_m=_f("hauteur_m"),
                    largeur_m=_f("largeur_m"),
                    distance_m=_f("distance_m"),
                    floraison=normalized_row.get("floraison", ""),
                    feuillage=normalized_row.get("feuillage", ""),
                    couleur=normalized_row.get("couleur", ""),
                    notes=normalized_row.get("notes", ""),
                    photo_url=_s("photo_url"),
                    exigences=_s("exigences"),
                    exposition_min_h=_f("exposition_min_h", None) if normalized_row.get("exposition_min_h") else None,
                    exposition_max_h=_f("exposition_max_h", None) if normalized_row.get("exposition_max_h") else None,
                    sol_prefere=_s("sol_prefere"),
                    ph_min=_f("ph_min", None) if normalized_row.get("ph_min") else None,
                    ph_max=_f("ph_max", None) if normalized_row.get("ph_max") else None,
                    periode_floraison=_s("periode_floraison"),
                    couleur_fleur=_s("couleur_fleur"),
                    persistant=(normalized_row.get("persistant", "").strip().lower() in ("oui","true","1","yes")) if normalized_row.get("persistant") else None,
                    rusticite_min_c=_f("rusticite_min_c", None) if normalized_row.get("rusticite_min_c") else None,
                    entretien=_s("entretien"),
                    prix_indicatif_eur=_f("prix_indicatif_eur", None) if normalized_row.get("prix_indicatif_eur") else None,
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


# -------------------------------------------------------------------
# Reverse geocoding (resume)
# -------------------------------------------------------------------
def reverse_city(latitude: float, longitude: float) -> dict:
    res = rg.search((latitude, longitude), mode=1)[0]
    return {
        "city": res.get("name"),
        "region": res.get("admin1"),
        "country_code": res.get("cc"),
    }


# -------------------------------------------------------------------
# Exposition précise (pvlib) - multi-blocs maison/extension
# -------------------------------------------------------------------
def compute_exposition_precise(terrain: TerrainInput) -> Dict:
    """Calcule une exposition solaire précise via le moteur shadow_engine."""
    pas_grille = float(terrain.pas_grille_m)
    W = float(terrain.parcelle.largeur)
    H = float(terrain.parcelle.hauteur)
    tz = terrain.timezone
    pas_min = int(terrain.pas_minutes)

    if terrain.heure_fin < terrain.heure_debut:
        raise ValueError("heure_fin doit etre >= heure_debut")

    parcel_geom = shapely_box(0, 0, W, H)
    obstacles = terrain_to_obstacles(terrain)

    grid, meta = sun_hours_grid(
        parcel=parcel_geom,
        obstacles=obstacles,
        date=terrain.date_ref,
        lat=float(terrain.latitude),
        lon=float(terrain.longitude),
        parcel_rotation=float(terrain.orientation_nord_deg),
        resolution_m=pas_grille,
        time_step_min=pas_min,
        tz=tz,
        slope_pct=float(terrain.slope_pct),
        slope_orientation_deg=float(terrain.slope_orientation_deg),
        start_hour=int(terrain.heure_debut),
        end_hour=int(terrain.heure_fin),
    )

    cells = []
    counts = {"ombre": 0, "mi_ombre": 0, "plein_soleil": 0}
    max_minutes = int(round(meta.get("max_hours", 0) * 60))

    ny, nx = grid.shape
    for iy in range(ny):
        for ix in range(nx):
            x = (ix + 0.5) * pas_grille
            y = (iy + 0.5) * pas_grille
            if not _cell_in_zone(x, y, terrain):
                continue

            hours = float(grid[iy, ix])
            minutes_soleil = int(round(hours * 60.0))
            ratio = 0.0 if max_minutes == 0 else minutes_soleil / max_minutes
            if ratio <= 0.25:
                classe = "ombre"
            elif ratio <= 0.60:
                classe = "mi_ombre"
            else:
                classe = "plein_soleil"

            counts[classe] += 1
            cells.append({
                "x": round(x, 3),
                "y": round(y, 3),
                "score": minutes_soleil,
                "classe": classe,
            })

    total = len(cells)
    loc = reverse_city(float(terrain.latitude), float(terrain.longitude))

    resume = {
        "date_ref": terrain.date_ref,
        "timezone": terrain.timezone,
        "pas_minutes": pas_min,
        "plage": f"{terrain.heure_debut:02d}:00-{terrain.heure_fin:02d}:00",
        "max_minutes_theorique": max_minutes,
        "pct_ombre": round(100 * counts["ombre"] / total, 1) if total else 0.0,
        "pct_mi_ombre": round(100 * counts["mi_ombre"] / total, 1) if total else 0.0,
        "pct_plein_soleil": round(100 * counts["plein_soleil"] / total, 1) if total else 0.0,
        "zone_analyse": terrain.zone_analyse,
        "cells_zone": total,
        "location": loc,
    }

    if total == 0:
        resume["warning"] = "Zone vide : aucune cellule dans la zone_analyse."

    return {
        "pas_grille_m": pas_grille,
        "largeur": W,
        "hauteur": H,
        "cells": cells,
        "resume": resume,
    }
