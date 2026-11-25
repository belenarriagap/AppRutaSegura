from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class abpSimulationParams:
    abp_dt_s: float = 0.1
    abp_max_time_s: float = 1800.0
    abp_record_every_s: float = 0.5
    abp_relaxation_s: float = 0.5
    abp_jam_density: float = 5.4
    abp_min_speed_factor: float = 0.1
    abp_speed_variation: float = 0.1
    abp_agent_strength: float = 2.0
    abp_agent_range_m: float = 0.3
    abp_interaction_cutoff_m: float = 1.2
    abp_wall_strength: float = 5.0
    abp_wall_range_m: float = 0.2
    abp_stair_travel_m: float = 8.0
    abp_stair_speed_factor: float = 0.5
    abp_stair_specific_flow: float = 1.1
    abp_congestion_density: float = 2.0
    abp_congestion_min_duration_s: float = 5.0

    def __post_init__(self) -> None:
        if self.abp_dt_s <= 0 or self.abp_max_time_s <= 0:
            raise ValueError("El paso de tiempo y el tiempo máximo deben ser positivos.")
        if self.abp_record_every_s < self.abp_dt_s:
            raise ValueError("Los cuadros no pueden registrarse más seguido que el paso de tiempo.")
        if not 0 < self.abp_min_speed_factor <= 1:
            raise ValueError("El factor mínimo de velocidad debe estar entre 0 y 1.")
