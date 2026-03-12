# -*- coding: utf-8 -*-
# core/terrain_relief.py
"""
Modèle de relief du terrain.
Permet de simuler des pentes qui modifient l'exposition solaire.
"""
import math
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class TerrainSlope:
    """Représente une pente du terrain."""
    orientation_deg: float  # Orientation de la pente (0=nord, 90=est, 180=sud, 270=ouest)
    steepness_percent: float  # Pente en pourcentage (0-100%)
    
    def get_slope_angle_rad(self) -> float:
        """Retourne l'angle de la pente en radians."""
        # Conversion : pourcentage -> angle
        # steepness = tan(angle) * 100
        angle_deg = math.degrees(math.atan(self.steepness_percent / 100.0))
        return math.radians(angle_deg)
    
    def get_effective_sun_altitude(self, actual_altitude_deg: float) -> float:
        """
        Calcule l'altitude effective du soleil en tenant compte de la pente du terrain.
        
        Une pente orientée vers le south reçoit plus de soleil (altitude augmente).
        Une pente orientée vers le nord reçoit moins de soleil (altitude diminue).
        """
        slope_angle = self.get_slope_angle_rad()
        
        # Pour une pente, l'angle effectif du soleil dépend de l'orientation
        # de la pente par rapport à l'azimut du soleil.
        # Approximation simple : la pente peut modifier l'altitude de ±angle_pente
        
        # Note: une implémentation plus réaliste exigerait de calculer
        # l'angle d'incidence du soleil sur la surface inclinée.
        
        return actual_altitude_deg + math.degrees(slope_angle)


class TerrainReliefModel:
    """Modèle de relief d'un terrain."""
    
    def __init__(self):
        self.slope: Optional[TerrainSlope] = None
        self.base_elevation_m: float = 0.0  # Altitude de base du terrain
    
    def set_slope(self, orientation_deg: float, steepness_percent: float) -> None:
        """Définit la pente du terrain."""
        self.slope = TerrainSlope(
            orientation_deg=float(orientation_deg),
            steepness_percent=float(steepness_percent),
        )
    
    def get_effective_altitude(self, actual_altitude_deg: float) -> float:
        """Retourne l'altitude effective du soleil en tenant compte de la pente."""
        if self.slope is None:
            return actual_altitude_deg
        
        return self.slope.get_effective_sun_altitude(actual_altitude_deg)
    
    def get_elevation_at_point(self, x: float, y: float) -> float:
        """
        Retourne l'altitude à un point (x, y) du terrain.
        
        Modèle simple : élévation linéaire selon la pente.
        """
        if self.slope is None:
            return self.base_elevation_m
        
        slope_angle = self.slope.get_slope_angle_rad()
        
        # Orientation de la pente en radians
        slope_azimuth = math.radians(self.slope.orientation_deg)
        
        # Distance dans la direction de la pente
        distance_in_slope_dir = (
            x * math.sin(slope_azimuth) + 
            y * math.cos(slope_azimuth)
        )
        
        # Élévation = élévation de base + distance * tan(angle)
        elevation = self.base_elevation_m + distance_in_slope_dir * math.tan(slope_angle)
        
        return elevation


# Fonctions utilitaires

def calculate_slope_from_elevation_map(
    elevation_grid: list,  # 2D list of elevations
    grid_step_m: float,  # Pas de la grille en mètres
) -> Tuple[float, float]:
    """
    Calcule la pente dominante d'un terrain à partir d'une carte d'élévation.
    
    Retourne :
        (orientation_deg, steepness_percent)
    """
    # Calcul des gradients dans les deux dimensions
    if len(elevation_grid) < 2 or len(elevation_grid[0]) < 2:
        return 0.0, 0.0
    
    # Gradient nord-sud
    grad_ns = (elevation_grid[-1][0] - elevation_grid[0][0]) / (len(elevation_grid) * grid_step_m)
    
    # Gradient est-ouest
    grad_ew = (elevation_grid[0][-1] - elevation_grid[0][0]) / (len(elevation_grid[0]) * grid_step_m)
    
    # Calcul de l'orientation et de la pente
    magnitude = math.hypot(grad_ns, grad_ew)
    if magnitude < 1e-6:
        return 0.0, 0.0
    
    # Orientation (0°=nord, 90°=est, etc.)
    orientation_rad = math.atan2(grad_ew, grad_ns)
    orientation_deg = math.degrees(orientation_rad)
    if orientation_deg < 0:
        orientation_deg += 360.0
    
    # Pente en pourcentage
    steepness_percent = magnitude * 100.0
    
    return orientation_deg, steepness_percent
