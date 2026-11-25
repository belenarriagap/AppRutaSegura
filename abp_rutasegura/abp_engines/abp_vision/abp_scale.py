from __future__ import annotations

from abp_rutasegura.abp_domain.abp_geometry import abpPoint


def abp_scale_from_reference(abp_p1: abpPoint, abp_p2: abpPoint, abp_meters: float) -> float:
    if abp_meters <= 0:
        raise ValueError("La medida real debe ser mayor que cero.")
    abp_pixels = abp_p1.abp_distance_to(abp_p2)
    if abp_pixels < 1.0:
        raise ValueError("Los dos puntos están demasiado cerca; márquelos más separados.")
    return abp_meters / abp_pixels
