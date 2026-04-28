"""Agent IA paysagiste — boucle agentique avec tool use et streaming."""
import json
import os
from typing import Generator

import anthropic
from dotenv import load_dotenv

from .tools import analyser_terrain, analyser_exposition, proposer_plantes
from .rapport import generer_rapport

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Side-effect : PDF généré pendant une session (récupéré par l'UI Streamlit)
_pending_pdf: tuple[bytes, str] | None = None

TOOL_LABELS = {
    "analyser_terrain": "Analyse des surfaces du terrain",
    "analyser_exposition_solaire": "Calcul de l'exposition solaire",
    "proposer_plantes": "Proposition d'un plan de plantation",
    "generer_rapport_pdf": "Génération du rapport PDF",
}

TOOLS = [
    {
        "name": "analyser_terrain",
        "description": (
            "Analyse le terrain configuré dans le formulaire et calcule toutes les surfaces : "
            "superficie de la parcelle, emprise de la maison, surface de la terrasse, "
            "et surface approximative du jardin. "
            "Utilise cet outil pour répondre aux questions sur les dimensions ou les surfaces."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "analyser_exposition_solaire",
        "description": (
            "Calcule l'exposition solaire précise de chaque zone du jardin en simulant "
            "la position du soleil heure par heure tout au long de la journée. "
            "Retourne les pourcentages de zones en plein soleil, mi-ombre et ombre. "
            "Utilise cet outil avant de recommander des plantes ou pour répondre "
            "aux questions sur l'ensoleillement."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "proposer_plantes",
        "description": (
            "Propose un plan de plantation complet adapté au terrain, à son exposition "
            "solaire, au type de sol et au climat. Retourne une liste de plantes avec "
            "leurs coordonnées de placement, leur type et leur exposition requise. "
            "Utilise cet outil pour recommander des plantes concrètes avec leurs positions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sol": {
                    "type": "string",
                    "enum": ["drainant", "normal", "argileux", "humide"],
                    "description": "Type de sol du jardin.",
                },
                "climat": {
                    "type": "string",
                    "enum": ["oceanique", "continental", "mediterraneen", "montagnard"],
                    "description": "Climat de la région.",
                },
            },
            "required": ["sol", "climat"],
        },
    },
    {
        "name": "generer_rapport_pdf",
        "description": (
            "Génère un rapport PDF professionnel complet du projet paysager pour le client. "
            "Le rapport inclut l'analyse des surfaces, l'exposition solaire et le plan de "
            "plantation avec toutes les recommandations. "
            "Utilise cet outil uniquement quand l'utilisateur demande explicitement un rapport."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nom_client": {
                    "type": "string",
                    "description": "Nom complet du client pour personnaliser le rapport.",
                },
                "titre_projet": {
                    "type": "string",
                    "description": "Titre ou nom du projet paysager.",
                },
                "sol": {
                    "type": "string",
                    "enum": ["drainant", "normal", "argileux", "humide"],
                    "description": "Type de sol pour le plan de plantation.",
                },
                "climat": {
                    "type": "string",
                    "enum": ["oceanique", "continental", "mediterraneen", "montagnard"],
                    "description": "Climat pour le plan de plantation.",
                },
            },
            "required": ["nom_client", "titre_projet", "sol", "climat"],
        },
    },
]


def _build_system_prompt(terrain_payload: dict) -> str:
    parcelle = terrain_payload.get("parcelle", {})
    maisons = terrain_payload.get("maisons", [])
    haies = terrain_payload.get("haies_auto", [])
    lat = terrain_payload.get("latitude", "?")
    lon = terrain_payload.get("longitude", "?")
    date_ref = terrain_payload.get("date_ref", "?")

    nb_ext = len(maisons) - 1
    batiments_str = f"1 maison principale{f' + {nb_ext} extension(s)' if nb_ext > 0 else ''}"

    terrain_info = (
        f"- Parcelle : {parcelle.get('largeur', '?')} m × {parcelle.get('hauteur', '?')} m\n"
        f"- Bâtiments : {batiments_str}\n"
        f"- Haies configurées : {len(haies)} côté(s)\n"
        f"- Localisation : latitude {lat}°, longitude {lon}°\n"
        f"- Date de référence pour l'analyse solaire : {date_ref}"
    )

    return f"""Tu es un expert en paysagisme et conception de jardins, intégré à l'application IA Paysagiste.
Tu aides les paysagistes et propriétaires à comprendre leur projet et à prendre les meilleures décisions.

**Données du terrain actuel :**
{terrain_info}

**Instructions :**
- Réponds toujours en français avec un ton professionnel et bienveillant.
- Utilise les outils disponibles pour baser tes réponses sur des données réelles du terrain.
- Explique clairement les résultats et formule des recommandations pratiques et actionnables.
- Pour recommander des plantes, analyse d'abord l'exposition solaire, puis propose une plantation.
- Ne devine pas les chiffres : utilise les outils pour obtenir des données précises.
"""


def _execute_tool(tool_name: str, tool_input: dict, terrain_payload: dict) -> str:
    """Exécute un outil et retourne le résultat JSON en string."""
    global _pending_pdf

    if tool_name == "analyser_terrain":
        result = analyser_terrain(terrain_payload)
        return json.dumps(result, ensure_ascii=False, indent=2)

    if tool_name == "analyser_exposition_solaire":
        result = analyser_exposition(terrain_payload)
        return json.dumps(result, ensure_ascii=False, indent=2)

    if tool_name == "proposer_plantes":
        sol = tool_input.get("sol", "normal")
        climat = tool_input.get("climat", "oceanique")
        result = proposer_plantes(terrain_payload, sol, climat)
        return json.dumps(result, ensure_ascii=False, indent=2)

    if tool_name == "generer_rapport_pdf":
        nom_client = tool_input.get("nom_client", "Client")
        titre_projet = tool_input.get("titre_projet", "Projet Paysager")
        sol = tool_input.get("sol", "normal")
        climat = tool_input.get("climat", "oceanique")

        surfaces = analyser_terrain(terrain_payload)
        exposition = analyser_exposition(terrain_payload)
        plantation = proposer_plantes(terrain_payload, sol, climat)

        pdf_bytes = generer_rapport(
            nom_client=nom_client,
            titre_projet=titre_projet,
            surfaces=surfaces,
            exposition=exposition,
            plantation=plantation,
        )
        filename = f"rapport_{nom_client.replace(' ', '_')}.pdf"
        _pending_pdf = (pdf_bytes, filename)

        return json.dumps({
            "success": True,
            "message": f"Rapport PDF généré pour {nom_client}.",
            "fichier": filename,
            "taille_ko": round(len(pdf_bytes) / 1024),
        }, ensure_ascii=False)

    return json.dumps({"error": f"Outil inconnu : {tool_name}"})


def agent_stream(terrain_payload: dict, messages: list) -> Generator[dict, None, None]:
    """
    Générateur d'événements de la boucle agentique :
    - {"type": "text_delta", "text": str}
    - {"type": "tool_start", "name": str, "label": str}
    - {"type": "tool_done", "name": str, "label": str, "success": bool, "error": str|None}
    - {"type": "done", "full_text": str, "updated_messages": list}
    """
    system = _build_system_prompt(terrain_payload)
    current_messages = list(messages)
    full_text = ""

    while True:
        tool_calls = []

        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system,
            tools=TOOLS,
            messages=current_messages,
        ) as stream:
            for chunk in stream.text_stream:
                if chunk:
                    full_text += chunk
                    yield {"type": "text_delta", "text": chunk}

            response = stream.get_final_message()

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(block)

        current_messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_calls:
            break

        tool_results = []
        for tc in tool_calls:
            label = TOOL_LABELS.get(tc.name, tc.name)
            yield {"type": "tool_start", "name": tc.name, "label": label}
            try:
                result_str = _execute_tool(tc.name, tc.input, terrain_payload)
                yield {"type": "tool_done", "name": tc.name, "label": label, "success": True}
            except Exception as exc:
                result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                yield {
                    "type": "tool_done",
                    "name": tc.name,
                    "label": label,
                    "success": False,
                    "error": str(exc),
                }
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_str,
            })

        current_messages.append({"role": "user", "content": tool_results})

    yield {"type": "done", "full_text": full_text, "updated_messages": current_messages}
