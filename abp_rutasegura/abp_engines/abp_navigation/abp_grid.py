from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpCellType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpStair
from abp_rutasegura.abp_engines.abp_navigation.abp_stairs import (
    abp_edge_distance,
    abp_edge_index,
    abp_edges,
    abp_needed,
    abp_stair_role,
    abpStairRole,
)

abp_CELL_SIZE_M = 0.4
abp_WALKABLE = (
    abpCellType.abp_FREE,
    abpCellType.abp_DOOR,
    abpCellType.abp_EXIT,
    abpCellType.abp_STAIR,
    abpCellType.abp_SAFE_ZONE,
)
abp_TARGETS = (abpCellType.abp_EXIT, abpCellType.abp_SAFE_ZONE)
abp__SHIFT = 4
abp__SAME_LINE_MAX_ANGLE_DEG = 25.0

abpFloatArray = npt.NDArray[np.float64]
abpIntArray = npt.NDArray[np.int64]
abpBoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, eq=False)
class abpNavGrid:
    abp_cells: npt.NDArray[np.int8]
    abp_cell_size: float
    abp_origin: tuple[float, float]
    abp_target_ids: npt.NDArray[np.int16]
    abp_target_names: tuple[str, ...]
    abp_target_stairs: tuple[int, ...] = ()
    abp_closed_stairs: tuple[int, ...] = ()

    def abp_stair_of(self, abp_target: int) -> int:
        return (
            self.abp_target_stairs[abp_target] if abp_target < len(self.abp_target_stairs) else -1
        )

    @property
    def abp_shape(self) -> tuple[int, int]:
        abp_rows, abp_cols = self.abp_cells.shape
        return int(abp_rows), int(abp_cols)

    @property
    def abp_walkable(self) -> abpBoolArray:
        return np.isin(self.abp_cells, [int(abp_c) for abp_c in abp_WALKABLE])

    @property
    def abp_targets(self) -> abpBoolArray:
        return np.asarray(self.abp_target_ids >= 0, dtype=np.bool_)

    def abp_to_cell(self, abp_xy: abpFloatArray) -> tuple[abpIntArray, abpIntArray]:
        abp_rows, abp_cols = self.abp_shape
        abp_c = np.floor((abp_xy[:, 0] - self.abp_origin[0]) / self.abp_cell_size).astype(np.int64)
        abp_r = np.floor((abp_xy[:, 1] - self.abp_origin[1]) / self.abp_cell_size).astype(np.int64)
        return np.clip(abp_r, 0, abp_rows - 1), np.clip(abp_c, 0, abp_cols - 1)

    def abp_cell_centers(self, abp_r: abpIntArray, abp_c: abpIntArray) -> abpFloatArray:
        abp_x = self.abp_origin[0] + (abp_c + 0.5) * self.abp_cell_size
        abp_y = self.abp_origin[1] + (abp_r + 0.5) * self.abp_cell_size
        return np.column_stack([abp_x, abp_y]).astype(np.float64)

    def abp_polygon_mask(self, abp_polygon_m: abpPolygon) -> abpBoolArray:
        abp_mask = np.zeros(self.abp_shape, dtype=np.uint8)
        cv2.fillPoly(
            abp_mask, [self.abp__to_cv(abp_polygon_m.abp_vertices)], 1, cv2.LINE_8, abp__SHIFT
        )
        return np.asarray(abp_mask > 0, dtype=np.bool_)

    def abp__to_cv(self, abp_points: Sequence[abpPoint]) -> npt.NDArray[np.int32]:
        abp_scale = 1 << abp__SHIFT
        abp_pts = [
            (
                round(((abp_p.abp_x - self.abp_origin[0]) / self.abp_cell_size - 0.5) * abp_scale),
                round(((abp_p.abp_y - self.abp_origin[1]) / self.abp_cell_size - 0.5) * abp_scale),
            )
            for abp_p in abp_points
        ]
        return np.array(abp_pts, dtype=np.int32).reshape(-1, 1, 2)


def abp__scale_point(abp_p: abpPoint, abp_s: float) -> abpPoint:
    return abpPoint(abp_p.abp_x * abp_s, abp_p.abp_y * abp_s)


def abp_segment_to_m(abp_segment: abpSegment, abp_scale: float) -> abpSegment:
    return abpSegment(
        abp__scale_point(abp_segment.abp_start, abp_scale),
        abp__scale_point(abp_segment.abp_end, abp_scale),
    )


def abp_polygon_to_m(abp_polygon: abpPolygon, abp_scale: float) -> abpPolygon:
    return abpPolygon(
        tuple(abp__scale_point(abp_p, abp_scale) for abp_p in abp_polygon.abp_vertices)
    )


def abp_build_grid(
    abp_plan: abpFloorPlan,
    *,
    abp_blocked_exits: Collection[str] = (),
    abp_cell_size: float = abp_CELL_SIZE_M,
    abp_margin_m: float = 1.2,
    abp_stairs_as_targets: bool = False,
    abp_exits_as_targets: bool = True,
    abp_keep_stairs: bool = False,
) -> abpNavGrid:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None:
        raise ValueError("El plano no tiene escala; defínala en el paso 2.")
    abp_walls = [abp_segment_to_m(abp_w.abp_segment, abp_scale) for abp_w in abp_plan.abp_walls]
    abp_doors = [abp_segment_to_m(abp_d.abp_segment, abp_scale) for abp_d in abp_plan.abp_doors]
    abp_usable = abp_exits_as_targets
    abp_active_exits = [
        abp_e
        for abp_e in abp_plan.abp_exits
        if abp_usable and abp_e.abp_confirmed and abp_e.abp_name not in abp_blocked_exits
    ]
    abp_closed_exits = [abp_e for abp_e in abp_plan.abp_exits if abp_e not in abp_active_exits]
    abp_obstacles = [
        abp_polygon_to_m(abp_o.abp_area, abp_scale)
        for abp_o in abp_plan.abp_obstacles
        if abp_o.abp_confirmed
    ]
    abp_zones = [
        (abp_z.abp_name, abp_polygon_to_m(abp_z.abp_area, abp_scale))
        for abp_z in abp_plan.abp_safe_zones
        if abp_exits_as_targets and not (abp_z.abp_name and abp_z.abp_name in abp_blocked_exits)
    ]
    abp_rooms = [abp_polygon_to_m(abp_r.abp_area, abp_scale) for abp_r in abp_plan.abp_rooms]
    abp_stairs = [
        abp_polygon_to_m(abp_st.abp_area, abp_scale)
        for abp_st in abp_plan.abp_stairs
        if abp_st.abp_confirmed
    ]
    abp_stair_indices = [
        abp_i for abp_i, abp_st in enumerate(abp_plan.abp_stairs) if abp_st.abp_confirmed
    ]

    abp_exit_segments = [
        abp_segment_to_m(abp_e.abp_segment, abp_scale) for abp_e in abp_plan.abp_exits
    ]
    abp_points = [
        abp_p
        for abp_s in abp_walls + abp_doors + abp_exit_segments
        for abp_p in (abp_s.abp_start, abp_s.abp_end)
    ]
    abp_points += [
        abp_p
        for abp_poly in abp_obstacles + abp_rooms + abp_stairs + [abp_z for _, abp_z in abp_zones]
        for abp_p in abp_poly.abp_vertices
    ]
    if not abp_points:
        raise ValueError("El plano está vacío: no hay muros ni ambientes.")
    abp_xs = [abp_p.abp_x for abp_p in abp_points]
    abp_ys = [abp_p.abp_y for abp_p in abp_points]
    abp_origin = (min(abp_xs) - abp_margin_m, min(abp_ys) - abp_margin_m)
    abp_cols = math.ceil((max(abp_xs) - abp_origin[0] + abp_margin_m) / abp_cell_size) + 1
    abp_rows = math.ceil((max(abp_ys) - abp_origin[1] + abp_margin_m) / abp_cell_size) + 1

    abp_cells = np.full((abp_rows, abp_cols), int(abpCellType.abp_FREE), dtype=np.uint8)
    abp_target_ids = np.full((abp_rows, abp_cols), -1, dtype=np.int16)
    abp_grid = abpNavGrid(abp_cells.astype(np.int8), abp_cell_size, abp_origin, abp_target_ids, ())

    def abp_line(abp_seg: abpSegment, abp_value: abpCellType, abp_line_type: int) -> None:
        abp_pts = abp_grid.abp__to_cv([abp_seg.abp_start, abp_seg.abp_end]).reshape(2, 2)
        cv2.line(
            abp_cells,
            tuple(abp_pts[0]),
            tuple(abp_pts[1]),
            int(abp_value),
            1,
            abp_line_type,
            abp__SHIFT,
        )

    def abp_fill(abp_poly: abpPolygon, abp_value: abpCellType) -> None:
        cv2.fillPoly(
            abp_cells,
            [abp_grid.abp__to_cv(abp_poly.abp_vertices)],
            int(abp_value),
            cv2.LINE_8,
            abp__SHIFT,
        )

    for abp_poly in abp_obstacles:
        abp_fill(abp_poly, abpCellType.abp_OBSTACLE)
    for abp_seg in abp_walls:
        abp_line(abp_seg, abpCellType.abp_WALL, cv2.LINE_4)
    for abp_exit_ in abp_closed_exits:
        abp_line(
            abp_segment_to_m(abp_exit_.abp_segment, abp_scale), abpCellType.abp_WALL, cv2.LINE_4
        )
    for abp_seg in abp_doors:
        abp_line(abp_seg, abpCellType.abp_DOOR, cv2.LINE_8)
    for abp_seg in abp_walls:
        if not any(abp__on_same_line(abp_seg, abp_door, abp_cell_size) for abp_door in abp_doors):
            abp_line(abp_seg, abpCellType.abp_WALL, cv2.LINE_4)

    abp_stair_masks: list[abpBoolArray] = []
    for abp_poly in abp_stairs:
        abp_inside = abp_grid.abp_polygon_mask(abp_poly)
        abp_stair_masks.append(
            np.asarray(abp_inside & (abp_cells == int(abpCellType.abp_FREE)), np.bool_)
        )
        abp_cells[abp_stair_masks[-1]] = int(abpCellType.abp_STAIR)

    abp_names: list[str] = []
    abp_kinds: list[int] = []
    for abp_exit_ in abp_active_exits:
        abp_before = abp_cells == int(abpCellType.abp_EXIT)
        abp_line(
            abp_segment_to_m(abp_exit_.abp_segment, abp_scale), abpCellType.abp_EXIT, cv2.LINE_4
        )
        abp_target_ids[(abp_cells == int(abpCellType.abp_EXIT)) & ~abp_before] = len(abp_names)
        abp_names.append(abp_exit_.abp_name or f"Salida {len(abp_names) + 1}")
        abp_kinds.append(-1)
    for abp_i, (abp_name, abp_poly) in enumerate(abp_zones):
        abp_zone_mask = np.zeros_like(abp_cells)
        cv2.fillPoly(
            abp_zone_mask, [abp_grid.abp__to_cv(abp_poly.abp_vertices)], 1, cv2.LINE_8, abp__SHIFT
        )
        abp_free_zone = (abp_zone_mask > 0) & (abp_cells == int(abpCellType.abp_FREE))
        abp_cells[abp_free_zone] = int(abpCellType.abp_SAFE_ZONE)
        abp_target_ids[abp_free_zone] = len(abp_names)
        abp_names.append(abp_name or f"Zona segura {abp_i + 1}")
        abp_kinds.append(-1)
    abp_roles = abp__stair_roles(
        [abp_plan.abp_stairs[abp_i] for abp_i in abp_stair_indices],
        abp_cells,
        abp_stair_masks,
        abp_target_ids,
        abp_stairs_as_targets,
    )
    abp_closed: list[int] = []
    for abp_index, abp_poly, abp_mask, abp_role in zip(
        abp_stair_indices, abp_stairs, abp_stair_masks, abp_roles, strict=True
    ):
        abp_own = abp_mask & (abp_cells == int(abpCellType.abp_STAIR))
        if abp_role is abpStairRole.abp_CLOSED:
            abp_closed.append(abp_index)
            if not abp_keep_stairs:
                abp_cells[abp_own] = int(abpCellType.abp_OBSTACLE)
        elif abp_role is not abpStairRole.abp_PASS:
            abp_stair = abp_plan.abp_stairs[abp_index]
            if abp_stair.abp_entry is not None:
                abp_own = abp__entrance(
                    abp_grid,
                    abp_own,
                    abp_poly,
                    abp__scale_point(abp_stair.abp_entry, abp_scale),
                    abp_cells,
                )
            abp_target_ids[abp_own] = len(abp_names)
            abp_names.append(abp_stair.abp_name or f"Escalera {abp_index + 1}")
            abp_kinds.append(abp_index if abp_stairs_as_targets else -1)

    abp__mark_outside(abp_cells)
    abp_target_ids[abp_cells == int(abpCellType.abp_OUTSIDE)] = -1
    return abpNavGrid(
        abp_cells.astype(np.int8),
        abp_cell_size,
        abp_origin,
        abp_target_ids,
        tuple(abp_names),
        tuple(abp_kinds),
        tuple(abp_closed),
    )


def abp__stair_roles(
    abp_stairs: Sequence[abpStair],
    abp_cells: npt.NDArray[np.uint8],
    abp_masks: Sequence[abpBoolArray],
    abp_target_ids: npt.NDArray[np.int16],
    abp_upper_floor: bool,
) -> list[abpStairRole]:
    abp_roles = [abp_stair_role(abp_s, abp_upper_floor=abp_upper_floor) for abp_s in abp_stairs]
    abp_auto = [abp_k for abp_k, abp_r in enumerate(abp_roles) if abp_r is None]
    if abp_auto:
        abp_walkable = np.isin(abp_cells, [int(abp_c) for abp_c in abp_WALKABLE])
        for abp_k, abp_role in enumerate(abp_roles):
            if abp_role in (None, abpStairRole.abp_CLOSED):
                abp_walkable &= ~abp_masks[abp_k]
        abp_targets = np.asarray(abp_target_ids >= 0, np.bool_)
        for abp_k, abp_role in enumerate(abp_roles):
            if abp_role is abpStairRole.abp_OUTSIDE:
                abp_targets = abp_targets | abp_masks[abp_k]
        abp_use = abp_needed(abp_walkable, abp_targets, [abp_masks[abp_k] for abp_k in abp_auto])
        for abp_k, abp_opened in zip(abp_auto, abp_use, strict=True):
            abp_roles[abp_k] = abpStairRole.abp_PASS if abp_opened else abpStairRole.abp_CLOSED
    return [abp_r if abp_r is not None else abpStairRole.abp_CLOSED for abp_r in abp_roles]


def abp__entrance(
    abp_grid: abpNavGrid,
    abp_own: abpBoolArray,
    abp_poly: abpPolygon,
    abp_entry: abpPoint,
    abp_cells: npt.NDArray[np.uint8],
) -> abpBoolArray:
    abp_rows, abp_cols = np.nonzero(abp_own)
    if abp_rows.size == 0:
        return abp_own
    abp_side = abp_edges(abp_poly)[abp_edge_index(abp_poly, abp_entry)]
    abp_away = abp_edge_distance(abp_grid.abp_cell_centers(abp_rows, abp_cols), *abp_side)
    abp_near = abp_away <= max(0.75 * abp_grid.abp_cell_size, float(abp_away.min()) + 0.1)
    abp_cells[abp_rows[~abp_near], abp_cols[~abp_near]] = int(abpCellType.abp_OBSTACLE)
    abp_out = np.zeros_like(abp_own)
    abp_out[abp_rows[abp_near], abp_cols[abp_near]] = True
    return abp_out


def abp_landing_cells(
    abp_grid: abpNavGrid,
    abp_distance: abpFloatArray,
    abp_poly: abpPolygon,
    abp_entry: abpPoint | None,
) -> abpFloatArray:
    abp_mask = abp_grid.abp_polygon_mask(abp_poly)
    abp_steps = abp_mask & (abp_grid.abp_cells == int(abpCellType.abp_OBSTACLE))
    abp_cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    abp_ring = cv2.dilate(abp_steps.astype(np.uint8), abp_cross) > 0
    abp_ring &= (
        ~abp_mask & abp_grid.abp_walkable & np.isfinite(abp_distance) & ~abp_grid.abp_targets
    )
    abp_rows, abp_cols = np.nonzero(abp_ring)
    abp_centers = abp_grid.abp_cell_centers(abp_rows, abp_cols)
    if abp_rows.size == 0:
        return abp_centers
    abp_sides = abp_edges(abp_poly)
    if abp_entry is not None:
        abp_index = abp_edge_index(abp_poly, abp_entry)
    else:
        abp_reach = 1.2 * abp_grid.abp_cell_size
        abp_fronts = [
            int((abp_edge_distance(abp_centers, abp_a, abp_b) < abp_reach).sum())
            for abp_a, abp_b in abp_sides
        ]
        abp_index = max(
            range(len(abp_sides)),
            key=lambda abp_k: (abp_fronts[abp_k], -abp__side_length(abp_sides[abp_k])),
        )
    abp_distances = np.array([abp_edge_distance(abp_centers, *abp_side) for abp_side in abp_sides])
    abp_front = abp_distances.argmin(axis=0) == abp_index
    if not abp_front.any():
        abp_front = (
            abp_distances[abp_index]
            <= float(abp_distances[abp_index].min()) + 0.5 * abp_grid.abp_cell_size
        )
    return np.asarray(abp_centers[abp_front], np.float64)


def abp__side_length(abp_side: tuple[abpPoint, abpPoint]) -> float:
    return abp_side[0].abp_distance_to(abp_side[1])


def abp__on_same_line(abp_wall: abpSegment, abp_door: abpSegment, abp_tolerance_m: float) -> bool:
    abp_wx, abp_wy = (
        abp_wall.abp_end.abp_x - abp_wall.abp_start.abp_x,
        abp_wall.abp_end.abp_y - abp_wall.abp_start.abp_y,
    )
    abp_dx, abp_dy = (
        abp_door.abp_end.abp_x - abp_door.abp_start.abp_x,
        abp_door.abp_end.abp_y - abp_door.abp_start.abp_y,
    )
    abp_wall_len, abp_door_len = math.hypot(abp_wx, abp_wy), math.hypot(abp_dx, abp_dy)
    if abp_wall_len == 0 or abp_door_len == 0:
        return False
    abp_sin_angle = abs(abp_wx * abp_dy - abp_wy * abp_dx) / (abp_wall_len * abp_door_len)
    if abp_sin_angle > math.sin(math.radians(abp__SAME_LINE_MAX_ANGLE_DEG)):
        return False
    abp_mid = abp_door.abp_midpoint
    abp_offset = (
        abs(
            abp_wx * (abp_mid.abp_y - abp_wall.abp_start.abp_y)
            - abp_wy * (abp_mid.abp_x - abp_wall.abp_start.abp_x)
        )
        / abp_wall_len
    )
    return abp_offset <= abp_tolerance_m


def abp__mark_outside(abp_cells: npt.NDArray[np.uint8]) -> None:
    abp_passable = np.isin(
        abp_cells,
        [int(abpCellType.abp_FREE), int(abpCellType.abp_STAIR), int(abpCellType.abp_SAFE_ZONE)],
    ).astype(np.uint8)
    abp_count, abp_labels = cv2.connectedComponents(abp_passable, connectivity=4)
    if abp_count <= 1:
        return
    abp_border = np.unique(
        np.concatenate([abp_labels[0, :], abp_labels[-1, :], abp_labels[:, 0], abp_labels[:, -1]])
    )
    abp_border = abp_border[abp_border > 0]
    abp_outside = np.isin(abp_labels, abp_border)
    abp_cells[abp_outside] = int(abpCellType.abp_OUTSIDE)
