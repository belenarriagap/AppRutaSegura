from __future__ import annotations

from collections.abc import Collection, Sequence

import numpy as np

from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid, abp_polygon_to_m
from abp_rutasegura.abp_engines.abp_simulation.abp_engine import abpSimulation
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abp_spawn_agents, abpRoomArea

abp_PROFILES = (
    abpPersonProfile("adulto", 1.3, 5.0, 2.0, 0.25),
    abpPersonProfile("niño", 1.0, 3.0, 1.0, 0.2),
)


def abp_make_simulation(
    abp_plan: abpFloorPlan,
    abp_occupancies: Sequence[abpOccupancy],
    *,
    abp_seed: int = 1,
    abp_params: abpSimulationParams | None = None,
    abp_blocked: Collection[str] = (),
    abp_profiles: Sequence[abpPersonProfile] = abp_PROFILES,
) -> abpSimulation:
    abp_params = abp_params or abpSimulationParams()
    abp_scale = abp_plan.abp_scale_m_per_px
    assert abp_scale is not None
    abp_grid = abp_build_grid(abp_plan, abp_blocked_exits=abp_blocked)
    abp_dist = abp_distance_field(
        abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
    )
    abp_rooms = [
        abpRoomArea(abp_r.abp_name, abp_plan.abp_level, abp_polygon_to_m(abp_r.abp_area, abp_scale))
        for abp_r in abp_plan.abp_rooms
    ]
    abp_rng = np.random.default_rng(abp_seed)
    abp_agents = abp_spawn_agents(
        abp_grid, abp_dist, abp_rooms, abp_occupancies, abp_profiles, abp_rng, abp_params
    )
    return abpSimulation(
        abp_grid,
        abp_agents,
        abp_params,
        abp_seed=abp_seed,
        abp_profile_names=[abp_p.abp_name for abp_p in abp_profiles],
        abp_distance=abp_dist,
    )
