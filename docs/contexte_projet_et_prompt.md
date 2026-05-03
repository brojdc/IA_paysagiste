# Contexte projet IA Paysagiste

Tu construis une IA paysagiste capable de proposer des plantations adaptées à une parcelle.

## Objectif
Créer une base de données végétale exploitable par un agent IA pour :
- filtrer les plantes par exposition : soleil, mi-ombre, ombre ;
- filtrer par type de sol : sec, frais, humide, drainé, calcaire, acide, riche, pauvre ;
- composer des massifs selon les hauteurs, largeurs, usages et couleurs ;
- proposer une palette de couleurs cohérente ;
- justifier les choix de plantation ;
- éviter les incohérences entre plante, sol, exposition et humidité.

## Icônes du livre
- soleil = exposition_soleil
- soleil + nuage = exposition_mi_ombre
- nuage = exposition_ombre
- !!! = plante_peu_courante

## Suivi actuel
- Total avant dernier lot : 187
- Entrées ajoutées dans le dernier lot : 58
- Total actuel : 245

## Règle de fiabilité
Les champs absents ou incertains doivent rester vides ou être marqués à vérifier.
Il ne faut pas inventer de caractéristiques non visibles.
