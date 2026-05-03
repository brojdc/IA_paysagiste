# Plan de nettoyage — Audit repo IA Paysagiste
> Généré le 2026-05-03 — lecture seule, aucune modification effectuée.  
> Attente de validation explicite avant toute action.

---

## 1. Fichiers SUPPRIMÉS non commités — analyse

### `.env.example` (supprimé depuis HEAD `38d0c50`)

**Contenu dans HEAD :** template de configuration multi-provider (Ollama, OpenAI, Anthropic, Mistral).  
Aucun secret : toutes les clés sont vides (`ANTHROPIC_API_KEY=`, `OPENAI_API_KEY=`, etc.).  
Les noms de providers (`anthropic`, `claude-haiku-4-5-20251001`) sont des références **techniques fonctionnelles**, pas des attributions d'IA.

**Verdict :** Suppression probablement **accidentelle** (le fichier est utile pour l'onboarding).  
**Recommandation :** Restaurer (`git restore .env.example`) et committer avec la migration v7.  
Seule modification à envisager : renommer `ANTHROPIC_MODEL` en gardant juste le nom du modèle (choix de neutralité, non obligatoire).

---

### `agent/agent.py` (supprimé depuis HEAD `38d0c50`)

**Contenu dans HEAD :** agent Anthropic natif (SDK `anthropic`, tool use, streaming).  
Utilise `anthropic.Anthropic()` directement. C'est la version single-provider.

**Remplacé par :** `agent/agent_libre.py` (multi-provider : Ollama, OpenAI, Anthropic, Mistral via LangChain).

**Verdict :** Suppression **volontaire et cohérente** — `agent_libre.py` couvre tout ce que faisait `agent.py` et plus.  
Pas de code critique perdu : toute la logique métier des tools est dans `agent/tools.py` (non supprimé).  
**Recommandation :** Confirmer la suppression. Committer `git rm agent/agent.py`.

**Note traces d'IA :** `agent.py` importait `anthropic` et instanciait `anthropic.Anthropic()`.
Ces lignes disparaissent avec le fichier — bonne chose pour l'objectif 2.

---

### `agent/agent_openai.py` (supprimé depuis HEAD `38d0c50`)

**Contenu dans HEAD :** agent OpenAI/LangChain (`ChatOpenAI`), fallback si ni Ollama ni Anthropic.  
Commentaire en tête : *"Ce module sert de fallback si aucune clé OLLAMA_API_KEY ni ANTHROPIC_API_KEY n'est disponible mais qu'une clé OPENAI_API_KEY est définie."*

**Remplacé par :** `agent/agent_libre.py` (contient exactement cette logique de fallback en auto-détection).

**Verdict :** Suppression **volontaire et cohérente**.  
**Recommandation :** Confirmer la suppression. Committer `git rm agent/agent_openai.py`.

---

### `test_haie_position.py` (supprimé, dernier commit : `7ead751`)

**Contenu dans HEAD :** script de test de positionnement de haies — teste `generate_obstacles_from_haies_auto()` avec des cas mode LISIÈRE et mode MAISON.  
Script standalone, à la racine, avec des valeurs en dur.

**Verdict :** Suppression **volontaire**. Ce script était un outil de debug de développement, pas un test pérenne.  
La fonctionnalité testée est dans `core/services.py` et couverte opérationnellement.  
**Recommandation :** Confirmer la suppression. Si tu veux conserver ce test, le déplacer d'abord dans `test/` et le convertir en test pytest — mais ce n'est pas une priorité.

---

### `ui/formulaire.py` (supprimé depuis HEAD `38d0c50`)

**Contenu dans HEAD :** interface Streamlit complète (~600+ lignes) avec formulaire de terrain, visualisation 2D, recommandation de plantes, hero banner, CSS custom.  
**Remplacé par :** `frontend/index.html` + `frontend/css/` + `frontend/js/` (interface HTML/JS pure, ~38 Ko, créée dans les commits récents).

**Verdict :** Suppression **volontaire** — migration Streamlit → frontend web statique.  
**Recommandation :** Confirmer la suppression. Committer `git rm ui/formulaire.py`.

**Note :** Le dossier `ui/` devient vide après cette suppression → à supprimer aussi.

---

## 2. Fichiers MODIFIÉS — diffs résumés

### `.claude/settings.local.json`

**Changement :** Remplacement des permissions Claude Code de développement (pip, python, node) par des permissions d'exploration PowerShell (Get-ChildItem sur Downloads et Bureau).  
**Ce fichier n'a rien à faire dans le repo.** C'est la configuration locale de l'outil Claude Code.  
**Verdict :** Ne pas committer. Ajouter `.claude/` au `.gitignore` (voir section 4).

---

### `README.md`

**Changement :** Réécriture complète. L'ancien README (178 lignes) décrivait l'architecture globale du projet (FastAPI+Streamlit, roadmap SaaS). Le nouveau README (60 lignes) documente exclusivement la **base de données plantes v7** (structure, tiers de données, fichiers, roadmap de complétion).

**Verdict :** Le nouveau README est pertinent pour la migration v7 et sera dans le commit. Cependant le projet n'a plus de README de présentation globale après la migration vers le frontend HTML. À décider : créer un second README global, ou accepter ce README centré données.

**Note :** Le nouveau README contient `"l'agent IA paysagiste"` — c'est le **nom du produit**, pas une attribution à Claude/ChatGPT.

---

### `core/pdf_export.py`

**Changement :** Bug fix — la terrasse est rendue optionnelle dans `_terrain_figure()` (guard `if terrain.terrasse is not None:`), et deux validations d'entrée sont ajoutées au début de `generate_pdf_report()` (terrain None et parcelle None).  
Ligne 223 conservée : `"Généré par IA Paysagiste — SaaS B2B"` — c'est le **nom du produit** dans le PDF, pas une attribution.

**Verdict :** Modification **légitime** à committer. Aucune trace d'IA attribution.

---

### `data/plantes.csv`

**Changement :**  
- **Avant (v6) :** 65 lignes, 25 colonnes, schéma simple (`nom, type, exposition, sol, climat, ...`)  
- **Après (v7) :** 246 lignes (245 plantes + header), 64 colonnes, schéma structuré par tiers (Tier 1/2/3), avec colonnes binarisées, `niveau_donnees`, `source_page`, `lot_integration`

**Ce n'est PAS un retour en arrière. C'est la migration v7 complète.**  
**Verdict :** À committer immédiatement. Fichier central de la migration.

---

## 3. Fichiers NON TRACKÉS — confirmation

Tous les fichiers suivants sont des **artefacts de la migration v7** à intégrer dans le repo :

| Fichier | Lignes | Statut |
|---------|--------|--------|
| `data/plantes.json` | 16 170 | Version JSON pour l'agent — à committer |
| `data/audit.csv` | 82 | Rapport d'incohérences v7 — à committer |
| `data/index_genres.csv` | 102 | Index par genre botanique — à committer |
| `data/resume_couleurs.csv` | 12 | Résumé par couleur binarisée — à committer |
| `data/suivi_integration.csv` | 4 | Historique des lots — à committer |
| `docs/migration_v6_v7.md` | — | Journal de migration — à committer |
| `docs/dictionnaire_champs.csv` | — | Définition des 64 colonnes avec tier — à committer |
| `docs/contexte_projet_et_prompt.md` | — | Contexte du projet — à committer |

**Note sur `docs/contexte_projet_et_prompt.md` :** Le titre contient "prompt" — à vérifier le contenu avant de committer (voir section Traces d'IA). L'aperçu montre : *"Tu construis une IA paysagiste capable..."* — c'est du contexte projet, pas un prompt système exposé. OK à committer tel quel, ou à renommer `docs/contexte_projet.md` si le mot "prompt" te dérange.

---

## 4. Parasites confirmés — à supprimer

### `.json/`
**Contenu :** `settings.local.json` avec permissions Claude Code (pip, python, node).  
**Origine :** Copie accidentelle du dossier `.claude/` avec un nom erroné.  
**Verdict :** Trace d'IA directe. À supprimer entièrement. Ne jamais committer.

### `backup_v6/`
**Contenu :** `data/plantes.csv` (v6, 65 plantes) + `data/communes.csv` + `docs/` (vide).  
**Taille :** 24 Ko.  
**Verdict :** Backup local créé avant la migration v7. La v6 est dans l'historique Git si besoin de récupération. À supprimer. Ne jamais committer.

### `debug_scroll.js`
**Contenu :** 69 lignes — script DevTools de debug pour inspecter le scroll de la sidebar dans le frontend HTML. Commentaire en tête : *"// debug_scroll.js — À coller dans la console DevTools (F12)"*.  
**Verdict :** Outil de debug oublié à la racine. À supprimer. Ne jamais committer.

---

## 5. Occurrences textuelles "IA / AI / Claude / Anthropic"

### Dans le code fonctionnel (références techniques — PAS des attributions)

| Fichier | Lignes | Nature |
|---------|--------|--------|
| `agent/agent_libre.py` | 3, 45-46, 62-112, 122-123 | Noms de providers LLM (`anthropic`, `openai`, modèles). Code fonctionnel indissociable. |
| `api/main.py` | 414, 437-513, 523-524 | Même : configuration multi-provider, messages d'erreur utilisateur mentionnant les providers. |
| `core/pdf_export.py:223` | 1 ligne | `"Généré par IA Paysagiste — SaaS B2B"` — **nom du produit** dans le PDF. |
| `docs/contexte_projet_et_prompt.md` | — | Contexte projet écrit à la 2e personne. Aucune mention de Claude/ChatGPT. |

**Conclusion code :** Aucune attribution du type "code généré par Claude" ou "Co-authored by ChatGPT" dans les fichiers de code. Les mentions d'Anthropic/OpenAI sont des intégrations API indissociables du produit.

### Dans les commits Git (traces réelles d'IA)

| Commit | Message | Trace |
|--------|---------|-------|
| `640ccc9` | fix(bug2+bug3): scroll sidebar + simulation toggle propre | **Co-Authored-By: Claude Sonnet 4.6 \<noreply@anthropic.com\>** |
| `7bf9228` | fix(bug3): simulation solaire toggle correct, auto-stop | **Co-Authored-By: Claude Sonnet 4.6 \<noreply@anthropic.com\>** |
| `1852ec8` | fix(bug2): sidebar scrollable avec boutons CTA fixes en bas | **Co-Authored-By: Claude Sonnet 4.6 \<noreply@anthropic.com\>** |
| `d0d3ddc` | Feat: first working AI landscape prototype | "AI" = description produit, acceptable |

**⚠️ Réécriture de l'historique Git :** Ces 3 commits sont les commits les plus récents de `main` (HEAD, HEAD~1, HEAD~2), et la branche est **4 commits en avance sur `origin/main`**. La réécriture par `git rebase -i` suivi d'un `git push --force` est techniquement faisable et **relativement peu risquée** car ces commits ne sont pas sur le remote. Mais je n'effectue rien sans ton accord explicite.

---

## 6. Patch `.gitignore` proposé

**`.gitignore` actuel :**
```
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
env/
.env
.env/
```

**Entrées manquantes :**

```gitignore
# Outils de développement IA (traces à exclure du repo)
.claude/
.json/

# Backups locaux
backup_*/

# Fichiers de debug
debug_*.js
*.tmp
*.bak

# Archives
*.zip

# Éditeurs
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Cache Python (déjà en partie présent, compléter)
*.pyd
```

**Note :** `api/__pycache__/main.cpython-311.pyc` est **déjà tracké** dans Git (il apparaît comme "modified" dans git status). Il faut le retirer avec `git rm --cached api/__pycache__/main.cpython-311.pyc` après avoir mis à jour le .gitignore.

---

## 7. Tableau des catégories A / B / C / D

### Racine

| Élément | Catégorie | Justification |
|---------|-----------|---------------|
| `run_api.py` | **A** | Point d'entrée API, 8 lignes, fonctionnel |
| `requirements.txt` | **A** | Dépendances projet |
| `.gitignore` | **A** | À conserver, patch à appliquer |
| `.env` | **A** | Secrets locaux, jamais commité ✓ |
| `README.md` (modifié) | **A** | À committer (doc v7), voir note section 2 |
| `debug_scroll.js` | **B** | Debug DevTools oublié, aucune valeur |
| `.claude/` | **B** | Config outil Claude Code, trace d'IA, hors repo |
| `.json/` | **B** | Copie accidentelle de `.claude/`, trace d'IA |
| `backup_v6/` | **B** | Backup local de la v6, historique Git suffit |

### Dossiers de code

| Élément | Catégorie | Justification |
|---------|-----------|---------------|
| `agent/` | **A** | Contient `agent_libre.py`, `tools.py`, `rapport.py` — code métier actif |
| `api/` | **A** | Backend FastAPI actif |
| `core/` | **A** | Moteur de calcul (géométrie, services, PDF, schémas) |
| `frontend/` | **A** | Nouveau frontend HTML/CSS/JS |
| `scripts/` | **A** | `dijkstra_demo.py` (R&D), `patch_compute_exposition_precise.py` |
| `data/` | **A** | Base plantes v7 + communes + fichiers audit |
| `docs/` | **A** | Documentation migration v7 |
| `.streamlit/` | **A** | Config Streamlit (si encore utilisée) |
| `ui/` | **B** | Vide après suppression de `formulaire.py` |
| `api/__pycache__/` | **B** | Cache Python compilé — à retirer du tracking |

### Fichiers supprimés (non commités)

| Élément | Catégorie | Recommandation |
|---------|-----------|----------------|
| `.env.example` | **A** | Restaurer — utile, suppression accidentelle |
| `agent/agent.py` | **B** | Confirmer suppression — remplacé par `agent_libre.py` |
| `agent/agent_openai.py` | **B** | Confirmer suppression — remplacé par `agent_libre.py` |
| `test_haie_position.py` | **B** | Confirmer suppression — script de debug dev |
| `ui/formulaire.py` | **B** | Confirmer suppression — remplacé par `frontend/` |

### Renommages suggérés (catégorie C)

| Élément | Renommage proposé | Raison |
|---------|-------------------|--------|
| `docs/contexte_projet_et_prompt.md` | `docs/contexte_projet.md` | "prompt" dans le nom est ambigu |

---

## 8. Structure finale proposée

```
IA_paysagiste/                     (ou à renommer : paysagiste-studio, jardindecision, etc.)
│
├── agent/
│   ├── __init__.py
│   ├── agent_libre.py             ← agent multi-provider (Ollama/OpenAI/Anthropic/Mistral)
│   ├── tools.py                   ← outils de l'agent
│   └── rapport.py                 ← génération de rapport texte
│
├── api/
│   └── main.py                    ← API FastAPI
│
├── core/
│   ├── geometry.py
│   ├── pdf_export.py
│   ├── schemas.py
│   └── services.py
│
├── data/
│   ├── plantes.csv                ← base v7 principale (245 plantes, 64 colonnes)
│   ├── plantes.json               ← version JSON pour agent
│   ├── communes.csv               ← données géographiques
│   ├── audit.csv                  ← rapport incohérences v7
│   ├── index_genres.csv
│   ├── resume_couleurs.csv
│   └── suivi_integration.csv
│
├── docs/
│   ├── dictionnaire_champs.csv
│   ├── migration_v6_v7.md
│   └── contexte_projet.md         ← (renommé depuis contexte_projet_et_prompt.md)
│
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
│
├── scripts/
│   ├── dijkstra_demo.py
│   ├── patch_compute_exposition_precise.py
│   └── cleanup_plan.md            ← ce fichier
│
├── .env                           ← non commité (✓)
├── .env.example                   ← template (à restaurer)
├── .gitignore                     ← patché
├── README.md
├── requirements.txt
└── run_api.py
```

---

## 9. Plan de commit unique

### Étape 0 — Nettoyage des parasites (local uniquement, pas de commit)
```powershell
# Supprimer les fichiers parasites du disque
Remove-Item -Recurse -Force ".json"
Remove-Item -Recurse -Force "backup_v6"
Remove-Item -Force "debug_scroll.js"
# Supprimer le dossier ui/ vide (après confirmation de formulaire.py)
Remove-Item -Recurse -Force "ui"
```

### Étape 1 — Retirer __pycache__ du tracking Git
```bash
git rm --cached api/__pycache__/main.cpython-311.pyc
```

### Étape 2 — Mettre à jour .gitignore
```bash
# Éditer .gitignore selon le patch section 6
git add .gitignore
```

### Étape 3 — Restaurer .env.example (si validé)
```bash
git restore .env.example
git add .env.example
```

### Étape 4 — Confirmer les suppressions volontaires
```bash
git rm agent/agent.py
git rm agent/agent_openai.py
git rm test_haie_position.py
git rm ui/formulaire.py
```

### Étape 5 — Stager la migration v7 et les correctifs métier
```bash
git add data/plantes.csv
git add data/plantes.json
git add data/audit.csv
git add data/index_genres.csv
git add data/resume_couleurs.csv
git add data/suivi_integration.csv
git add docs/
git add core/pdf_export.py
git add README.md
git add scripts/cleanup_plan.md
```

### Étape 6 — Créer le commit
```bash
git commit -m "feat(data): migration base plantes v6→v7 — 245 espèces, 64 colonnes structurées par tiers

- data/plantes.csv : restructuration complète (25 → 64 colonnes, 65 → 245 plantes)
- data/plantes.json : version JSON pour exploitation par l'agent
- data/audit.csv, index_genres.csv, resume_couleurs.csv, suivi_integration.csv : fichiers de qualité v7
- docs/ : dictionnaire des champs, journal de migration, contexte projet
- core/pdf_export.py : terrasse rendue optionnelle (bug fix)
- agent/ : consolidation multi-provider dans agent_libre.py, suppression des agents single-provider
- .gitignore : exclusion de .claude/, backup_*/, debug_*.js, caches"
```

### Étape 7 (optionnel) — Supprimer les Co-Authored-By de l'historique
> **Requiert ton accord explicite.** Ces 3 commits ne sont pas encore sur le remote (`origin/main`).
> 
> ```bash
> git rebase -i HEAD~7   # ouvrir l'éditeur pour les 3 commits concernés
> # Pour chaque commit 640ccc9, 7bf9228, 1852ec8 :
> # changer "pick" en "reword" → retirer la ligne Co-Authored-By du message
> git push --force-with-lease origin main
> ```
> 
> **Risque :** faible (commits non publiés). **Bénéfice :** supprime toute trace d'IA dans l'historique public.

---

## 10. Décisions en attente de ta validation

| # | Question | Options |
|---|----------|---------|
| 1 | `.env.example` : restaurer ou supprimer définitivement ? | Restaurer (recommandé) / Supprimer |
| 2 | `docs/contexte_projet_et_prompt.md` : renommer ? | Renommer en `contexte_projet.md` / Garder tel quel |
| 3 | Co-Authored-By dans les 3 commits : réécrire l'historique ? | Oui, réécrire + force-push / Laisser tel quel |
| 4 | `core/pdf_export.py:223` `"Généré par IA Paysagiste"` : modifier ? | Garder (nom produit) / Remplacer par ex. `"Généré par Paysagiste Pro"` |
| 5 | README.md : conserver comme doc v7 seule, ou ajouter une section projet global ? | Conserver tel quel / Ajouter section projet |
