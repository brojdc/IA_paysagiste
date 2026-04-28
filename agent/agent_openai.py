"""Agent IA paysagiste basé sur OpenAI.

Ce module sert de fallback si aucune clé OLLAMA_API_KEY ni ANTHROPIC_API_KEY
n'est disponible mais qu'une clé OPENAI_API_KEY est définie.
"""
import json
import os
from typing import Generator

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from .tools import analyser_terrain, analyser_exposition, proposer_plantes
from .rapport import generer_rapport

load_dotenv()

_pending_pdf: tuple[bytes, str] | None = None

TOOL_LABELS = {
    "analyser_terrain_tool": "Analyse des surfaces du terrain",
    "analyser_exposition_solaire_tool": "Calcul de l'exposition solaire",
    "proposer_plantes_tool": "Proposition d'un plan de plantation",
    "generer_rapport_pdf_tool": "Génération du rapport PDF",
}


def _make_tools(terrain_payload: dict):
    @tool
    def analyser_terrain_tool() -> str:
        return json.dumps(analyser_terrain(terrain_payload), ensure_ascii=False)

    @tool
    def analyser_exposition_solaire_tool() -> str:
        return json.dumps(analyser_exposition(terrain_payload), ensure_ascii=False)

    @tool
    def proposer_plantes_tool(sol: str, climat: str) -> str:
        return json.dumps(proposer_plantes(terrain_payload, sol, climat), ensure_ascii=False)

    @tool
    def generer_rapport_pdf_tool(nom_client: str, titre_projet: str, sol: str, climat: str) -> str:
        global _pending_pdf
        surfaces = analyser_terrain(terrain_payload)
        exposition = analyser_exposition(terrain_payload)
        plantation = proposer_plantes(terrain_payload, sol, climat)
        pdf_bytes = generer_rapport(nom_client, titre_projet, surfaces, exposition, plantation)
        filename = f"rapport_{nom_client.replace(' ', '_')}.pdf"
        _pending_pdf = (pdf_bytes, filename)
        return json.dumps({
            "success": True,
            "fichier": filename,
            "taille_ko": round(len(pdf_bytes) / 1024),
        }, ensure_ascii=False)

    return [
        analyser_terrain_tool,
        analyser_exposition_solaire_tool,
        proposer_plantes_tool,
        generer_rapport_pdf_tool,
    ]


def _build_system_prompt(terrain_payload: dict) -> str:
    parcelle = terrain_payload.get("parcelle", {})
    maisons = terrain_payload.get("maisons", [])
    haies = terrain_payload.get("haies_auto", [])
    nb_ext = max(0, len(maisons) - 1)
    batiments = f"1 maison principale{f' + {nb_ext} extension(s)' if nb_ext > 0 else ''}"

    return f"""Tu es un expert en paysagisme et conception de jardins, intégré à l'application IA Paysagiste.
Tu aides les paysagistes et propriétaires à comprendre leur projet et à prendre les meilleures décisions.

Données du terrain actuel :
- Parcelle : {parcelle.get('largeur','?')} m x {parcelle.get('hauteur','?')} m
- Batiments : {batiments}
- Haies configurées : {len(haies)} côte(s)
- Latitude : {terrain_payload.get('latitude','?')} | Date de référence : {terrain_payload.get('date_ref','?')}

Instructions :
- Réponds toujours en français avec un ton professionnel et bienveillant.
- Utilise les outils disponibles pour baser tes réponses sur des données réelles du terrain.
- Pour recommander des plantes, analyse d'abord l'exposition solaire, puis propose une plantation.
- Ne devine pas les chiffres : utilise les outils pour obtenir des données précises.
"""


def agent_stream(terrain_payload: dict, messages: list) -> Generator[dict, None, None]:
    tools = _make_tools(terrain_payload)
    tools_by_name = {t.name: t for t in tools}

    llm = ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-3.5-turbo",
        temperature=0,
    ).bind_tools(tools)

    lc_messages = [SystemMessage(content=_build_system_prompt(terrain_payload))]
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "user" and isinstance(content, str):
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant" and isinstance(content, str):
            lc_messages.append(AIMessage(content=content))

    full_text = ""
    updated_messages = list(messages)

    while True:
        response = llm.invoke(lc_messages)
        lc_messages.append(response)

        if response.content:
            full_text += response.content
            yield {"type": "text_delta", "text": response.content}

        if not response.tool_calls:
            break

        tool_results = []
        for tc in response.tool_calls:
            name = tc["name"]
            label = TOOL_LABELS.get(name, name)
            yield {"type": "tool_start", "name": name, "label": label}
            try:
                result = tools_by_name[name].invoke(tc["args"])
                yield {"type": "tool_done", "name": name, "label": label, "success": True}
                tool_results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            except Exception as exc:
                yield {"type": "tool_done", "name": name, "label": label, "success": False, "error": str(exc)}
                tool_results.append(ToolMessage(content=f"Erreur: {exc}", tool_call_id=tc["id"]))

        lc_messages.extend(tool_results)

    updated_messages.append({"role": "assistant", "content": full_text})
    yield {"type": "done", "full_text": full_text, "updated_messages": updated_messages}
