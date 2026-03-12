from fastapi.testclient import TestClient

from api.main import app
from core.services import load_plantes, compute_surfaces, build_plan_2d
from core.schemas import TerrainInput, PlantPlacement

client = TestClient(app)


def make_simple_terrain() -> TerrainInput:
    # minimal terrain used for tests (parcelle 10x10, terrasse 2x2)
    return TerrainInput(
        parcelle={"origine": [0, 0], "largeur": 10, "hauteur": 10},
        terrasse={"origine": [1, 1], "largeur": 2, "hauteur": 2},
        maisons=[],
        maison=None,
        trous_terrasse=[],
        obstacles=[],
        orientation_nord_deg=0.0,
        latitude=0.0,
        longitude=0.0,
        pas_grille_m=1.0,
        timezone="UTC",
        date_ref="2026-06-21",
        pas_minutes=10,
        heure_debut=6,
        heure_fin=18,
    )


def test_load_plantes_contains_new_fields():
    plantes = load_plantes()
    assert len(plantes) > 0
    # first items should at least have photo_url and exigences attributes
    first = plantes[0]
    assert hasattr(first, "photo_url")
    assert hasattr(first, "exigences")


def test_compute_surfaces_return_values():
    terrain = make_simple_terrain()
    surfaces = compute_surfaces(terrain)
    assert "Surface totale de la parcelle" in surfaces
    assert surfaces["Surface totale de la parcelle"] == 100


def test_api_analyser_resume_contains_expected_keys():
    terrain = make_simple_terrain().dict()
    response = client.post("/analyser", json=terrain)
    assert response.status_code == 200
    data = response.json()
    assert "surfaces_m2" in data
    assert "resume" in data
    assert data["resume"]["nb_batiments"] == 0


def test_plan_2d_with_placements():
    terrain = make_simple_terrain().dict()
    placements = [
        PlantPlacement(x=1, y=1, nom="Test", type="arbuste", exposition="ombre", distance_m=0.5).dict()
    ]
    payload = {"terrain": terrain, "placements": placements}
    response = client.post("/plan_2d", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "shapes" in data
    assert "plants" in data
    assert data["plants"] == placements
