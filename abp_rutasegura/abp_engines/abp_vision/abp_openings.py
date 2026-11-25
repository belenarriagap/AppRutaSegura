from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_vector import abpFloatArray
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import abp_point_segments_distance

abp_GAP_M = (0.6, 4.5)
abp_DOOR_MAX_M = 3.4
abp_LATERAL_M = 0.3
abp_COVERAGE = 0.55
abp_HULL_M = 0.6
abp_ENCLOSED, abp_ENCLOSED_WITH_EXITS = 0.5, 0.85
abp_CELL_M = 0.1


@dataclass(frozen=True, eq=False, slots=True)
class abpOpening:
    abp_segment: abpFloatArray
    abp_confidence: float
    abp_outside: bool


def abp_complete_openings(
    abp_walls: abpFloatArray,
    abp_openings: Sequence[abpFloatArray],
    abp_lines: abpFloatArray,
    abp_arcs: abpFloatArray,
) -> list[tuple[abpFloatArray, float]]:
    if len(abp_walls) < 2:
        return []
    abp_hull = abp__hull(abp_walls)
    abp_found: list[tuple[float, abpFloatArray, float]] = []
    abp_ends = np.vstack([abp_walls[:, :2], abp_walls[:, 2:]])
    for abp_i, abp_w in enumerate(abp_walls):
        abp_size = float(np.hypot(*(abp_w[2:] - abp_w[:2])))
        if abp_size < 0.3:
            continue
        for abp_k in (0, 2):
            abp_e = abp_w[abp_k : abp_k + 2]
            abp_u = (abp_e - abp_w[2 - abp_k : 4 - abp_k]) / abp_size
            abp_n = np.array([-abp_u[1], abp_u[0]])
            abp_rel = abp_ends - abp_e
            abp_ahead, abp_side = abp_rel @ abp_u, np.abs(abp_rel @ abp_n)
            abp_ok = (
                (abp_ahead >= abp_GAP_M[0])
                & (abp_ahead <= abp_GAP_M[1])
                & (abp_side <= abp_LATERAL_M)
            )
            abp_hit = abp__wall_ahead(abp_e, abp_u, np.delete(abp_walls, abp_i, axis=0))
            if abp_ok.any():
                abp_target = abp_ends[int(np.argmin(np.where(abp_ok, abp_ahead, np.inf)))]
            elif abp_hit is not None and abp_GAP_M[0] <= abp_hit <= abp_DOOR_MAX_M:
                abp_target = abp_e + abp_u * abp_hit
            else:
                continue
            abp_segment = np.r_[abp_e, abp_target]
            if not abp__is_free(abp_segment, abp_walls, abp_i):
                continue
            abp_confidence = abp__evidence(abp_segment, abp_lines, abp_arcs, abp_hull)
            if abp_confidence > 0:
                abp_found.append(
                    (-abp_confidence, abp_segment, float(np.hypot(*(abp_target - abp_e))))
                )
    abp_found.sort(key=lambda abp_x: (abp_x[0], abp_x[2]))
    abp_out: list[tuple[abpFloatArray, float]] = []
    abp_taken = [np.asarray(abp_o) for abp_o in abp_openings]
    for abp_minus, abp_segment, abp__length in abp_found:
        abp_middle = (abp_segment[:2] + abp_segment[2:]) / 2
        if any(
            abp_point_segments_distance(abp_middle, abp_o[None, :])[0] < 0.5 for abp_o in abp_taken
        ):
            continue
        abp_taken.append(abp_segment)
        abp_out.append((abp_segment, -abp_minus))
    return abp_out


def abp_opening_near(
    abp_walls_px: Sequence[tuple[float, float, float, float]],
    abp_point: tuple[float, float],
    abp_scale: float,
) -> tuple[float, float, float, float] | None:
    abp_walls = np.array(abp_walls_px, np.float64).reshape(-1, 4) * abp_scale
    if len(abp_walls) == 0:
        return None
    abp_p = np.array(abp_point) * abp_scale
    abp_ends = np.vstack([abp_walls[:, :2], abp_walls[:, 2:]])
    abp_best: tuple[float, abpFloatArray] | None = None
    for abp_i, abp_a in enumerate(abp_ends):
        for abp_b in abp_ends[abp_i + 1 :]:
            abp_length = float(np.hypot(*(abp_b - abp_a)))
            if not abp_GAP_M[0] <= abp_length <= abp_GAP_M[1]:
                continue
            abp_segment = np.r_[abp_a, abp_b]
            abp_away = float(abp_point_segments_distance(abp_p, abp_segment[None, :])[0])
            if abp_away > 0.8 or not abp__is_free(abp_segment, abp_walls, -1):
                continue
            abp_cost = abp_away + 0.2 * abp_length
            if abp_best is None or abp_cost < abp_best[0]:
                abp_best = (abp_cost, abp_segment)
    if abp_best is None:
        return None
    abp_x1, abp_y1, abp_x2, abp_y2 = (float(abp_v) for abp_v in abp_best[1] / abp_scale)
    return abp_x1, abp_y1, abp_x2, abp_y2


def abp_classify(
    abp_walls: abpFloatArray,
    abp_openings: Sequence[tuple[abpFloatArray, float]],
    abp_suspects: Collection[int] = (),
) -> list[abpOpening]:
    if len(abp_walls) == 0:
        return [abpOpening(abp_o, abp_c, False) for abp_o, abp_c in abp_openings]
    abp_hull = abp__hull(abp_walls)
    abp_segments = [abp_o for abp_o, abp__c in abp_openings]
    abp_flood, abp_origin, abp_enclosed = abp__flood(abp_walls, abp_segments, abp_hull)
    abp_needed = (
        abp_ENCLOSED_WITH_EXITS
        if any(abp__on_hull(abp_hull, abp_o) for abp_o in abp_segments)
        else abp_ENCLOSED
    )
    abp_out: list[abpOpening] = []
    for abp_index, (abp_o, abp_confidence) in enumerate(abp_openings):
        abp_middle = (abp_o[:2] + abp_o[2:]) / 2
        abp_outside = abp__on_hull(abp_hull, abp_o)
        if not abp_outside and abp_index in abp_suspects and abp_enclosed >= abp_needed:
            abp_d = abp_o[2:] - abp_o[:2]
            abp_n = np.array([-abp_d[1], abp_d[0]]) / max(float(np.hypot(*abp_d)), 1e-9)
            abp_sides = [
                abp__is_outside(abp_flood, abp_origin, abp_middle + abp_s * 0.6 * abp_n)
                for abp_s in (1.0, -1.0)
            ]
            abp_outside = abp_sides[0] != abp_sides[1]
        abp_out.append(abpOpening(abp_o, abp_confidence, abp_outside))
    return abp_out


def abp__hull(abp_walls: abpFloatArray) -> abpFloatArray:
    abp_points = np.vstack([abp_walls[:, :2], abp_walls[:, 2:]]).astype(np.float32)
    return np.asarray(cv2.convexHull(abp_points).reshape(-1, 2), np.float64)


def abp__on_hull(abp_hull: abpFloatArray, abp_o: abpFloatArray) -> bool:
    if len(abp_hull) < 3:
        return False
    abp_contour = abp_hull.astype(np.float32).reshape(-1, 1, 2)
    return all(
        abs(cv2.pointPolygonTest(abp_contour, (float(abp_p[0]), float(abp_p[1])), True))
        <= abp_HULL_M
        for abp_p in (abp_o[:2], (abp_o[:2] + abp_o[2:]) / 2, abp_o[2:])
    )


def abp__wall_ahead(
    abp_e: abpFloatArray, abp_u: abpFloatArray, abp_walls: abpFloatArray
) -> float | None:
    abp_n = np.array([-abp_u[1], abp_u[0]])
    abp_a, abp_b = (abp_walls[:, :2] - abp_e) @ abp_n, (abp_walls[:, 2:] - abp_e) @ abp_n
    abp_crossing = abp_a * abp_b < 0
    if not abp_crossing.any():
        return None
    abp_w, abp_a, abp_b = abp_walls[abp_crossing], abp_a[abp_crossing], abp_b[abp_crossing]
    abp_ta, abp_tb = (abp_w[:, :2] - abp_e) @ abp_u, (abp_w[:, 2:] - abp_e) @ abp_u
    abp_t = abp_ta + (abp_tb - abp_ta) * abp_a / (abp_a - abp_b)
    abp_t = abp_t[abp_t > 0.1]
    return float(abp_t.min()) if len(abp_t) else None


def abp__is_free(abp_segment: abpFloatArray, abp_walls: abpFloatArray, abp_own: int) -> bool:
    for abp_t in (0.35, 0.5, 0.65) if abp_own < 0 else (0.2, 0.35, 0.5, 0.65, 0.8):
        abp_p = abp_segment[:2] + abp_t * (abp_segment[2:] - abp_segment[:2])
        abp_others = abp_walls if abp_own < 0 else np.delete(abp_walls, abp_own, axis=0)
        if len(abp_others) and float(abp_point_segments_distance(abp_p, abp_others).min()) < 0.25:
            return False
    return True


def abp__evidence(
    abp_segment: abpFloatArray,
    abp_lines: abpFloatArray,
    abp_arcs: abpFloatArray,
    abp_hull: abpFloatArray,
) -> float:
    abp_length = float(np.hypot(*(abp_segment[2:] - abp_segment[:2])))
    abp_u = (abp_segment[2:] - abp_segment[:2]) / abp_length
    abp_n = np.array([-abp_u[1], abp_u[0]])
    abp_ends = (abp_segment[:2], abp_segment[2:])
    abp_hinges = (
        sum(
            float(np.hypot(abp_arcs[:, 0] - abp_e[0], abp_arcs[:, 1] - abp_e[1]).min()) < 0.5
            for abp_e in abp_ends
        )
        if len(abp_arcs)
        else 0
    )
    abp_coverage, abp_tracks = abp__line_coverage(
        abp_segment[:2], abp_u, abp_n, abp_length, abp_lines
    )
    abp_border = abp__on_hull(abp_hull, abp_segment)
    if abp_tracks >= 2 and abp_border and not abp_hinges:
        return 0.0
    if abp_hinges:
        return 0.85
    if abp_coverage >= abp_COVERAGE and abp_length <= abp_DOOR_MAX_M:
        return 0.65
    if abp_border:
        return 0.6 if abp_coverage >= abp_COVERAGE else 0.4
    return 0.0


def abp__line_coverage(
    abp_e: abpFloatArray,
    abp_u: abpFloatArray,
    abp_n: abpFloatArray,
    abp_length: float,
    abp_lines: abpFloatArray,
) -> tuple[float, int]:
    if len(abp_lines) == 0:
        return 0.0, 0
    abp_d = abp_lines[:, 2:] - abp_lines[:, :2]
    abp_size = np.maximum(np.hypot(abp_d[:, 0], abp_d[:, 1]), 1e-9)
    abp_parallel = np.abs(abp_d @ abp_n) / abp_size < math.sin(math.radians(8))
    abp_off = ((abp_lines[:, :2] + abp_lines[:, 2:]) / 2 - abp_e) @ abp_n
    abp_near = abp_lines[abp_parallel & (np.abs(abp_off) < 0.25)]
    abp_offsets = abp_off[abp_parallel & (np.abs(abp_off) < 0.25)]
    abp_t = np.sort(
        np.c_[(abp_near[:, :2] - abp_e) @ abp_u, (abp_near[:, 2:] - abp_e) @ abp_u], axis=1
    )
    abp_t = np.clip(abp_t, 0.0, abp_length)
    abp_long_enough = abp_t[:, 1] - abp_t[:, 0] > 0.05
    abp_t, abp_offsets = abp_t[abp_long_enough], abp_offsets[abp_long_enough]
    if len(abp_t) == 0:
        return 0.0, 0
    abp_grid = np.zeros(200, bool)
    for abp_a, abp_b in abp_t:
        abp_grid[int(abp_a / abp_length * 200) : int(abp_b / abp_length * 200) + 1] = True
    abp_tracks: list[float] = []
    for abp_value, (abp_a, abp_b) in zip(abp_offsets, abp_t, strict=True):
        if abp_b - abp_a > 0.5 * abp_length and all(
            abs(abp_value - abp_x) > 0.06 for abp_x in abp_tracks
        ):
            abp_tracks.append(float(abp_value))
    return float(abp_grid.mean()), len(abp_tracks)


def abp__flood(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray], abp_hull: abpFloatArray
) -> tuple[np.ndarray, abpFloatArray, float]:
    abp_everything = np.vstack([abp_walls, *[abp_o[None, :] for abp_o in abp_openings]])
    abp_lo = np.minimum(abp_everything[:, :2], abp_everything[:, 2:]).min(axis=0) - 1.0
    abp_hi = np.maximum(abp_everything[:, :2], abp_everything[:, 2:]).max(axis=0) + 1.0
    abp_w, abp_h = (int(abp_v) for abp_v in np.ceil((abp_hi - abp_lo) / abp_CELL_M))
    abp_mask = np.zeros((max(abp_h, 1), max(abp_w, 1)), np.uint8)
    for abp_x in abp_everything:
        abp_a, abp_b = (abp_x[:2] - abp_lo) / abp_CELL_M, (abp_x[2:] - abp_lo) / abp_CELL_M
        cv2.line(abp_mask, (int(abp_a[0]), int(abp_a[1])), (int(abp_b[0]), int(abp_b[1])), 1, 2)
    cv2.floodFill(abp_mask, None, (0, 0), (2,))
    abp_area = float(cv2.contourArea(abp_hull.astype(np.float32))) if len(abp_hull) >= 3 else 0.0
    abp_enclosed = float((abp_mask != 2).sum()) * abp_CELL_M**2 / max(abp_area, 1e-9)
    return abp_mask, abp_lo, abp_enclosed


def abp__is_outside(abp_mask: np.ndarray, abp_origin: abpFloatArray, abp_p: abpFloatArray) -> bool:
    abp_c, abp_r = (int(abp_v) for abp_v in (abp_p - abp_origin) / abp_CELL_M)
    abp_rows, abp_cols = abp_mask.shape
    return not (0 <= abp_r < abp_rows and 0 <= abp_c < abp_cols) or int(abp_mask[abp_r, abp_c]) == 2
