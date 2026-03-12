# -*- coding: utf-8 -*-
# core/shadow_engine.py
"""
Moteur de calcul des ombres sophistiqué.
Gère :
  - Ombres de la maison
  - Ombres des haies/murs (segments)
  - Projection des ombres selon la position du soleil (pvlib)
  - Relief du terrain (optionnel)
"""
import math
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class SunPosition:
    """Position du soleil : altitude et azimut en degrés."""
    altitude_deg: float
    azimuth_deg: float


class ShadowEngine:
    """Moteur de calcul des ombres pour un terrain."""
    
    def __init__(self, terrain_orientation_deg: float = 0.0):
        """
        Args:
            terrain_orientation_deg: Orientation du nord du terrain (0-360°).
                                    0° = nord vers le haut, 90° = nord vers la droite, etc.
        """
        self.north_offset = float(terrain_orientation_deg)
    
    def is_point_in_shadow_by_house(
        self,
        point: Tuple[float, float],
        house_origin: Tuple[float, float],
        house_width: float,
        house_height: float,
        house_building_height: float,
        sun_pos: SunPosition,
    ) -> bool:
        """
        Teste si un point est dans l'ombre d'un bâtiment rectangulaire.
        
        Modèle simplifié mais efficace :
        1. Le bâtiment projette une ombre conique selon l'altitude du soleil
        2. On teste si le point est dans cette zone d'ombre
        """
        if sun_pos.altitude_deg <= 0.0:
            return False
        
        # Calcul de la longueur de l'ombre projetée
        alt_rad = math.radians(max(1.0, sun_pos.altitude_deg))
        shadow_length = house_building_height / math.tan(alt_rad)
        
        # Ajustement de l'azimut dans le repère du terrain
        azimuth_in_terrain = (sun_pos.azimuth_deg - self.north_offset) % 360.0
        azimuth_rad = math.radians(azimuth_in_terrain)
        
        # Direction de l'ombre (opposite au soleil)
        shadow_dir_x = -math.sin(azimuth_rad)
        shadow_dir_y = -math.cos(azimuth_rad)
        
        # Rotation du point et du bâtiment dans le repère du terrain
        px, py = self._rotate_point(*point, -self.north_offset)
        ho_x, ho_y = self._rotate_point(*house_origin, -self.north_offset)
        
        # Limites du bâtiment
        h_x1, h_y1 = ho_x, ho_y
        h_x2, h_y2 = ho_x + house_width, ho_y + house_height
        
        # Test 1 : le point est-il directement sur le bâtiment ?
        if h_x1 <= px <= h_x2 and h_y1 <= py <= h_y2:
            return True
        
        # Test 2 : le point est-il dans la projection de l'ombre ?
        # Centre du bâtiment
        h_cx, h_cy = (h_x1 + h_x2) / 2.0, (h_y1 + h_y2) / 2.0
        
        # Vecteur du centre du bâtiment vers le point
        v_x = px - h_cx
        v_y = py - h_cy
        
        # Distance le long de la direction de l'ombre
        t = v_x * shadow_dir_x + v_y * shadow_dir_y
        
        # Est-ce que le point est derrière le bâtiment dans la direction de l'ombre ?
        if t <= 0 or t > shadow_length:
            return False
        
        # Projection du point perpendiculaire à la direction de l'ombre
        p_x = v_x - t * shadow_dir_x
        p_y = v_y - t * shadow_dir_y
        
        # Rayon approximatif du bâtiment pour la projection
        h_radius = 0.5 * math.hypot(house_width, house_height)
        
        return math.hypot(p_x, p_y) <= h_radius
    
    def is_point_in_shadow_by_hedge(
        self,
        point: Tuple[float, float],
        hedge_a: Tuple[float, float],
        hedge_b: Tuple[float, float],
        hedge_height: float,
        sun_pos: SunPosition,
        hedge_thickness: float = 0.3,
    ) -> bool:
        """
        Teste si un point est dans l'ombre d'une haie/mur (segment vertical).
        
        Modèle :
        1. La haie est modélisée comme un segment dans le plan du terrain
        2. L'ombre est projetée perpendiculairement selon l'altitude du soleil
        3. On teste si le point est dans cette zone d'ombre
        """
        if sun_pos.altitude_deg <= 0.0:
            return False
        
        # Calcul de la longueur de l'ombre
        alt_rad = math.radians(max(1.0, sun_pos.altitude_deg))
        shadow_length = hedge_height / math.tan(alt_rad)
        
        # Ajustement de l'azimut
        azimuth_in_terrain = (sun_pos.azimuth_deg - self.north_offset) % 360.0
        azimuth_rad = math.radians(azimuth_in_terrain)
        
        # Direction de l'ombre
        shadow_dir_x = -math.sin(azimuth_rad)
        shadow_dir_y = -math.cos(azimuth_rad)
        
        # Rotation du point et du segment dans le repère du terrain
        px, py = self._rotate_point(*point, -self.north_offset)
        ha_x, ha_y = self._rotate_point(*hedge_a, -self.north_offset)
        hb_x, hb_y = self._rotate_point(*hedge_b, -self.north_offset)
        
        # Distance perpendiculaire du point au segment de haie
        perp_dist = self._distance_point_to_segment(
            (px, py), (ha_x, ha_y), (hb_x, hb_y)
        )
        
        # Est-ce que le point est suffisamment proche du segment ?
        if perp_dist > hedge_thickness:
            return False
        
        # Centre du segment
        seg_cx = (ha_x + hb_x) / 2.0
        seg_cy = (ha_y + hb_y) / 2.0
        
        # Vecteur du centre du segment vers le point
        v_x = px - seg_cx
        v_y = py - seg_cy
        
        # Distance le long de la direction de l'ombre
        t = v_x * shadow_dir_x + v_y * shadow_dir_y
        
        # Est-ce dans la zone d'ombre ?
        return 0 < t <= shadow_length
    
    @staticmethod
    def _rotate_point(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
        """Rotate un point (x, y) par un angle en degrés autour de l'origine."""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)
    
    @staticmethod
    def _distance_point_to_segment(
        point: Tuple[float, float],
        seg_a: Tuple[float, float],
        seg_b: Tuple[float, float],
    ) -> float:
        """Distance perpendiculaire d'un point à un segment."""
        px, py = point
        ax, ay = seg_a
        bx, by = seg_b
        
        # Vecteurs
        ab_x = bx - ax
        ab_y = by - ay
        ap_x = px - ax
        ap_y = py - ay
        
        ab_len_sq = ab_x * ab_x + ab_y * ab_y
        if ab_len_sq < 1e-12:
            return math.hypot(px - ax, py - ay)
        
        # Projection sur le segment
        t = max(0.0, min(1.0, (ap_x * ab_x + ap_y * ab_y) / ab_len_sq))
        
        # Point le plus proche sur le segment
        closest_x = ax + t * ab_x
        closest_y = ay + t * ab_y
        
        return math.hypot(px - closest_x, py - closest_y)
