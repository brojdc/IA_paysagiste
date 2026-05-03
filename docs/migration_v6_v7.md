# Migration v6 → v7

## Objectif
Préparer la base pour une exploitation propre par l'agent IA paysagiste, et la rendre extensible à d'autres régions que le Nord de la France.

## Changements structurels

### 1. Architecture en tiers (nouveau)
Trois niveaux de provenance de donnée distingués via la nouvelle colonne `niveau_donnees` :
- `coquille` : 1 entrée (Actaea rubra, ID 14) — seuls nom et famille
- `livre_partiel` : 24 entrées avec transcription incomplète
- `livre_complet` : 220 entrées exploitables

### 2. Nouvelles colonnes Tier 3
Pour permettre des recommandations dans d'autres zones climatiques :
- `rusticite_min_C` : température minimum supportée
- `zone_rusticite` : zone USDA/européenne
- `feuillage_type` : persistant / semi_persistant / caduc
- `distance_plantation_cm` : distance entre plants
- `toxicite` : oui/non
- `attire_pollinisateurs` : 0/1
- `source_enrichissement` : traçabilité de l'enrichissement

### 3. Pré-remplissage prudent du Tier 3
Aucune extrapolation. Pré-remplissage uniquement sur preuve textuelle :
- Rusticité = -5 °C pour les plantes mentionnant "climat doux" ou "peu rustique" dans `remarques` ou `categorie` (4 entrées)
- Feuillage caduc pour les catégories "vivace bulbeuse" et "vivace tubéreuse" (9 entrées)
- Tout le reste reste vide → à enrichir depuis sources externes (Tela Botanica, RHS, Plantes & Jardins).

### 4. Convention d'encodage clarifiée
**Avant (v6)** : `0`, `1` et `vide` se mélangeaient sur les binaires sans convention claire.
**Maintenant (v7)** :
- Pour les lignes `livre_complet` et `livre_partiel` : tous les NaN ont été convertis en `0` (l'auteur a transcrit activement, donc l'absence de coche signifie "non").
- Pour les `coquille` : NaN est conservé (l'auteur n'a pas encore traité l'entrée → "inconnu").

### 5. JSON retypé
**Avant** : tous les champs étaient des strings (`"1"`, `"100"`).
**Maintenant** :
- Binaires et mesures : `int`
- Champs textuels : `string`
- Manquants : `null`

### 6. Audit automatique (nouveau)
Le fichier `data/audit.csv` liste 81 alertes ligne-à-ligne :
- 1 INFO (entrée coquille à compléter)
- 80 AVERTISSEMENTs (manques d'usage / sol pour les `livre_partiel`, plus quelques incohérences)

## Détection automatique d'erreurs
L'audit catch déjà des cas concrets, exemple : Actaea rubra (ID 14) a été marquée 0/0/0 sur les expositions dans la v6, alors que la fiche du livre montre des pictos. Ce genre d'erreur est désormais visible automatiquement.

## Nombre d'entrées par catégorie (inchangé)
- 245 lignes au total
- Distribution couleurs identique à la v6 (sanity check passé)
- Genres et lots d'intégration préservés

## Ce qui n'a pas changé
- Le contenu des fiches transcrites lots 1-5 et lot 6 (sauf conversion NaN→0 pour les binaires)
- Les IDs (1 à 245)
- `communes.csv` (non touché par cette migration)

## Prochaines étapes recommandées
1. Reprendre le livre pour les 24 entrées `livre_partiel` (Actaea pachypoda à Ajuga reptans principalement)
2. Vérifier les 58 entrées `à_vérifier_depuis_photo` du lot 6
3. Enrichir progressivement les colonnes Tier 3
4. Continuer la transcription pages 119+ du livre Horticolor
