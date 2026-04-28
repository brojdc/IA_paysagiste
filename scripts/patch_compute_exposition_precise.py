from pathlib import Path
import re

path = Path(__file__).resolve().parent.parent / 'core' / 'services.py'
text = path.read_text(encoding='utf-8')
pattern = re.compile(r'(def compute_exposition_precise\(terrain: TerrainInput\) -> Dict:)(.*?)(?=\n# -------------------------------------------------------------------|\Z)', re.S)
replacement = '''\1
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
            if hours < 3:
                classe = "ombre"
            elif hours < 6:
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
'''
new_text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError(f'Pattern match failed, count={count}')
path.write_text(new_text, encoding='utf-8')
print('patched compute_exposition_precise with count', count)
