from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_agents import abpAgentArrays
from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus, abpCellType, abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpFloorMap, abpSimulationResult, abpTrajectories
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_build_grid,
    abp_landing_cells,
    abp_polygon_to_m,
    abpNavGrid,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_manual_routes import abp_guides_for, abpRouteKey
from abp_rutasegura.abp_engines.abp_navigation.abp_stairs import abp_stair_role, abpStairRole
from abp_rutasegura.abp_engines.abp_simulation.abp_engine import (
    abpCancelCheck,
    abpProgressCallback,
    abpSimulation,
    abpSimulationCancelled,
    abpSimulationOutput,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_metrics import abp_find_bottlenecks
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_rutasegura.abp_engines.abp_simulation.abp_population import (
    abp_spawn_agents,
    abpPopulationError,
    abpRoomArea,
)

abp_MAX_FLOORS = 4
abp_IN_STAIRS = -1
abp_NOT_A_PAIR = (abpStairUse.abp_SAME_FLOOR, abpStairUse.abp_OUTSIDE, abpStairUse.abp_CLOSED)
abp_EVACUATED = int(abpAgentStatus.abp_EVACUATED)
abp_MOVING = int(abpAgentStatus.abp_MOVING)


class abpMultiFloorError(ValueError):
    pass


@dataclass(frozen=True)
class abp__Stair:
    abp_lower_index: int
    abp_seconds_per_person: float


def abp_stair_width_m(abp_plan: abpFloorPlan, abp_index: int) -> float:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_pts = (
        np.array(
            [
                [abp_p.abp_x, abp_p.abp_y]
                for abp_p in abp_plan.abp_stairs[abp_index].abp_area.abp_vertices
            ],
            np.float32,
        )
        * abp_scale
    )
    (_, _), (abp_w, abp_h), _ = cv2.minAreaRect(abp_pts)
    return float(max(min(abp_w, abp_h), 0.3))


def abp_pair_stairs(abp_upper: abpFloorPlan, abp_lower: abpFloorPlan) -> dict[int, int]:
    abp_lower_ok = [
        abp_i
        for abp_i, abp_st in enumerate(abp_lower.abp_stairs)
        if abp_st.abp_confirmed and abp_st.abp_use not in abp_NOT_A_PAIR
    ]
    abp_by_name = {
        abp_lower.abp_stairs[abp_i].abp_name.strip().lower(): abp_i
        for abp_i in abp_lower_ok
        if abp_lower.abp_stairs[abp_i].abp_name
    }
    abp_pairs: dict[int, int] = {}
    for abp_i, abp_stair in enumerate(abp_upper.abp_stairs):
        if (
            not abp_stair.abp_confirmed
            or abp_stair_role(abp_stair, abp_upper_floor=True) is not abpStairRole.abp_DOWN
        ):
            continue
        abp_key = (abp_stair.abp_leads_to or abp_stair.abp_name).strip().lower()
        if abp_key and abp_key in abp_by_name:
            abp_pairs[abp_i] = abp_by_name[abp_key]
        elif len(abp_lower_ok) == 1:
            abp_pairs[abp_i] = abp_lower_ok[0]
        else:
            abp_label = abp_stair.abp_name or f"Escalera {abp_i + 1}"
            raise abpMultiFloorError(
                f"La escalera «{abp_label}» del piso {abp_upper.abp_level + 1} no tiene una escalera "
                f"correspondiente en el piso {abp_lower.abp_level + 1}. Dibújela en ese piso con el "
                "mismo nombre."
            )
    return abp_pairs


def abp_guide_per_agent(
    abp_occupancies: Sequence[abpOccupancy], abp_level: int, abp_order: Mapping[abpRouteKey, int]
) -> npt.NDArray[np.int32]:
    abp_used = [abp_o for abp_o in abp_occupancies if abp_o.abp_count > 0]
    abp_index = [abp_order.get((abp_level, False, abp_o.abp_room_name), -1) for abp_o in abp_used]
    return np.repeat(
        np.array(abp_index, np.int32), np.array([abp_o.abp_count for abp_o in abp_used], np.int64)
    )


class abpMultiFloorSimulation:
    def __init__(
        self,
        abp_floors: Sequence[abpFloorPlan],
        abp_occupancies: Sequence[abpOccupancy],
        abp_profiles: Sequence[abpPersonProfile],
        abp_params: abpSimulationParams,
        *,
        abp_seed: int,
        abp_blocked_exits: Collection[str] = (),
        abp_routes: Sequence[abpManualRoute] = (),
    ) -> None:
        if not abp_floors:
            raise abpMultiFloorError("No hay pisos para simular.")
        if len(abp_floors) > abp_MAX_FLOORS:
            raise abpMultiFloorError(
                f"RutaSegura simula edificios de hasta {abp_MAX_FLOORS} pisos."
            )
        self.abp_params = abp_params
        self.abp_seed = abp_seed
        self.abp_plans = {
            abp_plan.abp_level: abp_plan
            for abp_plan in sorted(abp_floors, key=lambda abp_f: abp_f.abp_level)
        }
        self.abp_levels = sorted(self.abp_plans)
        self.abp_profile_names = tuple(abp_p.abp_name for abp_p in abp_profiles)
        abp_bottom = self.abp_levels[0]
        self.abp_grids: dict[int, abpNavGrid] = {}
        abp_distances: dict[int, npt.NDArray[np.float64]] = {}
        for abp_level, abp_plan in self.abp_plans.items():
            if abp_plan.abp_scale_m_per_px is None:
                raise abpMultiFloorError(f"El piso {abp_level + 1} no tiene escala.")
            abp_is_upper = abp_level > abp_bottom
            abp_grid = abp_build_grid(
                abp_plan,
                abp_blocked_exits=abp_blocked_exits,
                abp_stairs_as_targets=abp_is_upper,
                abp_exits_as_targets=not abp_is_upper,
            )
            self.abp_grids[abp_level] = abp_grid
            abp_distances[abp_level] = abp_distance_field(
                abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
            )

        self.abp__distances = abp_distances

        self.abp__stairs: dict[int, dict[int, abp__Stair]] = {}
        for abp_upper, abp_lower in zip(self.abp_levels[1:], self.abp_levels[:-1], strict=True):
            if abp_upper - abp_lower != 1:
                raise abpMultiFloorError(
                    f"Falta el piso {abp_lower + 2}: los pisos deben ser consecutivos."
                )
            abp_pairs = abp_pair_stairs(self.abp_plans[abp_upper], self.abp_plans[abp_lower])
            self.abp__stairs[abp_upper] = {
                abp_i: abp__Stair(
                    abp_j,
                    1.0
                    / (
                        abp_params.abp_stair_specific_flow
                        * abp_stair_width_m(self.abp_plans[abp_upper], abp_i)
                    ),
                )
                for abp_i, abp_j in abp_pairs.items()
            }
        self.abp__arrivals = {
            abp_level: {
                abp_i: self.abp__arrival_cells(abp_level, abp_i)
                for abp_i, abp_st in enumerate(self.abp_plans[abp_level].abp_stairs)
                if abp_st.abp_confirmed
            }
            for abp_level in self.abp_levels
        }

        self.abp__validate_stairs(abp_occupancies, abp_distances)

        abp_rng = np.random.default_rng(abp_seed)
        abp_blocks: list[tuple[int, abpAgentArrays]] = []
        abp_guides = {
            abp_level: abp_guides_for(
                self.abp_grids[abp_level], abp_distances[abp_level], abp_plan, abp_routes
            )
            for abp_level, abp_plan in self.abp_plans.items()
        }
        self.abp__guide_index = {
            abp_level: {abp_key: abp_k for abp_k, abp_key in enumerate(abp_g)}
            for abp_level, abp_g in abp_guides.items()
        }
        for abp_level in self.abp_levels:
            abp_plan = self.abp_plans[abp_level]
            abp_scale = abp_plan.abp_scale_m_per_px or 1.0
            abp_rooms = [
                abpRoomArea(abp_r.abp_name, abp_level, abp_polygon_to_m(abp_r.abp_area, abp_scale))
                for abp_r in abp_plan.abp_rooms
            ]
            abp_mine = [abp_o for abp_o in abp_occupancies if abp_o.abp_level == abp_level]
            try:
                abp_agents = abp_spawn_agents(
                    self.abp_grids[abp_level],
                    abp_distances[abp_level],
                    abp_rooms,
                    abp_mine,
                    abp_profiles,
                    abp_rng,
                    abp_params,
                )
            except abpPopulationError as abp_exc:
                abp_message = str(abp_exc)
                if abp_level > abp_bottom:
                    abp_message = abp_message.replace(
                        "no pueden llegar a ninguna salida", "no pueden llegar a ninguna escalera"
                    )
                raise abpMultiFloorError(f"Piso {abp_level + 1}: {abp_message}") from abp_exc
            abp_blocks.append((abp_level, abp_agents))
        abp_n = sum(len(abp_a) for _, abp_a in abp_blocks)
        self.abp_agents_total = abp_n
        self.abp_level = np.full(abp_n, abp_IN_STAIRS, dtype=np.int8)
        self.abp_max_speed = np.zeros(abp_n)
        self.abp_radius = np.zeros(abp_n, dtype=np.float32)
        self.abp_profile_index = np.zeros(abp_n, dtype=np.int32)
        abp_reaction = np.zeros(abp_n)
        abp_start = 0
        for abp_level, abp_agents in abp_blocks:
            abp_sl = slice(abp_start, abp_start + len(abp_agents))
            self.abp_level[abp_sl] = abp_level
            self.abp_max_speed[abp_sl] = abp_agents.abp_max_speed
            self.abp_radius[abp_sl] = abp_agents.abp_radius
            self.abp_profile_index[abp_sl] = abp_agents.abp_profile_index
            abp_reaction[abp_sl] = abp_agents.abp_reaction_time
            abp_start += len(abp_agents)

        self.abp_sims: dict[int, abpSimulation] = {}
        for abp_level, abp_agents in abp_blocks:
            abp_floor_agents = abpAgentArrays.abp_empty(abp_n)
            abp_floor_agents.abp_max_speed[:] = self.abp_max_speed
            abp_floor_agents.abp_radius[:] = self.abp_radius
            abp_floor_agents.abp_reaction_time[:] = abp_reaction
            abp_floor_agents.abp_profile_index[:] = self.abp_profile_index
            abp_floor_agents.abp_status[:] = abp_EVACUATED
            abp_here = np.flatnonzero(self.abp_level == abp_level)
            abp_floor_agents.abp_position[abp_here] = abp_agents.abp_position
            abp_floor_agents.abp_status[abp_here] = abp_agents.abp_status
            abp_guide_of = np.full(abp_n, -1, np.int32)
            abp_guide_of[abp_here] = abp_guide_per_agent(
                [abp_o for abp_o in abp_occupancies if abp_o.abp_level == abp_level],
                abp_level,
                self.abp__guide_index[abp_level],
            )
            self.abp_sims[abp_level] = abpSimulation(
                self.abp_grids[abp_level],
                abp_floor_agents,
                abp_params,
                abp_seed=abp_seed,
                abp_profile_names=self.abp_profile_names,
                abp_distance=abp_distances[abp_level],
                abp_record=False,
                abp_guides=[abp_g.abp_distance for abp_g in abp_guides[abp_level].values()],
                abp_guide_of=abp_guide_of,
            )

        self.abp_time_s = 0.0
        self.abp_steps = 0
        self.abp_evacuation_time = np.full(abp_n, np.nan)
        self.abp_exit_name: list[str | None] = [None] * abp_n
        self.abp__transit_until = np.full(abp_n, np.inf)
        self.abp__transit_to: list[tuple[int, int] | None] = [None] * abp_n
        self.abp__stair_free_at: dict[tuple[int, int], float] = {}
        self.abp__arrival_rng = np.random.default_rng([abp_seed, 1])
        self.abp__record_every = max(1, round(abp_params.abp_record_every_s / abp_params.abp_dt_s))
        self.abp__frames_t: list[float] = []
        self.abp__frames_pos: list[npt.NDArray[np.float32]] = []
        self.abp__frames_status: list[npt.NDArray[np.int8]] = []
        self.abp__frames_level: list[npt.NDArray[np.int8]] = []
        self.abp__record()

    @property
    def abp_evacuated(self) -> int:
        return int(np.count_nonzero(~np.isnan(self.abp_evacuation_time)))

    @property
    def abp_finished(self) -> bool:
        return (
            self.abp_evacuated == self.abp_agents_total
            or self.abp_time_s >= self.abp_params.abp_max_time_s - 1e-9
        )

    def abp__validate_stairs(
        self,
        abp_occupancies: Sequence[abpOccupancy],
        abp_distances: dict[int, npt.NDArray[np.float64]],
    ) -> None:
        abp_bottom = self.abp_levels[0]
        for abp_level in self.abp_levels[1:]:
            abp_plan = self.abp_plans[abp_level]
            abp_people = sum(
                abp_o.abp_count for abp_o in abp_occupancies if abp_o.abp_level == abp_level
            )
            abp_confirmed = [
                abp_i for abp_i, abp_st in enumerate(abp_plan.abp_stairs) if abp_st.abp_confirmed
            ]
            if abp_people and not abp_confirmed:
                raise abpMultiFloorError(
                    f"El piso {abp_level + 1} tiene {abp_people} persona(s) pero ninguna escalera. En un "
                    "sismo se baja por la escalera y se sale por el primer piso: dibuje la "
                    f"escalera en el paso 3 del piso {abp_level + 1} y en el piso {abp_level}, en el "
                    "mismo lugar y con el mismo nombre."
                )
        for abp_upper, abp_stairs in self.abp__stairs.items():
            abp_lower = abp_upper - 1
            abp_grid, abp_dist = self.abp_grids[abp_lower], abp_distances[abp_lower]
            for abp__i, abp_stair in abp_stairs.items():
                abp_cells = self.abp__arrival_cells(abp_lower, abp_stair.abp_lower_index)
                abp_r, abp_c = (
                    abp_grid.abp_to_cell(abp_cells)
                    if abp_cells.size
                    else (np.zeros(0, int), np.zeros(0, int))
                )
                if not np.isfinite(abp_dist[abp_r, abp_c]).any():
                    abp_name = (
                        self.abp_plans[abp_lower].abp_stairs[abp_stair.abp_lower_index].abp_name
                        or "la escalera"
                    )
                    abp_goal = "una salida" if abp_lower == abp_bottom else "otra escalera"
                    raise abpMultiFloorError(
                        f"Desde «{abp_name}» del piso {abp_lower + 1} no se llega a {abp_goal}. Revise que la "
                        "escalera esté dentro del local y comunicada por puertas."
                    )

    def abp__arrival_cells(self, abp_level: int, abp_index: int) -> npt.NDArray[np.float64]:
        abp_plan = self.abp_plans[abp_level]
        abp_grid = self.abp_grids[abp_level]
        abp_stair = abp_plan.abp_stairs[abp_index]
        abp_scale = abp_plan.abp_scale_m_per_px or 1.0
        abp_area = abp_polygon_to_m(abp_stair.abp_area, abp_scale)
        if abp_index in abp_grid.abp_closed_stairs:
            abp_entry = abp_stair.abp_entry
            abp_foot = (
                abpPoint(abp_entry.abp_x * abp_scale, abp_entry.abp_y * abp_scale)
                if abp_entry is not None
                else None
            )
            return abp_landing_cells(abp_grid, self.abp__distances[abp_level], abp_area, abp_foot)
        abp_mask = abp_grid.abp_polygon_mask(abp_area)
        abp_rows, abp_cols = np.nonzero(
            abp_mask & (abp_grid.abp_cells == int(abpCellType.abp_STAIR))
        )
        if abp_rows.size == 0:
            abp_rows, abp_cols = np.nonzero(abp_mask & abp_grid.abp_walkable)
        return abp_grid.abp_cell_centers(abp_rows, abp_cols)

    def abp_step(self) -> None:
        abp_dt = self.abp_params.abp_dt_s
        abp_now = self.abp_time_s + abp_dt
        for abp_level in self.abp_levels:
            abp_sim = self.abp_sims[abp_level]
            abp_before = abp_sim.abp_agents.abp_status.copy()
            abp_sim.abp_step()
            abp_arrived = np.flatnonzero(
                (abp_before != abp_EVACUATED)
                & (abp_sim.abp_agents.abp_status == abp_EVACUATED)
                & (self.abp_level == abp_level)
            )
            for abp_agent in abp_arrived:
                self.abp__leave_floor(
                    int(abp_agent), abp_level, int(abp_sim.abp_exit_index[abp_agent]), abp_now
                )
        self.abp__arrive(abp_now)
        self.abp_time_s = abp_now
        self.abp_steps += 1
        if self.abp_steps % self.abp__record_every == 0:
            self.abp__record()

    def abp__leave_floor(
        self, abp_agent: int, abp_level: int, abp_target: int, abp_now: float
    ) -> None:
        abp_grid = self.abp_grids[abp_level]
        abp_stair = abp_grid.abp_stair_of(abp_target)
        if abp_stair < 0:
            self.abp_evacuation_time[abp_agent] = abp_now
            self.abp_exit_name[abp_agent] = abp_grid.abp_target_names[abp_target]
            return
        if abp_stair not in self.abp__stairs[abp_level]:
            abp_floors = abp_level - self.abp_levels[0]
            abp_pace = max(
                self.abp_max_speed[abp_agent] * self.abp_params.abp_stair_speed_factor, 0.05
            )
            self.abp_evacuation_time[abp_agent] = (
                abp_now + abp_floors * self.abp_params.abp_stair_travel_m / abp_pace
            )
            self.abp_exit_name[abp_agent] = abp_grid.abp_target_names[abp_target]
            return
        abp_info = self.abp__stairs[abp_level][abp_stair]
        abp_key = (abp_level, abp_stair)
        abp_enter = max(abp_now, self.abp__stair_free_at.get(abp_key, 0.0))
        self.abp__stair_free_at[abp_key] = abp_enter + abp_info.abp_seconds_per_person
        abp_speed = max(
            self.abp_max_speed[abp_agent] * self.abp_params.abp_stair_speed_factor, 0.05
        )
        self.abp__transit_until[abp_agent] = (
            abp_enter + self.abp_params.abp_stair_travel_m / abp_speed
        )
        self.abp__transit_to[abp_agent] = (abp_level - 1, abp_info.abp_lower_index)
        self.abp_level[abp_agent] = abp_IN_STAIRS

    def abp__arrive(self, abp_now: float) -> None:
        abp_due = np.flatnonzero(
            (self.abp_level == abp_IN_STAIRS) & (self.abp__transit_until <= abp_now + 1e-9)
        )
        for abp_agent in abp_due:
            abp_destination = self.abp__transit_to[abp_agent]
            if abp_destination is None:
                continue
            abp_level, abp_stair = abp_destination
            abp_cells = self.abp__arrivals[abp_level][abp_stair]
            abp_center = abp_cells[int(self.abp__arrival_rng.integers(0, len(abp_cells)))]
            abp_jitter = self.abp__arrival_rng.uniform(-0.15, 0.15, size=2)
            abp_sim = self.abp_sims[abp_level]
            abp_sim.abp_agents.abp_position[abp_agent] = abp_center + abp_jitter
            abp_sim.abp_agents.abp_velocity[abp_agent] = 0.0
            abp_sim.abp_agents.abp_status[abp_agent] = abp_MOVING
            abp_name = self.abp_plans[abp_level].abp_stairs[abp_stair].abp_name
            abp_sim.abp_guide_of[abp_agent] = self.abp__guide_index[abp_level].get(
                (abp_level, True, abp_name), -1
            )
            abp_sim.abp_exit_index[abp_agent] = -1
            abp_sim.abp_evacuation_time[abp_agent] = np.nan
            self.abp_level[abp_agent] = abp_level
            self.abp__transit_until[abp_agent] = np.inf
            self.abp__transit_to[abp_agent] = None

    def abp__record(self) -> None:
        abp_n = self.abp_agents_total
        abp_positions = np.zeros((abp_n, 2), dtype=np.float32)
        for abp_level, abp_sim in self.abp_sims.items():
            abp_here = self.abp_level == abp_level
            abp_positions[abp_here] = abp_sim.abp_agents.abp_position[abp_here]
        abp_status = np.where(
            ~np.isnan(self.abp_evacuation_time),
            abp_EVACUATED,
            np.where(self.abp__started(), abp_MOVING, int(abpAgentStatus.abp_WAITING)),
        ).astype(np.int8)
        self.abp__frames_t.append(self.abp_time_s)
        self.abp__frames_pos.append(abp_positions)
        self.abp__frames_status.append(abp_status)
        self.abp__frames_level.append(self.abp_level.copy())

    def abp__started(self) -> npt.NDArray[np.bool_]:
        abp_started = np.zeros(self.abp_agents_total, dtype=bool)
        for abp_level, abp_sim in self.abp_sims.items():
            abp_here = self.abp_level == abp_level
            abp_started[abp_here] = abp_sim.abp_agents.abp_status[abp_here] != int(
                abpAgentStatus.abp_WAITING
            )
        return np.asarray(abp_started | (self.abp_level == abp_IN_STAIRS), dtype=np.bool_)

    def abp_run(
        self,
        abp_progress: abpProgressCallback | None = None,
        abp_should_cancel: abpCancelCheck | None = None,
    ) -> abpSimulationOutput:
        abp_total = max(self.abp_agents_total, 1)
        abp_last = -1.0
        while not self.abp_finished:
            self.abp_step()
            if abp_should_cancel is not None and self.abp_steps % 10 == 0 and abp_should_cancel():
                raise abpSimulationCancelled
            if abp_progress is not None:
                abp_fraction = max(
                    self.abp_evacuated / abp_total, self.abp_time_s / self.abp_params.abp_max_time_s
                )
                if abp_fraction - abp_last >= 0.01:
                    abp_last = abp_fraction
                    abp_progress(min(abp_fraction, 1.0))
        if self.abp__frames_t[-1] != self.abp_time_s:
            self.abp__record()
        if abp_progress is not None:
            abp_progress(1.0)
        return self.abp_output()

    def abp_output(self) -> abpSimulationOutput:
        abp_names = sorted({abp_n for abp_n in self.abp_exit_name if abp_n is not None})
        abp_per_exit = tuple(
            (
                abp_name,
                round(
                    float(
                        max(
                            abp_t
                            for abp_t, abp_e in zip(
                                self.abp_evacuation_time, self.abp_exit_name, strict=True
                            )
                            if abp_e == abp_name
                        )
                    ),
                    2,
                ),
            )
            for abp_name in abp_names
        )
        abp_completed = self.abp_evacuated == self.abp_agents_total
        if abp_completed and self.abp_agents_total:
            abp_total_time = float(np.nanmax(self.abp_evacuation_time))
        else:
            abp_total_time = self.abp_time_s if self.abp_agents_total else 0.0
        abp_bottlenecks = sorted(
            (
                dataclasses.replace(abp_b, abp_level=abp_level)
                for abp_level in self.abp_levels
                for abp_b in abp_find_bottlenecks(
                    self.abp_grids[abp_level],
                    self.abp_sims[abp_level].abp_time_above,
                    self.abp_sims[abp_level].abp_density_when_above,
                    abp_min_duration_s=self.abp_params.abp_congestion_min_duration_s,
                )
            ),
            key=lambda abp_b: (
                -abp_b.abp_severity,
                abp_b.abp_level,
                abp_b.abp_location.abp_x,
                abp_b.abp_location.abp_y,
            ),
        )[:10]
        abp_floor_maps = tuple(
            abpFloorMap(
                abp_level,
                self.abp_sims[abp_level].abp_density_accumulated.copy(),
                self.abp_grids[abp_level].abp_origin,
                self.abp_grids[abp_level].abp_cell_size,
            )
            for abp_level in self.abp_levels
        )
        abp_bottom = abp_floor_maps[0]
        abp_curve_t = np.array(self.abp__frames_t, dtype=np.float64)
        abp_evac = np.array(
            [np.count_nonzero(self.abp_evacuation_time <= abp_t + 1e-9) for abp_t in abp_curve_t],
            dtype=np.int32,
        )
        abp_result = abpSimulationResult(
            abp_seed=self.abp_seed,
            abp_total_time_s=round(abp_total_time, 2),
            abp_time_per_exit_s=abp_per_exit,
            abp_curve_times_s=abp_curve_t,
            abp_curve_evacuated=abp_evac,
            abp_density_map=abp_bottom.abp_density_map,
            abp_bottlenecks=tuple(abp_bottlenecks),
            abp_agents_total=self.abp_agents_total,
            abp_agents_evacuated=self.abp_evacuated,
            abp_completed=abp_completed,
            abp_grid_origin_m=abp_bottom.abp_grid_origin_m,
            abp_cell_size_m=abp_bottom.abp_cell_size_m,
            abp_floor_maps=abp_floor_maps,
        )
        abp_trajectories = abpTrajectories(
            abp_times_s=abp_curve_t,
            abp_positions=np.stack(self.abp__frames_pos).astype(np.float32),
            abp_status=np.stack(self.abp__frames_status).astype(np.int8),
            abp_radius_m=self.abp_radius.astype(np.float32),
            abp_profile_index=self.abp_profile_index.astype(np.int32),
            abp_profile_names=self.abp_profile_names,
            abp_level=np.stack(self.abp__frames_level).astype(np.int8),
        )
        abp_exit_index = np.full(self.abp_agents_total, -1, dtype=np.int16)
        for abp_i, abp_name in enumerate(self.abp_exit_name):
            if abp_name is not None:
                abp_exit_index[abp_i] = abp_names.index(abp_name)
        return abpSimulationOutput(
            abp_result, abp_trajectories, abp_exit_index, self.abp_evacuation_time.copy()
        )


def abp_simulate_building(
    abp_floors: Sequence[abpFloorPlan],
    abp_occupancies: Sequence[abpOccupancy],
    abp_profiles: Sequence[abpPersonProfile],
    abp_params: abpSimulationParams,
    *,
    abp_seed: int,
    abp_blocked_exits: Collection[str] = (),
    abp_routes: Sequence[abpManualRoute] = (),
    abp_progress: Callable[[float], None] | None = None,
    abp_should_cancel: Callable[[], bool] | None = None,
) -> abpSimulationOutput:
    abp_simulation = abpMultiFloorSimulation(
        abp_floors,
        abp_occupancies,
        abp_profiles,
        abp_params,
        abp_seed=abp_seed,
        abp_blocked_exits=abp_blocked_exits,
        abp_routes=abp_routes,
    )
    return abp_simulation.abp_run(abp_progress=abp_progress, abp_should_cancel=abp_should_cancel)
