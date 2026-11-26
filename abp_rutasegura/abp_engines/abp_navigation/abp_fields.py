from __future__ import annotations

import heapq
import math

import cv2
import numpy as np
import numpy.typing as npt

abpFloatArray = npt.NDArray[np.float64]
abpBoolArray = npt.NDArray[np.bool_]

abp_NEIGHBORS = (
    (-1, 0, 1.0),
    (1, 0, 1.0),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (-1, -1, math.sqrt(2)),
    (-1, 1, math.sqrt(2)),
    (1, -1, math.sqrt(2)),
    (1, 1, math.sqrt(2)),
)


def abp_distance_field(
    abp_walkable: abpBoolArray, abp_targets: abpBoolArray, abp_cell_size: float
) -> abpFloatArray:
    abp_rows, abp_cols = abp_walkable.shape
    abp_dist = np.full((abp_rows, abp_cols), np.inf)
    abp_walk = abp_walkable.tolist()
    abp_heap: list[tuple[float, int, int]] = []
    for abp_r, abp_c in zip(*np.nonzero(abp_targets & abp_walkable), strict=True):
        abp_dist[abp_r, abp_c] = 0.0
        abp_heap.append((0.0, int(abp_r), int(abp_c)))
    heapq.heapify(abp_heap)
    abp_d = abp_dist.tolist()
    while abp_heap:
        abp_current, abp_r, abp_c = heapq.heappop(abp_heap)
        if abp_current > abp_d[abp_r][abp_c]:
            continue
        for abp_dr, abp_dc, abp_cost in abp_NEIGHBORS:
            abp_nr, abp_nc = abp_r + abp_dr, abp_c + abp_dc
            if (
                not (0 <= abp_nr < abp_rows and 0 <= abp_nc < abp_cols)
                or not abp_walk[abp_nr][abp_nc]
            ):
                continue
            if (
                abp_dr
                and abp_dc
                and not (abp_walk[abp_r + abp_dr][abp_c] and abp_walk[abp_r][abp_c + abp_dc])
            ):
                continue
            abp_candidate = abp_current + abp_cost * abp_cell_size
            if abp_candidate < abp_d[abp_nr][abp_nc]:
                abp_d[abp_nr][abp_nc] = abp_candidate
                heapq.heappush(abp_heap, (abp_candidate, abp_nr, abp_nc))
    return np.array(abp_d, dtype=np.float64)


def abp_weighted_distance_field(
    abp_walk: abpBoolArray, abp_targets: abpBoolArray, abp_cost: abpFloatArray, abp_cell_size: float
) -> abpFloatArray:
    abp_rows, abp_cols = abp_walk.shape
    abp_w, abp_price = abp_walk.tolist(), abp_cost.tolist()
    abp_d = [[math.inf] * abp_cols for _ in range(abp_rows)]
    abp_heap: list[tuple[float, int, int]] = []
    for abp_r, abp_c in zip(*np.nonzero(abp_targets & abp_walk), strict=True):
        abp_d[int(abp_r)][int(abp_c)] = 0.0
        abp_heap.append((0.0, int(abp_r), int(abp_c)))
    heapq.heapify(abp_heap)
    while abp_heap:
        abp_current, abp_r, abp_c = heapq.heappop(abp_heap)
        if abp_current > abp_d[abp_r][abp_c]:
            continue
        for abp_dr, abp_dc, abp_step in abp_NEIGHBORS:
            abp_nr, abp_nc = abp_r + abp_dr, abp_c + abp_dc
            if not (0 <= abp_nr < abp_rows and 0 <= abp_nc < abp_cols) or not abp_w[abp_nr][abp_nc]:
                continue
            if (
                abp_dr
                and abp_dc
                and not (abp_w[abp_r + abp_dr][abp_c] and abp_w[abp_r][abp_c + abp_dc])
            ):
                continue
            abp_candidate = abp_current + abp_step * abp_cell_size * 0.5 * (
                abp_price[abp_r][abp_c] + abp_price[abp_nr][abp_nc]
            )
            if abp_candidate < abp_d[abp_nr][abp_nc] - 1e-12:
                abp_d[abp_nr][abp_nc] = abp_candidate
                heapq.heappush(abp_heap, (abp_candidate, abp_nr, abp_nc))
    return np.array(abp_d, np.float64)


def abp_direction_field(abp_dist: abpFloatArray, abp_walkable: abpBoolArray) -> abpFloatArray:
    abp_rows, abp_cols = abp_dist.shape
    abp_padded = np.pad(abp_dist, 1, constant_values=np.inf)
    abp_walk_pad = np.pad(abp_walkable, 1, constant_values=False)
    abp_finite = np.isfinite(abp_dist) & abp_walkable
    abp_best_slope = np.zeros((abp_rows, abp_cols))
    abp_vec = np.zeros((abp_rows, abp_cols, 2))
    for abp_dr, abp_dc, abp_cost in abp_NEIGHBORS:
        abp_neighbor = abp_padded[
            1 + abp_dr : 1 + abp_dr + abp_rows, 1 + abp_dc : 1 + abp_dc + abp_cols
        ]
        abp_allowed = abp_walk_pad[
            1 + abp_dr : 1 + abp_dr + abp_rows, 1 + abp_dc : 1 + abp_dc + abp_cols
        ]
        if abp_dr and abp_dc:
            abp_allowed = (
                abp_allowed
                & abp_walk_pad[1 + abp_dr : 1 + abp_dr + abp_rows, 1 : 1 + abp_cols]
                & abp_walk_pad[1 : 1 + abp_rows, 1 + abp_dc : 1 + abp_dc + abp_cols]
            )
        with np.errstate(invalid="ignore"):
            abp_slope = np.where(
                abp_allowed & abp_finite & np.isfinite(abp_neighbor),
                (abp_dist - abp_neighbor) / abp_cost,
                0.0,
            )
        abp_take = abp_slope > abp_best_slope + 1e-12
        abp_best_slope = np.where(abp_take, abp_slope, abp_best_slope)
        abp_vec[abp_take] = np.array([abp_dc, abp_dr], dtype=np.float64) / abp_cost
    abp_smoothed = cv2.blur(abp_vec, (3, 3), borderType=cv2.BORDER_CONSTANT)
    abp_smoothed[~abp_walkable] = 0.0
    abp_norm = np.linalg.norm(abp_smoothed, axis=2, keepdims=True)
    abp_result = np.where(abp_norm > 1e-9, abp_smoothed / np.maximum(abp_norm, 1e-12), abp_vec)
    return np.asarray(abp_result, dtype=np.float64)


def abp_wall_distance(
    abp_walkable: abpBoolArray, abp_cell_size: float
) -> tuple[abpFloatArray, abpFloatArray]:
    abp_dist = cv2.distanceTransform(abp_walkable.astype(np.uint8), cv2.DIST_L2, 5).astype(
        np.float64
    )
    abp_dist *= abp_cell_size
    abp_gy, abp_gx = np.gradient(abp_dist)
    abp_grad = np.stack([abp_gx, abp_gy], axis=2)
    abp_norm = np.linalg.norm(abp_grad, axis=2, keepdims=True)
    abp_grad = np.where(abp_norm > 1e-9, abp_grad / np.maximum(abp_norm, 1e-12), 0.0)
    return abp_dist, np.asarray(abp_grad, dtype=np.float64)
