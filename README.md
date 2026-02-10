# IA Paysagiste – Prototype V1

## Objectif

Ce projet est un prototype d’outil d’analyse de surfaces pour un chantier paysager.

Il permet de :

* saisir les dimensions d’une parcelle, d’une maison et d’une terrasse
* prendre en compte des trous ou massifs dans la terrasse
* calculer automatiquement les surfaces utiles
* afficher les résultats via une interface web simple

---

## Architecture du projet

```
IA_paysagiste/
│
├── api/
│   └── main.py          → API FastAPI (moteur de calcul)
│
├── core/
│   └── geometry.py      → Fonctions mathématiques (aires, polygones, cercles)
│
├── ui/
│   └── formulaire.py    → Interface utilisateur Streamlit
│
├── scripts/
│   └── dijkstra_demo.py → Prototype d’algorithme de chemin le plus court
│
├── run_api.py           → Lance l’API
├── run_ui.py            → Lance l’interface
└── requirements.txt
```

---

## Rôle des composants

### Backend – API FastAPI

Le fichier `api/main.py` :

* reçoit les données du formulaire
* effectue les calculs de surfaces
* renvoie un résultat JSON

C’est le **moteur logique** du projet.

---

### Frontend – Interface Streamlit

Le fichier `ui/formulaire.py` :

* affiche un formulaire de saisie
* envoie les données à l’API
* affiche les résultats

C’est la **partie visible par l’utilisateur**.

---

### Logique mathématique

Le fichier `core/geometry.py` :

* contient les fonctions de calcul d’aire
* est utilisé directement par l’API
* constitue la **base métier du projet**

---

### Recherche algorithmique

Le fichier `scripts/dijkstra_demo.py` :

* implémente l’algorithme de Dijkstra
* n’est pas encore utilisé dans l’application
* servira plus tard pour :

  * circulation dans un jardin
  * optimisation de trajets
  * robot tondeuse
  * irrigation intelligente

C’est la partie **R&D vers une future IA paysagiste**.

---

## Lancement du projet

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Lancer l’API

```bash
python run_api.py
```

Documentation disponible sur :

```
http://127.0.0.1:8000/docs
```

### 3. Lancer l’interface utilisateur

```bash
python run_ui.py
```

Interface disponible sur :

```
http://localhost:8502
```

---

## État actuel

Version V1 :

* calcul des surfaces fonctionnel
* API opérationnelle
* interface simple utilisable

---

## Prochaines étapes

* géolocalisation du terrain
* calcul d’ensoleillement
* recommandation de plantes
* optimisation de circulation (algorithmes de graphe)
* intégration d’intelligence artificielle

---

## Vision

Construire un **assistant IA pour les paysagistes** capable de :

* analyser automatiquement un terrain
* proposer des aménagements optimisés
* générer des plans et devis

---

Projet en cours de développement.
