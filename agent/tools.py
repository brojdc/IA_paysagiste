"""Appels directs aux services core (sans HTTP, évite les deadlocks)."""
from core.schemas import TerrainInput, PlantationRequest
from core.services import compute_surfaces, compute_exposition_precise, proposer_plantation


def analyser_terrain(payload: dict) -> dict:
    terrain = TerrainInput(**payload)
    surfaces_m2 = compute_surfaces(terrain)
    return {
        "surfaces_m2": surfaces_m2,
        "resume": {
            "nb_batiments": len(terrain.get_blocs_maison()),
            "nb_obstacles": len(terrain.obstacles or []),
            "surfaces": surfaces_m2,
        },
    }


def analyser_exposition(payload: dict) -> dict:
    terrain = TerrainInput(**payload)
    return compute_exposition_precise(terrain)


def proposer_plantes(payload: dict, sol: str | None, climat: str | None) -> dict:
    terrain = TerrainInput(**payload)
    req = PlantationRequest(terrain=terrain, sol=sol, climat=climat)
    result = proposer_plantation(req)
    return result.model_dump()
