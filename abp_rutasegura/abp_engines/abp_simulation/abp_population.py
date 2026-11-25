from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_agents import abpAgentArrays
from abp_rutasegura.abp_domain.abp_enums import abpCellType
from abp_rutasegura.abp_domain.abp_geometry import abpPolygon
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abpNavGrid
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams


class abpPopulationError(ValueError):
    pass


@dataclass(frozen=True)
class abpRoomArea:
    abp_name: str
    abp_level: int
    abp_polygon_m: abpPolygon


def abp_lognormal_params(abp_mean: float, abp_std: float) -> tuple[float, float]:
    if abp_mean <= 0:
        return -math.inf, 0.0
    abp_sigma2 = math.log(1.0 + (abp_std / abp_mean) ** 2)
    return math.log(abp_mean) - abp_sigma2 / 2.0, math.sqrt(abp_sigma2)


def abp_sample_reaction_times(
    abp_rng: np.random.Generator, abp_mean: float, abp_std: float, abp_n: int
) -> npt.NDArray[np.float64]:
    if abp_n == 0:
        return np.zeros(0)
    if abp_mean <= 0:
        return np.zeros(abp_n)
    if abp_std <= 0:
        return np.full(abp_n, float(abp_mean))
    abp_mu, abp_sigma = abp_lognormal_params(abp_mean, abp_std)
    return np.asarray(abp_rng.lognormal(abp_mu, abp_sigma, size=abp_n), dtype=np.float64)


def abp_spawn_agents(
    abp_grid: abpNavGrid,
    abp_distance: npt.NDArray[np.float64],
    abp_rooms: Sequence[abpRoomArea],
    abp_occupancies: Sequence[abpOccupancy],
    abp_profiles: Sequence[abpPersonProfile],
    abp_rng: np.random.Generator,
    abp_params: abpSimulationParams,
) -> abpAgentArrays:
    abp_profile_index: Mapping[str, int] = {
        abp_p.abp_name: abp_i for abp_i, abp_p in enumerate(abp_profiles)
    }
    abp_room_index = {(abp_r.abp_level, abp_r.abp_name): abp_r for abp_r in abp_rooms}
    abp_usable = (abp_grid.abp_cells == int(abpCellType.abp_FREE)) & np.isfinite(abp_distance)
    abp_blocks = []
    for abp_occ in abp_occupancies:
        if abp_occ.abp_count == 0:
            continue
        abp_room = abp_room_index.get((abp_occ.abp_level, abp_occ.abp_room_name))
        if abp_room is None:
            raise abpPopulationError(f"No existe el ambiente «{abp_occ.abp_room_name}».")
        if abp_occ.abp_profile_name not in abp_profile_index:
            raise abpPopulationError(f"No existe el perfil «{abp_occ.abp_profile_name}».")
        abp_cells = abp_grid.abp_polygon_mask(abp_room.abp_polygon_m) & abp_usable
        abp_rows, abp_cols = np.nonzero(abp_cells)
        if abp_rows.size == 0:
            abp_outside = abp_grid.abp_polygon_mask(abp_room.abp_polygon_m) & (
                abp_grid.abp_cells == int(abpCellType.abp_OUTSIDE)
            )
            if abp_outside.any():
                raise abpPopulationError(
                    f"«{abp_occ.abp_room_name}» quedó conectado con el exterior: hay un hueco en el "
                    "contorno del edificio (un muro exterior que no llega a cerrar o una puerta "
                    "que lo atraviesa). Cierre el contorno en el paso 3; las salidas se dibujan "
                    "con la herramienta Salida, no como puerta."
                )
            raise abpPopulationError(
                f"Las personas de «{abp_occ.abp_room_name}» no pueden llegar a ninguna salida. Revise que "
                "el ambiente tenga una puerta y que las salidas estén dibujadas sobre un muro "
                "exterior (si quedan separadas del muro, el paso sigue cerrado)."
            )
        abp_pick = abp_rng.integers(0, abp_rows.size, size=abp_occ.abp_count)
        abp_centers = abp_grid.abp_cell_centers(abp_rows[abp_pick], abp_cols[abp_pick])
        abp_jitter = (
            abp_rng.uniform(-0.45, 0.45, size=(abp_occ.abp_count, 2)) * abp_grid.abp_cell_size
        )
        abp_profile = abp_profiles[abp_profile_index[abp_occ.abp_profile_name]]
        abp_factor = np.clip(
            abp_rng.normal(1.0, abp_params.abp_speed_variation, size=abp_occ.abp_count), 0.7, 1.3
        )
        abp_blocks.append(
            (
                abp_centers + abp_jitter,
                abp_profile.abp_max_speed_mps * abp_factor,
                np.full(abp_occ.abp_count, abp_profile.abp_radius_m),
                abp_sample_reaction_times(
                    abp_rng,
                    abp_profile.abp_reaction_mean_s,
                    abp_profile.abp_reaction_std_s,
                    abp_occ.abp_count,
                ),
                np.full(
                    abp_occ.abp_count, abp_profile_index[abp_occ.abp_profile_name], dtype=np.int32
                ),
            )
        )
    if not abp_blocks:
        return abpAgentArrays.abp_empty(0)
    abp_agents = abpAgentArrays.abp_empty(sum(len(abp_b[0]) for abp_b in abp_blocks))
    abp_agents.abp_position[:] = np.vstack([abp_b[0] for abp_b in abp_blocks])
    abp_agents.abp_max_speed[:] = np.concatenate([abp_b[1] for abp_b in abp_blocks])
    abp_agents.abp_radius[:] = np.concatenate([abp_b[2] for abp_b in abp_blocks])
    abp_agents.abp_reaction_time[:] = np.concatenate([abp_b[3] for abp_b in abp_blocks])
    abp_agents.abp_profile_index[:] = np.concatenate([abp_b[4] for abp_b in abp_blocks])
    return abp_agents
