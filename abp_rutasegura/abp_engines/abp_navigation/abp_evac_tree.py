from __future__ import annotations

import dataclasses
import heapq
import itertools
import math
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpCellType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import (
    abpEvacuationNetwork,
    abpRoomEscape,
    abpRouteBranch,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import (
    abp_NEIGHBORS,
    abp_wall_distance,
    abp_weighted_distance_field,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_build_grid,
    abp_polygon_to_m,
    abp_segment_to_m,
    abpNavGrid,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea

abpFloatArray = npt.NDArray[np.float64]
abpBoolArray = npt.NDArray[np.bool_]
abpIntArray = npt.NDArray[np.int64]
abpCell = tuple[int, int]

abp_CELL_M = 0.2
abp_COMFORT_M = 0.8
abp_NETWORK_COST = 0.5
abp_CLUTTER_COST = 14.0
abp_TURN_COST_M = 0.9
abp_COVER_M = 2.6
abp_COVER_CLUTTERED_M = 1.25
abp_MAX_BRANCHES = 10
abp_MIN_PENDING = 0.07
abp_MIN_BRANCH_M = 1.8
abp_SIMPLIFY_M = 0.28
abp_ROOM_CROSSING = 4.0
abp_CHAIR_COST = 6.0
abp_SKEW_DEG = 6.0
abp_CLOSED_STAIR_COST = 80.0
abp_PREFERRED_COST = 0.3
abp_PREFERRED_M = 0.5
abp_GUIDED_GAIN = 0.8
abp_EDGE_COST = 10.0
abp_OTHER_ZONE = 1.8
abp_CIRCULATION = ("PASILLO", "HALL", "CORREDOR", "VESTIBULO", "INGRESO", "SALIDA", "PASADIZO")
abp_DOOR_STEP_M = 0.55


def abp_evacuation_time(
    abp_people: int, abp_width_m: float, abp_distance_m: float, abp_k: float, abp_v: float
) -> float:
    if abp_width_m <= 0 or abp_k <= 0 or abp_v <= 0:
        raise ValueError("El ancho, K y V deben ser positivos.")
    return abp_people / (abp_width_m * abp_k) + abp_distance_m / abp_v


def abp_evacuation_network(
    abp_plan: abpFloorPlan,
    abp_rooms: Sequence[abpRoomArea],
    *,
    abp_blocked_exits: Collection[str] = (),
    abp_upper_floor: bool = False,
    abp_clutter_m: abpFloatArray | None = None,
    abp_cell_size: float = abp_CELL_M,
    abp_assigned: Mapping[str, str] | None = None,
    abp_preferred_m: Sequence[Sequence[abpPoint]] = (),
) -> abpEvacuationNetwork:
    abp_open_exits = {
        abp_e.abp_name
        for abp_e in abp_plan.abp_exits
        if abp_e.abp_confirmed and abp_e.abp_name not in abp_blocked_exits
    }
    abp_chosen = {
        abp_r: abp_e for abp_r, abp_e in (abp_assigned or {}).items() if abp_e in abp_open_exits
    }
    if abp_chosen and not abp_upper_floor:
        return abp__by_exit(
            abp_plan,
            abp_rooms,
            abp_chosen,
            abp_open_exits,
            abp_blocked_exits,
            abp_clutter_m,
            abp_cell_size,
            abp_preferred_m,
        )
    abp_grid = abp_build_grid(
        dataclasses.replace(abp_plan, abp_obstacles=()),
        abp_blocked_exits=abp_blocked_exits,
        abp_cell_size=abp_cell_size,
        abp_margin_m=2.0,
        abp_stairs_as_targets=abp_upper_floor,
        abp_exits_as_targets=not abp_upper_floor,
        abp_keep_stairs=True,
    )
    abp_floor = abp__Floor.abp_build(abp_plan, abp_grid, abp_clutter_m, abp_preferred_m)
    abp_rooms = [abp_r for abp_r in abp_rooms if not abp_is_circulation(abp_r.abp_name)] or list(
        abp_rooms
    )
    for abp_room in sorted(
        abp_rooms,
        key=lambda abp_r: (-abp__room_reach(abp_grid, abp_r, abp_floor.abp_dist), abp_r.abp_name),
    ):
        abp_floor.abp_cover_room(abp_room)
    abp_branches = tuple(
        abpRouteBranch(abp_points, abp_plan.abp_level, abp_target, abp_trunk)
        for abp_region in abp_floor.abp_regions
        for abp_points, abp_target, abp_trunk in abp_region.abp_branches(abp_floor)
    )
    abp_links = () if abp_upper_floor else abp__meeting_links(abp_plan, abp_grid)
    abp_meeting = {abp_name: abp_points for abp_name, abp_points in reversed(abp_links)}
    abp_escapes: list[abpRoomEscape] = []
    for abp_room in abp_rooms:
        if abp_room.abp_name not in abp_floor.abp_first_start:
            continue
        abp_points, abp_target = abp_floor.abp_full_path(
            *abp_floor.abp_first_start[abp_room.abp_name]
        )
        abp_outside = abp_meeting.get(abp_target, ())
        abp_escapes.append(
            abpRoomEscape(
                abp_room_name=abp_room.abp_name,
                abp_level=abp_plan.abp_level,
                abp_target_name=abp_target,
                abp_door_width_m=abp__first_door_width(abp_points, abp_floor.abp_openings),
                abp_distance_m=round(abp__length(abp_points), 2),
                abp_meeting_distance_m=round(abp__length(abp_outside), 2),
                abp_path_m=abp_points,
            )
        )
    return abpEvacuationNetwork(abp_plan.abp_level, abp_branches, tuple(abp_escapes), abp_links)


def abp__by_exit(
    abp_plan: abpFloorPlan,
    abp_rooms: Sequence[abpRoomArea],
    abp_chosen: Mapping[str, str],
    abp_open_exits: Collection[str],
    abp_blocked: Collection[str],
    abp_clutter_m: abpFloatArray | None,
    abp_cell_size: float,
    abp_preferred_m: Sequence[Sequence[abpPoint]],
) -> abpEvacuationNetwork:
    abp_parts: list[abpEvacuationNetwork] = []
    abp_moving = [abp_r for abp_r in abp_rooms if not abp_is_circulation(abp_r.abp_name)] or list(
        abp_rooms
    )
    abp_free = [abp_r for abp_r in abp_moving if abp_r.abp_name not in abp_chosen]
    abp_base = abp_evacuation_network(
        abp_plan,
        abp_free,
        abp_blocked_exits=abp_blocked,
        abp_clutter_m=abp_clutter_m,
        abp_cell_size=abp_cell_size,
        abp_preferred_m=abp_preferred_m,
    )
    abp_groups = {abp_e.abp_room_name: abp_e.abp_target_name for abp_e in abp_base.abp_escapes}
    abp_fixed = set(abp_chosen.values())
    abp_missing: set[str] = set()
    for abp_target in (*sorted(abp_fixed), ""):
        abp_group = [
            abp_r
            for abp_r in abp_moving
            if abp_chosen.get(abp_r.abp_name, abp__shared(abp_groups, abp_r.abp_name, abp_fixed))
            == abp_target
        ]
        if not abp_target:
            abp_group += [abp_r for abp_r in abp_moving if abp_r.abp_name in abp_missing]
        if not abp_group:
            continue
        abp_shut = set(abp_blocked) | (
            {abp_e for abp_e in abp_open_exits if abp_e != abp_target} if abp_target else set()
        )
        abp_part = abp_evacuation_network(
            abp_plan,
            abp_group,
            abp_blocked_exits=abp_shut,
            abp_clutter_m=abp_clutter_m,
            abp_cell_size=abp_cell_size,
            abp_preferred_m=abp_preferred_m,
        )
        abp_parts.append(abp_part)
        abp_missing |= {abp_r.abp_name for abp_r in abp_group} - {
            abp_e.abp_room_name for abp_e in abp_part.abp_escapes
        }
    abp_everything = abp__meeting_links(
        abp_plan,
        abp_build_grid(
            abp_plan, abp_blocked_exits=abp_blocked, abp_cell_size=abp_cell_size, abp_margin_m=2.0
        ),
    )
    return abpEvacuationNetwork(
        abp_plan.abp_level,
        tuple(abp_b for abp_p in abp_parts for abp_b in abp_p.abp_branches),
        tuple(abp_e for abp_p in abp_parts for abp_e in abp_p.abp_escapes),
        abp_everything,
    )


def abp__shared(abp_groups: Mapping[str, str], abp_room: str, abp_fixed: Collection[str]) -> str:
    abp_target = abp_groups.get(abp_room, "")
    return abp_target if abp_target in abp_fixed else ""


def abp_is_circulation(abp_name: str) -> bool:
    abp_decomposed = unicodedata.normalize("NFKD", abp_name)
    abp_clean = "".join(
        abp_c for abp_c in abp_decomposed if not unicodedata.combining(abp_c)
    ).upper()
    return abp_clean.startswith(abp_CIRCULATION)


def abp__length(abp_points: Sequence[abpPoint]) -> float:
    return sum(abp_a.abp_distance_to(abp_b) for abp_a, abp_b in itertools.pairwise(abp_points))


def abp__near_lines(abp_grid: abpNavGrid, abp_lines: Sequence[Sequence[abpPoint]]) -> abpBoolArray:
    abp_mask = np.zeros(abp_grid.abp_shape, np.uint8)
    abp_thick = max(1, round(2 * abp_PREFERRED_M / abp_grid.abp_cell_size))
    for abp_line in abp_lines:
        cv2.polylines(abp_mask, [abp_grid.abp__to_cv(abp_line)], False, 1, abp_thick, cv2.LINE_8, 4)
    return np.asarray(abp_mask > 0, np.bool_)


def abp__clutter_mask(abp_grid: abpNavGrid, abp_segments: abpFloatArray | None) -> abpBoolArray:
    abp_mask = np.zeros(abp_grid.abp_shape, np.uint8)
    if abp_segments is not None:
        for abp_x1, abp_y1, abp_x2, abp_y2 in abp_segments:
            abp_pts = abp_grid.abp__to_cv(
                [abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2)]
            ).reshape(2, 2)
            cv2.line(
                abp_mask,
                (int(abp_pts[0][0]), int(abp_pts[0][1])),
                (int(abp_pts[1][0]), int(abp_pts[1][1])),
                1,
                1,
                cv2.LINE_8,
                4,
            )
        abp_passages = np.isin(
            abp_grid.abp_cells, [int(abpCellType.abp_DOOR), int(abpCellType.abp_EXIT)]
        ).astype(np.uint8)
        abp_mask[cv2.dilate(abp_passages, np.ones((5, 5), np.uint8)) > 0] = 0
    return np.asarray(abp_mask > 0, np.bool_)


def abp__blocked_by_furniture(abp_plan: abpFloorPlan, abp_grid: abpNavGrid) -> abpBoolArray:
    abp_mask = np.zeros(abp_grid.abp_shape, np.bool_)
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    for abp_obstacle in abp_plan.abp_obstacles:
        abp_mask |= abp_grid.abp_polygon_mask(abp_polygon_to_m(abp_obstacle.abp_area, abp_scale))
    abp_passages = np.isin(
        abp_grid.abp_cells, [int(abpCellType.abp_DOOR), int(abpCellType.abp_EXIT)]
    ).astype(np.uint8)
    abp_mask[cv2.dilate(abp_passages, np.ones((5, 5), np.uint8)) > 0] = False
    return abp_mask


def abp__cost(
    abp_clearance: abpFloatArray,
    abp_clutter: abpBoolArray,
    abp_cell_size: float,
    abp_loose: abpBoolArray | None = None,
    abp_furniture: abpBoolArray | None = None,
) -> abpFloatArray:
    abp_cost: abpFloatArray = (
        1.0 + 2.5 * np.clip(1.0 - abp_clearance / abp_COMFORT_M, 0.0, 1.0) ** 2
    )
    if abp_clutter.any():
        abp_free = (~abp_clutter).astype(np.uint8)
        abp_away = (
            cv2.distanceTransform(abp_free, cv2.DIST_L2, 5).astype(np.float64) * abp_cell_size
        )
        abp_cost += 1.2 * np.clip(1.0 - abp_away / 0.6, 0.0, 1.0) ** 2
        abp_cost[abp_clutter] += abp_CLUTTER_COST
    if abp_loose is not None and abp_furniture is not None and abp_furniture.any():
        abp_cost[abp_loose] += abp_CHAIR_COST - abp_CLUTTER_COST
        abp_cost[abp_furniture] += abp_CLUTTER_COST
    return np.asarray(abp_cost, np.float64)


@dataclass(frozen=True, eq=False)
class abp__Portal:
    abp_region: int
    abp_inner: abpFloatArray
    abp_through: tuple[abpFloatArray, ...]
    abp_next_region: int
    abp_target_name: str
    abp_cost: float


@dataclass(eq=False)
class abp__Region:
    abp_index: int
    abp_angle: float
    abp_origin: abpFloatArray
    abp_size: float
    abp_walk: list[list[bool]]
    abp_cost: list[list[float]]
    abp_portals: list[abp__Portal]
    abp_root_of: dict[abpCell, int]
    abp_next: dict[abpCell, abpCell | None] = field(default_factory=dict)
    abp_starts: list[abpCell] = field(default_factory=list)
    abp_lead_in: dict[abpCell, abpFloatArray] = field(default_factory=dict)
    abp_skewed: abpBoolArray | None = None
    abp_guided: bool = False

    @property
    def abp_shape(self) -> abpCell:
        return len(self.abp_walk), len(self.abp_walk[0])

    def abp_to_world(self, abp_cells: abpFloatArray) -> abpFloatArray:
        abp_x, abp_y = abp_cells[:, 1] * self.abp_size, abp_cells[:, 0] * self.abp_size
        abp_c, abp_si = math.cos(self.abp_angle), math.sin(self.abp_angle)
        abp_out = np.c_[
            self.abp_origin[0] + abp_x * abp_c - abp_y * abp_si,
            self.abp_origin[1] + abp_x * abp_si + abp_y * abp_c,
        ]
        return np.asarray(abp_out, np.float64)

    def abp_to_cell(self, abp_point: abpFloatArray) -> abpCell:
        abp_d = abp_point - self.abp_origin
        abp_c, abp_si = math.cos(self.abp_angle), math.sin(self.abp_angle)
        abp_x, abp_y = abp_d[0] * abp_c + abp_d[1] * abp_si, -abp_d[0] * abp_si + abp_d[1] * abp_c
        return round(abp_y / self.abp_size), round(abp_x / self.abp_size)

    def abp_nearest_walkable(self, abp_point: abpFloatArray) -> abpCell | None:
        abp_r0, abp_c0 = self.abp_to_cell(abp_point)
        abp_rows, abp_cols = self.abp_shape
        abp_best: tuple[float, abpCell] | None = None
        for abp_dr in range(-5, 6):
            for abp_dc in range(-5, 6):
                abp_r, abp_c = abp_r0 + abp_dr, abp_c0 + abp_dc
                if 0 <= abp_r < abp_rows and 0 <= abp_c < abp_cols and self.abp_walk[abp_r][abp_c]:
                    abp_d = math.hypot(abp_dr, abp_dc)
                    if abp_best is None or abp_d < abp_best[0]:
                        abp_best = (abp_d, (abp_r, abp_c))
        return abp_best[1] if abp_best is not None else None

    def abp_aligned(self, abp_start: abpCell | None) -> abpCell | None:
        if abp_start is None:
            return None
        for abp_root in self.abp_root_of:
            for abp_cell in ((abp_start[0], abp_root[1]), (abp_root[0], abp_start[1])):
                abp_shift = abs(abp_cell[0] - abp_start[0]) + abs(abp_cell[1] - abp_start[1])
                if 0 < abp_shift <= 2 and self.abp_walk[abp_cell[0]][abp_cell[1]]:
                    return abp_cell
        return abp_start

    def abp_search(self, abp_start: abpCell, *, abp_straight: bool) -> list[abpCell]:
        abp_steps = abp_NEIGHBORS[:4] if abp_straight else abp_NEIGHBORS
        abp_rows, abp_cols = self.abp_shape
        abp_heap: list[tuple[float, int, abpCell, int]] = [(0.0, 0, abp_start, -1)]
        abp_best: dict[tuple[abpCell, int], float] = {(abp_start, -1): 0.0}
        abp_came: dict[tuple[abpCell, int], tuple[abpCell, int]] = {}
        abp_counter = 0
        abp_end: tuple[abpCell, int] | None = None
        while abp_heap:
            abp_g, _, abp_cell, abp_direction = heapq.heappop(abp_heap)
            if abp_direction == -2:
                abp_end = abp_came[(abp_cell, -2)]
                break
            if abp_g > abp_best[(abp_cell, abp_direction)] + 1e-12:
                continue
            if abp_cell in self.abp_root_of:
                abp_total = abp_g + self.abp_portals[self.abp_root_of[abp_cell]].abp_cost
                abp_key = (abp_cell, -2)
                if abp_total < abp_best.get(abp_key, math.inf):
                    abp_best[abp_key] = abp_total
                    abp_came[abp_key] = (abp_cell, abp_direction)
                    abp_counter += 1
                    heapq.heappush(abp_heap, (abp_total, abp_counter, abp_cell, -2))
            abp_r, abp_c = abp_cell
            for abp_k, (abp_dr, abp_dc, abp_step) in enumerate(abp_steps):
                abp_nr, abp_nc = abp_r + abp_dr, abp_c + abp_dc
                if (
                    not (0 <= abp_nr < abp_rows and 0 <= abp_nc < abp_cols)
                    or not self.abp_walk[abp_nr][abp_nc]
                ):
                    continue
                if (
                    abp_dr
                    and abp_dc
                    and not (self.abp_walk[abp_nr][abp_c] and self.abp_walk[abp_r][abp_nc])
                ):
                    continue
                abp_other = (abp_nr, abp_nc)
                abp_price = (
                    abp_step
                    * self.abp_size
                    * 0.5
                    * (self.abp_cost[abp_r][abp_c] + self.abp_cost[abp_nr][abp_nc])
                )
                abp_on_network = abp_cell in self.abp_next and abp_other in self.abp_next
                if abp_on_network:
                    abp_price *= abp_NETWORK_COST
                if abp_direction not in (-1, abp_k) and not (
                    abp_on_network and abp_cell != abp_start
                ):
                    abp_price += abp_TURN_COST_M if abp_straight else 0.1 * abp_TURN_COST_M
                abp_state = (abp_other, abp_k)
                if abp_g + abp_price < abp_best.get(abp_state, math.inf) - 1e-12:
                    abp_best[abp_state] = abp_g + abp_price
                    abp_came[abp_state] = (abp_cell, abp_direction)
                    abp_counter += 1
                    heapq.heappush(abp_heap, (abp_g + abp_price, abp_counter, abp_other, abp_k))
        if abp_end is None:
            return []
        abp_path = [abp_end[0]]
        abp_state = abp_end
        while abp_state in abp_came:
            abp_state = abp_came[abp_state]
            abp_path.append(abp_state[0])
        abp_path.reverse()
        for abp_k, abp_cell in enumerate(abp_path):
            if abp_cell in self.abp_next:
                return abp_path[: abp_k + 1]
        return abp_path

    def abp_route(self, abp_start: abpCell) -> list[abpCell]:
        abp_straight = self.abp_search(abp_start, abp_straight=True)
        abp_free = self.abp_search(abp_start, abp_straight=False)
        if not abp_straight or not abp_free:
            return abp_straight or abp_free
        if self.abp_guided and self.abp__price(abp_free) < abp_GUIDED_GAIN * self.abp__price(
            abp_straight
        ):
            return abp_free
        if self.abp_follows_shape(abp_free):
            return abp_free
        return (
            abp_straight
            if self.abp__bends(abp_straight) <= max(2, self.abp__bends(abp_free))
            else abp_free
        )

    def abp__price(self, abp_path: Sequence[abpCell]) -> float:
        return sum(
            math.hypot(abp_b[0] - abp_a[0], abp_b[1] - abp_a[1])
            * 0.5
            * (self.abp_cost[abp_a[0]][abp_a[1]] + self.abp_cost[abp_b[0]][abp_b[1]])
            for abp_a, abp_b in itertools.pairwise(abp_path)
        )

    def abp__bends(self, abp_path: Sequence[abpCell]) -> int:
        abp_points = self.abp_simplify(abp_path)
        abp_inner = [
            float(np.hypot(*(abp_b - abp_a))) for abp_a, abp_b in itertools.pairwise(abp_points)
        ][1:-1]
        return len(abp_points) - 2 + sum(1 for abp_x in abp_inner if abp_x < 1.0)

    def abp_add(self, abp_path: Sequence[abpCell]) -> None:
        self.abp_starts.append(abp_path[0])
        for abp_a, abp_b in itertools.pairwise(abp_path):
            self.abp_next.setdefault(abp_a, abp_b)
        self.abp_next.setdefault(abp_path[-1], None)

    def abp_joints(self) -> set[abpCell]:
        abp_into: dict[abpCell, int] = {}
        for abp_following in self.abp_next.values():
            if abp_following is not None:
                abp_into[abp_following] = abp_into.get(abp_following, 0) + 1
        abp_starts = set(self.abp_starts)
        return {abp_c for abp_c, abp_n in abp_into.items() if abp_n >= 2 or abp_c in abp_starts}

    def abp_chain(self, abp_start: abpCell, abp_stop: Collection[abpCell]) -> list[abpCell]:
        abp_chain = [abp_start]
        while (abp_following := self.abp_next.get(abp_chain[-1])) is not None:
            abp_chain.append(abp_following)
            if abp_following in abp_stop:
                break
        return abp_chain

    def abp_simplify(self, abp_chain: Sequence[abpCell]) -> list[abpFloatArray]:
        if self.abp_follows_shape(abp_chain):
            return abp__drop_flat(self.abp__pull(abp_chain))
        abp_points = self.abp_to_world(np.array(abp_chain, np.float64).reshape(-1, 2))
        return abp__drop_flat(self.abp__straighten(abp_points))

    def abp_follows_shape(self, abp_chain: Sequence[abpCell]) -> bool:
        if self.abp_skewed is None or len(abp_chain) < 4:
            return False
        abp_rows, abp_cols = np.array(abp_chain).T
        return float(self.abp_skewed[abp_rows, abp_cols].mean()) > 0.3

    def abp__pull(self, abp_chain: Sequence[abpCell]) -> list[abpFloatArray]:
        abp_costs = np.array([self.abp_cost[abp_r][abp_c] for abp_r, abp_c in abp_chain])
        abp_points = self.abp_to_world(np.array(abp_chain, np.float64).reshape(-1, 2))
        abp_out = [abp_points[0]]
        abp_i = 0
        while abp_i < len(abp_chain) - 1:
            abp_best = abp_i + 1
            for abp_j in range(abp_i + 2, len(abp_chain)):
                abp_allowed = 1.12 * float(abp_costs[abp_i : abp_j + 1].mean()) + 0.08
                if self.abp__mean_cost(abp_points[abp_i], abp_points[abp_j]) <= abp_allowed:
                    abp_best = abp_j
            abp_out.append(abp_points[abp_best])
            abp_i = abp_best
        return abp_out

    def abp__mean_cost(self, abp_a: abpFloatArray, abp_b: abpFloatArray) -> float:
        abp_n = max(2, math.ceil(float(np.hypot(*(abp_b - abp_a))) / (self.abp_size * 0.5)))
        abp_rows, abp_cols = self.abp_shape
        abp_total = 0.0
        for abp_t in np.linspace(0.0, 1.0, abp_n):
            abp_r, abp_c = self.abp_to_cell(abp_a + abp_t * (abp_b - abp_a))
            if not (
                0 <= abp_r < abp_rows and 0 <= abp_c < abp_cols and self.abp_walk[abp_r][abp_c]
            ):
                return math.inf
            abp_total += self.abp_cost[abp_r][abp_c]
        return abp_total / abp_n

    def abp__straighten(self, abp_run: abpFloatArray) -> list[abpFloatArray]:
        abp_a, abp_b = abp_run[0], abp_run[-1]
        if len(abp_run) <= 2:
            return [abp_a, abp_b]
        abp_d = abp_b - abp_a
        abp_length = float(np.hypot(abp_d[0], abp_d[1]))
        if abp_length < 1e-9:
            abp_off = np.hypot(abp_run[:, 0] - abp_a[0], abp_run[:, 1] - abp_a[1])
        else:
            abp_off = (
                np.abs(
                    (abp_run[:, 0] - abp_a[0]) * abp_d[1] - (abp_run[:, 1] - abp_a[1]) * abp_d[0]
                )
                / abp_length
            )
        abp_k = int(np.argmax(abp_off))
        if abp_off[abp_k] <= abp_SIMPLIFY_M and self.abp__clear(abp_a, abp_b):
            return [abp_a, abp_b]
        if abp_k in (0, len(abp_run) - 1):
            abp_k = len(abp_run) // 2
        return [
            *self.abp__straighten(abp_run[: abp_k + 1])[:-1],
            *self.abp__straighten(abp_run[abp_k:]),
        ]

    def abp__clear(self, abp_a: abpFloatArray, abp_b: abpFloatArray) -> bool:
        abp_n = max(2, math.ceil(float(np.hypot(*(abp_b - abp_a))) / (self.abp_size * 0.5)))
        abp_rows, abp_cols = self.abp_shape
        for abp_t in np.linspace(0.0, 1.0, abp_n):
            abp_r, abp_c = self.abp_to_cell(abp_a + abp_t * (abp_b - abp_a))
            if not (
                0 <= abp_r < abp_rows and 0 <= abp_c < abp_cols and self.abp_walk[abp_r][abp_c]
            ):
                return False
        return True

    def abp_part(
        self, abp_origin: abpCell, abp_joints: Collection[abpCell]
    ) -> tuple[list[abpFloatArray], abpCell]:
        abp_chain = self.abp_chain(abp_origin, abp_joints)
        abp_points = self.abp_simplify(abp_chain) if len(abp_chain) > 1 else []
        if abp_origin in self.abp_lead_in and abp_origin in self.abp_starts:
            abp_points = [
                self.abp_lead_in[abp_origin],
                *(abp_points or self.abp_simplify([abp_origin, abp_origin])[:1]),
            ]
        if abp_chain[-1] in self.abp_root_of and self.abp_next.get(abp_chain[-1]) is None:
            abp_portal = self.abp_portals[self.abp_root_of[abp_chain[-1]]]
            abp_points = [*abp_points, *abp_portal.abp_through[:1]] if abp_points else []
        return abp__drop_flat(abp_points) if len(abp_points) > 1 else [], abp_chain[-1]

    def abp_branches(self, abp_floor: abp__Floor) -> list[tuple[tuple[abpPoint, ...], str, bool]]:
        abp_joints = self.abp_joints()
        abp_out: list[tuple[tuple[abpPoint, ...], str, bool]] = []
        abp_done: set[abpCell] = set()
        for abp_origin in [*self.abp_starts, *sorted(abp_joints)]:
            if abp_origin in abp_done:
                continue
            abp_done.add(abp_origin)
            abp_points, abp_end = self.abp_part(abp_origin, abp_joints)
            if len(abp_points) < 2:
                continue
            abp_target = ""
            if abp_end in self.abp_root_of and self.abp_next.get(abp_end) is None:
                abp_target = self.abp_portals[self.abp_root_of[abp_end]].abp_target_name
            abp_trunk = abp_origin in abp_joints or abp_origin in self.abp_lead_in
            if not abp_trunk:
                abp_points = abp__trim_hook(abp_points)
            abp_out.append((abp__points(abp_points), abp_target, abp_trunk))
        return abp_out


def abp__points(abp_points: Sequence[abpFloatArray]) -> tuple[abpPoint, ...]:
    return tuple(abpPoint(float(abp_p[0]), float(abp_p[1])) for abp_p in abp_points)


@dataclass(eq=False)
class abp__Floor:
    abp_grid: abpNavGrid
    abp_walk: abpBoolArray
    abp_clearance: abpFloatArray
    abp_clutter: abpBoolArray
    abp_cost: abpFloatArray
    abp_dist: abpFloatArray
    abp_labels: abpIntArray
    abp_openings: list[abpSegment]
    abp_regions: list[abp__Region]
    abp_reachable: abpBoolArray
    abp_furniture: abpBoolArray | None = None
    abp_passage: abpBoolArray | None = None
    abp_guided: bool = False
    abp_first_start: dict[str, tuple[int, abpCell]] = field(default_factory=dict)

    @classmethod
    def abp_build(
        cls,
        abp_plan: abpFloorPlan,
        abp_grid: abpNavGrid,
        abp_clutter_m: abpFloatArray | None,
        abp_preferred_m: Sequence[Sequence[abpPoint]] = (),
    ) -> abp__Floor:
        abp_walk = abp_grid.abp_walkable
        abp_clearance, _ = abp_wall_distance(abp_walk, abp_grid.abp_cell_size)
        abp_clutter = abp__clutter_mask(abp_grid, abp_clutter_m)
        abp_furniture = abp__blocked_by_furniture(abp_plan, abp_grid)
        abp_loose = (
            abp_clutter & ~abp_furniture
            if abp_furniture.any()
            else np.zeros(abp_grid.abp_shape, np.bool_)
        )
        abp_clutter = abp_clutter | abp_furniture
        abp_cost = abp__cost(
            abp_clearance, abp_clutter, abp_grid.abp_cell_size, abp_loose, abp_furniture
        )
        for abp_index in abp_grid.abp_closed_stairs:
            abp_stair = abp_polygon_to_m(
                abp_plan.abp_stairs[abp_index].abp_area, abp_plan.abp_scale_m_per_px or 1.0
            )
            abp_cost[abp_grid.abp_polygon_mask(abp_stair)] += abp_CLOSED_STAIR_COST
        abp_crossing = abp_cost.copy()
        for abp_room in abp_plan.abp_rooms:
            if not abp_is_circulation(abp_room.abp_name):
                abp_area = abp_polygon_to_m(abp_room.abp_area, abp_plan.abp_scale_m_per_px or 1.0)
                abp_crossing[abp_grid.abp_polygon_mask(abp_area)] *= abp_ROOM_CROSSING
        if abp_preferred_m:
            abp_near = abp__near_lines(abp_grid, abp_preferred_m)
            abp_cost[abp_near] *= abp_PREFERRED_COST
            abp_crossing[abp_near] = abp_cost[abp_near]
        abp_dist = abp_weighted_distance_field(
            abp_walk, abp_grid.abp_targets, abp_crossing, abp_grid.abp_cell_size
        )
        abp_passing = (
            np.isin(abp_grid.abp_cells, [int(abpCellType.abp_DOOR), int(abpCellType.abp_EXIT)])
            | abp_grid.abp_targets
        )
        abp_body = (abp_walk & ~abp_passing & np.isfinite(abp_dist)).astype(np.uint8)
        abp_count, abp_raw = cv2.connectedComponents(abp_body, connectivity=4)
        abp_labels = np.asarray(abp_raw, np.int64) - 1
        abp_openings = abp__openings(abp_plan)
        abp_cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        abp_open_floor = abp_walk & ~(cv2.dilate(abp_clutter.astype(np.uint8), abp_cross) > 0)
        abp_reachable = np.isfinite(
            abp_weighted_distance_field(
                abp_open_floor, abp_grid.abp_targets, abp_cost, abp_grid.abp_cell_size
            )
        )
        abp_floor = cls(
            abp_grid,
            abp_walk,
            abp_clearance,
            abp_clutter,
            abp_cost,
            abp_dist,
            abp_labels,
            abp_openings,
            [],
            abp_reachable,
        )
        abp_floor.abp_furniture = abp_furniture
        abp_floor.abp_guided = bool(abp_preferred_m)
        abp_floor.abp_passage = np.zeros(abp_grid.abp_shape, np.bool_)
        for abp_room in abp_plan.abp_rooms:
            if abp_is_circulation(abp_room.abp_name):
                abp_floor.abp_passage |= abp_grid.abp_polygon_mask(
                    abp_polygon_to_m(abp_room.abp_area, abp_plan.abp_scale_m_per_px or 1.0)
                )
        abp_portals = [*abp_floor.abp__door_portals(abp_plan), *abp_floor.abp__area_portals()]
        abp_walls = [
            abp_segment_to_m(abp_w.abp_segment, abp_plan.abp_scale_m_per_px or 1.0)
            for abp_w in abp_plan.abp_walls
        ]
        for abp_index in range(abp_count - 1):
            abp_mine = [abp_p for abp_p in abp_portals if abp_p.abp_region == abp_index]
            abp_floor.abp_regions.append(abp_floor.abp__make_region(abp_index, abp_mine, abp_walls))
        return abp_floor

    def abp__label_at(self, abp_point: abpFloatArray) -> int:
        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_point[None, :])
        return int(self.abp_labels[abp_r[0], abp_c[0]])

    def abp__side(
        self, abp_middle: abpFloatArray, abp_normal: abpFloatArray
    ) -> tuple[abpFloatArray, int]:
        for abp_step in (abp_DOOR_STEP_M, 0.4, 0.7, 0.3, 0.9):
            abp_point = abp_middle + abp_normal * abp_step
            abp_label = self.abp__label_at(abp_point)
            if abp_label >= 0:
                return abp_point, abp_label
        return abp_middle + abp_normal * abp_DOOR_STEP_M, -1

    def abp__dist_at(self, abp_point: abpFloatArray) -> float:
        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_point[None, :])
        return float(self.abp_dist[abp_r[0], abp_c[0]])

    def abp__door_portals(self, abp_plan: abpFloorPlan) -> list[abp__Portal]:
        abp_scale = abp_plan.abp_scale_m_per_px or 1.0
        abp_out: list[abp__Portal] = []
        abp_names = set(self.abp_grid.abp_target_names)
        for abp_door in abp_plan.abp_doors:
            abp_s = abp_segment_to_m(abp_door.abp_segment, abp_scale)
            abp_middle, abp_normal = abp__middle_and_normal(abp_s)
            if abp_normal is None:
                continue
            (abp_a, abp_la), (abp_b, abp_lb) = (
                self.abp__side(abp_middle, abp_normal),
                self.abp__side(abp_middle, -abp_normal),
            )
            if abp_la < 0 or abp_lb < 0 or abp_la == abp_lb:
                continue
            abp_da, abp_db = self.abp__dist_at(abp_a), self.abp__dist_at(abp_b)
            if abp_da < abp_db:
                abp_a, abp_la, abp_da, abp_b, abp_lb, abp_db = (
                    abp_b,
                    abp_lb,
                    abp_db,
                    abp_a,
                    abp_la,
                    abp_da,
                )
            abp_out.append(abp__Portal(abp_la, abp_a, (abp_middle, abp_b), abp_lb, "", abp_db))
        for abp_exit_ in abp_plan.abp_exits:
            if abp_exit_.abp_name not in abp_names:
                continue
            abp_middle, abp_normal = abp__middle_and_normal(
                abp_segment_to_m(abp_exit_.abp_segment, abp_scale)
            )
            if abp_normal is None:
                continue
            for abp_sign in (1.0, -1.0):
                abp_point, abp_label = self.abp__side(abp_middle, abp_normal * abp_sign)
                if abp_label >= 0:
                    abp_out.append(
                        abp__Portal(
                            abp_label, abp_point, (abp_middle,), -1, abp_exit_.abp_name, 0.0
                        )
                    )
        return abp_out

    def abp__area_portals(self) -> list[abp__Portal]:
        abp_out: list[abp__Portal] = []
        abp_areas = np.isin(
            self.abp_grid.abp_cells, [int(abpCellType.abp_STAIR), int(abpCellType.abp_SAFE_ZONE)]
        )
        for abp_target, abp_name in enumerate(self.abp_grid.abp_target_names):
            abp_cells = (self.abp_grid.abp_target_ids == abp_target) & abp_areas
            if not abp_cells.any():
                continue
            abp_ring = cv2.dilate(abp_cells.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            for abp_label in np.unique(self.abp_labels[abp_ring & (self.abp_labels >= 0)]):
                abp_edge = np.argwhere(abp_ring & (self.abp_labels == abp_label))
                abp_open_side = self.abp_clearance[abp_edge[:, 0], abp_edge[:, 1]]
                abp_wide = abp_edge[abp_open_side >= 0.9 * abp_open_side.max()]
                abp_r, abp_c = abp_wide[len(abp_wide) // 2]
                abp_point = self.abp_grid.abp_cell_centers(np.array([abp_r]), np.array([abp_c]))[0]
                abp_inside = np.argwhere(abp_cells)
                abp_near = abp_inside[
                    int(np.argmin(np.hypot(abp_inside[:, 0] - abp_r, abp_inside[:, 1] - abp_c)))
                ]
                abp_goal = self.abp_grid.abp_cell_centers(abp_near[:1], abp_near[1:])[0]
                abp_out.append(
                    abp__Portal(int(abp_label), abp_point, (abp_goal,), -1, abp_name, 0.0)
                )
        return abp_out

    def abp__make_region(
        self, abp_index: int, abp_portals: list[abp__Portal], abp_walls: Sequence[abpSegment]
    ) -> abp__Region:
        abp_rows, abp_cols = np.nonzero(self.abp_labels == abp_index)
        abp_centers = self.abp_grid.abp_cell_centers(abp_rows, abp_cols)
        abp_angle = abp__dominant_angle(abp_centers, abp_walls)
        abp_size = self.abp_grid.abp_cell_size
        abp_anchor = abp_portals[0].abp_inner if abp_portals else abp_centers[0]
        abp_c, abp_si = math.cos(abp_angle), math.sin(abp_angle)
        abp_local = abp_centers - abp_anchor
        abp_x, abp_y = (
            abp_local[:, 0] * abp_c + abp_local[:, 1] * abp_si,
            -abp_local[:, 0] * abp_si + abp_local[:, 1] * abp_c,
        )
        abp_left, abp_top = (
            math.floor(abp_x.min() / abp_size) - 1,
            math.floor(abp_y.min() / abp_size) - 1,
        )
        abp_width = math.ceil(abp_x.max() / abp_size) + 2 - abp_left
        abp_height = math.ceil(abp_y.max() / abp_size) + 2 - abp_top
        abp_origin = abp_anchor + abp_size * np.array(
            [abp_left * abp_c - abp_top * abp_si, abp_left * abp_si + abp_top * abp_c]
        )
        abp_rr, abp_cc = np.mgrid[0:abp_height, 0:abp_width]
        abp_px = abp_origin[0] + abp_size * (abp_cc * abp_c - abp_rr * abp_si)
        abp_py = abp_origin[1] + abp_size * (abp_cc * abp_si + abp_rr * abp_c)
        abp_flat = np.c_[abp_px.ravel(), abp_py.ravel()]
        abp_gr, abp_gc = self.abp_grid.abp_to_cell(abp_flat)
        abp_gx = (abp_flat[:, 0] - self.abp_grid.abp_origin[0]) / abp_size
        abp_gy = (abp_flat[:, 1] - self.abp_grid.abp_origin[1]) / abp_size
        abp_valid = (
            (abp_gx >= 0)
            & (abp_gy >= 0)
            & (abp_gx < self.abp_grid.abp_shape[1])
            & (abp_gy < self.abp_grid.abp_shape[0])
        )
        abp_inside = (abp_valid & (self.abp_labels[abp_gr, abp_gc] == abp_index)).reshape(
            abp_height, abp_width
        )
        abp_cost = np.where(abp_valid, self.abp_cost[abp_gr, abp_gc], 1.0).reshape(
            abp_height, abp_width
        )
        abp_region = abp__Region(
            abp_index,
            abp_angle,
            abp_origin,
            abp_size,
            abp_inside.tolist(),
            abp_cost.tolist(),
            abp_portals,
            {},
        )
        abp_region.abp_guided = self.abp_guided
        if self.abp__is_open(abp_index):
            abp_region.abp_skewed = abp__skewed(abp_region, abp_walls)
        for abp_number, abp_portal in enumerate(abp_portals):
            abp_cell = abp_region.abp_nearest_walkable(abp_portal.abp_inner)
            if abp_cell is not None:
                abp_region.abp_root_of.setdefault(abp_cell, abp_number)
        return abp_region

    def abp__is_open(self, abp_index: int) -> bool:
        abp_area = self.abp_labels == abp_index
        if self.abp_passage is not None and float(self.abp_passage[abp_area].mean()) > 0.5:
            return True
        return float(self.abp_clutter[abp_area].mean()) < 0.03

    def abp_cover_room(self, abp_room: abpRoomArea) -> None:
        abp_grid, abp_dist = self.abp_grid, self.abp_dist
        abp_area = abp_grid.abp_polygon_mask(abp_room.abp_polygon_m) & (self.abp_labels >= 0)
        if not abp_area.any():
            return
        abp_good = abp_area & (self.abp_clearance >= 0.4) & ~self.abp_clutter
        abp_good &= self.abp_reachable if (abp_good & self.abp_reachable).any() else True
        abp_good = abp_good if abp_good.sum() >= 0.15 * abp_area.sum() else abp_area
        abp_cluttered = bool(self.abp_clutter[abp_area].any())
        abp_radius = abp_COVER_CLUTTERED_M if abp_cluttered else abp_COVER_M
        abp_tolerated = abp_MIN_PENDING if abp_cluttered else 2 * abp_MIN_PENDING
        abp_pending = abp_good & ~abp__within(
            self.abp__route_mask() & abp_area, abp_radius, abp_grid.abp_cell_size
        )
        abp_total = int(abp_good.sum())
        abp_second = not (self.abp_furniture is not None and (self.abp_furniture & abp_area).any())
        for _ in range(abp_MAX_BRANCHES):
            if (
                abp_room.abp_name in self.abp_first_start
                and abp_pending.sum() < abp_tolerated * abp_total
            ):
                break
            abp_candidates = abp_pending if abp_pending.any() else abp_good
            abp_flat = int(np.argmax(np.where(abp_candidates, abp_dist, -np.inf)))
            abp_r, abp_c = abp_flat // abp_dist.shape[1], abp_flat % abp_dist.shape[1]
            abp_point = abp_grid.abp_cell_centers(np.array([abp_r]), np.array([abp_c]))[0]
            abp_region = self.abp_regions[int(self.abp_labels[abp_r, abp_c])]
            abp_start = abp_region.abp_aligned(abp_region.abp_nearest_walkable(abp_point))
            abp_path = abp_region.abp_route(abp_start) if abp_start is not None else []
            abp_reached = np.zeros(abp_grid.abp_shape, np.bool_)
            abp_reached[abp_r, abp_c] = True
            if abp_path and abp_start is not None:
                abp_first = abp_room.abp_name not in self.abp_first_start
                if abp_first or (len(abp_path) - 1) * abp_region.abp_size >= abp_MIN_BRANCH_M:
                    if abp_start not in abp_region.abp_next:
                        abp_region.abp_add(abp_path)
                        self.abp__continue(abp_region, abp_path[-1])
                    if abp_first:
                        self.abp_first_start[abp_room.abp_name] = (abp_region.abp_index, abp_start)
                for abp_x in abp_region.abp_to_world(np.array(abp_path, np.float64)):
                    abp_gr, abp_gc = abp_grid.abp_to_cell(abp_x[None, :])
                    abp_reached[abp_gr[0], abp_gc[0]] = True
            elif not abp_candidates.any() or abp_room.abp_name not in self.abp_first_start:
                return
            abp_pending &= ~abp__within(abp_reached, abp_radius, abp_grid.abp_cell_size)
            if (
                not abp_second
                and abp_pending.sum() < abp_tolerated * abp_total
                and self.abp_furniture is not None
            ):
                abp_second = True
                abp_aisles = abp_area & ~self.abp_furniture & (self.abp_clearance >= 0.4)
                abp_aisles &= ~abp__within(self.abp_furniture, 0.3, abp_grid.abp_cell_size)
                abp_aisles &= ~abp__within(
                    self.abp__route_mask() & abp_area, abp_radius, abp_grid.abp_cell_size
                )
                abp_wide = cv2.morphologyEx(
                    abp_aisles.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)
                )
                abp_pending = np.asarray(abp_wide > 0, np.bool_)

    def abp__continue(self, abp_region: abp__Region, abp_end: abpCell) -> None:
        while abp_end in abp_region.abp_root_of and abp_region.abp_next.get(abp_end) is None:
            abp_portal = abp_region.abp_portals[abp_region.abp_root_of[abp_end]]
            if abp_portal.abp_next_region < 0:
                return
            abp_following = self.abp_regions[abp_portal.abp_next_region]
            abp_start = abp_following.abp_nearest_walkable(abp_portal.abp_through[1])
            if abp_start is None or abp_start in abp_following.abp_lead_in:
                return
            abp_following.abp_lead_in[abp_start] = abp_portal.abp_through[0]
            if abp_start in abp_following.abp_next:
                abp_following.abp_starts.append(abp_start)
                return
            abp_path = abp_following.abp_route(abp_start)
            if not abp_path:
                return
            abp_following.abp_add(abp_path)
            abp_region, abp_end = abp_following, abp_path[-1]

    def abp__route_mask(self) -> abpBoolArray:
        abp_mask = np.zeros(self.abp_grid.abp_shape, np.bool_)
        for abp_region in self.abp_regions:
            if abp_region.abp_next:
                abp_cells = np.array(list(abp_region.abp_next), np.float64)
                abp_r, abp_c = self.abp_grid.abp_to_cell(abp_region.abp_to_world(abp_cells))
                abp_mask[abp_r, abp_c] = True
        return abp_mask

    def abp_full_path(
        self, abp_region_index: int, abp_start: abpCell
    ) -> tuple[tuple[abpPoint, ...], str]:
        abp_points: list[abpFloatArray] = []
        abp_region, abp_origin = self.abp_regions[abp_region_index], abp_start
        abp_target = ""
        for _ in range(500):
            abp_joints = abp_region.abp_joints()
            abp_part, abp_end = abp_region.abp_part(abp_origin, abp_joints)
            if (
                not abp_part
                and abp_end == abp_origin
                and abp_region.abp_next.get(abp_end) is not None
            ):
                break
            if abp_points and abp_part and abp_origin not in abp_region.abp_lead_in:
                abp_part = abp_part[1:]
            abp_points.extend(
                abp_p
                for abp_p in abp_part
                if not abp_points or float(np.hypot(*(abp_p - abp_points[-1]))) > 1e-9
            )
            if abp_region.abp_next.get(abp_end) is not None:
                abp_origin = abp_end
                continue
            if abp_end not in abp_region.abp_root_of:
                break
            abp_portal = abp_region.abp_portals[abp_region.abp_root_of[abp_end]]
            abp_target = abp_portal.abp_target_name
            if abp_portal.abp_next_region < 0:
                break
            abp_region = self.abp_regions[abp_portal.abp_next_region]
            abp_following = abp_region.abp_nearest_walkable(abp_portal.abp_through[1])
            if abp_following is None or abp_following not in abp_region.abp_next:
                break
            abp_origin = abp_following
        return abp__points(abp_points), abp_target


def abp__middle_and_normal(abp_s: abpSegment) -> tuple[abpFloatArray, abpFloatArray | None]:
    abp_middle = np.array([abp_s.abp_midpoint.abp_x, abp_s.abp_midpoint.abp_y])
    abp_d = np.array(
        [abp_s.abp_end.abp_x - abp_s.abp_start.abp_x, abp_s.abp_end.abp_y - abp_s.abp_start.abp_y]
    )
    abp_length = float(np.hypot(*abp_d))
    return abp_middle, (np.array([-abp_d[1], abp_d[0]]) / abp_length if abp_length > 1e-6 else None)


def abp__dominant_angle(abp_centers: abpFloatArray, abp_walls: Sequence[abpSegment]) -> float:
    if not abp_walls:
        return 0.0
    abp_lo, abp_hi = abp_centers.min(axis=0) - 0.6, abp_centers.max(axis=0) + 0.6
    abp_near: list[tuple[float, float]] = []
    for abp_w in abp_walls:
        abp_a, abp_b = (
            np.array([abp_w.abp_start.abp_x, abp_w.abp_start.abp_y]),
            np.array([abp_w.abp_end.abp_x, abp_w.abp_end.abp_y]),
        )
        abp_samples = abp_a + np.linspace(0, 1, 9)[:, None] * (abp_b - abp_a)
        abp_touching = ((abp_samples >= abp_lo) & (abp_samples <= abp_hi)).all(axis=1)
        abp_length = 0.0
        for abp_q in abp_samples[abp_touching]:
            if (
                float(np.hypot(abp_centers[:, 0] - abp_q[0], abp_centers[:, 1] - abp_q[1]).min())
                < 0.6
            ):
                abp_length += abp_w.abp_length / 9
        if abp_length > 0:
            abp_near.append(
                (math.atan2(abp_b[1] - abp_a[1], abp_b[0] - abp_a[0]) % (math.pi / 2), abp_length)
            )
    if not abp_near:
        return 0.0
    abp_quarter = math.pi / 2

    def abp_score(abp_angle: float) -> float:
        abp_total = 0.0
        for abp_other, abp_weight in abp_near:
            abp_diff = abs(
                (abp_other - abp_angle + abp_quarter / 2) % abp_quarter - abp_quarter / 2
            )
            abp_total += abp_weight * max(0.0, 1.0 - abp_diff / math.radians(8))
        return abp_total

    return max((abp_angle for abp_angle, _ in abp_near), key=abp_score)


def abp__skewed(abp_region: abp__Region, abp_walls: Sequence[abpSegment]) -> abpBoolArray:
    abp_rows, abp_cols = abp_region.abp_shape
    abp_out = np.zeros((abp_rows, abp_cols), np.bool_)
    abp_ends = np.array(
        [
            (abp_w.abp_start.abp_x, abp_w.abp_start.abp_y, abp_w.abp_end.abp_x, abp_w.abp_end.abp_y)
            for abp_w in abp_walls
            if abp_w.abp_length > 0.3
        ]
    )
    if len(abp_ends) == 0:
        return abp_out
    abp_quarter = math.pi / 2
    abp_angles = np.arctan2(abp_ends[:, 3] - abp_ends[:, 1], abp_ends[:, 2] - abp_ends[:, 0])
    abp_diff = np.abs(
        (abp_angles - abp_region.abp_angle + abp_quarter / 2) % abp_quarter - abp_quarter / 2
    )
    abp_tilted = abp_diff > math.radians(abp_SKEW_DEG)
    if not abp_tilted.any():
        return abp_out
    abp_cells = np.argwhere(np.array(abp_region.abp_walk, np.bool_))
    abp_points = abp_region.abp_to_world(abp_cells.astype(np.float64))
    abp_a, abp_d = abp_ends[:, :2], abp_ends[:, 2:] - abp_ends[:, :2]
    abp_l2 = np.maximum((abp_d**2).sum(axis=1), 1e-9)
    abp_best = np.full(len(abp_points), np.inf)
    abp_flag = np.zeros(len(abp_points), np.bool_)
    for abp_k in range(len(abp_ends)):
        abp_t = np.clip(((abp_points - abp_a[abp_k]) @ abp_d[abp_k]) / abp_l2[abp_k], 0.0, 1.0)
        abp_q = abp_a[abp_k] + abp_t[:, None] * abp_d[abp_k]
        abp_away = np.hypot(abp_points[:, 0] - abp_q[:, 0], abp_points[:, 1] - abp_q[:, 1])
        abp_closer = abp_away < abp_best
        abp_best[abp_closer] = abp_away[abp_closer]
        abp_flag[abp_closer] = abp_tilted[abp_k]
    abp_out[abp_cells[:, 0], abp_cells[:, 1]] = abp_flag
    return abp_out


def abp__drop_flat(abp_points: Sequence[abpFloatArray]) -> list[abpFloatArray]:
    abp_out = [abp_points[0]]
    for abp_k in range(1, len(abp_points) - 1):
        abp_a, abp_p, abp_b = abp_out[-1], abp_points[abp_k], abp_points[abp_k + 1]
        abp_u, abp_v = abp_p - abp_a, abp_b - abp_p
        if float(np.hypot(*abp_u)) < 1e-6 or float(np.hypot(*abp_v)) < 1e-6:
            continue
        abp_turn = abs(
            math.degrees(
                math.atan2(abp_u[0] * abp_v[1] - abp_u[1] * abp_v[0], float(abp_u @ abp_v))
            )
        )
        if abp_turn >= 4.0:
            abp_out.append(abp_p)
    abp_out.append(abp_points[-1])
    return abp_out


def abp__trim_hook(abp_points: list[abpFloatArray]) -> list[abpFloatArray]:
    while len(abp_points) >= 3:
        abp_first, abp_second = (
            float(np.hypot(*(abp_b - abp_a))) for abp_a, abp_b in itertools.pairwise(abp_points[:3])
        )
        if abp_first >= 1.6 or abp_second < 1.4 * abp_first:
            break
        abp_points = abp_points[1:]
    return abp_points


def abp__room_reach(abp_grid: abpNavGrid, abp_room: abpRoomArea, abp_dist: abpFloatArray) -> float:
    abp_mask = abp_grid.abp_polygon_mask(abp_room.abp_polygon_m) & np.isfinite(abp_dist)
    return float(abp_dist[abp_mask].max()) if abp_mask.any() else -1.0


def abp__within(abp_mask: abpBoolArray, abp_radius: float, abp_cell_size: float) -> abpBoolArray:
    if not abp_mask.any():
        return abp_mask.copy()
    abp_away = cv2.distanceTransform((~abp_mask).astype(np.uint8), cv2.DIST_L2, 5) * abp_cell_size
    return np.asarray(abp_away <= abp_radius, np.bool_)


def abp__openings(abp_plan: abpFloorPlan) -> list[abpSegment]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_segments = [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]
    return [abp_segment_to_m(abp_x, abp_scale) for abp_x in abp_segments]


def abp__first_door_width(
    abp_points: Sequence[abpPoint], abp_openings: Sequence[abpSegment]
) -> float | None:
    for abp_p in abp_points:
        for abp_s in abp_openings:
            if abp_p.abp_distance_to(abp_s.abp_midpoint) < 1e-6:
                return round(abp_s.abp_length, 2)
    return None


def abp__meeting_links(
    abp_plan: abpFloorPlan, abp_grid: abpNavGrid
) -> tuple[tuple[str, tuple[abpPoint, ...]], ...]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_outside = np.asarray(abp_grid.abp_cells == int(abpCellType.abp_OUTSIDE), np.bool_)
    abp_zones: list[abpBoolArray] = []
    for abp_zone in abp_plan.abp_safe_zones:
        abp_mask = (
            abp_grid.abp_polygon_mask(abp_polygon_to_m(abp_zone.abp_area, abp_scale)) & abp_outside
        )
        if abp_mask.any():
            abp_zones.append(abp_mask)
    if not abp_zones:
        return ()
    abp_every = np.logical_or.reduce(abp_zones)
    abp_wall = np.asarray(abp_grid.abp_cells == int(abpCellType.abp_WALL), np.bool_)
    abp_inside = (~abp_outside & ~abp_wall).astype(np.uint8)
    abp_by_building = cv2.dilate(abp_inside, np.ones((5, 5), np.uint8)) > 0
    abp_edge = abp_wall & ~abp_by_building
    abp_clearance, _ = abp_wall_distance(abp_outside | abp_edge, abp_grid.abp_cell_size)
    abp_cost = abp__cost(
        abp_clearance, np.zeros(abp_grid.abp_shape, np.bool_), abp_grid.abp_cell_size
    )
    abp_cost[abp_edge] += abp_EDGE_COST
    abp_outside = abp_outside | abp_edge
    abp_fields = [
        abp_weighted_distance_field(abp_outside, abp_z, abp_cost, abp_grid.abp_cell_size)
        for abp_z in abp_zones
    ]
    abp_region = abp__outside_region(abp_plan, abp_grid, abp_outside & ~abp_every, abp_cost)
    abp_ways: list[abp__Way] = []
    for abp_exit_ in abp_plan.abp_exits:
        if abp_exit_.abp_name not in abp_grid.abp_target_names:
            continue
        abp_middle, abp_normal = abp__middle_and_normal(
            abp_segment_to_m(abp_exit_.abp_segment, abp_scale)
        )
        abp_start = abp__outer_point(abp_grid, abp_outside, abp_middle, abp_normal)
        if abp_start is None:
            continue
        abp_r, abp_c = (int(abp_v[0]) for abp_v in abp_grid.abp_to_cell(abp_start[None, :]))
        abp_reach = [float(abp_f[abp_r, abp_c]) for abp_f in abp_fields]
        abp_best = min(abp_reach)
        if not math.isfinite(abp_best):
            continue
        for abp_z in sorted(range(len(abp_zones)), key=lambda abp_k: abp_reach[abp_k]):
            if abp_reach[abp_z] <= abp_OTHER_ZONE * abp_best:
                abp_ways.append(
                    (abp_reach[abp_z], abp_exit_.abp_name, abp_middle, abp_start, abp_z)
                )
    abp_primary = {
        abp_name: abp_z
        for abp__length, abp_name, abp__m, abp__s, abp_z in reversed(abp__by_length(abp_ways))
    }
    abp_out: list[tuple[str, tuple[abpPoint, ...]]] = []
    abp_extra: list[tuple[str, tuple[abpPoint, ...]]] = []
    for abp_z in range(len(abp_zones)):
        abp_region.abp_next.clear()
        abp_region.abp_starts.clear()
        abp_region.abp_portals = []
        abp_region.abp_root_of = {}
        for abp_r, abp_c in abp__edge_cells(abp_zones[abp_z], abp_outside & ~abp_every):
            abp_point = abp_grid.abp_cell_centers(np.array([abp_r]), np.array([abp_c]))[0]
            abp_cell = abp_region.abp_nearest_walkable(abp_point)
            if abp_cell is not None and abp_cell not in abp_region.abp_root_of:
                abp_region.abp_root_of[abp_cell] = len(abp_region.abp_portals)
                abp_region.abp_portals.append(abp__Portal(0, abp_point, (abp_point,), -1, "", 0.0))
        for abp__length, abp_name, abp_middle, abp_start, abp__z in reversed(
            abp__by_length([abp_w for abp_w in abp_ways if abp_w[4] == abp_z])
        ):
            abp_first = abp_region.abp_nearest_walkable(abp_start)
            abp_path = abp_region.abp_route(abp_first) if abp_first is not None else []
            if not abp_path or abp_first is None:
                continue
            abp_region.abp_add(abp_path)
            abp_points = abp__drop_flat(
                [abp_middle, *abp_region.abp_simplify(abp_region.abp_chain(abp_first, ()))]
            )
            if len(abp_points) >= 2:
                (abp_out if abp_primary[abp_name] == abp_z else abp_extra).append(
                    (abp_name, abp__points(abp_points))
                )
    abp_drawn = [abp_line for abp__name, abp_line in abp_out]
    for abp_name, abp_line in abp_extra:
        abp_rest = abp__after_shared(abp_line, abp_drawn)
        if len(abp_rest) >= 2:
            abp_out.append((abp_name, abp_rest))
            abp_drawn.append(abp_rest)
    return tuple(abp_out)


abp__Way = tuple[float, str, abpFloatArray, abpFloatArray, int]


def abp__by_length(abp_ways: Sequence[abp__Way]) -> list[abp__Way]:
    return sorted(abp_ways, key=lambda abp_w: (abp_w[0], abp_w[1], abp_w[4]))


def abp__after_shared(
    abp_points: tuple[abpPoint, ...], abp_drawn: Sequence[tuple[abpPoint, ...]]
) -> tuple[abpPoint, ...]:
    abp_dense: list[abpPoint] = []
    for abp_a, abp_b in itertools.pairwise(abp_points):
        abp_n = max(1, math.ceil(abp_a.abp_distance_to(abp_b) / 0.2))
        abp_dense += [
            abpPoint(
                abp_a.abp_x + (abp_b.abp_x - abp_a.abp_x) * abp_k / abp_n,
                abp_a.abp_y + (abp_b.abp_y - abp_a.abp_y) * abp_k / abp_n,
            )
            for abp_k in range(abp_n)
        ]
    abp_dense.append(abp_points[-1])
    abp_last = 0
    for abp_k, abp_p in enumerate(abp_dense):
        if any(
            abp__segment_gap(abp_p, abp_a, abp_b) < 0.35
            for abp_line in abp_drawn
            for abp_a, abp_b in itertools.pairwise(abp_line)
        ):
            abp_last = abp_k
    abp_run = np.array(
        [(abp_p.abp_x, abp_p.abp_y) for abp_p in abp_dense[abp_last:]], np.float32
    ).reshape(-1, 1, 2)
    if len(abp_run) < 2:
        return ()
    abp_simple = cv2.approxPolyDP(abp_run, 0.1, False).reshape(-1, 2)
    return tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_simple)


def abp__segment_gap(abp_p: abpPoint, abp_a: abpPoint, abp_b: abpPoint) -> float:
    abp_dx, abp_dy = abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y
    abp_l2 = abp_dx * abp_dx + abp_dy * abp_dy
    abp_t = (
        0.0
        if abp_l2 < 1e-12
        else max(
            0.0,
            min(
                1.0,
                ((abp_p.abp_x - abp_a.abp_x) * abp_dx + (abp_p.abp_y - abp_a.abp_y) * abp_dy)
                / abp_l2,
            ),
        )
    )
    return math.hypot(
        abp_p.abp_x - abp_a.abp_x - abp_t * abp_dx, abp_p.abp_y - abp_a.abp_y - abp_t * abp_dy
    )


def abp__outer_point(
    abp_grid: abpNavGrid,
    abp_outside: abpBoolArray,
    abp_middle: abpFloatArray,
    abp_normal: abpFloatArray | None,
) -> abpFloatArray | None:
    if abp_normal is None:
        return None
    for abp_step in (0.6, 0.8, 1.0, 0.4):
        for abp_sign in (1.0, -1.0):
            abp_point = abp_middle + abp_normal * abp_sign * abp_step
            abp_r, abp_c = (int(abp_v[0]) for abp_v in abp_grid.abp_to_cell(abp_point[None, :]))
            if (
                0 <= abp_r < abp_grid.abp_shape[0]
                and 0 <= abp_c < abp_grid.abp_shape[1]
                and abp_outside[abp_r, abp_c]
            ):
                return np.asarray(abp_point, np.float64)
    return None


def abp__edge_cells(abp_zone: abpBoolArray, abp_around: abpBoolArray) -> list[abpCell]:
    abp_ring = (cv2.dilate(abp_zone.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & abp_around
    return [(int(abp_r), int(abp_c)) for abp_r, abp_c in np.argwhere(abp_ring)]


def abp__outside_region(
    abp_plan: abpFloorPlan, abp_grid: abpNavGrid, abp_free: abpBoolArray, abp_cost: abpFloatArray
) -> abp__Region:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_walls = [abp_segment_to_m(abp_w.abp_segment, abp_scale) for abp_w in abp_plan.abp_walls]
    abp_quarter = math.pi / 2
    abp_weights: dict[int, float] = {}
    for abp_w in abp_walls:
        abp_angle = (
            math.atan2(
                abp_w.abp_end.abp_y - abp_w.abp_start.abp_y,
                abp_w.abp_end.abp_x - abp_w.abp_start.abp_x,
            )
            % abp_quarter
        )
        abp_key = round(math.degrees(abp_angle)) % 90
        abp_weights[abp_key] = abp_weights.get(abp_key, 0.0) + abp_w.abp_length
    abp_angle = (
        math.radians(max(abp_weights, key=lambda abp_k: abp_weights[abp_k])) if abp_weights else 0.0
    )
    abp_rows, abp_cols = abp_grid.abp_shape
    abp_size = abp_grid.abp_cell_size
    abp_origin = np.asarray(abp_grid.abp_cell_centers(np.array([0]), np.array([0]))[0], np.float64)
    if min(abp_angle, abp_quarter - abp_angle) < math.radians(2):
        return abp__Region(
            0, 0.0, abp_origin, abp_size, abp_free.tolist(), abp_cost.tolist(), [], {}
        )
    abp_corners = abp_grid.abp_cell_centers(
        np.array([0, 0, abp_rows - 1, abp_rows - 1]), np.array([0, abp_cols - 1] * 2)
    )
    abp_c, abp_si = math.cos(abp_angle), math.sin(abp_angle)
    abp_local = abp_corners - abp_origin
    abp_x, abp_y = (
        abp_local[:, 0] * abp_c + abp_local[:, 1] * abp_si,
        -abp_local[:, 0] * abp_si + abp_local[:, 1] * abp_c,
    )
    abp_left, abp_top = math.floor(abp_x.min() / abp_size), math.floor(abp_y.min() / abp_size)
    abp_width, abp_height = (
        math.ceil(abp_x.max() / abp_size) + 1 - abp_left,
        math.ceil(abp_y.max() / abp_size) + 1 - abp_top,
    )
    abp_start = abp_origin + abp_size * np.array(
        [abp_left * abp_c - abp_top * abp_si, abp_left * abp_si + abp_top * abp_c]
    )
    abp_rr, abp_cc = np.mgrid[0:abp_height, 0:abp_width]
    abp_flat = np.c_[
        (abp_start[0] + abp_size * (abp_cc * abp_c - abp_rr * abp_si)).ravel(),
        (abp_start[1] + abp_size * (abp_cc * abp_si + abp_rr * abp_c)).ravel(),
    ]
    abp_gr, abp_gc = abp_grid.abp_to_cell(abp_flat)
    abp_gx, abp_gy = (
        (abp_flat[:, 0] - abp_grid.abp_origin[0]) / abp_size,
        (abp_flat[:, 1] - abp_grid.abp_origin[1]) / abp_size,
    )
    abp_valid = (abp_gx >= 0) & (abp_gy >= 0) & (abp_gx < abp_cols) & (abp_gy < abp_rows)
    abp_walk = (abp_valid & abp_free[abp_gr, abp_gc]).reshape(abp_height, abp_width)
    abp_price = np.where(abp_valid, abp_cost[abp_gr, abp_gc], 1.0).reshape(abp_height, abp_width)
    return abp__Region(
        0, abp_angle, abp_start, abp_size, abp_walk.tolist(), abp_price.tolist(), [], {}
    )
