# -*- coding: utf-8 -*-
# core/shadow_engine.py
"""
Moteur d'ombres central et autoritaire — pvlib + shapely.
Fonctions principales :
  - SunPosition          : position solaire calculée via pvlib
  - apply_slope_correction : correction altitude par pente du terrain
  - project_shadow       : polygone d'ombre d'un obstacle
  - sun_hours_grid       : grille 2D float32 d'heures de soleil
  - shadows_snapshot     : polygones d'ombre à un instant T
  - terrain_to_obstacles : conversion TerrainInput → obstacles shapely
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import pvlib
from shapely.geometry import (
    LineString, MultiPoint, Point, Polygon, box, MultiPolygon
)
from shapely.ops import unary_union


# ── Position solaire ─────────────────────────────────────────────────────────

@dataclass
class SunPosition:
    """Position du soleil : azimut et élévation en degrés."""
    azimuth_deg: float
    elevation_deg: float

    @classmethod
    def from_datetime(
        cls,
        dt: Union[datetime, "pd.Timestamp"],
        lat: float,
        lon: float,
        tz: str = "Europe/Paris",
    ) -> "SunPosition":
        """Calcule la position solaire via pvlib pour un instant donné."""
        if isinstance(dt, datetime) and dt.tzinfo is None:
            ts = pd.DatetimeIndex([dt]).tz_localize(tz)
        else:
            ts = pd.DatetimeIndex([pd.Timestamp(dt)])
            if ts.tz is None:
                ts = ts.tz_localize(tz)
        solpos = pvlib.solarposition.get_solarposition(ts, lat, lon)
        return cls(
            azimuth_deg=float(solpos["azimuth"].iloc[0]),
            elevation_deg=float(solpos["apparent_elevation"].iloc[0]),
        )

    def is_above_horizon(self) -> bool:
        return self.elevation_deg > 0.0


# ── Correction relief ─────────────────────────────────────────────────────────

def apply_slope_correction(
    elevation_deg: float,
    azimuth_deg: float,
    slope_pct: float,
    slope_orientation_deg: float,
) -> float:
    """
    Corrige l'altitude solaire effective selon la pente du terrain.
    Formule : elevation_eff = elevation + slope_pct/100 * cos(az - slope_or) * 30
    Borné entre 0 et 90°.
    """
    if slope_pct <= 0:
        return elevation_deg
    az_rad = math.radians(azimuth_deg - slope_orientation_deg)
    correction = (slope_pct / 100.0) * math.cos(az_rad) * 30.0
    return float(np.clip(elevation_deg + correction, 0.0, 90.0))


# ── Projection d'ombre ────────────────────────────────────────────────────────

def project_shadow(
    geometry: Union[Polygon, LineString],
    height: float,
    sun_position: SunPosition,
    parcel_rotation: float = 0.0,
    slope_pct: float = 0.0,
    slope_orientation_deg: float = 0.0,
) -> Optional[Polygon]:
    """
    Projette l'ombre d'un obstacle (Polygon ou LineString) au sol.
    Retourne un polygone shapely ou None si le soleil est sous l'horizon.
    """
    elevation_eff = apply_slope_correction(
        sun_position.elevation_deg,
        sun_position.azimuth_deg,
        slope_pct,
        slope_orientation_deg,
    )
    if elevation_eff <= 0.0:
        return None

    alt_rad = math.radians(max(0.5, elevation_eff))
    shadow_len = float(height) / math.tan(alt_rad)

    # Azimut dans le repère du terrain (rotation parcelle)
    az_plan = (sun_position.azimuth_deg - parcel_rotation) % 360.0
    az_rad = math.radians(az_plan)
    # Direction de l'ombre (opposée au soleil)
    sdx = -math.sin(az_rad)
    sdy = -math.cos(az_rad)

    # Coins de la géométrie
    if isinstance(geometry, Polygon):
        coords = list(geometry.exterior.coords[:-1])  # sans doublon final
    elif isinstance(geometry, LineString):
        coords = list(geometry.coords)
    else:
        return None

    if not coords:
        return None

    proj_coords = [(x + sdx * shadow_len, y + sdy * shadow_len) for x, y in coords]
    all_pts = coords + proj_coords

    if len(all_pts) < 3:
        return None

    shadow_poly = MultiPoint(all_pts).convex_hull
    if hasattr(shadow_poly, "area") and shadow_poly.area > 1e-6:
        if shadow_poly.geom_type == "Polygon":
            return shadow_poly
    return None


# ── Grille d'heures de soleil ─────────────────────────────────────────────────

def sun_hours_grid(
    parcel: Polygon,
    obstacles: List[Tuple],
    date: Union[datetime, str],
    lat: float,
    lon: float,
    parcel_rotation: float = 0.0,
    resolution_m: float = 1.0,
    time_step_min: int = 15,
    tz: str = "Europe/Paris",
    slope_pct: float = 0.0,
    slope_orientation_deg: float = 0.0,
    start_hour: int = 5,
    end_hour: int = 21,
) -> Tuple[np.ndarray, dict]:
    """
    Calcule la grille 2D float32 d'heures de soleil par cellule sur une journée.
    Retourne (grille np.ndarray shape (ny, nx), meta dict).
    """
    minx, miny, maxx, maxy = parcel.bounds
    xs = np.arange(minx + resolution_m / 2, maxx, resolution_m)
    ys = np.arange(miny + resolution_m / 2, maxy, resolution_m)
    nx, ny = len(xs), len(ys)
    grid = np.zeros((ny, nx), dtype=np.float32)

    # Positions solaires sur la plage horaire demandée
    date_str = date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date)
    start = pd.Timestamp(f"{date_str} {start_hour:02d}:00:00", tz=tz)
    end = pd.Timestamp(f"{date_str} {end_hour:02d}:00:00", tz=tz)
    times = pd.date_range(start=start, end=end, freq=f"{time_step_min}min")
    solpos = pvlib.solarposition.get_solarposition(times, lat, lon)

    sun_steps = [
        (float(row["azimuth"]), float(row["apparent_elevation"]))
        for _, row in solpos.iterrows()
        if float(row["apparent_elevation"]) > 0.0
    ]
    n_steps = len(sun_steps)
    max_hours = n_steps * time_step_min / 60.0

    meta = {
        "bbox": [minx, miny, maxx, maxy],
        "pas_m": resolution_m,
        "nx": int(nx),
        "ny": int(ny),
        "max_hours": float(max_hours),
        "n_steps": n_steps,
        "step_min": time_step_min,
    }

    if n_steps == 0 or nx == 0 or ny == 0:
        return grid, meta

    # Précalcul de la liste de points et appartenance à la parcelle
    pts_geom = [Point(xs[ix], ys[iy]) for iy in range(ny) for ix in range(nx)]
    in_parcel = [parcel.contains(p) for p in pts_geom]
    step_h = time_step_min / 60.0

    for az, elev in sun_steps:
        sun_pos = SunPosition(azimuth_deg=az, elevation_deg=elev)
        elev_eff = apply_slope_correction(elev, az, slope_pct, slope_orientation_deg)
        if elev_eff <= 0:
            continue

        # Union des ombres au pas de temps courant
        shadows_list = []
        for geom, h in obstacles:
            sh = project_shadow(geom, h, sun_pos, parcel_rotation, slope_pct, slope_orientation_deg)
            if sh is not None:
                sh_clipped = sh.intersection(parcel)
                if not sh_clipped.is_empty:
                    shadows_list.append(sh_clipped)

        shadow_union = unary_union(shadows_list) if shadows_list else None

        # Accumulation d'heures de soleil par cellule
        for idx, (pt, in_p) in enumerate(zip(pts_geom, in_parcel)):
            if not in_p:
                continue
            if shadow_union is None or not shadow_union.contains(pt):
                iy, ix = divmod(idx, nx)
                grid[iy, ix] += step_h

    return grid, meta


# ── Snapshot d'ombres ─────────────────────────────────────────────────────────

def shadows_snapshot(
    parcel: Polygon,
    obstacles: List[Tuple],
    datetime_iso: str,
    lat: float,
    lon: float,
    parcel_rotation: float = 0.0,
    tz: str = "Europe/Paris",
    slope_pct: float = 0.0,
    slope_orientation_deg: float = 0.0,
) -> List[List[Tuple[float, float]]]:
    """
    Retourne les polygones d'ombre à un instant T, clippés à la parcelle.
    Format : liste de liste de (x, y).
    """
    dt = pd.Timestamp(datetime_iso)
    if dt.tz is None:
        dt = dt.tz_localize(tz)
    solpos = pvlib.solarposition.get_solarposition(
        pd.DatetimeIndex([dt]), lat, lon
    )
    az = float(solpos["azimuth"].iloc[0])
    elev = float(solpos["apparent_elevation"].iloc[0])
    sun_pos = SunPosition(azimuth_deg=az, elevation_deg=elev)

    if not sun_pos.is_above_horizon():
        return []

    polygons_coords = []
    for geom, h in obstacles:
        sh = project_shadow(geom, h, sun_pos, parcel_rotation, slope_pct, slope_orientation_deg)
        if sh is None:
            continue
        sh_clipped = sh.intersection(parcel)
        if sh_clipped.is_empty:
            continue
        if sh_clipped.geom_type == "Polygon":
            polygons_coords.append(
                [(float(x), float(y)) for x, y in sh_clipped.exterior.coords]
            )
        elif sh_clipped.geom_type in ("MultiPolygon", "GeometryCollection"):
            for part in getattr(sh_clipped, "geoms", []):
                if part.geom_type == "Polygon":
                    polygons_coords.append(
                        [(float(x), float(y)) for x, y in part.exterior.coords]
                    )

    return polygons_coords


# ── Conversion TerrainInput → obstacles shapely ──────────────────────────────

def terrain_to_obstacles(terrain) -> List[Tuple]:
    """
    Convertit un TerrainInput en liste de (geometry shapely, hauteur en m).
    Inclut maisons, extensions, haies manuelles et haies auto.
    """
    result = []

    # Blocs maison/extensions → rectangles shapely
    for m in terrain.get_blocs_maison():
        ox, oy = float(m.origine[0]), float(m.origine[1])
        w, h = float(m.largeur), float(m.hauteur)
        geom = box(ox, oy, ox + w, oy + h)
        result.append((geom, float(m.hauteur_batiment)))

    # Haies/murs manuels (ObstacleSegment)
    for obs in (terrain.obstacles or []):
        ax, ay = float(obs.a[0]), float(obs.a[1])
        bx, by = float(obs.b[0]), float(obs.b[1])
        geom = LineString([(ax, ay), (bx, by)])
        result.append((geom, float(obs.hauteur)))

    # Haies auto-générées (côtés de la maison ou lisière)
    from core.services import generate_obstacles_from_haies_auto
    for ao in generate_obstacles_from_haies_auto(terrain):
        ax, ay = float(ao["a"][0]), float(ao["a"][1])
        bx, by = float(ao["b"][0]), float(ao["b"][1])
        geom = LineString([(ax, ay), (bx, by)])
        result.append((geom, float(ao["hauteur"])))

    return result


# ── Classe wrapper rétrocompatible ────────────────────────────────────────────

class ShadowEngine:
    """
    Wrapper rétrocompatible — gardé pour ne pas casser les anciens imports.
    Délègue vers les nouvelles fonctions pvlib/shapely.
    """

    def __init__(self, terrain_orientation_deg: float = 0.0):
        self.north_offset = float(terrain_orientation_deg)

    def _make_sun_pos(self, sun_pos) -> SunPosition:
        elev = getattr(sun_pos, "altitude_deg",
               getattr(sun_pos, "elevation_deg", 0.0))
        return SunPosition(
            azimuth_deg=float(sun_pos.azimuth_deg),
            elevation_deg=float(elev),
        )

    def is_point_in_shadow_by_house(
        self, point, house_origin, house_width, house_height,
        house_building_height, sun_pos,
    ) -> bool:
        geom = box(
            float(house_origin[0]), float(house_origin[1]),
            float(house_origin[0]) + house_width,
            float(house_origin[1]) + house_height,
        )
        sp = self._make_sun_pos(sun_pos)
        shadow = project_shadow(geom, float(house_building_height), sp, self.north_offset)
        return shadow is not None and shadow.contains(Point(float(point[0]), float(point[1])))

    def is_point_in_shadow_by_hedge(
        self, point, hedge_a, hedge_b, hedge_height, sun_pos,
        hedge_thickness: float = 0.3,
    ) -> bool:
        geom = LineString([hedge_a, hedge_b]).buffer(hedge_thickness / 2)
        sp = self._make_sun_pos(sun_pos)
        shadow = project_shadow(geom, float(hedge_height), sp, self.north_offset)
        return shadow is not None and shadow.contains(Point(float(point[0]), float(point[1])))
