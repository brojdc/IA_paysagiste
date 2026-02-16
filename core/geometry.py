from typing import List, Tuple
import math

Point = Tuple[float, float]


def rect_to_poly(x: float, y: float, w: float, h: float) -> List[Point]:
    return [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
    ]


def poly_area(poly: List[Point]) -> float:
    x = [p[0] for p in poly]
    y = [p[1] for p in poly]
    n = len(poly)
    s = 0.0
    for i in range(n):
        j = (i + 1) % n
        s += x[i] * y[j] - x[j] * y[i]
    return abs(s) / 2.0


def circle_area(r: float) -> float:
    return math.pi * r * r
