from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.geometry import rect_to_poly, poly_area, circle_area
from core.schemas import TerrainInput, Shape2D


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
