from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class abpPersonProfile:
    abp_name: str
    abp_max_speed_mps: float
    abp_reaction_mean_s: float
    abp_reaction_std_s: float
    abp_radius_m: float

    def __post_init__(self) -> None:
        if self.abp_max_speed_mps <= 0:
            raise ValueError("La velocidad máxima debe ser positiva.")
        if self.abp_reaction_mean_s < 0 or self.abp_reaction_std_s < 0:
            raise ValueError("Los tiempos de reacción no pueden ser negativos.")
        if self.abp_radius_m <= 0:
            raise ValueError("El radio debe ser positivo.")


@dataclass(frozen=True, slots=True)
class abpOccupancy:
    abp_room_name: str
    abp_profile_name: str
    abp_count: int
    abp_level: int = 0

    def __post_init__(self) -> None:
        if self.abp_count < 0:
            raise ValueError("La cantidad de ocupantes no puede ser negativa.")
