# IA Paysagiste – Prototype V1

## Objectif du projet

**IA Paysagiste** est un prototype d’outil d’aide à la conception de jardins.

L’application permet de :

* modéliser un terrain (parcelle, maison, terrasse, massifs)
* calculer automatiquement les surfaces utiles
* simuler l’ensoleillement réel du jardin 
* recommander des plantes adaptées :

  * à l’exposition solaire
  * au type de sol
  * au climat
* proposer automatiquement un **plan de plantation en 2D**

Ce projet constitue la base d’un futur **assistant IA pour paysagistes**.

---

## Architecture du projet

```
IA_paysagiste/
│
├── api/
│   └── main.py              → API FastAPI (logique métier)
│
├── core/
│   ├── geometry.py          → Calculs géométriques (aires, polygones…)
│   ├── schemas.py           → Modèles de données (Pydantic)
│   └── services.py          → Algorithmes :
│                             - surfaces
│                             - plan 2D
│                             - exposition solaire
│                             - filtrage plantes
│                             - proposition de plantation
│
├── data/
│   └── plantes.csv          → Catalogue de plantes
│
├── ui/
│   └── formulaire.py        → Interface Streamlit
│
├── scripts/
│   └── dijkstra_demo.py     → Prototype d’algorithme de graphe (R&D)
│
├── run_api.py               → Lance l’API
├── run_ui.py                → Lance l’interface
└── requirements.txt
```

---

## Fonctionnalités actuelles

### Backend (FastAPI)

* Calcul des **surfaces en m²**
* Génération d’un **plan 2D**
* Simulation d’**exposition solaire** :

  * version simplifiée
  * version réelle basée sur **pvlib**
* Filtrage de plantes selon :

  * exposition
  * sol
  * climat
* **Algorithme de placement automatique** des plantes

Constitue un **moteur IA paysagiste prototype**.

---

### Frontend (Streamlit)

* Formulaire complet de chantier
* Visualisation :

  * plan 2D
  * carte d’ensoleillement
* Recommandation de plantes catalogue

Fournit une **démo interactive utilisable**.

---

## Lancement du projet

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Lancer l’API

```bash
python run_api.py
```

Documentation :

```
http://127.0.0.1:8000/docs
```

---

### 3. Lancer l’interface

```bash
python run_ui.py
```

Interface :

```
http://localhost:8501
```

---

## État actuel

**Prototype technique avancé** :

* moteur de calcul fonctionnel
* simulation solaire réelle
* recommandation de plantes
* plan de plantation automatique
* interface de démonstration

Niveau : **MVP technique IA paysagiste**

---

## Roadmap

### Court terme

* affichage des plantes sur le plan 2D
* résumé intelligent du jardin
* amélioration UX de l’interface

### Moyen terme

* import de plans réels / cadastre
* gestion de zones (pelouse, massif, potager…)
* génération de dossier PDF client

### Long terme

* optimisation automatique du jardin
* apprentissage sur projets réels
* transformation en **SaaS pour paysagistes**

---

## Vision

Créer un **assistant IA métier** capable de :

* analyser automatiquement un terrain
* proposer des aménagements optimisés
* générer plans, listes de plantes et devis
* faire gagner du temps aux paysagistes

Objectif final : **produit SaaS IA pour le paysage**.

---

## Statut

Projet en cours de développement — Prototype V1.
