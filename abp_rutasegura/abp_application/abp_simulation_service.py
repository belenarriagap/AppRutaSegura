from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import math
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_application.abp_errors import abpOperationCancelled, abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_serialization import abp_plan_to_dict, abp_scenario_to_dict
from abp_rutasegura.abp_data.abp_database import abpDatabase
from abp_rutasegura.abp_data.abp_repositories import abpNotFoundError
from abp_rutasegura.abp_data.abp_trajectories import abp_load_run, abp_save_run
from abp_rutasegura.abp_domain.abp_enums import abpObservationType, abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import (
    abpBottleneck,
    abpFloorClearance,
    abpObservation,
    abpRoomRoute,
    abpRunStatistics,
    abpSimulationResult,
    abpTrajectories,
)
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute, abpScenario
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_build_grid,
    abp_polygon_to_m,
    abp_segment_to_m,
    abpNavGrid,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_manual_routes import (
    abp_apply_guides,
    abp_guide,
    abp_guides_for,
    abpGuidedRoute,
    abpRouteError,
    abpRouteKey,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_stairs import abp_stair_role, abpStairRole
from abp_rutasegura.abp_engines.abp_simulation.abp_engine import (
    abpSimulation,
    abpSimulationCancelled,
    abpSimulationOutput,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_metrics import abp_floor_clearance
from abp_rutasegura.abp_engines.abp_simulation.abp_multifloor import (
    abp_guide_per_agent,
    abp_pair_stairs,
    abpMultiFloorError,
    abpMultiFloorSimulation,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_rutasegura.abp_engines.abp_simulation.abp_population import (
    abp_spawn_agents,
    abpPopulationError,
    abpRoomArea,
)

abp_BASE_SCENARIO = "Escenario base"
abp__NO_EXITS = (
    "El plano{floor} no tiene ninguna salida confirmada ni zona segura disponible. "
    "Dibuje una salida sobre un muro exterior (paso 3) o confirme las salidas propuestas."
)
abp_DEFAULT_SEED = 2026

abp_CONGESTION_TEXT = (
    "Congestión {place}: densidad media de {density:.1f} personas/m² durante {duration:.0f} s."
)
abp_CONGESTION_ADVICE = (
    "Revise este paso: puede ensancharlo, retirar obstáculos, señalizar una ruta alternativa "
    "o habilitar otra salida para repartir a las personas."
)


@dataclass(frozen=True, eq=False)
class abpSimulationRun:
    abp_simulation_id: int
    abp_result: abpSimulationResult
    abp_trajectories: abpTrajectories
    abp_observations: tuple[abpObservation, ...]
    abp_scale_m_per_px: float
    abp_floor_scales: tuple[tuple[int, float], ...] = ()
    abp_statistics: abpRunStatistics | None = None
    abp_fingerprint: str = ""

    @property
    def abp_floor_clearance(self) -> tuple[abpFloorClearance, ...]:
        return abp_floor_clearance(self.abp_trajectories)

    def abp_scale_of(self, abp_level: int) -> float:
        return dict(self.abp_floor_scales).get(abp_level, self.abp_scale_m_per_px)


@dataclass(frozen=True, slots=True)
class abpRouteSource:
    abp_name: str
    abp_level: int
    abp_people: int
    abp_goals: tuple[str, ...]
    abp_from_stair: bool = False

    @property
    def abp_key(self) -> tuple[int, bool, str]:
        return (self.abp_level, self.abp_from_stair, self.abp_name)


def abp__simulated_part(abp_data: dict[str, Any]) -> dict[str, Any]:
    abp_part = {
        abp_key: abp_value for abp_key, abp_value in abp_data.items() if abp_key != "senales"
    }
    abp_part["ambientes"] = [
        {abp_key: abp_value for abp_key, abp_value in abp_room.items() if abp_key != "salida"}
        for abp_room in abp_data.get("ambientes", [])
    ]
    if abp_data.get("escaleras"):
        abp_part["modelo_escaleras"] = 2
    return abp_part


class abpSimulationService:
    def __init__(
        self,
        abp_db: abpDatabase,
        abp_runs_dir: Path,
        abp_params: abpSimulationParams | None = None,
        abp_norms: abpNormsService | None = None,
    ) -> None:
        self.abp__db = abp_db
        self.abp__runs_dir = abp_runs_dir
        self.abp_params = abp_params or abpSimulationParams()
        self.abp__norms = abp_norms

    def abp_fingerprint(
        self, abp_plan: abpFloorPlan | Sequence[abpFloorPlan], abp_scenario: abpScenario
    ) -> str:
        abp_floors = abp__as_floors(abp_plan)
        abp_scenario_data = abp_scenario_to_dict(abp_scenario)
        abp_scenario_data.pop("nombre", None)
        abp_data = {
            "pisos": [abp__simulated_part(abp_plan_to_dict(abp_f)) for abp_f in abp_floors],
            "escenario": abp_scenario_data,
            "perfiles": [dataclasses.astuple(abp_p) for abp_p in self.abp_profiles()],
        }
        abp_text = json.dumps(abp_data, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(abp_text.encode("utf-8")).hexdigest()[:32]

    def abp_is_outdated(
        self,
        abp_run: abpSimulationRun,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
    ) -> bool:
        return bool(abp_run.abp_fingerprint) and abp_run.abp_fingerprint != self.abp_fingerprint(
            abp_plan, abp_scenario
        )

    def abp_project_runs_dir(self, abp_project_id: int) -> Path:
        return self.abp__runs_dir / f"proyecto_{abp_project_id}"

    def abp_profiles(self) -> list[abpPersonProfile]:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            return abp_uow.abp_profiles.abp_list_all()

    def abp_load_scenario(
        self, abp_project_id: int, abp_name: str = abp_BASE_SCENARIO
    ) -> abpScenario:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                return abp_uow.abp_scenarios.abp_get(
                    abp_uow.abp_scenarios.abp_find_id(abp_project_id, abp_name)
                )
            except abpNotFoundError:
                if abp_name == abp_BASE_SCENARIO:
                    return abpScenario(abp_BASE_SCENARIO, abp_DEFAULT_SEED)
                raise abpUserFacingError(f"No existe el escenario «{abp_name}».") from None

    def abp_list_scenarios(self, abp_project_id: int) -> list[abpScenario]:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_stored = [abp_s for _, abp_s in abp_uow.abp_scenarios.abp_list_all(abp_project_id)]
        abp_base = next(
            (abp_s for abp_s in abp_stored if abp_s.abp_name == abp_BASE_SCENARIO), None
        )
        abp_others = [abp_s for abp_s in abp_stored if abp_s.abp_name != abp_BASE_SCENARIO]
        return [abp_base or abpScenario(abp_BASE_SCENARIO, abp_DEFAULT_SEED), *abp_others]

    def abp_save_variant(
        self,
        abp_project_id: int,
        abp_name: str,
        abp_base: abpScenario,
        abp_occupancy_percent: float,
        abp_blocked_exits: Collection[str],
        *,
        abp_previous_name: str | None = None,
        abp_description: str = "",
        abp_reaction_factor: float = 1.0,
        abp_speed_factor: float = 1.0,
        abp_runs: int = 1,
    ) -> abpScenario:
        abp_name = abp_name.strip()
        if not abp_name:
            raise abpUserFacingError("Escriba un nombre para el escenario.")
        if abp_name == abp_BASE_SCENARIO:
            raise abpUserFacingError(f"«{abp_BASE_SCENARIO}» se edita en el paso 4.")
        if abp_occupancy_percent <= 0:
            raise abpUserFacingError("El porcentaje de ocupación debe ser mayor que cero.")
        abp_target = round(abp_base.abp_total_occupants * abp_occupancy_percent / 100)
        abp_saved = self.abp_list_scenarios(abp_project_id)
        abp_existing = {abp_s.abp_name for abp_s in abp_saved}
        abp_previous = next(
            (abp_s for abp_s in abp_saved if abp_s.abp_name == abp_previous_name), None
        )
        if abp_name in abp_existing and abp_name != abp_previous_name:
            raise abpUserFacingError(f"Ya existe un escenario llamado «{abp_name}».")
        try:
            abp_variant = abpScenario(
                abp_name=abp_name,
                abp_seed=abp_base.abp_seed,
                abp_occupancies=abp_scale_occupancies(abp_base.abp_occupancies, abp_target),
                abp_blocked_exits=frozenset(abp_blocked_exits),
                abp_description=abp_description.strip(),
                abp_reaction_factor=abp_reaction_factor,
                abp_speed_factor=abp_speed_factor,
                abp_runs=abp_runs,
                abp_routes=(abp_previous or abp_base).abp_routes,
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        with self.abp__db.abp_unit_of_work() as abp_uow:
            if abp_previous_name is not None and abp_previous_name != abp_name:
                with contextlib.suppress(abpNotFoundError):
                    abp_uow.abp_scenarios.abp_rename(
                        abp_uow.abp_scenarios.abp_find_id(abp_project_id, abp_previous_name),
                        abp_name,
                    )
            try:
                abp_uow.abp_scenarios.abp_save(abp_project_id, abp_variant)
            except ValueError as abp_exc:
                raise abpUserFacingError(str(abp_exc)) from abp_exc
        return abp_variant

    def abp_delete_scenario(self, abp_project_id: int, abp_name: str) -> None:
        if abp_name == abp_BASE_SCENARIO:
            raise abpUserFacingError("El escenario base no se puede eliminar.")
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                abp_uow.abp_scenarios.abp_delete(
                    abp_uow.abp_scenarios.abp_find_id(abp_project_id, abp_name)
                )
            except abpNotFoundError:
                return

    def abp_save_scenario(self, abp_project_id: int, abp_scenario: abpScenario) -> int:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                return abp_uow.abp_scenarios.abp_save(abp_project_id, abp_scenario)
            except ValueError as abp_exc:
                raise abpUserFacingError(str(abp_exc)) from abp_exc

    def abp_run(
        self,
        abp_project_id: int,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        *,
        abp_progress: Callable[[float], None] | None = None,
        abp_should_cancel: Callable[[], bool] | None = None,
    ) -> abpSimulationRun:
        abp_floors = abp__as_floors(abp_plan)
        if abp_scenario.abp_runs <= 1:
            abp_output = self.abp_simulate(
                abp_floors,
                abp_scenario,
                abp_progress=abp_progress,
                abp_should_cancel=abp_should_cancel,
            )
            return self.abp__store(abp_project_id, abp_floors, abp_scenario, abp_output)
        abp_statistics = self.abp_run_statistics(
            abp_floors, abp_scenario, abp_progress=abp_progress, abp_should_cancel=abp_should_cancel
        )
        abp_representative = dataclasses.replace(
            abp_scenario, abp_seed=abp_statistics.abp_representative_seed, abp_runs=1
        )
        abp_output = self.abp_simulate(
            abp_floors, abp_representative, abp_should_cancel=abp_should_cancel
        )
        abp_stored = self.abp__store(
            abp_project_id, abp_floors, abp_scenario, abp_output, abp_statistics
        )
        if abp_progress is not None:
            abp_progress(1.0)
        return abp_stored

    def abp_run_statistics(
        self,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        *,
        abp_progress: Callable[[float], None] | None = None,
        abp_should_cancel: Callable[[], bool] | None = None,
    ) -> abpRunStatistics:
        abp_floors = abp__as_floors(abp_plan)
        abp_seeds = abp_scenario.abp_seeds
        abp_totals: list[float] = []
        abp_ninety: list[float | None] = []
        abp_completed: list[bool] = []
        for abp_k, abp_seed in enumerate(abp_seeds):

            def abp_partial(abp_fraction: float, abp_k: int = abp_k) -> None:
                if abp_progress is not None:
                    abp_progress(0.95 * (abp_k + abp_fraction) / len(abp_seeds))

            abp_single = dataclasses.replace(abp_scenario, abp_seed=abp_seed, abp_runs=1)
            abp_output = self.abp_simulate(
                abp_floors,
                abp_single,
                abp_progress=abp_partial,
                abp_should_cancel=abp_should_cancel,
                abp_record=False,
            )
            abp_totals.append(abp_output.abp_result.abp_total_time_s)
            abp_ninety.append(abp_output.abp_result.abp_time_to_evacuate(0.9))
            abp_completed.append(abp_output.abp_result.abp_completed)
        abp_median = sorted(abp_totals)[len(abp_totals) // 2]
        abp_representative = min(
            range(len(abp_seeds)), key=lambda abp_i: (abs(abp_totals[abp_i] - abp_median), abp_i)
        )
        return abpRunStatistics(
            abp_seeds=abp_seeds,
            abp_total_times_s=tuple(abp_totals),
            abp_ninety_times_s=tuple(abp_ninety),
            abp_completed=tuple(abp_completed),
            abp_representative_seed=abp_seeds[abp_representative],
        )

    def abp_routes(
        self,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario | None = None,
    ) -> tuple[abpRoomRoute, ...]:
        abp_floors = abp__as_floors(abp_plan)
        abp_blocked = sorted(abp_scenario.abp_blocked_exits) if abp_scenario is not None else []
        abp_lowest = abp_floors[0].abp_level
        abp_routes: list[abpRoomRoute] = []
        for abp_floor in abp_floors:
            abp_upper = abp_floor.abp_level != abp_lowest
            abp_found = abpNormsService.abp_routes(
                abp_floor, abp_blocked=abp_blocked, abp_upper_floor=abp_upper
            )
            if abp_scenario is not None and any(
                abp_r.abp_level == abp_floor.abp_level for abp_r in abp_scenario.abp_routes
            ):
                abp_found = self.abp__with_manual(
                    abp_floor, abp_found, abp_scenario, abp_upper_floor=abp_upper
                )
            abp_routes.extend(abp_found)
        return tuple(abp_routes)

    @staticmethod
    def abp__field(
        abp_plan: abpFloorPlan, abp_scenario: abpScenario, *, abp_upper_floor: bool
    ) -> tuple[abpNavGrid, npt.NDArray[np.float64]]:
        abp_grid = abp_build_grid(
            abp_plan,
            abp_blocked_exits=abp_scenario.abp_blocked_exits,
            abp_stairs_as_targets=abp_upper_floor,
            abp_exits_as_targets=not abp_upper_floor,
        )
        return abp_grid, abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )

    def abp__with_manual(
        self,
        abp_plan: abpFloorPlan,
        abp_found: Sequence[abpRoomRoute],
        abp_scenario: abpScenario,
        *,
        abp_upper_floor: bool,
    ) -> tuple[abpRoomRoute, ...]:
        try:
            abp_grid, abp_distance = self.abp__field(
                abp_plan, abp_scenario, abp_upper_floor=abp_upper_floor
            )
        except ValueError:
            return tuple(abp_found)
        abp_guides: dict[abpRouteKey, abpGuidedRoute] = {}
        for abp_route in abp_scenario.abp_routes:
            with contextlib.suppress(abpRouteError):
                abp_guides.update(abp_guides_for(abp_grid, abp_distance, abp_plan, [abp_route]))
        abp_shown = list(abp_apply_guides(abp_grid, abp_plan, abp_found, abp_guides))
        abp_shown += [
            abpRoomRoute(
                abp_g.abp_route.abp_source,
                abp_plan.abp_level,
                abp_g.abp_target_name,
                0.0,
                abp_g.abp_path_m[0],
                abp_g.abp_path_m,
                abp_manual=True,
                abp_from_stair=True,
            )
            for abp_g in abp_guides.values()
            if abp_g.abp_route.abp_from_stair
        ]
        return tuple(abp_shown)

    def abp_check_route(
        self,
        abp_plan: abpFloorPlan,
        abp_scenario: abpScenario,
        abp_route: abpManualRoute,
        *,
        abp_upper_floor: bool = False,
    ) -> None:
        try:
            abp_guide(
                *self.abp__field(abp_plan, abp_scenario, abp_upper_floor=abp_upper_floor),
                abp_plan,
                abp_route,
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    def abp_move_routes(
        self,
        abp_project_id: int,
        abp_base: abpScenario,
        abp_level: int,
        abp_move: Callable[[abpPoint], abpPoint] | None,
    ) -> abpScenario:
        for abp_variant in self.abp_list_scenarios(abp_project_id)[1:]:
            abp_changed = abp_variant.abp_moved_routes(abp_level, abp_move)
            if abp_changed != abp_variant:
                self.abp_save_scenario(abp_project_id, abp_changed)
        return abp_base.abp_moved_routes(abp_level, abp_move)

    def abp_route_sources(
        self, abp_floors: Sequence[abpFloorPlan], abp_scenario: abpScenario
    ) -> tuple[abpRouteSource, ...]:
        abp_ordered = abp__as_floors(abp_floors)
        abp_people: dict[tuple[int, str], int] = {}
        for abp_o in abp_scenario.abp_occupancies:
            abp_people[(abp_o.abp_level, abp_o.abp_room_name)] = (
                abp_people.get((abp_o.abp_level, abp_o.abp_room_name), 0) + abp_o.abp_count
            )
        abp_out: list[abpRouteSource] = []
        for abp_index, abp_plan in enumerate(abp_ordered):
            if abp_index:
                abp_goals = tuple(
                    abp_s.abp_name
                    for abp_s in abp_plan.abp_stairs
                    if abp_s.abp_confirmed
                    and abp_s.abp_name
                    and abp_stair_role(abp_s, abp_upper_floor=True)
                    in (abpStairRole.abp_DOWN, abpStairRole.abp_OUTSIDE)
                )
            else:
                abp_goals = tuple(
                    abp_e.abp_name for abp_e in abp_plan.abp_exits if abp_e.abp_confirmed
                )
                abp_goals += tuple(
                    abp_z.abp_name for abp_z in abp_plan.abp_safe_zones if abp_z.abp_name
                )
                abp_goals += tuple(
                    abp_s.abp_name
                    for abp_s in abp_plan.abp_stairs
                    if abp_s.abp_confirmed
                    and abp_s.abp_name
                    and abp_s.abp_use is abpStairUse.abp_OUTSIDE
                )
            abp_goals = tuple(
                abp_g for abp_g in abp_goals if abp_g not in abp_scenario.abp_blocked_exits
            )
            abp_out += [
                abpRouteSource(
                    abp_r.abp_name,
                    abp_plan.abp_level,
                    abp_people.get((abp_plan.abp_level, abp_r.abp_name), 0),
                    abp_goals,
                )
                for abp_r in abp_plan.abp_rooms
            ]
            abp_above = abp_ordered[abp_index + 1] if abp_index + 1 < len(abp_ordered) else None
            if abp_above is None:
                continue
            with contextlib.suppress(abpMultiFloorError):
                abp_pairs = abp_pair_stairs(abp_above, abp_plan)
                abp_arrive = sorted(
                    {abp_plan.abp_stairs[abp_j].abp_name for abp_j in abp_pairs.values()} - {""}
                )
                abp_out += [
                    abpRouteSource(abp_n, abp_plan.abp_level, 0, abp_goals, abp_from_stair=True)
                    for abp_n in abp_arrive
                ]
        return tuple(abp_out)

    def abp_profiles_for(
        self, abp_scenario: abpScenario, abp_profiles: Sequence[abpPersonProfile] | None = None
    ) -> list[abpPersonProfile]:
        abp_base = list(abp_profiles) if abp_profiles is not None else self.abp_profiles()
        if abp_scenario.abp_reaction_factor == 1.0 and abp_scenario.abp_speed_factor == 1.0:
            return abp_base
        return [
            dataclasses.replace(
                abp_p,
                abp_max_speed_mps=abp_p.abp_max_speed_mps * abp_scenario.abp_speed_factor,
                abp_reaction_mean_s=abp_p.abp_reaction_mean_s * abp_scenario.abp_reaction_factor,
                abp_reaction_std_s=abp_p.abp_reaction_std_s * abp_scenario.abp_reaction_factor,
            )
            for abp_p in abp_base
        ]

    def abp_simulate(
        self,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        abp_profiles: Sequence[abpPersonProfile] | None = None,
        *,
        abp_progress: Callable[[float], None] | None = None,
        abp_should_cancel: Callable[[], bool] | None = None,
        abp_record: bool = True,
    ) -> abpSimulationOutput:
        abp_floors = abp__as_floors(abp_plan)
        abp_profiles = self.abp_profiles_for(abp_scenario, abp_profiles)
        if len(abp_floors) > 1:
            return self.abp__simulate_building(
                abp_floors,
                abp_scenario,
                abp_profiles,
                abp_progress=abp_progress,
                abp_should_cancel=abp_should_cancel,
            )
        abp_plan = abp_floors[0]
        abp_scale = self.abp__validate(abp_plan, abp_scenario)
        abp_grid = abp_build_grid(abp_plan, abp_blocked_exits=abp_scenario.abp_blocked_exits)
        abp_distance = abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )
        abp_rooms = [
            abpRoomArea(
                abp_r.abp_name, abp_plan.abp_level, abp_polygon_to_m(abp_r.abp_area, abp_scale)
            )
            for abp_r in abp_plan.abp_rooms
        ]
        abp_rng = np.random.default_rng(abp_scenario.abp_seed)
        try:
            abp_agents = abp_spawn_agents(
                abp_grid,
                abp_distance,
                abp_rooms,
                abp_scenario.abp_occupancies,
                abp_profiles,
                abp_rng,
                self.abp_params,
            )
        except abpPopulationError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        try:
            abp_guides = abp_guides_for(abp_grid, abp_distance, abp_plan, abp_scenario.abp_routes)
        except abpRouteError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        abp_order = {abp_key: abp_k for abp_k, abp_key in enumerate(abp_guides)}
        abp_simulation = abpSimulation(
            abp_grid,
            abp_agents,
            self.abp_params,
            abp_seed=abp_scenario.abp_seed,
            abp_profile_names=[abp_p.abp_name for abp_p in abp_profiles],
            abp_distance=abp_distance,
            abp_record=abp_record,
            abp_guides=[abp_g.abp_distance for abp_g in abp_guides.values()],
            abp_guide_of=abp_guide_per_agent(
                abp_scenario.abp_occupancies, abp_plan.abp_level, abp_order
            ),
        )
        try:
            return abp_simulation.abp_run(
                abp_progress=abp_progress, abp_should_cancel=abp_should_cancel
            )
        except abpSimulationCancelled as abp_exc:
            raise abpOperationCancelled from abp_exc

    def abp__simulate_building(
        self,
        abp_floors: Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        abp_profiles: Sequence[abpPersonProfile] | None,
        *,
        abp_progress: Callable[[float], None] | None,
        abp_should_cancel: Callable[[], bool] | None,
    ) -> abpSimulationOutput:
        self.abp__validate_building(abp_floors, abp_scenario)
        try:
            abp_simulation = abpMultiFloorSimulation(
                abp_floors,
                abp_scenario.abp_occupancies,
                list(abp_profiles) if abp_profiles is not None else self.abp_profiles(),
                self.abp_params,
                abp_seed=abp_scenario.abp_seed,
                abp_blocked_exits=abp_scenario.abp_blocked_exits,
                abp_routes=abp_scenario.abp_routes,
            )
            return abp_simulation.abp_run(
                abp_progress=abp_progress, abp_should_cancel=abp_should_cancel
            )
        except (abpMultiFloorError, abpRouteError) as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        except abpSimulationCancelled as abp_exc:
            raise abpOperationCancelled from abp_exc

    def abp__store(
        self,
        abp_project_id: int,
        abp_floors: Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        abp_output: abpSimulationOutput,
        abp_statistics: abpRunStatistics | None = None,
    ) -> abpSimulationRun:
        abp_by_level = {abp_f.abp_level: abp_f for abp_f in abp_floors}
        abp_multi = len(abp_floors) > 1
        abp_observations = tuple(
            self.abp__congestion(abp_b, abp_by_level.get(abp_b.abp_level, abp_floors[0]), abp_multi)
            for abp_b in abp_output.abp_result.abp_bottlenecks[:5]
        )
        abp_norm_observations = (
            self.abp__norms.abp_evaluate_building(abp_floors, abp_scenario).abp_observations
            if self.abp__norms is not None
            else ()
        )
        abp_scales = tuple(
            (abp_f.abp_level, abp_f.abp_scale_m_per_px or 1.0) for abp_f in abp_floors
        )
        abp_scale = abp_floors[0].abp_scale_m_per_px or 1.0
        abp_fingerprint = self.abp_fingerprint(abp_floors, abp_scenario)
        abp_scenario_id = self.abp_save_scenario(abp_project_id, abp_scenario)
        abp_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        abp_path = (
            self.abp_project_runs_dir(abp_project_id)
            / f"escenario_{abp_scenario_id}_{abp_stamp}.npz"
        )
        abp_save_run(abp_path, abp_output.abp_result, abp_output.abp_trajectories)
        abp_result = dataclasses.replace(abp_output.abp_result, abp_trajectories_path=str(abp_path))
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_simulation_id = abp_uow.abp_simulations.abp_add(
                abp_scenario_id,
                abp_result,
                abp_observations + abp_norm_observations,
                abp_statistics,
                abp_fingerprint,
            )
        return abpSimulationRun(
            abp_simulation_id,
            abp_result,
            abp_output.abp_trajectories,
            abp_observations,
            abp_scale,
            abp_scales,
            abp_statistics,
            abp_fingerprint,
        )

    def abp_last_run(
        self, abp_project_id: int, abp_name: str = abp_BASE_SCENARIO
    ) -> abpSimulationRun | None:
        abp_plan_scale = None
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                abp_scenario_id = abp_uow.abp_scenarios.abp_find_id(abp_project_id, abp_name)
            except abpNotFoundError:
                return None
            abp_runs = abp_uow.abp_simulations.abp_list_all(abp_scenario_id)
            if not abp_runs:
                return None
            abp_simulation_id, abp_summary = abp_runs[-1]
            abp_observations = tuple(
                abp_o
                for abp_o in abp_uow.abp_simulations.abp_observations(abp_simulation_id)
                if abp_o.abp_kind is abpObservationType.abp_CONGESTION
            )
            abp_levels = abp_uow.abp_floors.abp_levels(abp_project_id)
            if not abp_levels:
                return None
            abp_scales = tuple(
                (
                    abp_level,
                    abp_uow.abp_floors.abp_get(abp_project_id, abp_level).abp_scale_m_per_px or 1.0,
                )
                for abp_level in abp_levels
            )
            abp_plan_scale = abp_scales[0][1]
        if abp_summary.abp_trajectories_path is None or abp_plan_scale is None:
            return None
        try:
            abp_stored = abp_load_run(Path(abp_summary.abp_trajectories_path))
        except (OSError, ValueError, KeyError):
            return None
        abp_result = abpSimulationResult(
            abp_seed=abp_summary.abp_seed,
            abp_total_time_s=abp_summary.abp_total_time_s,
            abp_time_per_exit_s=abp_summary.abp_time_per_exit_s,
            abp_curve_times_s=abp_stored.abp_curve_times_s,
            abp_curve_evacuated=abp_stored.abp_curve_evacuated,
            abp_density_map=abp_stored.abp_density_map,
            abp_bottlenecks=abp_stored.abp_bottlenecks,
            abp_trajectories_path=abp_summary.abp_trajectories_path,
            abp_agents_total=abp_stored.abp_agents_total,
            abp_agents_evacuated=abp_stored.abp_agents_evacuated,
            abp_completed=abp_stored.abp_completed,
            abp_grid_origin_m=abp_stored.abp_grid_origin_m,
            abp_cell_size_m=abp_stored.abp_cell_size_m,
            abp_floor_maps=abp_stored.abp_floor_maps,
        )
        return abpSimulationRun(
            abp_simulation_id,
            abp_result,
            abp_stored.abp_trajectories,
            abp_observations,
            abp_plan_scale,
            abp_scales,
            abp_summary.abp_statistics,
            abp_summary.abp_fingerprint,
        )

    @staticmethod
    def abp__validate(abp_plan: abpFloorPlan, abp_scenario: abpScenario) -> float:
        if abp_plan.abp_scale_m_per_px is None:
            raise abpUserFacingError("Primero defina la escala del plano (paso 2).")
        abp_usable_exits = [
            abp_e
            for abp_e in abp_plan.abp_exits
            if abp_e.abp_confirmed and abp_e.abp_name not in abp_scenario.abp_blocked_exits
        ]
        abp_zones = [
            abp_z
            for abp_z in abp_plan.abp_safe_zones
            if not (abp_z.abp_name and abp_z.abp_name in abp_scenario.abp_blocked_exits)
        ]
        abp_outside = any(
            abp_s.abp_confirmed and abp_s.abp_use is abpStairUse.abp_OUTSIDE
            for abp_s in abp_plan.abp_stairs
        )
        if not abp_usable_exits and not abp_zones and not abp_outside:
            raise abpUserFacingError(abp__NO_EXITS.format(floor=""))
        if not abp_plan.abp_rooms:
            raise abpUserFacingError("Primero marque los ambientes del local (paso 4).")
        if abp_scenario.abp_total_occupants == 0:
            raise abpUserFacingError("Indique cuántas personas hay en cada ambiente (paso 4).")
        return abp_plan.abp_scale_m_per_px

    def abp__validate_building(
        self, abp_floors: Sequence[abpFloorPlan], abp_scenario: abpScenario
    ) -> None:
        for abp_plan in abp_floors:
            if abp_plan.abp_scale_m_per_px is None:
                raise abpUserFacingError(
                    f"El piso {abp_plan.abp_level + 1} no tiene escala; defínala en el paso 2."
                )
        if not any(abp_plan.abp_rooms for abp_plan in abp_floors):
            raise abpUserFacingError("Primero marque los ambientes del local (paso 4).")
        if abp_scenario.abp_total_occupants == 0:
            raise abpUserFacingError("Indique cuántas personas hay en cada ambiente (paso 4).")
        abp_lowest = min(abp_floors, key=lambda abp_f: abp_f.abp_level)
        abp_usable = [
            abp_e
            for abp_e in abp_lowest.abp_exits
            if abp_e.abp_confirmed and abp_e.abp_name not in abp_scenario.abp_blocked_exits
        ]
        if not abp_usable and not abp_lowest.abp_safe_zones:
            raise abpUserFacingError(
                abp__NO_EXITS.format(floor=f" del piso {abp_lowest.abp_level + 1}")
            )

    @staticmethod
    def abp__congestion(
        abp_bottleneck: abpBottleneck, abp_plan: abpFloorPlan, abp_multi: bool = False
    ) -> abpObservation:
        abp_scale = abp_plan.abp_scale_m_per_px or 1.0
        abp_place = abp_describe_place(abp_plan, abp_scale, abp_bottleneck.abp_location)
        if abp_multi:
            abp_place = f"en el piso {abp_bottleneck.abp_level + 1}, {abp_place}"
        return abpObservation(
            abp_kind=abpObservationType.abp_CONGESTION,
            abp_description=abp_CONGESTION_TEXT.format(
                place=abp_place,
                density=abp_bottleneck.abp_mean_density,
                duration=abp_bottleneck.abp_duration_s,
            ),
            abp_recommendation=abp_CONGESTION_ADVICE,
            abp_location=abp_bottleneck.abp_location,
        )


def abp__as_floors(abp_plan: abpFloorPlan | Sequence[abpFloorPlan]) -> list[abpFloorPlan]:
    if isinstance(abp_plan, abpFloorPlan):
        return [abp_plan]
    abp_floors = sorted(abp_plan, key=lambda abp_f: abp_f.abp_level)
    if not abp_floors:
        raise abpUserFacingError("No hay pisos para simular.")
    return abp_floors


def abp_scale_occupancies(
    abp_occupancies: Sequence[abpOccupancy], abp_target_total: int
) -> tuple[abpOccupancy, ...]:
    abp_current = sum(abp_o.abp_count for abp_o in abp_occupancies)
    if abp_current == 0 or abp_target_total <= 0:
        return ()
    abp_exact = [abp_o.abp_count * abp_target_total / abp_current for abp_o in abp_occupancies]
    abp_counts = [math.floor(abp_x) for abp_x in abp_exact]
    abp_order = sorted(
        range(len(abp_exact)), key=lambda abp_i: (-(abp_exact[abp_i] - abp_counts[abp_i]), abp_i)
    )
    for abp_i in abp_order[: abp_target_total - sum(abp_counts)]:
        abp_counts[abp_i] += 1
    return tuple(
        dataclasses.replace(abp_o, abp_count=abp_c)
        for abp_o, abp_c in zip(abp_occupancies, abp_counts, strict=True)
        if abp_c > 0
    )


def abp_describe_place(abp_plan: abpFloorPlan, abp_scale: float, abp_point_m: abpPoint) -> str:
    abp_best_name, abp_best_dist = "", 2.5
    for abp_exit_ in abp_plan.abp_exits:
        abp_seg = abp_segment_to_m(abp_exit_.abp_segment, abp_scale)
        abp_dist = abp_seg.abp_midpoint.abp_distance_to(abp_point_m)
        if abp_dist < abp_best_dist:
            abp_best_name, abp_best_dist = f"junto a «{abp_exit_.abp_name}»", abp_dist
    if not abp_best_name:
        for abp_door in abp_plan.abp_doors:
            if (
                abp_segment_to_m(abp_door.abp_segment, abp_scale).abp_midpoint.abp_distance_to(
                    abp_point_m
                )
                < 1.5
            ):
                abp_best_name = "junto a una puerta"
                break
    for abp_room in abp_plan.abp_rooms:
        abp_polygon = abp_polygon_to_m(abp_room.abp_area, abp_scale)
        if abp__inside(abp_polygon.abp_vertices, abp_point_m):
            abp_suffix = (
                f" de «{abp_room.abp_name}»" if abp_best_name else f"en «{abp_room.abp_name}»"
            )
            return (abp_best_name + abp_suffix) if abp_best_name else abp_suffix.strip()
    return abp_best_name or "en un pasillo o zona de circulación"


def abp__inside(abp_vertices: tuple[abpPoint, ...], abp_p: abpPoint) -> bool:
    abp_inside = False
    abp_j = len(abp_vertices) - 1
    for abp_i, abp_vi in enumerate(abp_vertices):
        abp_vj = abp_vertices[abp_j]
        if (abp_vi.abp_y > abp_p.abp_y) != (abp_vj.abp_y > abp_p.abp_y):
            abp_x_cross = (abp_vj.abp_x - abp_vi.abp_x) * (abp_p.abp_y - abp_vi.abp_y) / (
                abp_vj.abp_y - abp_vi.abp_y
            ) + abp_vi.abp_x
            if abp_p.abp_x < abp_x_cross:
                abp_inside = not abp_inside
        abp_j = abp_i
    return abp_inside
