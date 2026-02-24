# ui/formulaire.py
import math
from typing import Any, Dict, List

import requests
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="IA Paysagiste", layout="centered")

st.title("IA Paysagiste - Formulaire chantier (V1)")
st.write("Remplis les dimensions, puis lance l'analyse des surfaces / exposition / plantation.")


# ----------------------------
# OUTILS
# ----------------------------
def compute_terrasse_attachee(
    bloc: Dict[str, Any],
    side: str,
    profondeur: float,
    largeur: float,
    offset: float,
    full_width: bool,
) -> Dict[str, Any]:
    x, y = float(bloc["origine"][0]), float(bloc["origine"][1])
    w, h = float(bloc["largeur"]), float(bloc["hauteur"])

    if full_width:
        largeur = w if side in ("sud", "nord") else h

    if side == "sud":
        ox = x + offset
        oy = y - profondeur
        tw = largeur
        th = profondeur
    elif side == "nord":
        ox = x + offset
        oy = y + h
        tw = largeur
        th = profondeur
    elif side == "ouest":
        ox = x - profondeur
        oy = y + offset
        tw = profondeur
        th = largeur
    elif side == "est":
        ox = x + w
        oy = y + offset
        tw = profondeur
        th = largeur
    else:
        raise ValueError("side invalide")

    return {"origine": [ox, oy], "largeur": tw, "hauteur": th}


def _get_maison_shapes_from_payload(terrain: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "maisons" in terrain and terrain["maisons"]:
        return terrain["maisons"]
    if "maison" in terrain and terrain["maison"]:
        return [terrain["maison"]]
    return []


# ----------------------------
# Bloc recommandations plantes
# ----------------------------
st.subheader("Recommandation de plantes (catalogue)")

exposition_filtre = st.selectbox("Exposition", ["(peu importe)", "plein_soleil", "mi_ombre", "ombre"], key="pl_expo")
sol_filtre = st.selectbox("Type de sol", ["(peu importe)", "drainant", "normal", "argileux", "humide"], key="pl_sol")
climat_filtre = st.selectbox("Climat", ["(peu importe)", "oceanique", "continental", "mediterraneen", "montagnard"], key="pl_climat")

if st.button("Recommander des plantes"):
    payload_plantes = {
        "exposition": None if exposition_filtre == "(peu importe)" else exposition_filtre,
        "sol": None if sol_filtre == "(peu importe)" else sol_filtre,
        "climat": None if climat_filtre == "(peu importe)" else climat_filtre,
        "type": None,
    }
    try:
        r = requests.post(f"{API_URL}/plantes/filtrer", json=payload_plantes, timeout=20)
        r.raise_for_status()
        data = r.json()

        st.success(f"{data['nb']} plante(s) trouvée(s)")
        if data["nb"] == 0:
            st.info("Aucune plante ne correspond aux filtres.")
        else:
            for p in data["plantes"]:
                st.write(f"{p['nom']} — {p['type']} | {p['exposition']} | sol {p['sol']} | climat {p['climat']}")
                if p.get("notes"):
                    st.caption(p["notes"])
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur API : {e}")

st.divider()


# ----------------------------
# Formulaire terrain
# ----------------------------
st.subheader("Parcelle")
parcelle_largeur = st.number_input("Largeur de la parcelle (m)", min_value=0.0, value=40.0, step=0.5)
parcelle_hauteur = st.number_input("Longueur/Hauteur de la parcelle (m)", min_value=0.0, value=30.0, step=0.5)

st.subheader("Maison (bloc principal)")
maison_x = st.number_input("Position X (m)", min_value=0.0, value=10.0, step=0.5, key="m0_x")
maison_y = st.number_input("Position Y (m)", min_value=0.0, value=10.0, step=0.5, key="m0_y")
maison_largeur = st.number_input("Largeur (m)", min_value=0.0, value=12.0, step=0.5, key="m0_w")
maison_hauteur = st.number_input("Longueur/Hauteur (m)", min_value=0.0, value=10.0, step=0.5, key="m0_h")
maison_hauteur_batiment = st.number_input("Hauteur du batiment (m)", min_value=0.0, value=10.0, step=0.5, key="m0_z")

st.subheader("Extensions de la maison (optionnel)")
use_extensions = st.checkbox("Ajouter des extensions ?", value=True)
extensions: List[Dict[str, Any]] = []

if use_extensions:
    nb_ext = st.number_input("Nombre d'extensions", min_value=1, max_value=20, value=1, step=1)
    for i in range(int(nb_ext)):
        st.markdown(f"**Extension {i+1}**")
        ex = st.number_input(f"Position X extension {i+1} (m)", min_value=0.0, value=25.0, step=0.5, key=f"ex_x_{i}")
        ey = st.number_input(f"Position Y extension {i+1} (m)", min_value=0.0, value=10.0, step=0.5, key=f"ex_y_{i}")
        ew = st.number_input(f"Largeur extension {i+1} (m)", min_value=0.0, value=8.0, step=0.5, key=f"ex_w_{i}")
        eh = st.number_input(f"Hauteur extension {i+1} (m)", min_value=0.0, value=6.0, step=0.5, key=f"ex_h_{i}")
        ez = st.number_input(f"Hauteur extension {i+1} (m)", min_value=0.0, value=10.0, step=0.5, key=f"ex_z_{i}")
        extensions.append({"origine": [ex, ey], "largeur": ew, "hauteur": eh, "hauteur_batiment": ez})


# ----------------------------
# Terrasse (manuel ou attachée)
# ----------------------------
st.subheader("Terrasse")

mode_terrasse = st.radio("Mode terrasse", ["Manuel", "Attachée à la maison/extension"], horizontal=True)

if mode_terrasse == "Manuel":
    terrasse_x = st.number_input("Position X de la terrasse (m)", min_value=0.0, value=12.0, step=0.5)
    terrasse_y = st.number_input("Position Y de la terrasse (m)", min_value=0.0, value=6.0, step=0.5)
    terrasse_largeur = st.number_input("Largeur terrasse (m)", min_value=0.0, value=8.0, step=0.5)
    terrasse_hauteur = st.number_input("Longueur/Hauteur terrasse (m)", min_value=0.0, value=4.0, step=0.5)

else:
    blocs_maison = [{"label": "Maison", "bloc": {
        "origine": [maison_x, maison_y],
        "largeur": maison_largeur,
        "hauteur": maison_hauteur,
        "hauteur_batiment": maison_hauteur_batiment,
    }}]
    for i, ext in enumerate(extensions, start=1):
        blocs_maison.append({"label": f"Extension {i}", "bloc": ext})

    choix_bloc = st.selectbox("Terrasse attachée à quel bloc ?", [b["label"] for b in blocs_maison])
    bloc = next(b["bloc"] for b in blocs_maison if b["label"] == choix_bloc)

    side = st.selectbox("Côté du bloc", ["sud", "nord", "ouest", "est"])
    profondeur = st.number_input("Profondeur terrasse (m)", min_value=0.5, value=4.0, step=0.5)
    full_width = st.checkbox("Prendre toute la largeur du bloc", value=True)

    largeur = st.number_input("Largeur terrasse (m)", min_value=0.5, value=8.0, step=0.5, disabled=full_width)
    offset = st.number_input("Décalage (offset) le long du bloc (m)", value=0.0, step=0.5)

    terrasse_auto = compute_terrasse_attachee(bloc, side, float(profondeur), float(largeur), float(offset), bool(full_width))
    st.info(f"Terrasse auto calculée : origine={terrasse_auto['origine']}, largeur={terrasse_auto['largeur']}, hauteur={terrasse_auto['hauteur']}")

    terrasse_x = float(terrasse_auto["origine"][0])
    terrasse_y = float(terrasse_auto["origine"][1])
    terrasse_largeur = float(terrasse_auto["largeur"])
    terrasse_hauteur = float(terrasse_auto["hauteur"])


# ----------------------------
# Paramètres d'exposition
# ----------------------------
st.subheader("Paramètres d'exposition")
orientation_nord_deg = st.number_input("Orientation nord (degrés)", value=0.0, step=5.0)
latitude = st.number_input("Latitude", value=48.8566, step=0.0001, format="%.6f")
longitude = st.number_input("Longitude", value=2.3522, step=0.0001, format="%.6f")
pas_grille_m = st.number_input("Pas de grille (m)", min_value=0.5, value=1.0, step=0.5)

st.subheader("Paramètres solaires (exposition précise)")
timezone = st.text_input("Timezone (IANA)", value="Europe/Paris")
date_ref = st.text_input("Date de référence (YYYY-MM-DD)", value="2026-06-21")
pas_minutes = st.number_input("Pas de temps (minutes)", min_value=1, value=10, step=1)
heure_debut = st.number_input("Heure début (0-23)", min_value=0, max_value=23, value=9, step=1)
heure_fin = st.number_input("Heure fin (0-23)", min_value=0, max_value=23, value=16, step=1)


# ----------------------------
# Trous / massifs sur la terrasse
# ----------------------------
st.subheader("Trous / massifs sur la terrasse (optionnel)")
a_des_trous = st.checkbox("La terrasse a des trous (massifs / arbres) ?", value=False)

trous_terrasse: List[Dict[str, Any]] = []
if a_des_trous:
    nb_trous = st.number_input("Nombre de trous", min_value=1, max_value=20, value=1, step=1)
    for i in range(int(nb_trous)):
        st.markdown(f"Trou {i+1}")
        forme = st.selectbox(f"Forme trou {i+1}", ["rectangle", "cercle"], key=f"forme_{i}")
        pos_x = st.number_input(f"Position X trou {i+1}", min_value=0.0, value=14.0, step=0.1, key=f"tx_{i}")
        pos_y = st.number_input(f"Position Y trou {i+1}", min_value=0.0, value=6.0, step=0.1, key=f"ty_{i}")

        if forme == "rectangle":
            dim_l = st.number_input(f"Largeur trou {i+1} (m)", min_value=0.0, value=1.5, step=0.1, key=f"dl_{i}")
            dim_h = st.number_input(f"Hauteur trou {i+1} (m)", min_value=0.0, value=1.0, step=0.1, key=f"dh_{i}")
            trous_terrasse.append({"forme": "rectangle", "position": [pos_x, pos_y], "dimensions": [dim_l, dim_h]})
        else:
            rayon = st.number_input(f"Rayon trou {i+1} (m)", min_value=0.0, value=0.7, step=0.1, key=f"r_{i}")
            trous_terrasse.append({"forme": "cercle", "position": [pos_x, pos_y], "rayon": rayon})

st.divider()


# ----------------------------
# Dessins
# ----------------------------
def draw_plan(plan: Dict[str, Any], parcelle_w: float, parcelle_h: float) -> None:
    fig, ax = plt.subplots()
    for s in plan["shapes"]:
        if s["type"] == "rectangle":
            ax.add_patch(Rectangle((s["x"], s["y"]), s["w"], s["h"], fill=False))
            ax.text(s["x"], s["y"], s["label"])
        elif s["type"] == "cercle":
            ax.add_patch(Circle((s["x"], s["y"]), s["r"], fill=False))
            ax.text(s["x"], s["y"], s["label"])

    ax.set_xlim(0, parcelle_w)
    ax.set_ylim(0, parcelle_h)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Plan 2D (prototype)")
    st.pyplot(fig)


def draw_exposition(expo: Dict[str, Any], terrain: Dict[str, Any], title: str) -> None:
    pas = expo["pas_grille_m"]
    W = expo["largeur"]
    H = expo["hauteur"]
    cells = expo["cells"]

    nx = int(math.ceil(W / pas))
    ny = int(math.ceil(H / pas))

    grid = [[0 for _ in range(nx)] for _ in range(ny)]
    map_val = {"ombre": 0, "mi_ombre": 1, "plein_soleil": 2}

    for c in cells:
        ix = int(c["x"] // pas)
        iy = int(c["y"] // pas)
        ix = min(max(ix, 0), nx - 1)
        iy = min(max(iy, 0), ny - 1)
        grid[iy][ix] = map_val.get(c["classe"], 0)

    fig, ax = plt.subplots()
    im = ax.imshow(grid, origin="lower", extent=[0, W, 0, H], interpolation="nearest", aspect="equal")
    cbar = fig.colorbar(im, ax=ax, ticks=[0, 1, 2])
    cbar.ax.set_yticklabels(["ombre", "mi-ombre", "plein soleil"])

    ax.add_patch(Rectangle((0, 0), W, H, fill=False))

    for i, m in enumerate(_get_maison_shapes_from_payload(terrain), start=1):
        label = "Maison" if i == 1 else f"Ext {i-1}"
        ax.add_patch(Rectangle((m["origine"][0], m["origine"][1]), m["largeur"], m["hauteur"], fill=False))
        ax.text(m["origine"][0], m["origine"][1], label)

    t = terrain["terrasse"]
    ax.add_patch(Rectangle((t["origine"][0], t["origine"][1]), t["largeur"], t["hauteur"], fill=False))

    for tr in terrain.get("trous_terrasse", []):
        if tr["forme"] == "rectangle" and tr.get("dimensions"):
            w, h = tr["dimensions"]
            ax.add_patch(Rectangle((tr["position"][0], tr["position"][1]), w, h, fill=False))
        elif tr["forme"] == "cercle" and tr.get("rayon") is not None:
            ax.add_patch(Circle((tr["position"][0], tr["position"][1]), tr["rayon"], fill=False))

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(title)
    st.pyplot(fig)

    st.write("Résumé")
    st.json(expo["resume"])


def draw_plantation(placements: List[Dict[str, Any]], terrain: Dict[str, Any], parcelle_w: float, parcelle_h: float) -> None:
    fig, ax = plt.subplots()
    ax.set_xlim(0, parcelle_w)
    ax.set_ylim(0, parcelle_h)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Plantation (points)")

    ax.add_patch(Rectangle((0, 0), parcelle_w, parcelle_h, fill=False))

    for m in _get_maison_shapes_from_payload(terrain):
        ax.add_patch(Rectangle((m["origine"][0], m["origine"][1]), m["largeur"], m["hauteur"], fill=False))

    t = terrain["terrasse"]
    ax.add_patch(Rectangle((t["origine"][0], t["origine"][1]), t["largeur"], t["hauteur"], fill=False))

    for tr in terrain.get("trous_terrasse", []):
        if tr["forme"] == "rectangle" and tr.get("dimensions"):
            w, h = tr["dimensions"]
            ax.add_patch(Rectangle((tr["position"][0], tr["position"][1]), w, h, fill=False))
        elif tr["forme"] == "cercle" and tr.get("rayon") is not None:
            ax.add_patch(Circle((tr["position"][0], tr["position"][1]), tr["rayon"], fill=False))

    xs = [p["x"] for p in placements]
    ys = [p["y"] for p in placements]
    ax.scatter(xs, ys)
    st.pyplot(fig)


# ----------------------------
# Payload
# ----------------------------
def build_terrain_payload() -> Dict[str, Any]:
    maison_principale = {
        "origine": [maison_x, maison_y],
        "largeur": maison_largeur,
        "hauteur": maison_hauteur,
        "hauteur_batiment": maison_hauteur_batiment,
    }
    maisons = [maison_principale] + extensions

    return {
        "parcelle": {"origine": [0, 0], "largeur": parcelle_largeur, "hauteur": parcelle_hauteur},
        "maisons": maisons,
        "maison": None,
        "terrasse": {"origine": [terrasse_x, terrasse_y], "largeur": terrasse_largeur, "hauteur": terrasse_hauteur},
        "trous_terrasse": trous_terrasse,
        "orientation_nord_deg": orientation_nord_deg,
        "latitude": latitude,
        "longitude": longitude,
        "pas_grille_m": pas_grille_m,
        "timezone": timezone,
        "date_ref": date_ref,
        "pas_minutes": int(pas_minutes),
        "heure_debut": int(heure_debut),
        "heure_fin": int(heure_fin),
    }


# ----------------------------
# Analyse globale
# ----------------------------
if st.button("Lancer l'analyse"):
    payload = build_terrain_payload()
    try:
        r = requests.post(f"{API_URL}/analyser", json=payload, timeout=20)
        if r.status_code != 200:
            st.error(f"Erreur API ({r.status_code}) : {r.text}")
            st.stop()
        st.success("Analyse surfaces terminée.")
        st.json(r.json())

        plan = requests.post(f"{API_URL}/plan_2d", json=payload, timeout=20)
        plan.raise_for_status()
        draw_plan(plan.json(), parcelle_largeur, parcelle_hauteur)

        expo = requests.post(f"{API_URL}/exposition", json=payload, timeout=60)
        expo.raise_for_status()
        draw_exposition(expo.json(), payload, "Exposition (simplifiée) : ombre / mi-ombre / plein soleil")

        expo_p = requests.post(f"{API_URL}/exposition_precise", json=payload, timeout=120)
        expo_p.raise_for_status()
        draw_exposition(expo_p.json(), payload, "Exposition précise : ombre / mi-ombre / plein soleil")

    except Exception as e:
        st.error(f"Impossible de contacter l'API : {e}")

st.divider()


# ----------------------------
# Plantation automatique
# ----------------------------
st.subheader("Plantation automatique (selon exposition précise)")

sol_pl = st.selectbox("Filtre sol (plantation)", ["(peu importe)", "drainant", "normal", "argileux", "humide"], key="sol_pl_auto")
climat_pl = st.selectbox("Filtre climat (plantation)", ["(peu importe)", "oceanique", "continental", "mediterraneen", "montagnard"], key="climat_pl_auto")

if st.button("Proposer une plantation"):
    terrain_payload = build_terrain_payload()
    payload_plantation = {
        "terrain": terrain_payload,
        "sol": None if sol_pl == "(peu importe)" else sol_pl,
        "climat": None if climat_pl == "(peu importe)" else climat_pl,
    }

    try:
        r = requests.post(f"{API_URL}/plantation/proposer", json=payload_plantation, timeout=180)
        if r.status_code != 200:
            st.error(f"Erreur API ({r.status_code}) : {r.text}")
            st.stop()

        data = r.json()
        resume = data.get("resume", {})
        placements = data.get("placements", [])

        st.success("Plantation proposée.")
        st.json(resume)

        if len(placements) == 0:
            st.warning("Aucun placement. Essaie d'enrichir plantes.csv ou enlève les filtres sol/climat.")
        else:
            draw_plantation(placements, terrain_payload, parcelle_largeur, parcelle_hauteur)

    except Exception as e:
        st.error(f"Impossible de contacter l'API : {e}")

st.caption("V1 : surfaces + plan 2D + exposition (simple + précise) + proposition plantation.")