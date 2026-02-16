import streamlit as st
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle


st.set_page_config(page_title="IA Paysagiste", layout="centered")

st.title("IA Paysagiste - Formulaire chantier (V1)")
st.write("Remplis les dimensions, puis lance l'analyse des surfaces.")

API_URL = "http://127.0.0.1:8000"


st.subheader("Parcelle")
parcelle_largeur = st.number_input("Largeur de la parcelle (m)", min_value=0.0, value=26.0, step=0.5)
parcelle_hauteur = st.number_input("Longueur/Hauteur de la parcelle (m)", min_value=0.0, value=20.0, step=0.5)

st.subheader("Maison")
maison_x = st.number_input("Position X de la maison (m)", min_value=0.0, value=7.5, step=0.5)
maison_y = st.number_input("Position Y de la maison (m)", min_value=0.0, value=5.0, step=0.5)
maison_largeur = st.number_input("Largeur maison (m)", min_value=0.0, value=11.0, step=0.5)
maison_hauteur = st.number_input("Longueur/Hauteur maison (m)", min_value=0.0, value=10.0, step=0.5)
maison_hauteur_batiment = st.number_input("Hauteur du batiment (m)", min_value=0.0, value=6.0, step=0.5)

st.subheader("Terrasse")
terrasse_x = st.number_input("Position X de la terrasse (m)", min_value=0.0, value=9.0, step=0.5)
terrasse_y = st.number_input("Position Y de la terrasse (m)", min_value=0.0, value=3.5, step=0.5)
terrasse_largeur = st.number_input("Largeur terrasse (m)", min_value=0.0, value=6.0, step=0.5)
terrasse_hauteur = st.number_input("Longueur/Hauteur terrasse (m)", min_value=0.0, value=4.0, step=0.5)

st.subheader("Parametres d'exposition")
orientation_nord_deg = st.number_input("Orientation nord (degres)", value=0.0, step=5.0)
latitude = st.number_input("Latitude", value=48.8566, step=0.1)
pas_grille_m = st.number_input("Pas de grille (m)", min_value=0.5, value=1.0, step=0.5)

st.subheader("Trous / massifs sur la terrasse (optionnel)")
a_des_trous = st.checkbox("La terrasse a des trous (massifs / arbres) ?")

trous_terrasse = []
if a_des_trous:
    nb_trous = st.number_input("Nombre de trous", min_value=1, max_value=20, value=1, step=1)
    for i in range(int(nb_trous)):
        st.markdown(f"Trou {i+1}")
        forme = st.selectbox(f"Forme trou {i+1}", ["rectangle", "cercle"], key=f"forme_{i}")
        pos_x = st.number_input(f"Position X trou {i+1}", min_value=0.0, value=10.0, step=0.1, key=f"tx_{i}")
        pos_y = st.number_input(f"Position Y trou {i+1}", min_value=0.0, value=4.2, step=0.1, key=f"ty_{i}")

        if forme == "rectangle":
            dim_l = st.number_input(f"Largeur trou {i+1} (m)", min_value=0.0, value=1.2, step=0.1, key=f"dl_{i}")
            dim_h = st.number_input(f"Hauteur trou {i+1} (m)", min_value=0.0, value=0.6, step=0.1, key=f"dh_{i}")
            trous_terrasse.append({"forme": "rectangle", "position": [pos_x, pos_y], "dimensions": [dim_l, dim_h]})
        else:
            rayon = st.number_input(f"Rayon trou {i+1} (m)", min_value=0.0, value=0.5, step=0.1, key=f"r_{i}")
            trous_terrasse.append({"forme": "cercle", "position": [pos_x, pos_y], "rayon": rayon})

st.divider()


def draw_plan(plan: dict, parcelle_w: float, parcelle_h: float):
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


def draw_exposition(expo: dict):
    # Heatmap simple par classes (0,1,2) sur la grille
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
    ax.imshow(grid, origin="lower")
    ax.set_title("Exposition (0=ombre, 1=mi-ombre, 2=plein soleil)")
    st.pyplot(fig)

    st.write("Resume exposition")
    st.json(expo["resume"])


if st.button("Lancer l'analyse"):
    payload = {
        "parcelle": {"origine": [0, 0], "largeur": parcelle_largeur, "hauteur": parcelle_hauteur},
        "maison": {
            "origine": [maison_x, maison_y],
            "largeur": maison_largeur,
            "hauteur": maison_hauteur,
            "hauteur_batiment": maison_hauteur_batiment,
        },
        "terrasse": {"origine": [terrasse_x, terrasse_y], "largeur": terrasse_largeur, "hauteur": terrasse_hauteur},
        "trous_terrasse": trous_terrasse,
        "orientation_nord_deg": orientation_nord_deg,
        "latitude": latitude,
        "pas_grille_m": pas_grille_m,
    }

    try:
        r = requests.post(f"{API_URL}/analyser", json=payload, timeout=10)
        if r.status_code != 200:
            st.error(f"Erreur API ({r.status_code}) : {r.text}")
            st.stop()

        data = r.json()
        st.success("Analyse terminee.")
        st.json(data)

        plan = requests.post(f"{API_URL}/plan_2d", json=payload, timeout=10).json()
        draw_plan(plan, parcelle_largeur, parcelle_hauteur)

        expo = requests.post(f"{API_URL}/exposition", json=payload, timeout=30).json()
        import math
        draw_exposition(expo)

    except Exception as e:
        st.error(f"Impossible de contacter l'API : {e}")

st.caption("V1 : surfaces + plan 2D + exposition simplifiee.")
