from typing import List, Tuple

# Un point (x, y) dans le plan (mètres)
Point = Tuple[float, float]

def rect_to_poly(x: float, y: float, w: float, h: float) -> List[Point]:
    """
    Convertit un rectangle défini par son coin sud-ouest (x, y),
    sa largeur (w) et sa hauteur (h) en une liste de 4 points (polygone).
    """
    return [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h)
    ]

def poly_area(poly: List[Point]) -> float:
    """
    Calcule l'aire d'un polygone à partir de ses sommets.
    (Méthode du "shoelace" ou 'formule de la chaussure')
    """
    x = [p[0] for p in poly]
    y = [p[1] for p in poly]
    n = len(poly)
    s = 0.0
    for i in range(n):
        j = (i + 1) % n
        s += x[i] * y[j] - x[j] * y[i]
    return abs(s) / 2.0

def circle_area(r: float) -> float:
    """
    Calcule l'aire d'un cercle à partir de son rayon (r en mètres).
    """
    import math
    return math.pi * r * r