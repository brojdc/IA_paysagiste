from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from core.schemas import (
    TerrainInput,
    SurfacesOutput,
    Plan2DOutput,
    ExpositionOutput,
    PlantesFiltrerInput,
    PlantesFiltrerOutput,
)

from core.services import (
    compute_surfaces,
    build_plan_2d,
    compute_exposition,
    filtrer_plantes,
)

from core.schemas import ExpositionPreciseOutput
from core.services import compute_exposition_precise
from core.schemas import PlantationRequest, PlantationPlanOutput
from core.services import proposer_plantation


app = FastAPI(title="IA Paysagiste - Prototype")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/ping")
def ping():
    return {"statut": "ok", "message": "IA Paysagiste operationnelle"}


@app.post("/analyser", response_model=SurfacesOutput)
def analyser(donnees: TerrainInput):
    surfaces_m2 = compute_surfaces(donnees)
    return SurfacesOutput(surfaces_m2=surfaces_m2)


@app.post("/plan_2d", response_model=Plan2DOutput)
def plan_2d(donnees: TerrainInput):
    shapes = build_plan_2d(donnees)
    return Plan2DOutput(shapes=shapes)


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
