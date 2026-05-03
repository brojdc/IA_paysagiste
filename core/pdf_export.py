# -*- coding: utf-8 -*-
# core/pdf_export.py
"""
Génération de rapports PDF professionnels (8 pages) via reportlab + matplotlib.
Page 0 : Couverture
Page 1 : Plan général
Pages 2-4 : Ombres 9h / 13h / 17h
Page 5 : Heatmap d'ensoleillement
Page 6 : Synthèse technique + course solaire
Page 7 : Plantes recommandées
"""
import io
import math
from datetime import datetime
from typing import List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader

from core.schemas import TerrainInput
from core.shadow_engine import terrain_to_obstacles, shadows_snapshot, sun_hours_grid
from shapely.geometry import box as shapely_box


PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm

GREEN       = HexColor('#2d5016')
LIGHT_GREEN = HexColor('#e8f5e0')

# Palette heatmap 7 stops (ombre → plein soleil)
HEATMAP_PALETTE = [
    "#0a1f3d",  # bleu nuit
    "#1a4f8a",  # bleu
    "#5b2d8e",  # violet
    "#8b4513",  # orangé sombre
    "#e07020",  # orange
    "#d4a020",  # jaune ocre
    "#fff3a0",  # jaune vif
]


# ── Helpers matplotlib ────────────────────────────────────────────────────────

def _terrain_figure(terrain: TerrainInput, shadow_polygons=None, title="", figsize=(8, 5)):
    """Génère une figure matplotlib : plan terrain + ombres optionnelles."""
    fig, ax = plt.subplots(figsize=figsize, facecolor='#f5f5f0')
    pw = float(terrain.parcelle.largeur)
    ph = float(terrain.parcelle.hauteur)

    # Parcelle
    ax.add_patch(mpatches.Rectangle(
        (0, 0), pw, ph,
        facecolor='#e8f5e0', edgecolor='#2d5016', linewidth=2, zorder=1,
    ))

    # Ombres (avant les bâtiments)
    if shadow_polygons:
        for poly_coords in shadow_polygons:
            xs_s = [p[0] for p in poly_coords]
            ys_s = [p[1] for p in poly_coords]
            ax.fill(xs_s, ys_s, color='#0f0f1e', alpha=0.42, zorder=2)

    # Maisons
    for i, m in enumerate(terrain.get_blocs_maison()):
        ox, oy = float(m.origine[0]), float(m.origine[1])
        mw, mh = float(m.largeur), float(m.hauteur)
        ax.add_patch(mpatches.Rectangle(
            (ox, oy), mw, mh,
            facecolor='#9e9e9e', edgecolor='#424242', linewidth=1, zorder=3,
        ))
        ax.text(
            ox + mw / 2, oy + mh / 2,
            'Maison' if i == 0 else f'Ext.{i}',
            ha='center', va='center', fontsize=8, color='white', fontweight='bold', zorder=4,
        )

    # Terrasse (optionnelle)
    if terrain.terrasse is not None:
        t = terrain.terrasse
        tx, ty = float(t.origine[0]), float(t.origine[1])
        ax.add_patch(mpatches.Rectangle(
            (tx, ty), float(t.largeur), float(t.hauteur),
            facecolor='#d4b896', edgecolor='#8b6914', linewidth=1, alpha=0.85, zorder=3,
        ))
        ax.text(
            tx + t.largeur / 2, ty + t.hauteur / 2, 'Terrasse',
            ha='center', va='center', fontsize=7, color='#6b4a10', zorder=4,
        )

    ax.set_xlim(-0.5, pw + 0.5)
    ax.set_ylim(-0.5, ph + 0.5)
    ax.set_aspect('equal')
    ax.set_xlabel('Largeur (m)', fontsize=9)
    ax.set_ylabel('Profondeur (m)', fontsize=9)
    ax.set_title(title, fontsize=11, fontweight='bold', pad=8)
    ax.grid(True, alpha=0.25, linestyle='--', linewidth=0.6)
    fig.tight_layout()
    return fig


def _heatmap_figure(terrain: TerrainInput, grid: np.ndarray, meta: dict, figsize=(8, 5)):
    """Génère la heatmap d'ensoleillement avec palette 7 stops."""
    fig, ax = plt.subplots(figsize=figsize, facecolor='#f5f5f0')
    cmap = LinearSegmentedColormap.from_list('soleil', HEATMAP_PALETTE, N=256)
    minx, miny, maxx, maxy = meta["bbox"]

    im = ax.imshow(
        grid, origin='lower', cmap=cmap,
        extent=[minx, maxx, miny, maxy],
        vmin=0, vmax=max(meta["max_hours"], 1),
        aspect='auto',
    )

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Heures de soleil / jour', fontsize=9)

    # Overlay maisons
    for m in terrain.get_blocs_maison():
        ox, oy = float(m.origine[0]), float(m.origine[1])
        ax.add_patch(mpatches.Rectangle(
            (ox, oy), float(m.largeur), float(m.hauteur),
            facecolor='#9e9e9e', edgecolor='#424242', linewidth=1, zorder=5,
        ))

    ax.set_title("Carte d'ensoleillement", fontsize=11, fontweight='bold')
    ax.set_xlabel('m', fontsize=9)
    ax.set_ylabel('m', fontsize=9)
    fig.tight_layout()
    return fig


def _fig_to_bytes(fig) -> bytes:
    """Convertit une figure matplotlib en PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Helpers reportlab ─────────────────────────────────────────────────────────

def _draw_page_header(c, title: str, subtitle: str = "", date_str: str = ""):
    """Bande verte en haut de page avec titre."""
    y_top = PAGE_H - MARGIN
    c.setFillColor(GREEN)
    c.rect(MARGIN, y_top - 1.15 * cm, PAGE_W - 2 * MARGIN, 1.15 * cm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN + 0.35 * cm, y_top - 0.82 * cm, title)
    if subtitle:
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN + 0.35 * cm, y_top - 1.05 * cm, subtitle)
    if date_str:
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - MARGIN - 0.35 * cm, y_top - 0.82 * cm, date_str)
    c.setFillColor(black)


def _embed_image(c, img_bytes: bytes, x, y, w, h):
    """Insère un PNG dans le canvas reportlab."""
    buf = io.BytesIO(img_bytes)
    img = ImageReader(buf)
    c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, anchor='c')


# ── Génération du rapport ─────────────────────────────────────────────────────

def generate_pdf_report(
    terrain: TerrainInput,
    nom_projet: str = "Projet paysager",
    paysagiste: str = "Paysagiste",
    sun_course_data: Optional[dict] = None,
    plants_data: Optional[dict] = None,
) -> bytes:
    """
    Génère le rapport PDF 8 pages.
    Retourne les bytes du PDF prêts à être envoyés au client.
    """
    if terrain is None:
        raise ValueError("Données du terrain manquantes — vérifier le payload envoyé au backend.")
    if terrain.parcelle is None:
        raise ValueError("Parcelle manquante dans les données du terrain.")

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    date_str = datetime.now().strftime("%d/%m/%Y")

    # Géométrie parcel + obstacles pour les snapshots
    parcel_geom = shapely_box(
        0, 0,
        float(terrain.parcelle.largeur),
        float(terrain.parcelle.hauteur),
    )
    obstacles = terrain_to_obstacles(terrain)

    img_h = PAGE_H - 4.5 * cm - 2 * MARGIN  # hauteur disponible pour images
    img_w = PAGE_W - 2 * MARGIN

    # ── PAGE 0 : Couverture ──────────────────────────────────────────────────
    c.setFillColor(GREEN)
    c.rect(0, PAGE_H * 0.55, PAGE_W, PAGE_H * 0.45, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.80, "Rapport d'Aménagement Paysager")
    c.setFont("Helvetica", 15)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.73, nom_projet)

    c.setFillColor(HexColor('#ccddcc'))
    c.setFont("Helvetica", 10)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.63, "Généré par IA Paysagiste — SaaS B2B")

    c.setFillColor(black)
    y = PAGE_H * 0.50
    info_rows = [
        ("Paysagiste", paysagiste),
        ("Date du rapport", date_str),
        ("Coordonnées", f"{terrain.latitude}°N / {terrain.longitude}°E"),
        ("Parcelle", f"{terrain.parcelle.largeur} × {terrain.parcelle.hauteur} m  "
                     f"({terrain.parcelle.largeur * terrain.parcelle.hauteur:.0f} m²)"),
        ("Orientation nord", f"{terrain.orientation_nord_deg:.0f}°"),
        ("Date de référence", terrain.date_ref),
    ]
    for label, val in info_rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, f"{label} :")
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN + 5.2 * cm, y, val)
        y -= 0.68 * cm

    c.showPage()

    # ── PAGE 1 : Plan général ────────────────────────────────────────────────
    _draw_page_header(c, "Plan général du terrain", date_str=date_str)
    fig = _terrain_figure(terrain, title="Vue d'ensemble — sans ombres")
    _embed_image(c, _fig_to_bytes(fig), MARGIN, MARGIN, img_w, img_h)
    c.showPage()

    # ── PAGES 2-4 : Ombres 9h / 13h / 17h ───────────────────────────────────
    for heure, label in [(9, "Matin 9h"), (13, "Midi 13h"), (17, "Après-midi 17h")]:
        dt_str = f"{terrain.date_ref} {heure:02d}:00:00"
        try:
            shadow_polys = shadows_snapshot(
                parcel=parcel_geom,
                obstacles=obstacles,
                datetime_iso=dt_str,
                lat=float(terrain.latitude),
                lon=float(terrain.longitude),
                parcel_rotation=float(terrain.orientation_nord_deg),
                tz=terrain.timezone,
                slope_pct=float(terrain.slope_pct),
                slope_orientation_deg=float(terrain.slope_orientation_deg),
            )
        except Exception:
            shadow_polys = []

        _draw_page_header(c, f"Ombres portées — {label}", date_str=date_str)
        fig = _terrain_figure(
            terrain, shadow_polys,
            title=f"Ombres au {label} — {terrain.date_ref}  ({terrain.latitude}°N)",
        )
        _embed_image(c, _fig_to_bytes(fig), MARGIN, MARGIN + 0.8 * cm, img_w, img_h - 0.8 * cm)

        # Commentaire automatique
        n_shadows = len(shadow_polys)
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(HexColor('#555555'))
        c.drawString(
            MARGIN, MARGIN + 0.2 * cm,
            f"{n_shadows} zone(s) d'ombre détectée(s) à {label}. "
            f"Lat {terrain.latitude}°  —  Réf : {terrain.date_ref}.",
        )
        c.setFillColor(black)
        c.showPage()

    # ── PAGE 5 : Heatmap ─────────────────────────────────────────────────────
    _draw_page_header(c, "Carte d'ensoleillement", date_str=date_str)
    try:
        grid, meta = sun_hours_grid(
            parcel=parcel_geom,
            obstacles=obstacles,
            date=terrain.date_ref,
            lat=float(terrain.latitude),
            lon=float(terrain.longitude),
            parcel_rotation=float(terrain.orientation_nord_deg),
            resolution_m=max(1.0, float(terrain.pas_grille_m)),
            time_step_min=max(15, int(terrain.pas_minutes)),
            tz=terrain.timezone,
            slope_pct=float(terrain.slope_pct),
            slope_orientation_deg=float(terrain.slope_orientation_deg),
        )
        fig = _heatmap_figure(terrain, grid, meta)
        _embed_image(c, _fig_to_bytes(fig), MARGIN, MARGIN, img_w, img_h)
    except Exception as exc:
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor('#c62828'))
        c.drawString(MARGIN, PAGE_H / 2, f"Heatmap non disponible : {exc}")
        c.setFillColor(black)
    c.showPage()

    # ── PAGE 6 : Synthèse technique + course solaire ──────────────────────────
    _draw_page_header(c, "Synthèse technique", date_str=date_str)
    y = PAGE_H - MARGIN - 1.8 * cm

    blocs = terrain.get_blocs_maison()
    surf_parcelle = float(terrain.parcelle.largeur) * float(terrain.parcelle.hauteur)
    surf_maison   = sum(float(m.largeur) * float(m.hauteur) for m in blocs)
    surf_terrasse = float(terrain.terrasse.largeur) * float(terrain.terrasse.hauteur)
    surf_jardin   = max(0, surf_parcelle - surf_maison - surf_terrasse)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Données du terrain")
    y -= 0.65 * cm

    tech_rows = [
        ("Parcelle", f"{terrain.parcelle.largeur} × {terrain.parcelle.hauteur} m  =  {surf_parcelle:.0f} m²"),
        ("Surface maison", f"{surf_maison:.1f} m²"),
        ("Surface terrasse", f"{surf_terrasse:.1f} m²"),
        ("Surface jardin estimée", f"{surf_jardin:.1f} m²"),
        ("Orientation nord", f"{terrain.orientation_nord_deg:.0f}°"),
        ("Date de référence", terrain.date_ref),
        ("Lat / Lon", f"{terrain.latitude}° / {terrain.longitude}°"),
        ("Fuseau horaire", terrain.timezone),
        ("Pente",
         f"{terrain.slope_pct:.0f}% (orientation {terrain.slope_orientation_deg:.0f}°)"
         if terrain.slope_pct > 0 else "Terrain plat"),
        ("Résolution grille", f"{terrain.pas_grille_m} m"),
        ("Pas de temps", f"{terrain.pas_minutes} min"),
    ]
    for label, val in tech_rows:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, y, f"{label} :")
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN + 5.5 * cm, y, val)
        y -= 0.52 * cm

    # Course solaire
    if sun_course_data:
        y -= 0.4 * cm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGIN, y, "Course solaire")
        y -= 0.6 * cm

        for saison, label in [("ete", "Été (21 juin)"), ("hiver", "Hiver (21 déc.)")]:
            data = sun_course_data.get(saison) or {}
            if data:
                c.setFont("Helvetica-Bold", 9)
                c.drawString(MARGIN, y, f"{label} :")
                y -= 0.5 * cm
                c.setFont("Helvetica", 9)
                c.drawString(
                    MARGIN + 0.5 * cm, y,
                    f"Lever {data.get('lever','?')} az {data.get('az_lever','?')}°  /  "
                    f"Coucher {data.get('coucher','?')} az {data.get('az_coucher','?')}°  /  "
                    f"Hmax {data.get('hauteur_max','?')}°  /  {data.get('duree_h','?')} h",
                )
                y -= 0.52 * cm

        diff = sun_course_data.get("diff_eclairement_pct")
        if diff is not None:
            c.setFont("Helvetica-Oblique", 9)
            c.setFillColor(HexColor('#555555'))
            c.drawString(MARGIN, y, f"Différence d'éclairement été / hiver : {diff:.0f}%")
            c.setFillColor(black)

    c.showPage()

    # ── PAGE 7 : Plantes recommandées ─────────────────────────────────────────
    _draw_page_header(c, "Plantes recommandées par zone", date_str=date_str)
    y = PAGE_H - MARGIN - 1.8 * cm

    if plants_data and plants_data.get("zones"):
        for zone in plants_data["zones"]:
            zone_label = zone["zone"].replace("_", " ").title()
            pct   = zone.get("pct", 0)
            surf  = zone.get("surface_m2", 0)

            if y < MARGIN + 2 * cm:
                c.showPage()
                _draw_page_header(c, "Plantes recommandées (suite)", date_str=date_str)
                y = PAGE_H - MARGIN - 1.8 * cm

            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(GREEN)
            c.drawString(MARGIN, y, f"Zone : {zone_label}  —  {pct:.0f}%  —  {surf:.0f} m²")
            c.setFillColor(black)
            y -= 0.55 * cm

            for plante in zone.get("plantes", [])[:6]:
                if y < MARGIN + 1.2 * cm:
                    c.showPage()
                    _draw_page_header(c, "Plantes recommandées (suite)", date_str=date_str)
                    y = PAGE_H - MARGIN - 1.8 * cm

                nom   = plante.get("nom", "?")
                ptype = plante.get("type", "?")
                flor  = plante.get("floraison", "?")
                haut  = plante.get("hauteur_m", "?")
                just  = plante.get("justification", "")

                c.setFont("Helvetica-Bold", 9)
                c.drawString(MARGIN + 0.4 * cm, y, f"• {nom}")
                c.setFont("Helvetica", 8.5)
                c.drawString(
                    MARGIN + 0.4 * cm + 4 * cm, y,
                    f"{ptype}  —  floraison : {flor}  —  hauteur : {haut} m",
                )
                y -= 0.42 * cm
                if just:
                    c.setFont("Helvetica-Oblique", 8)
                    c.setFillColor(HexColor('#666666'))
                    c.drawString(MARGIN + 0.8 * cm, y, just)
                    c.setFillColor(black)
                    y -= 0.4 * cm

            y -= 0.25 * cm
    else:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(HexColor('#888888'))
        c.drawString(
            MARGIN, y,
            "Données de plantation non disponibles — lancez l'analyse d'exposition complète.",
        )
        c.setFillColor(black)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
