from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path

import abp_rutasegura
from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_projects import abpProjectService
from abp_rutasegura.abp_application.abp_simulation_service import abpSimulationService
from abp_rutasegura.abp_data.abp_evacuation_sheet import (
    abp_format_time,
    abp_SCALES,
    abp_SHEET_SIZES,
    abp_write_evacuation_sheet,
    abpRoomNote,
    abpRouteSummary,
    abpSheetContent,
    abpSheetFloor,
    abpSheetOptions,
    abpZoneSummary,
)
from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSign
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork, abpRoomEscape, abpRoomRoute
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan
from abp_rutasegura.abp_engines.abp_navigation.abp_evac_tree import (
    abp_evacuation_network,
    abp_evacuation_time,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_polygon_to_m
from abp_rutasegura.abp_engines.abp_navigation.abp_sign_proposals import abp_propose_signs
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import abp_furniture_segments

abp_SHEET_PAPERS: tuple[str, ...] = tuple(abp_SHEET_SIZES)
abp_LEVEL_NAMES = ("Primer nivel", "Segundo nivel", "Tercer nivel", "Cuarto nivel")
abp_NOT_FOR_COMING_DOWN = (
    abpStairUse.abp_SAME_FLOOR,
    abpStairUse.abp_OUTSIDE,
    abpStairUse.abp_CLOSED,
)
abp_STAIR_PREFIX = "\x00escalera:"

__all__ = [
    "abp_SCALES",
    "abp_SHEET_PAPERS",
    "abpSheetOptions",
    "abpSheetService",
    "abp_format_time",
]


class abpSheetService:
    def __init__(
        self,
        abp_projects: abpProjectService,
        abp_simulations: abpSimulationService,
        abp_norms: abpNormsService,
    ) -> None:
        self.abp__projects = abp_projects
        self.abp__simulations = abp_simulations
        self.abp__norms = abp_norms

    @staticmethod
    def abp_network(
        abp_plan: abpFloorPlan,
        abp_people: Mapping[str, int],
        *,
        abp_vector: abpVectorPlan | None = None,
        abp_upper_floor: bool = False,
        abp_from_stairs: bool = False,
        abp_blocked: Sequence[str] = (),
        abp_manual: Sequence[abpRoomRoute] = (),
    ) -> abpEvacuationNetwork:
        abp_scale = abp_plan.abp_scale_m_per_px
        if abp_scale is None:
            raise abpUserFacingError("Primero defina la escala del plano (paso 2).")
        abp_used = [
            abp_r for abp_r in abp_plan.abp_rooms if abp_people.get(abp_r.abp_name, 0) > 0
        ] or list(abp_plan.abp_rooms)
        abp_rooms = [
            abpRoomArea(
                abp_r.abp_name, abp_plan.abp_level, abp_polygon_to_m(abp_r.abp_area, abp_scale)
            )
            for abp_r in abp_used
        ]
        if abp_from_stairs:
            abp_rooms += [
                abpRoomArea(
                    abp_STAIR_PREFIX + (abp_st.abp_name or f"#{abp_i}"),
                    abp_plan.abp_level,
                    abp_polygon_to_m(abp_st.abp_area, abp_scale),
                )
                for abp_i, abp_st in enumerate(abp_plan.abp_stairs)
                if abp_st.abp_confirmed and abp_st.abp_use not in abp_NOT_FOR_COMING_DOWN
            ]
        abp_chosen = {
            abp_r.abp_name: abp_r.abp_exit_name
            for abp_r in abp_plan.abp_rooms
            if abp_r.abp_exit_name
        }
        abp_followed = [
            abp_r
            for abp_r in abp_manual
            if abp_r.abp_level == abp_plan.abp_level
            and abp_chosen.get(abp_r.abp_room_name, abp_r.abp_target_name) == abp_r.abp_target_name
        ]
        abp_guided = {
            (abp_STAIR_PREFIX if abp_r.abp_from_stair else "")
            + abp_r.abp_room_name: abp_r.abp_target_name
            for abp_r in abp_followed
        }
        abp_clutter = (
            abp_furniture_segments(abp_vector, abp_plan) * abp_scale
            if abp_vector is not None
            else None
        )
        try:
            return abp_evacuation_network(
                abp_plan,
                abp_rooms,
                abp_blocked_exits=abp_blocked,
                abp_upper_floor=abp_upper_floor,
                abp_clutter_m=abp_clutter,
                abp_assigned={**abp_guided, **abp_chosen},
                abp_preferred_m=[abp_r.abp_path_m for abp_r in abp_followed],
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    def abp_manual_routes(
        self, abp_floors: Sequence[abpFloorPlan], abp_scenario: abpScenario | None
    ) -> tuple[abpRoomRoute, ...]:
        if abp_scenario is None or not abp_scenario.abp_routes:
            return ()
        abp_everything = dataclasses.replace(abp_scenario, abp_blocked_exits=frozenset())
        return tuple(
            abp_r
            for abp_r in self.abp__simulations.abp_routes(abp_floors, abp_everything)
            if abp_r.abp_manual
        )

    def abp_people_by_room(
        self, abp_floors: Sequence[abpFloorPlan], abp_scenario: abpScenario | None, abp_source: str
    ) -> dict[tuple[int, str], int]:
        abp_counts: dict[tuple[int, str], int] = {}
        for abp_c in self.abp__norms.abp_evaluate_building(abp_floors, abp_scenario).abp_capacities:
            abp_use_capacity = abp_source == "aforo" and abp_c.abp_capacity is not None
            abp_counts[(abp_c.abp_level, abp_c.abp_room_name)] = (
                abp_c.abp_capacity
                if abp_use_capacity and abp_c.abp_capacity is not None
                else abp_c.abp_occupants
            )
        return abp_counts

    def abp_content(self, abp_project_id: int, abp_options: abpSheetOptions) -> abpSheetContent:
        abp_project = self.abp__projects.abp_get_project(abp_project_id)
        abp_floors = [
            abp_f
            for abp_f in self.abp__projects.abp_load_floors(abp_project_id)
            if abp_f.abp_is_scaled
        ]
        if not abp_floors:
            raise abpUserFacingError("Primero cargue el plano y defina su escala (pasos 1 y 2).")
        if (
            not any(abp_e.abp_confirmed for abp_e in abp_floors[0].abp_exits)
            and not abp_floors[0].abp_safe_zones
        ):
            raise abpUserFacingError(
                "El primer piso no tiene salidas confirmadas: no hay rutas que dibujar (paso 3)."
            )
        if not any(abp_f.abp_rooms for abp_f in abp_floors):
            raise abpUserFacingError("Primero marque los ambientes del local (paso 4).")
        abp_scenario = self.abp__simulations.abp_load_scenario(abp_project_id)
        abp_people = self.abp_people_by_room(
            abp_floors, abp_scenario, abp_options.abp_people_source
        )
        abp_manual = self.abp_manual_routes(abp_floors, abp_scenario)
        abp_networks: list[abpEvacuationNetwork] = []
        for abp_index, abp_plan in enumerate(abp_floors):
            abp_vector = (
                self.abp__projects.abp_load_floor_vector(abp_plan)
                if abp_options.abp_follow_furniture
                else None
            )
            abp_networks.append(
                self.abp_network(
                    abp_plan,
                    {
                        abp_name: abp_n
                        for (abp_level, abp_name), abp_n in abp_people.items()
                        if abp_level == abp_plan.abp_level
                    },
                    abp_vector=abp_vector,
                    abp_upper_floor=abp_index > 0,
                    abp_from_stairs=abp_index == 0
                    and any(abp_st.abp_confirmed for abp_st in abp_plan.abp_stairs),
                    abp_manual=abp_manual,
                )
            )
        abp_notes, abp_routes = self.abp__times(abp_floors, abp_networks, abp_people, abp_options)
        abp_zones = abp__zone_summaries(abp_floors[0], abp_networks[0], abp_notes)
        if not abp_notes:
            raise abpUserFacingError(
                "Ningún ambiente con personas llega a una salida. Revise las puertas (paso 3)."
            )
        abp_sheets: list[abpSheetFloor] = []
        for abp_plan, abp_network in zip(abp_floors, abp_networks, strict=True):
            abp_on_floor = {
                abp_name: abp_n
                for (abp_level, abp_name), abp_n in abp_people.items()
                if abp_level == abp_plan.abp_level
            }
            abp_extra = (
                abp_propose_signs(abp_plan, abp_network, abp_on_floor)
                if abp_options.abp_propose_signs
                else ()
            )
            abp_sheets.append(
                abpSheetFloor(
                    abp_plan=abp_plan,
                    abp_network=dataclasses.replace(
                        abp_network,
                        abp_escapes=tuple(
                            abp_e
                            for abp_e in abp_network.abp_escapes
                            if not abp__is_stair(abp_e.abp_room_name)
                        ),
                    ),
                    abp_notes=tuple(
                        abp_n for abp_n in abp_notes if abp_n.abp_level == abp_plan.abp_level
                    ),
                    abp_signs=(*abp_plan.abp_signs, *abp_extra),
                    abp_image=self.abp__projects.abp_load_floor_image(abp_plan)
                    if abp_options.abp_underlay == "original"
                    else None,
                )
            )
        abp_run = self.abp__simulations.abp_last_run(abp_project_id)
        return abpSheetContent(
            abp_project=abp_project,
            abp_floors=tuple(abp_sheets),
            abp_routes=abp_routes,
            abp_zones=abp_zones,
            abp_options=abp_options,
            abp_level_names=tuple(
                abp_LEVEL_NAMES[abp_f.abp_level]
                if abp_f.abp_level < len(abp_LEVEL_NAMES)
                else f"Nivel {abp_f.abp_level + 1}"
                for abp_f in abp_floors
            ),
            abp_simulated_s=abp_run.abp_result.abp_total_time_s if abp_run is not None else None,
            abp_app_version=abp_rutasegura.__version__,
        )

    def abp__times(
        self,
        abp_floors: Sequence[abpFloorPlan],
        abp_networks: Sequence[abpEvacuationNetwork],
        abp_people: Mapping[tuple[int, str], int],
        abp_options: abpSheetOptions,
    ) -> tuple[tuple[abpRoomNote, ...], tuple[abpRouteSummary, ...]]:
        abp_lowest = abp_floors[0]
        abp_order = [abp_e.abp_name for abp_e in abp_lowest.abp_exits if abp_e.abp_confirmed] + [
            abp_z.abp_name for abp_z in abp_lowest.abp_safe_zones
        ]
        abp_from_stair = {
            abp_e.abp_room_name.removeprefix(abp_STAIR_PREFIX): abp_e
            for abp_e in abp_networks[0].abp_escapes
            if abp__is_stair(abp_e.abp_room_name)
        }
        abp_widths = {
            abp_e.abp_name: abp_e.abp_segment.abp_length * (abp_lowest.abp_scale_m_per_px or 1.0)
            for abp_e in abp_lowest.abp_exits
        }
        abp_raw: list[tuple[abpRoomEscape, int, float, str]] = []
        for abp_plan, abp_network in zip(abp_floors, abp_networks, strict=True):
            for abp_escape in abp_network.abp_escapes:
                abp_count = abp_people.get((abp_plan.abp_level, abp_escape.abp_room_name), 0)
                if abp__is_stair(abp_escape.abp_room_name) or abp_count <= 0:
                    continue
                abp_distance, abp_target = (
                    abp_escape.abp_distance_m + abp_escape.abp_meeting_distance_m,
                    abp_escape.abp_target_name,
                )
                if abp_plan is not abp_lowest:
                    abp_below = abp_from_stair.get(abp_target) or next(
                        iter(abp_from_stair.values()), None
                    )
                    abp_down = (
                        abp_plan.abp_level - abp_lowest.abp_level
                    ) * self.abp__simulations.abp_params.abp_stair_travel_m
                    abp_distance += abp_down
                    if abp_below is not None:
                        abp_distance += abp_below.abp_distance_m + abp_below.abp_meeting_distance_m
                        abp_target = abp_below.abp_target_name
                abp_raw.append((abp_escape, abp_count, abp_distance, abp_target))
        abp_targets = sorted(
            {abp_t for *_, abp_t in abp_raw},
            key=lambda abp_t: (abp_order.index(abp_t) if abp_t in abp_order else 99, abp_t),
        )
        abp_by_room = abp_options.abp_identify == "ambiente"
        abp_ordered = sorted(
            abp_raw, key=lambda abp_x: (abp_targets.index(abp_x[3]), abp_x[0].abp_level, abp_x[2])
        )
        abp_room_ids = {
            (abp_e.abp_level, abp_e.abp_room_name): f"R{abp_i}"
            for abp_i, (abp_e, *abp__rest) in enumerate(abp_ordered, start=1)
        }
        abp_ids = {abp_t: f"R{abp_i}" for abp_i, abp_t in enumerate(abp_targets, start=1)}
        abp_notes = tuple(
            abpRoomNote(
                abp_room_name=abp_escape.abp_room_name,
                abp_level=abp_escape.abp_level,
                abp_people=abp_count,
                abp_door_width_m=abp_escape.abp_door_width_m or abp_widths.get(abp_target, 1.0),
                abp_distance_m=round(abp_distance, 2),
                abp_time_s=round(
                    abp_evacuation_time(
                        abp_count,
                        abp_escape.abp_door_width_m or abp_widths.get(abp_target, 1.0),
                        abp_distance,
                        abp_options.abp_flow,
                        abp_options.abp_speed,
                    ),
                    2,
                ),
                abp_route_id=abp_room_ids[(abp_escape.abp_level, abp_escape.abp_room_name)]
                if abp_by_room
                else abp_ids[abp_target],
                abp_exit_name=abp_target,
            )
            for abp_escape, abp_count, abp_distance, abp_target in abp_raw
        )
        abp_routes: list[abpRouteSummary] = []
        if abp_by_room:
            for abp_n in sorted(abp_notes, key=lambda abp_n: int(abp_n.abp_route_id[1:])):
                abp_routes.append(
                    abpRouteSummary(
                        abp_n.abp_route_id,
                        abp_n.abp_exit_name,
                        abp_n.abp_people,
                        abp_n.abp_distance_m,
                        abp_n.abp_time_s,
                        abp_n.abp_room_name,
                    )
                )
            return abp_notes, tuple(abp_routes)
        for abp_target in abp_targets:
            abp_mine = [abp_n for abp_n in abp_notes if abp_n.abp_exit_name == abp_target]
            abp_worst = max(abp_mine, key=lambda abp_n: abp_n.abp_time_s)
            abp_routes.append(
                abpRouteSummary(
                    abp_ids[abp_target],
                    abp_target,
                    sum(abp_n.abp_people for abp_n in abp_mine),
                    abp_worst.abp_distance_m,
                    abp_worst.abp_time_s,
                )
            )
        return abp_notes, tuple(abp_routes)

    def abp_propose_signs(
        self,
        abp_floors: Sequence[abpFloorPlan],
        abp_level: int,
        abp_scenario: abpScenario | None,
        abp_vector: abpVectorPlan | None = None,
    ) -> tuple[abpSign, ...]:
        abp_ordered = sorted(abp_floors, key=lambda abp_f: abp_f.abp_level)
        abp_plan = next(abp_f for abp_f in abp_ordered if abp_f.abp_level == abp_level)
        if not abp_plan.abp_is_scaled or not abp_plan.abp_rooms:
            return ()
        abp_people = self.abp_people_by_room(
            [abp_f for abp_f in abp_ordered if abp_f.abp_is_scaled], abp_scenario, "aforo"
        )
        abp_on_floor = {
            abp_name: abp_n
            for (abp_lv, abp_name), abp_n in abp_people.items()
            if abp_lv == abp_level
        }
        abp_upper = abp_level != abp_ordered[0].abp_level
        abp_network = self.abp_network(
            abp_plan,
            abp_on_floor,
            abp_vector=abp_vector,
            abp_upper_floor=abp_upper,
            abp_manual=self.abp_manual_routes(abp_ordered, abp_scenario),
        )
        return abp_propose_signs(abp_plan, abp_network, abp_on_floor)

    def abp_generate(
        self, abp_project_id: int, abp_path: Path, abp_options: abpSheetOptions
    ) -> Path:
        if abp_path.suffix.lower() != ".pdf":
            abp_path = abp_path.with_suffix(".pdf")
        abp_content = self.abp_content(abp_project_id, abp_options)
        try:
            abp_write_evacuation_sheet(abp_path, abp_content)
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo guardar la lámina: {abp_exc}") from abp_exc
        return abp_path


def abp__zone_summaries(
    abp_plan: abpFloorPlan, abp_network: abpEvacuationNetwork, abp_notes: Sequence[abpRoomNote]
) -> tuple[abpZoneSummary, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_goal: dict[str, int] = {}
    for abp_exit_name, abp_points in abp_network.abp_meeting_links:
        abp_end = abp_points[-1]
        abp_distances = [
            min(
                abpPoint(abp_v.abp_x * abp_scale, abp_v.abp_y * abp_scale).abp_distance_to(abp_end)
                for abp_v in abp_z.abp_area.abp_vertices
            )
            for abp_z in abp_plan.abp_safe_zones
        ]
        abp_goal.setdefault(abp_exit_name, abp_distances.index(min(abp_distances)))
    abp_out: list[abpZoneSummary] = []
    for abp_index, abp_zone in enumerate(abp_plan.abp_safe_zones):
        abp_mine = [abp_n for abp_n in abp_notes if abp_goal.get(abp_n.abp_exit_name) == abp_index]
        abp_worst = max(abp_mine, key=lambda abp_n: abp_n.abp_time_s, default=None)
        abp_xs = [abp_v.abp_x for abp_v in abp_zone.abp_area.abp_vertices]
        abp_ys = [abp_v.abp_y for abp_v in abp_zone.abp_area.abp_vertices]
        abp_radius = (max(abp_xs) - min(abp_xs) + max(abp_ys) - min(abp_ys)) / 4 * abp_scale
        abp_out.append(
            abpZoneSummary(
                abp_number=abp_index + 1,
                abp_name=abp_zone.abp_name or f"Zona de reunión {abp_index + 1}",
                abp_radius_m=round(abp_radius, 2),
                abp_people=sum(abp_n.abp_people for abp_n in abp_mine),
                abp_distance_m=abp_worst.abp_distance_m if abp_worst is not None else 0.0,
                abp_time_s=abp_worst.abp_time_s if abp_worst is not None else 0.0,
                abp_route_ids=tuple(
                    sorted(
                        {abp_n.abp_route_id for abp_n in abp_mine},
                        key=lambda abp_r: (len(abp_r), abp_r),
                    )
                ),
            )
        )
    return tuple(abp_out)


def abp__is_stair(abp_name: str) -> bool:
    return abp_name.startswith(abp_STAIR_PREFIX)
