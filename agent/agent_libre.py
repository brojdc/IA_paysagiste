"""
Agent paysagiste expert — multi-provider LLM.
Providers supportés via LLM_PROVIDER : ollama_local, ollama_cloud, openai, anthropic, mistral.
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
    "analyser_terrain_tool"           : "Analyse des surfaces du terrain",
    "analyser_exposition_solaire_tool": "Calcul de l'exposition solaire",
    "proposer_plantes_tool"           : "Proposition d'un plan de plantation",
    "generer_rapport_pdf_tool"        : "Génération du rapport PDF",
}


# ── Création du LLM avec auto-détection (Part I) ─────────────────────────────

def _ping_ollama_local() -> bool:
    """Vérifie si Ollama local répond sur le port 11434."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/", timeout=1)
        return True
    except Exception:
        return False


def _make_llm():
    """
    Auto-détecte le provider LLM dans l'ordre :
      1. LLM_PROVIDER explicite dans .env → honore la configuration
      2. ANTHROPIC_API_KEY présente → Claude (claude-haiku-4-5)
      3. OPENAI_API_KEY présente → GPT-4o-mini
      4. Ollama local joignable → llama3 local
    Lève RuntimeError si aucun provider n'est disponible.
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()

    # Provider explicitement configuré
    if provider == "ollama_local":
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        return ChatOpenAI(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            model=model,
            temperature=0,
        )

    if provider == "openai":
        key   = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if not key:
            raise RuntimeError("OPENAI_API_KEY manquante. Ajoutez-la dans .env.")
        return ChatOpenAI(api_key=key, model=model, temperature=0)

    if provider == "anthropic":
        key   = os.environ.get("ANTHROPIC_API_KEY", "")
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY manquante. Ajoutez-la dans .env.")
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=key, model=model, temperature=0)

    if provider == "mistral":
        key   = os.environ.get("MISTRAL_API_KEY", "")
        model = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
        if not key:
            raise RuntimeError("MISTRAL_API_KEY manquante. Ajoutez-la dans .env.")
        return ChatOpenAI(
            api_key=key, base_url="https://api.mistral.ai/v1", model=model, temperature=0,
        )

    if provider == "ollama_cloud":
        key   = os.environ.get("OLLAMA_API_KEY", "")
        model = os.environ.get("OLLAMA_MODEL", "llama3.1")
        if not key:
            raise RuntimeError("OLLAMA_API_KEY manquante. Ajoutez-la dans .env.")
        return ChatOpenAI(
            api_key=key, base_url="https://api.ollama.com/v1", model=model, temperature=0,
        )

    # Auto-détection : Anthropic > OpenAI > Ollama local
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(api_key=anthropic_key, model=model, temperature=0)
        except ImportError:
            pass  # langchain_anthropic non installé, continue

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(api_key=openai_key, model=model, temperature=0)

    if _ping_ollama_local():
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        return ChatOpenAI(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            model=model,
            temperature=0,
        )

    raise RuntimeError(
        "Aucun agent IA disponible.\n\n"
        "Options pour activer l'assistant :\n"
        "  • Anthropic (recommandé) : ANTHROPIC_API_KEY=sk-ant-... dans .env\n"
        "  • OpenAI : OPENAI_API_KEY=sk-... dans .env\n"
        "  • Ollama local (gratuit) : installer Ollama + ollama pull llama3\n\n"
        "Relancez le serveur après modification du .env."
    )


# ── Outils LangChain ─────────────────────────────────────────────────────────

def _make_tools(terrain_payload: dict):
    @tool
    def analyser_terrain_tool() -> str:
        """Analyse le terrain configuré et calcule toutes les surfaces en m²."""
        return json.dumps(analyser_terrain(terrain_payload), ensure_ascii=False)

    @tool
    def analyser_exposition_solaire_tool() -> str:
        """Calcule l'exposition solaire précise de chaque zone du jardin. Retourne % soleil/mi-ombre/ombre."""
        return json.dumps(analyser_exposition(terrain_payload), ensure_ascii=False)

    @tool
    def proposer_plantes_tool(sol: str, climat: str) -> str:
        """Propose un plan de plantation adapté. sol: drainant|normal|argileux|humide. climat: oceanique|continental|mediterraneen|montagnard."""
        return json.dumps(proposer_plantes(terrain_payload, sol, climat), ensure_ascii=False)

    @tool
    def generer_rapport_pdf_tool(nom_client: str, titre_projet: str, sol: str, climat: str) -> str:
        """Génère un rapport PDF professionnel avec toutes les analyses et recommandations."""
        global _pending_pdf
        surfaces   = analyser_terrain(terrain_payload)
        exposition = analyser_exposition(terrain_payload)
        plantation = proposer_plantes(terrain_payload, sol, climat)
        pdf_bytes  = generer_rapport(nom_client, titre_projet, surfaces, exposition, plantation)
        filename   = f"rapport_{nom_client.replace(' ', '_')}.pdf"
        _pending_pdf = (pdf_bytes, filename)
        return json.dumps({
            "success" : True,
            "fichier" : filename,
            "taille_ko": round(len(pdf_bytes) / 1024),
        }, ensure_ascii=False)

    return [
        analyser_terrain_tool,
        analyser_exposition_solaire_tool,
        proposer_plantes_tool,
        generer_rapport_pdf_tool,
    ]


# ── Prompt système expert (B7) ───────────────────────────────────────────────

def _build_system_prompt(terrain_payload: dict) -> str:
    """
    Construit le prompt système expert paysagiste.
    Inclut : données terrain, pourcentages d'exposition, course solaire, plantes.
    """
    parcelle = terrain_payload.get("parcelle", {})
    maisons  = terrain_payload.get("maisons", [])
    haies    = terrain_payload.get("haies_auto", [])
    synthese = terrain_payload.get("_synthese", {})
    nb_ext   = len(maisons) - 1 if maisons else 0
    batiments = f"1 maison{f' + {nb_ext} extension(s)' if nb_ext > 0 else ''}"

    # Exposition (si disponible dans synthèse enrichie)
    expo_block = ""
    if synthese:
        pct_soleil = synthese.get("pct_plein_soleil") or synthese.get("surf_jardin", "?")
        expo_block = f"""
Données d'exposition (dernière analyse) :
- Plein soleil (≥6h) : {synthese.get('pct_plein_soleil', 'non calculé')}
- Mi-ombre (3-6h) : {synthese.get('pct_mi_ombre', 'non calculé')}
- Ombre (<3h) : {synthese.get('pct_ombre', 'non calculé')}
- Surface jardin : {synthese.get('surf_jardin', '?')}
- Haies : {synthese.get('haies', '?')}
- Massifs : {synthese.get('massifs', '?')}
- Course solaire été : {synthese.get('soleil_ete', 'non calculé')}
- Course solaire hiver : {synthese.get('soleil_hiver', 'non calculé')}
"""

    return f"""Tu es un consultant paysagiste expert qui assiste un paysagiste professionnel.

Données du terrain en cours d'analyse :
- Parcelle : {parcelle.get('largeur','?')} m × {parcelle.get('hauteur','?')} m
- Bâtiments : {batiments}
- Haies configurées : {len(haies)} côté(s)
- Latitude : {terrain_payload.get('latitude','?')}° | Date de référence : {terrain_payload.get('date_ref','?')}
- Type de sol : {terrain_payload.get('sol') or 'non défini'}
- Climat : {terrain_payload.get('climat') or 'non défini'}
{expo_block}

Ton rôle :
1. Répondre naturellement comme un assistant conversationnel.
2. Répondre toujours en français.
3. Ne jamais répondre en anglais.
4. Ne pas lancer d’analyse technique si l’utilisateur dit seulement bonjour, salut, coucou, bonsoir ou hello.
5. Utiliser les outils uniquement si l’utilisateur demande clairement une analyse du terrain, de l’exposition solaire, des plantes, du relief ou un rapport.
6. Ne jamais inventer de chiffres ou de données.
7. Si une information manque, poser une question simple.
8. Répondre court, clair et utile.
9. Expliquer comme à un paysagiste ou un particulier, jamais comme à un développeur.
10. Toujours rester pratique et concret.

Règles importantes :
- Pour une salutation simple, réponds seulement avec une salutation et demande ce que l’utilisateur souhaite faire.
- Pour une question générale, réponds sans outil.
- Pour une demande d’analyse précise, utilise les outils adaptés.
- Ne commence jamais automatiquement par l’analyse d’exposition.
- Ne jamais afficher de code.
- Ne jamais parler de Python, JSON, pandas, API, DataFrame ou programmation.
- Ne jamais afficher des données techniques brutes.
- Après un outil, résume toujours le résultat en langage simple.
- Si l’utilisateur demande des plantes, commence par demander le type de sol et la région si l’information manque.
- Les réponses doivent être compréhensibles par une personne non technique.
"""

# ── Streaming agent ──────────────────────────────────────────────────────────
def _clean_response_for_user(text: str) -> str:
    forbidden = ["```", "import ", "pd.", "DataFrame", "print(", "python", "JSON", "code"]

    if any(word.lower() in text.lower() for word in forbidden):
        return (
            "Voici une proposition simple :\n\n"
            "Je peux vous aider à choisir des plantes adaptées à votre terrain. "
            "Pour faire une bonne recommandation, j’ai besoin de deux informations : "
            "le type de sol et le climat de votre région.\n\n"
            "Par exemple : sol normal, argileux, humide ou drainant ; "
            "climat océanique, continental, méditerranéen ou montagnard."
        )

    return text

def agent_stream(terrain_payload: dict, messages: list) -> Generator[dict, None, None]:
    """
    Générateur SSE multi-provider.
    Yields : text_delta, tool_start, tool_done, done, error.
    """

    # --- Bloquer les tools pour simples salutations ---
    last_user_message = ""

    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            last_user_message = m.get("content", "").strip().lower()
            break

    salutations = [
        "bonjour",
        "salut",
        "coucou",
        "bonsoir",
        "hello",
        "hey"
    ]

    if last_user_message in salutations:
        reply = (
            "Bonjour ! Je suis votre assistant d’aménagement paysager. "
            "Que souhaitez-vous faire aujourd’hui : analyser votre terrain, "
            "étudier l’ensoleillement, choisir des plantes ou préparer un plan ?"
        )

        updated_messages = list(messages)
        updated_messages.append({
            "role": "assistant",
            "content": reply
        })

        yield {"type": "text_delta", "text": reply}
        yield {
            "type": "done",
            "full_text": reply,
            "updated_messages": updated_messages
        }
        return

    tools = _make_tools(terrain_payload)
    tools_by_name = {t.name: t for t in tools}

    try:
        base_llm = _make_llm()
    except RuntimeError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    llm = base_llm.bind_tools(tools)

    # Construction de l'historique LangChain
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
        try:
            response = llm.invoke(lc_messages)

        except Exception as exc:
            err = str(exc)

            if "401" in err or "unauthorized" in err.lower() or "api_key" in err.lower():
                msg = (
                    "Clé API invalide ou expirée. "
                    "Vérifiez votre fichier .env (LLM_PROVIDER + clé correspondante)."
                )

            elif "connect" in err.lower() or "connection" in err.lower():
                provider = os.environ.get("LLM_PROVIDER", "ollama_cloud")

                if provider == "ollama_local":
                    msg = (
                        "Ollama non joignable. "
                        "Vérifiez qu’Ollama est lancé et qu’un modèle est installé."
                    )
                else:
                    msg = f"Connexion impossible au provider LLM ({provider}) : {err}"

            else:
                msg = f"Erreur LLM : {err}"

            yield {"type": "error", "message": msg}
            return

        lc_messages.append(response)

        if response.content:
            cleaned = _clean_response_for_user(response.content)
            full_text += cleaned
            yield {"type": "text_delta", "text": cleaned}

        if not response.tool_calls:
            break

        tool_results = []

        for tc in response.tool_calls:
            name = tc["name"]
            label = TOOL_LABELS.get(name, name)

            yield {
                "type": "tool_start",
                "name": name,
                "label": label
            }

            try:
                result = tools_by_name[name].invoke(tc["args"])

                yield {
                    "type": "tool_done",
                    "name": name,
                    "label": label,
                    "success": True
                }

                tool_results.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"]
                    )
                )

            except Exception as exc:
                yield {
                    "type": "tool_done",
                    "name": name,
                    "label": label,
                    "success": False,
                    "error": str(exc)
                }

                tool_results.append(
                    ToolMessage(
                        content=f"Erreur: {exc}",
                        tool_call_id=tc["id"]
                    )
                )

        lc_messages.extend(tool_results)

    updated_messages.append({
        "role": "assistant",
        "content": full_text
    })

    yield {
        "type": "done",
        "full_text": full_text,
        "updated_messages": updated_messages
    }