from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpRoomRoute
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute
from abp_rutasegura.abp_engines.abp_navigation.abp_astar import abp_astar, abpCell
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import (
    abp_distance_field,
    abp_weighted_distance_field,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_landing_cells,
    abp_polygon_to_m,
    abpNavGrid,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_routes import (
    abp_descend,
    abp_room_routes,
    abp_to_points,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea

abpFloatArray = npt.NDArray[np.float64]
abpBoolArray = npt.NDArray[np.bool_]

abp_CORRIDOR_M = 0.7
abp_FADE_M = 0.6
abp_OFF_ROUTE = 6.0
abp_OTHER_EXIT = 25.0
abp_SNAP_M = 1.5

abpRouteKey = tuple[int, bool, str]


class abpRouteError(ValueError):
    pass


@dataclass(frozen=True, eq=False)
class abpGuidedRoute:
    abp_route: abpManualRoute
    abp_distance: abpFloatArray
    abp_path_m: tuple[abpPoint, ...]
    abp_target_name: str


def abp_source_mask(
    abp_grid: abpNavGrid,
    abp_distance: abpFloatArray,
    abp_plan: abpFloorPlan,
    abp_source: str,
    *,
    abp_from_stair: bool,
) -> abpBoolArray | None:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_usable = abp_grid.abp_walkable & np.isfinite(abp_distance) & ~abp_grid.abp_targets
    abp_mask = np.zeros(abp_grid.abp_shape, np.bool_)
    if not abp_from_stair:
        for abp_room in abp_plan.abp_rooms:
            if abp_room.abp_name == abp_source:
                abp_mask = (
                    abp_grid.abp_polygon_mask(abp_polygon_to_m(abp_room.abp_area, abp_scale))
                    & abp_usable
                )
    for abp_index, abp_stair in enumerate(abp_plan.abp_stairs if abp_from_stair else ()):
        if not abp_stair.abp_confirmed or abp_stair.abp_name != abp_source:
            continue
        abp_area = abp_polygon_to_m(abp_stair.abp_area, abp_scale)
        if abp_index not in abp_grid.abp_closed_stairs:
            abp_mask = abp_grid.abp_polygon_mask(abp_area) & abp_usable
            continue
        abp_entry = abp_stair.abp_entry
        abp_foot = (
            abpPoint(abp_entry.abp_x * abp_scale, abp_entry.abp_y * abp_scale)
            if abp_entry is not None
            else None
        )
        abp_cells = abp_landing_cells(abp_grid, abp_distance, abp_area, abp_foot)
        if abp_cells.size:
            abp_mask[abp_grid.abp_to_cell(abp_cells)] = True
    return np.asarray(abp_mask, np.bool_) if abp_mask.any() else None


def abp_guide(
    abp_grid: abpNavGrid,
    abp_distance: abpFloatArray,
    abp_plan: abpFloorPlan,
    abp_route: abpManualRoute,
) -> abpGuidedRoute | None:
    if abp_route.abp_is_empty:
        return None
    abp_mask = abp_source_mask(
        abp_grid,
        abp_distance,
        abp_plan,
        abp_route.abp_source,
        abp_from_stair=abp_route.abp_from_stair,
    )
    if abp_mask is None:
        return None
    abp_goal = abp_grid.abp_targets
    if abp_route.abp_exit_name:
        if abp_route.abp_exit_name not in abp_grid.abp_target_names:
            return None
        abp_goal = abp_grid.abp_target_ids == abp_grid.abp_target_names.index(
            abp_route.abp_exit_name
        )
    abp_goal = np.asarray(abp_goal & abp_grid.abp_walkable, np.bool_)
    abp_line = abp__line(
        abp_grid, abp_distance, abp_route, abp_mask, abp_goal, abp_plan.abp_scale_m_per_px or 1.0
    )
    abp_cost = abp__cost(abp_grid, abp_line, abp_mask, abp_goal)
    abp_field = abp_weighted_distance_field(
        abp_grid.abp_walkable, abp_goal, abp_cost, abp_grid.abp_cell_size
    )
    abp_path = abp_descend(abp_grid, abp_field, abp_line[0])
    abp_target = int(abp_grid.abp_target_ids[abp_path[-1]])
    abp_name = abp_grid.abp_target_names[abp_target] if abp_target >= 0 else ""
    return abpGuidedRoute(abp_route, abp_field, abp_to_points(abp_grid, abp_path), abp_name)


def abp_guides_for(
    abp_grid: abpNavGrid,
    abp_distance: abpFloatArray,
    abp_plan: abpFloorPlan,
    abp_routes: Sequence[abpManualRoute],
) -> dict[abpRouteKey, abpGuidedRoute]:
    abp_out: dict[abpRouteKey, abpGuidedRoute] = {}
    for abp_route in abp_routes:
        if abp_route.abp_level == abp_plan.abp_level:
            abp_guided = abp_guide(abp_grid, abp_distance, abp_plan, abp_route)
            if abp_guided is not None:
                abp_out[abp_route.abp_key] = abp_guided
    return abp_out


def abp_apply_guides(
    abp_grid: abpNavGrid,
    abp_plan: abpFloorPlan,
    abp_routes: Sequence[abpRoomRoute],
    abp_guides: Mapping[abpRouteKey, abpGuidedRoute],
) -> tuple[abpRoomRoute, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_areas = {
        abp_r.abp_name: abp_polygon_to_m(abp_r.abp_area, abp_scale) for abp_r in abp_plan.abp_rooms
    }
    abp_out: list[abpRoomRoute] = []
    for abp_route in abp_routes:
        abp_guided = abp_guides.get((abp_route.abp_level, False, abp_route.abp_room_name))
        abp_own: tuple[abpRoomRoute, ...] = ()
        if abp_guided is not None and abp_route.abp_room_name in abp_areas:
            abp_area = abpRoomArea(
                abp_route.abp_room_name, abp_route.abp_level, abp_areas[abp_route.abp_room_name]
            )
            abp_own = abp_room_routes(abp_grid, abp_guided.abp_distance, [abp_area])
        if abp_guided is None or not abp_own:
            abp_out.append(abp_route)
            continue
        abp_far = abp_own[0].abp_farthest_path_m
        abp_out.append(
            dataclasses.replace(
                abp_own[0],
                abp_path_m=abp_guided.abp_path_m,
                abp_target_name=abp_guided.abp_target_name,
                abp_max_distance_m=round(
                    sum(
                        abp_a.abp_distance_to(abp_b) for abp_a, abp_b in itertools.pairwise(abp_far)
                    ),
                    2,
                ),
                abp_manual=True,
            )
        )
    return tuple(abp_out)


def abp__line(
    abp_grid: abpNavGrid,
    abp_distance: abpFloatArray,
    abp_route: abpManualRoute,
    abp_mask: abpBoolArray,
    abp_goal: abpBoolArray,
    abp_scale: float,
) -> list[abpCell]:
    abp_rows, abp_cols = np.nonzero(abp_mask)
    abp_centers = abp_grid.abp_cell_centers(abp_rows, abp_cols)
    abp_middle = abp_centers.mean(axis=0)
    abp_first = int(np.argmin(np.hypot(*(abp_centers - abp_middle).T)))
    abp_line: list[abpCell] = [(int(abp_rows[abp_first]), int(abp_cols[abp_first]))]
    for abp_number, abp_point in enumerate(abp_route.abp_waypoints, start=1):
        abp_cell = abp__snap(
            abp_grid,
            abp_distance,
            abpPoint(abp_point.abp_x * abp_scale, abp_point.abp_y * abp_scale),
        )
        abp_leg = (
            abp_astar(abp_grid.abp_walkable, abp_line[-1], abp_cell)
            if abp_cell is not None
            else None
        )
        if abp_leg is None:
            raise abpRouteError(
                f"La ruta a mano de «{abp_route.abp_source}» pasa por un punto al que no se puede llegar "
                f"(el {abp_number}.º). Muévalo a un pasillo o vuelva a la ruta automática."
            )
        abp_line += abp_leg[1:]
    abp_rest = abp_distance_field(abp_grid.abp_walkable, abp_goal, abp_grid.abp_cell_size)
    if not np.isfinite(abp_rest[abp_line[-1]]):
        raise abpRouteError(
            f"Desde «{abp_route.abp_source}» no se puede llegar a «{abp_route.abp_exit_name}». Elija otra salida "
            "o vuelva a la ruta automática."
        )
    return abp_line + abp_descend(abp_grid, abp_rest, abp_line[-1])[1:]


def abp__snap(
    abp_grid: abpNavGrid, abp_distance: abpFloatArray, abp_point: abpPoint
) -> abpCell | None:
    abp_rows, abp_cols = np.nonzero(abp_grid.abp_walkable & np.isfinite(abp_distance))
    if abp_rows.size == 0:
        return None
    abp_centers = abp_grid.abp_cell_centers(abp_rows, abp_cols)
    abp_away = np.hypot(abp_centers[:, 0] - abp_point.abp_x, abp_centers[:, 1] - abp_point.abp_y)
    abp_k = int(np.argmin(abp_away))
    return (int(abp_rows[abp_k]), int(abp_cols[abp_k])) if abp_away[abp_k] <= abp_SNAP_M else None


def abp__cost(
    abp_grid: abpNavGrid,
    abp_line: Sequence[abpCell],
    abp_mask: abpBoolArray,
    abp_goal: abpBoolArray,
) -> abpFloatArray:
    abp_off = np.ones(abp_grid.abp_shape, np.uint8)
    for abp_r, abp_c in abp_line:
        abp_off[abp_r, abp_c] = 0
    abp_away = (
        cv2.distanceTransform(abp_off, cv2.DIST_L2, 5).astype(np.float64) * abp_grid.abp_cell_size
    )
    abp_cost = 1.0 + np.clip(abp_away / abp_CORRIDOR_M, 0.0, 1.0)
    abp_cost += (abp_OFF_ROUTE - 2.0) * np.clip((abp_away - abp_CORRIDOR_M) / abp_FADE_M, 0.0, 1.0)
    abp_cost[abp_mask] = 1.0
    abp_cost[abp_grid.abp_targets & ~abp_goal] = abp_OTHER_EXIT
    return np.asarray(abp_cost, np.float64)
