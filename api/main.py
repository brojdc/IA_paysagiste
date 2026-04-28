import json
import math
import os
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.exposure import compute_exposition_v2
from core.schemas import (
    TerrainInput, SurfacesOutput, Plan2DOutput, ExpositionOutput,
    PlantesFiltrerInput, PlantesFiltrerOutput, ExpositionPreciseOutput,
    PlantationRequest, PlantationPlanOutput, ExpositionV2Input,
)
from core.services import (
    compute_surfaces, build_plan_2d, compute_exposition,
    filtrer_plantes, compute_exposition_precise, proposer_plantation,
    load_plantes,
)

app = FastAPI(title="IA Paysagiste")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ── Endpoints existants ─────────────────────────────────────────────────────

@app.get("/ping")
def ping():
    return {"statut": "ok"}


@app.post("/exposition_v2")
def exposition_v2(data: ExpositionV2Input):
    return compute_exposition_v2(
        lat=data.lat, lon=data.lon,
        date=datetime.fromisoformat(data.date),
        tz=data.timezone, north_offset=data.north_offset,
        step_minutes=data.step_minutes,
    )


@app.post("/analyser", response_model=SurfacesOutput)
def analyser(donnees: TerrainInput):
    surfaces_m2 = compute_surfaces(donnees)
    resume = {
        "zone_analyse": donnees.zone_analyse,
        "nb_obstacles": len(getattr(donnees, "obstacles", []) or []),
        "nb_batiments": len(donnees.get_blocs_maison()),
        "surfaces": surfaces_m2,
    }
    return SurfacesOutput(surfaces_m2=surfaces_m2, resume=resume)


@app.post("/plan_2d", response_model=Plan2DOutput)
def plan_2d(donnees: TerrainInput):
    return Plan2DOutput(shapes=build_plan_2d(donnees))


@app.post("/exposition", response_model=ExpositionOutput)
def exposition(donnees: TerrainInput):
    return compute_exposition(donnees)


@app.post("/plantes/filtrer", response_model=PlantesFiltrerOutput)
def plantes_filtrer(filtres: PlantesFiltrerInput):
    return filtrer_plantes(filtres)


@app.post("/exposition_precise", response_model=ExpositionPreciseOutput)
def exposition_precise(donnees: TerrainInput):
    return compute_exposition_precise(donnees)


@app.post("/plantation/proposer", response_model=PlantationPlanOutput)
def plantation_proposer(req: PlantationRequest):
    return proposer_plantation(req)


# ── Course solaire ──────────────────────────────────────────────────────────

@app.get("/sun-course")
def sun_course(
    lat: float = Query(48.8566, description="Latitude"),
    lon: float = Query(2.3522, description="Longitude"),
    tz: str  = Query("Europe/Paris", description="Timezone IANA"),
):
    """
    Calcule les données de la course solaire pour l'été et l'hiver.
    Utilise pvlib avec une résolution d'une minute.
    """
    import pandas as pd
    from pvlib.solarposition import get_solarposition

    def _course_for_date(date_str: str) -> Optional[dict]:
        ts = pd.date_range(
            f"{date_str} 04:00", f"{date_str} 22:00",
            freq="1min", tz=tz,
        )
        solpos = get_solarposition(ts, lat, lon)
        above  = solpos[solpos["apparent_elevation"] > 0]
        if above.empty:
            return None
        lever_t   = above.index[0]
        coucher_t = above.index[-1]
        return {
            "lever"     : lever_t.strftime("%H:%M"),
            "az_lever"  : round(float(above.loc[lever_t, "azimuth"]), 1),
            "coucher"   : coucher_t.strftime("%H:%M"),
            "az_coucher": round(float(above.loc[coucher_t, "azimuth"]), 1),
            "hauteur_max": round(float(above["apparent_elevation"].max()), 1),
            "duree_h"   : round(len(above) / 60.0, 1),
        }

    try:
        ete   = _course_for_date("2026-06-21")
        hiver = _course_for_date("2026-12-21")

        diff = None
        if ete and hiver and ete["duree_h"] > 0:
            diff = round((ete["duree_h"] - hiver["duree_h"]) / ete["duree_h"] * 100, 1)

        return {"ete": ete, "hiver": hiver, "diff_eclairement_pct": diff}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Positions solaires (existant) ───────────────────────────────────────────

class SunPositionsRequest(BaseModel):
    latitude  : float
    longitude : float
    date      : str
    timezone  : str = "Europe/Paris"
    step_minutes: int = 30


@app.post("/sun-positions")
def sun_positions(req: SunPositionsRequest):
    """Retourne les positions du soleil (altitude + azimut) pour une journée."""
    import pandas as pd
    from pvlib.solarposition import get_solarposition

    try:
        start = pd.Timestamp(f"{req.date} 05:00:00", tz=req.timezone)
        end   = pd.Timestamp(f"{req.date} 22:00:00", tz=req.timezone)
        times = pd.date_range(start=start, end=end, freq=f"{req.step_minutes}min")
        solpos = get_solarposition(times, req.latitude, req.longitude)

        positions = []
        for t, row in solpos.iterrows():
            alt = float(row["apparent_elevation"])
            if alt > 0:
                positions.append({
                    "time": t.strftime("%H:%M"),
                    "alt" : round(alt, 1),
                    "az"  : round(float(row["azimuth"]), 1),
                })
        return {"positions": positions, "date": req.date}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Grille solaire ──────────────────────────────────────────────────────────

@app.post("/sun-grid")
def sun_grid(donnees: TerrainInput):
    """
    Calcule la grille d'ensoleillement (heures / jour) via shadow_engine.
    Retourne grid JSON + bbox + meta.
    """
    from shapely.geometry import box as shapely_box
    from core.shadow_engine import terrain_to_obstacles, sun_hours_grid

    try:
        parcel_geom = shapely_box(
            0, 0,
            float(donnees.parcelle.largeur),
            float(donnees.parcelle.hauteur),
        )
        obstacles = terrain_to_obstacles(donnees)
        grid, meta = sun_hours_grid(
            parcel=parcel_geom,
            obstacles=obstacles,
            date=donnees.date_ref,
            lat=float(donnees.latitude),
            lon=float(donnees.longitude),
            parcel_rotation=float(donnees.orientation_nord_deg),
            resolution_m=float(donnees.pas_grille_m),
            time_step_min=int(donnees.pas_minutes),
            tz=donnees.timezone,
            slope_pct=float(donnees.slope_pct),
            slope_orientation_deg=float(donnees.slope_orientation_deg),
        )
        return {
            "grid": grid.tolist(),
            "bbox": meta["bbox"],
            "meta": meta,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Snapshot d'ombres ───────────────────────────────────────────────────────

class ShadowsSnapshotRequest(BaseModel):
    terrain     : TerrainInput
    datetime_iso: str


@app.post("/shadows-snapshot")
def shadows_snapshot_endpoint(req: ShadowsSnapshotRequest):
    """
    Retourne les polygones d'ombre à un instant T donné (datetime ISO).
    """
    from shapely.geometry import box as shapely_box
    from core.shadow_engine import terrain_to_obstacles, shadows_snapshot

    terrain = req.terrain
    try:
        parcel_geom = shapely_box(
            0, 0,
            float(terrain.parcelle.largeur),
            float(terrain.parcelle.hauteur),
        )
        obstacles = terrain_to_obstacles(terrain)
        polys = shadows_snapshot(
            parcel=parcel_geom,
            obstacles=obstacles,
            datetime_iso=req.datetime_iso,
            lat=float(terrain.latitude),
            lon=float(terrain.longitude),
            parcel_rotation=float(terrain.orientation_nord_deg),
            tz=terrain.timezone,
            slope_pct=float(terrain.slope_pct),
            slope_orientation_deg=float(terrain.slope_orientation_deg),
        )
        return {"polygons": polys, "datetime_iso": req.datetime_iso}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Export PDF ──────────────────────────────────────────────────────────────

class PdfRequest(BaseModel):
    terrain      : TerrainInput
    nom_projet   : str = "Projet paysager"
    paysagiste   : str = "Paysagiste"


@app.post("/pdf-time-slices")
def pdf_time_slices(req: PdfRequest):
    """
    Génère un rapport PDF 8 pages :
    couverture / plan / ombres 9h-13h-17h / heatmap / synthèse / plantes.
    """
    from core.pdf_export import generate_pdf_report

    # Récupère la course solaire pour la page 6
    try:
        import pandas as pd
        from pvlib.solarposition import get_solarposition

        terrain = req.terrain
        lat, lon = float(terrain.latitude), float(terrain.longitude)
        tz = terrain.timezone

        def _course(date_str):
            ts = pd.date_range(f"{date_str} 04:00", f"{date_str} 22:00", freq="1min", tz=tz)
            sp = get_solarposition(ts, lat, lon)
            ab = sp[sp["apparent_elevation"] > 0]
            if ab.empty:
                return None
            return {
                "lever"     : ab.index[0].strftime("%H:%M"),
                "az_lever"  : round(float(ab.loc[ab.index[0], "azimuth"]), 1),
                "coucher"   : ab.index[-1].strftime("%H:%M"),
                "az_coucher": round(float(ab.loc[ab.index[-1], "azimuth"]), 1),
                "hauteur_max": round(float(ab["apparent_elevation"].max()), 1),
                "duree_h"   : round(len(ab) / 60.0, 1),
            }

        ete   = _course("2026-06-21")
        hiver = _course("2026-12-21")
        diff  = None
        if ete and hiver and ete["duree_h"] > 0:
            diff = round((ete["duree_h"] - hiver["duree_h"]) / ete["duree_h"] * 100, 1)
        sun_course_data = {"ete": ete, "hiver": hiver, "diff_eclairement_pct": diff}
    except Exception:
        sun_course_data = None

    try:
        pdf_bytes = generate_pdf_report(
            terrain=req.terrain,
            nom_projet=req.nom_projet,
            paysagiste=req.paysagiste,
            sun_course_data=sun_course_data,
            plants_data=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Génération PDF échouée : {exc}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="rapport_terrain.pdf"'},
    )


# ── Recommandations plantes depuis exposition ────────────────────────────────

class RecommendPlantsRequest(BaseModel):
    terrain : TerrainInput
    sol     : Optional[str] = None
    climat  : Optional[str] = None
    grid    : Optional[List[List[float]]] = None  # grille hours optionnelle


@app.post("/recommend-plants-from-exposure")
def recommend_plants_from_exposure(req: RecommendPlantsRequest):
    """
    Recommande des plantes par zone d'exposition.
    Si grid est fourni, utilise la grille. Sinon, calcule l'exposition précise.
    """
    terrain = req.terrain

    # Si pas de grille fournie : on recalcule
    if not req.grid:
        expo = compute_exposition_precise(terrain)
        cells = expo["cells"]
        max_min = expo["resume"].get("max_minutes_theorique", 1) or 1
        # Convertir en liste de heures
        grid_flat = [c["score"] / 60.0 for c in cells]
    else:
        grid_flat = [v for row in req.grid for v in row]
        max_min = None

    if not grid_flat:
        return {"zones": []}

    total = len(grid_flat)
    cell_area = float(terrain.pas_grille_m) ** 2

    # Seuils : ≥6h = plein soleil, 3-6h = mi-ombre, <3h = ombre
    plein_soleil_cells = [v for v in grid_flat if v >= 6]
    mi_ombre_cells     = [v for v in grid_flat if 3 <= v < 6]
    ombre_cells        = [v for v in grid_flat if v < 3]

    plantes = load_plantes()
    if req.sol:
        plantes = [p for p in plantes if p.sol == req.sol]
    if req.climat:
        plantes = [p for p in plantes if p.climat == req.climat]

    def _build_zone(expo_type: str, cells_list: list) -> dict:
        n = len(cells_list)
        pct = n / total * 100
        surf = n * cell_area
        candidates = [p for p in plantes if p.exposition == expo_type][:8]
        avg_h = (sum(cells_list) / n) if n > 0 else 0
        plantes_list = [
            {
                "nom"          : p.nom,
                "type"         : p.type,
                "exposition"   : p.exposition,
                "hauteur_m"    : p.hauteur_m,
                "floraison"    : p.floraison,
                "feuillage"    : p.feuillage,
                "couleur"      : p.couleur,
                "notes"        : p.notes,
                "justification": (
                    f"Recommandée car votre zone reçoit en moyenne "
                    f"{avg_h:.1f} h de soleil — idéal pour une plante "
                    f"{expo_type.replace('_', ' ')}."
                ),
            }
            for p in candidates
        ]
        return {
            "zone"      : expo_type,
            "pct"       : round(pct, 1),
            "surface_m2": round(surf, 1),
            "plantes"   : plantes_list,
        }

    zones = []
    if plein_soleil_cells:
        zones.append(_build_zone("plein_soleil", plein_soleil_cells))
    if mi_ombre_cells:
        zones.append(_build_zone("mi_ombre", mi_ombre_cells))
    if ombre_cells:
        zones.append(_build_zone("ombre", ombre_cells))

    return {"zones": zones}


# ── Statut LLM (multi-provider) ─────────────────────────────────────────────

@app.get("/llm-status")
def llm_status():
    """
    Teste la connexion LLM selon le provider configuré via LLM_PROVIDER.
    Providers supportés : ollama_local, ollama_cloud, openai, anthropic, mistral.
    """
    import requests as req_lib

    provider = os.environ.get("LLM_PROVIDER", "").strip().lower() or "auto"

    if provider == "ollama_local":
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        try:
            r = req_lib.post(
                "http://localhost:11434/v1/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3},
                timeout=5,
            )
            if r.status_code == 200:
                return {"ok": True, "provider": "ollama_local", "model": model,
                        "message": f"Ollama local opérationnel ({model})"}
            return {"ok": False, "provider": "ollama_local", "model": model,
                    "message": f"HTTP {r.status_code} — Vérifiez qu'Ollama est lancé (ollama serve)"}
        except Exception as exc:
            return {"ok": False, "provider": "ollama_local", "model": model,
                    "message": f"Ollama non joignable. Lancez 'ollama serve' puis 'ollama pull {model}'."}

    elif provider == "openai":
        key   = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if not key:
            return {"ok": False, "provider": "openai", "model": model,
                    "message": "OPENAI_API_KEY manquante dans .env"}
        try:
            r = req_lib.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3},
                timeout=8,
            )
            if r.status_code == 200:
                return {"ok": True, "provider": "openai", "model": model,
                        "message": f"OpenAI opérationnel ({model})"}
            return {"ok": False, "provider": "openai", "model": model,
                    "message": f"HTTP {r.status_code} — clé invalide ?"}
        except Exception as exc:
            return {"ok": False, "provider": "openai", "model": model, "message": str(exc)}

    elif provider == "anthropic":
        key   = os.environ.get("ANTHROPIC_API_KEY", "")
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        if not key:
            return {"ok": False, "provider": "anthropic", "model": model,
                    "message": "ANTHROPIC_API_KEY manquante dans .env"}
        try:
            import anthropic as ant
            client = ant.Anthropic(api_key=key)
            client.messages.create(
                model=model, max_tokens=3,
                messages=[{"role": "user", "content": "hi"}],
            )
            return {"ok": True, "provider": "anthropic", "model": model,
                    "message": f"Anthropic opérationnel ({model})"}
        except Exception as exc:
            return {"ok": False, "provider": "anthropic", "model": model, "message": str(exc)}

    elif provider == "mistral":
        key   = os.environ.get("MISTRAL_API_KEY", "")
        model = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
        if not key:
            return {"ok": False, "provider": "mistral", "model": model,
                    "message": "MISTRAL_API_KEY manquante dans .env"}
        try:
            r = req_lib.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3},
                timeout=8,
            )
            if r.status_code == 200:
                return {"ok": True, "provider": "mistral", "model": model,
                        "message": f"Mistral opérationnel ({model})"}
            return {"ok": False, "provider": "mistral", "model": model,
                    "message": f"HTTP {r.status_code}"}
        except Exception as exc:
            return {"ok": False, "provider": "mistral", "model": model, "message": str(exc)}

    elif provider == "auto":
        # Auto-détection : Anthropic → OpenAI → Ollama local
        if os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return {"ok": True, "provider": "anthropic (auto)", "model": os.environ.get("ANTHROPIC_MODEL","claude-haiku-4-5-20251001"),
                    "message": "Agent IA prêt — Anthropic Claude (auto-détecté)"}
        if os.environ.get("OPENAI_API_KEY", "").strip():
            return {"ok": True, "provider": "openai (auto)", "model": os.environ.get("OPENAI_MODEL","gpt-4o-mini"),
                    "message": "Agent IA prêt — OpenAI (auto-détecté)"}
        try:
            r_ping = req_lib.get("http://localhost:11434/", timeout=1)
            if r_ping.ok:
                return {"ok": True, "provider": "ollama_local (auto)", "model": os.environ.get("OLLAMA_MODEL","llama3"),
                        "message": "Agent IA prêt — Ollama local (auto-détecté)"}
        except Exception:
            pass
        return {"ok": False, "provider": "none", "model": "",
                "message": "Aucun agent IA disponible. Ajoutez ANTHROPIC_API_KEY ou OPENAI_API_KEY dans .env"}

    else:  # ollama_cloud
        key   = os.environ.get("OLLAMA_API_KEY", "")
        model = os.environ.get("OLLAMA_MODEL", "llama3.1")
        if not key:
            return {
                "ok": False, "provider": "ollama_cloud", "model": model,
                "message": (
                    "Aucun LLM configuré. Options : "
                    "(1) ANTHROPIC_API_KEY dans .env (recommandé), "
                    "(2) OPENAI_API_KEY + LLM_PROVIDER=openai, "
                    "(3) Ollama local + LLM_PROVIDER=ollama_local."
                ),
            }
        try:
            r = req_lib.post(
                "https://api.ollama.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3},
                timeout=8,
            )
            if r.status_code == 200:
                return {"ok": True, "provider": "ollama_cloud", "model": model,
                        "message": f"Ollama Cloud opérationnel ({model})"}
            return {"ok": False, "provider": "ollama_cloud", "model": model,
                    "message": f"HTTP {r.status_code} — clé invalide ou expirée. "
                               "Générez une nouvelle clé sur https://api.ollama.com"}
        except Exception as exc:
            return {"ok": False, "provider": "ollama_cloud", "model": model, "message": str(exc)}


# ── Agent chat (SSE streaming) ──────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    question: str
    terrain : Optional[TerrainInput] = None
    history : List[dict] = []


@app.post("/agent/chat")
def agent_chat(req: AgentChatRequest):
    from agent import agent_libre
    terrain_dict = req.terrain.model_dump(mode="json") if req.terrain else {}
    messages = list(req.history)
    messages.append({"role": "user", "content": req.question})

    def stream():
        try:
            for event in agent_libre.agent_stream(terrain_dict, messages):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Frontend statique (doit être en dernier) ────────────────────────────────
_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
