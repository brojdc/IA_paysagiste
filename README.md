# IA Paysagiste — Base de données plantes v7

Base de données végétale exploitée par l'agent IA paysagiste pour proposer des plantations adaptées à une parcelle, son exposition, son sol et ses contraintes climatiques.

## Source primaire
**Horticolor — Guide des Végétaux : Plantes Vivaces.**
Les pictogrammes du livre (soleil, mi-ombre, ombre, !!!) sont transcrits dans les colonnes `exposition_*` et `plante_peu_courante`.

## Périmètre actuel
- **245 plantes** transcrites
- **Pages 17 à 118** du livre couvertes
- L'encyclopédie complète couvre les pages 17 à 365 → la base est destinée à grandir.

## Architecture en tiers
La base distingue trois niveaux d'origine de la donnée pour rester traçable.

| Tier | Origine | Exemples |
|------|---------|----------|
| 1 | Donnée extraite directement du livre | exposition, sol, hauteur, floraison, usage |
| 2 | Donnée dérivée par calcul | binarisations couleur, palette_couleur |
| 3 | Donnée enrichie depuis source externe | rusticite_min_C, feuillage_type, toxicité |

L'agent IA peut connaître son niveau de confiance grâce à la colonne `niveau_donnees` :
- `coquille` : seuls nom et famille renseignés (à compléter)
- `livre_partiel` : transcription incomplète mais utilisable pour certains filtres
- `livre_complet` : Tier 1+2 complets, utilisable pour toutes recommandations dans la zone du livre
- `enrichi` : Tier 3 ajouté, pleinement utilisable hors zone géographique d'origine

## Convention d'encodage des binaires
- `1` = compatible / présent (picto coché ou caractéristique présente)
- `0` = non compatible / absent (l'info est documentée comme négative ou non cochée)
- `vide / null` = non documenté (uniquement pour les entrées `coquille`)

Cette distinction est importante : pour les entrées `livre_complet`, l'absence de coche signifie "non" (close-world). Pour les `coquille`, l'absence signifie "inconnu" (open-world) et l'agent doit exclure ces lignes par défaut.

## Fichiers

### `data/`
- `plantes.csv` : base principale, 245 lignes, 64 colonnes
- `plantes.json` : version JSON pour agent IA (typage propre : ints pour binaires, null pour inconnu)
- `audit.csv` : rapport ligne-à-ligne des incohérences détectées (à corriger en continu)
- `index_genres.csv` : nombre d'entrées par genre botanique
- `resume_couleurs.csv` : nombre d'entrées par couleur binarisée
- `suivi_integration.csv` : historique des versions
- `communes.csv` : données géographiques (inchangé depuis v6)

### `docs/`
- `dictionnaire_champs.csv` : définition de chaque colonne avec son tier
- `contexte_projet_et_prompt.md` : contexte du projet IA
- `migration_v6_v7.md` : journal des changements depuis v6

## Roadmap suggérée

1. **Court terme** : corriger les 80 alertes du fichier `audit.csv` (les 24 entrées partielles à compléter, surtout).
2. **Moyen terme** : enrichir progressivement les colonnes Tier 3 (`rusticite_min_C`, `feuillage_type`) en commençant par les plantes les plus utilisées.
3. **Long terme** : transcrire les pages 119+ du livre Horticolor pour étendre le périmètre, et envisager d'autres sources (graminées, arbustes, plantes aquatiques) selon l'usage de l'IA.

## Notes de validation
- Aucune donnée n'a été inventée. Les colonnes Tier 3 vides doivent être remplies depuis une source externe documentée (Tela Botanica, RHS, Plantes & Jardins…).
- La colonne `source_enrichissement` doit être renseignée à chaque enrichissement Tier 3.
