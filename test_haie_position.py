#!/usr/bin/env python3
# Test script for haie positioning

from core.schemas import TerrainInput, Rectangle2D, HaieAuto, Maison
from core.services import generate_obstacles_from_haies_auto

# Terrain de test
parcelle = Rectangle2D(origine=(0, 0), largeur=100, hauteur=100)
terrasse = Rectangle2D(origine=(50, 50), largeur=10, hauteur=10)
maison = Maison(origine=(30, 30), largeur=20, hauteur=20)

# Haies test
haies = [HaieAuto(cote="nord", hauteur=2.5, epaisseur=0.5)]

# Test 1: Lisière
t1 = TerrainInput(
    parcelle=parcelle, 
    terrasse=terrasse, 
    maison=maison,
    haies_auto=haies,
    haie_position="À la lisière de la parcelle (recommandé)"
)
obs1 = generate_obstacles_from_haies_auto(t1)
print("Mode LISIÈRE:")
print(f"  Obstacle: a={obs1[0]['a']}, b={obs1[0]['b']}")

# Test 2: Maison
t2 = TerrainInput(
    parcelle=parcelle,
    terrasse=terrasse,
    maison=maison, 
    haies_auto=haies,
    haie_position="Autour de la maison"
)
obs2 = generate_obstacles_from_haies_auto(t2)
print("\nMode MAISON:")
print(f"  Obstacle: a={obs2[0]['a']}, b={obs2[0]['b']}")

print("\nExpected:")
print("  LISIÈRE nord: a=(0, 100), b=(100, 100)")
print("  MAISON nord: a=(30, 50), b=(50, 50)")
