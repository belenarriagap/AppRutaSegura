from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpMask
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import (
    abp_remove_small_components,
    abp_thin,
)

abpSegmentArray = npt.NDArray[np.float64]


def abp_wall_mask(abp_binary: abpMask, abp_thickness: float) -> abpMask:
    abp_k = max(3, round(0.6 * abp_thickness))
    abp_closed = cv2.morphologyEx(
        abp_binary.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)
    )
    abp_opened = cv2.morphologyEx(abp_closed, cv2.MORPH_OPEN, np.ones((abp_k, abp_k), np.uint8))
    return abp_remove_small_components(
        abp_opened > 0, int(max(20.0, 3.0 * abp_thickness * abp_thickness))
    )


def abp_hough_segments(
    abp_mask: abpMask, *, abp_min_length: float, abp_max_gap: float
) -> abpSegmentArray:
    abp_skeleton = abp_thin(abp_mask).astype(np.uint8) * 255
    abp_lines = cv2.HoughLinesP(
        abp_skeleton,
        rho=1,
        theta=np.pi / 720,
        threshold=max(8, int(abp_min_length * 0.5)),
        minLineLength=abp_min_length,
        maxLineGap=abp_max_gap,
    )
    if abp_lines is None:
        return np.zeros((0, 4), dtype=np.float64)
    return np.asarray(abp_lines, dtype=np.float64).reshape(-1, 4)


def abp__line_params(abp_seg: npt.NDArray[np.float64]) -> tuple[float, float]:
    abp_x1, abp_y1, abp_x2, abp_y2 = (float(abp_v) for abp_v in abp_seg)
    abp_theta = math.atan2(abp_y2 - abp_y1, abp_x2 - abp_x1) % math.pi
    abp_rho = -math.sin(abp_theta) * abp_x1 + math.cos(abp_theta) * abp_y1
    return abp_theta, abp_rho


@dataclass(slots=True)
class abpLineGroup:
    abp_theta: float
    abp_rho: float
    abp_weight: float
    abp_members: list[npt.NDArray[np.float64]] = field(default_factory=list)

    @property
    def abp_direction(self) -> tuple[float, float]:
        return math.cos(self.abp_theta), math.sin(self.abp_theta)

    @property
    def abp_normal(self) -> tuple[float, float]:
        return -math.sin(self.abp_theta), math.cos(self.abp_theta)

    def abp_project(self, abp_x: float, abp_y: float) -> float:
        abp_dx, abp_dy = self.abp_direction
        return abp_dx * abp_x + abp_dy * abp_y

    def abp_point_at(self, abp_t: float) -> abpPoint:
        abp_dx, abp_dy = self.abp_direction
        abp_nx, abp_ny = self.abp_normal
        return abpPoint(
            abp_t * abp_dx + self.abp_rho * abp_nx, abp_t * abp_dy + self.abp_rho * abp_ny
        )

    def abp_refit(self) -> None:
        abp_samples = []
        for abp_x1, abp_y1, abp_x2, abp_y2 in self.abp_members:
            abp_n = max(2, int(math.hypot(abp_x2 - abp_x1, abp_y2 - abp_y1) / 4))
            abp_t = np.linspace(0.0, 1.0, abp_n)
            abp_samples.append(
                np.column_stack(
                    [abp_x1 + abp_t * (abp_x2 - abp_x1), abp_y1 + abp_t * (abp_y2 - abp_y1)]
                )
            )
        abp_pts = np.vstack(abp_samples)
        abp_center = abp_pts.mean(axis=0)
        _, _, abp_vt = np.linalg.svd(abp_pts - abp_center, full_matrices=False)
        abp_dx, abp_dy = float(abp_vt[0, 0]), float(abp_vt[0, 1])
        self.abp_theta = math.atan2(abp_dy, abp_dx) % math.pi
        self.abp_rho = -math.sin(self.abp_theta) * float(abp_center[0]) + math.cos(
            self.abp_theta
        ) * float(abp_center[1])

    def abp_intervals(self) -> list[tuple[float, float]]:
        abp_result = []
        for abp_x1, abp_y1, abp_x2, abp_y2 in self.abp_members:
            abp_a, abp_b = (
                self.abp_project(float(abp_x1), float(abp_y1)),
                self.abp_project(float(abp_x2), float(abp_y2)),
            )
            abp_result.append((min(abp_a, abp_b), max(abp_a, abp_b)))
        return sorted(abp_result)


def abp__aligned(abp_theta: float, abp_rho: float, abp_ref_theta: float) -> tuple[float, float]:
    if abp_theta - abp_ref_theta > math.pi / 2:
        return abp_theta - math.pi, -abp_rho
    if abp_ref_theta - abp_theta > math.pi / 2:
        return abp_theta + math.pi, -abp_rho
    return abp_theta, abp_rho


def abp_group_collinear(
    abp_segments: abpSegmentArray, *, abp_angle_tol_deg: float, abp_dist_tol: float
) -> list[abpLineGroup]:
    abp_angle_tol = math.radians(abp_angle_tol_deg)
    abp_lengths = np.hypot(
        abp_segments[:, 2] - abp_segments[:, 0], abp_segments[:, 3] - abp_segments[:, 1]
    )
    abp_groups: list[abpLineGroup] = []
    for abp_idx in np.argsort(-abp_lengths):
        abp_seg = abp_segments[abp_idx]
        abp_length = float(abp_lengths[abp_idx])
        abp_theta, abp_rho = abp__line_params(abp_seg)
        abp_best: abpLineGroup | None = None
        abp_best_dist = abp_dist_tol
        for abp_group in abp_groups:
            abp_th, abp_rh = abp__aligned(abp_theta, abp_rho, abp_group.abp_theta)
            if abs(abp_th - abp_group.abp_theta) > abp_angle_tol:
                continue
            abp_nx, abp_ny = abp_group.abp_normal
            abp_d = max(
                abs(abp_nx * abp_seg[0] + abp_ny * abp_seg[1] - abp_group.abp_rho),
                abs(abp_nx * abp_seg[2] + abp_ny * abp_seg[3] - abp_group.abp_rho),
            )
            if abp_d <= abp_best_dist:
                abp_best, abp_best_dist = abp_group, float(abp_d)
        if abp_best is None:
            abp_groups.append(abpLineGroup(abp_theta, abp_rho, abp_length, [abp_seg]))
            continue
        abp_th, abp_rh = abp__aligned(abp_theta, abp_rho, abp_best.abp_theta)
        abp_total = abp_best.abp_weight + abp_length
        abp_new_theta = (abp_best.abp_theta * abp_best.abp_weight + abp_th * abp_length) / abp_total
        abp_new_rho = (abp_best.abp_rho * abp_best.abp_weight + abp_rh * abp_length) / abp_total
        if abp_new_theta < 0 or abp_new_theta >= math.pi:
            abp_new_theta, abp_new_rho = abp_new_theta % math.pi, -abp_new_rho
        abp_best.abp_theta, abp_best.abp_rho, abp_best.abp_weight = (
            abp_new_theta,
            abp_new_rho,
            abp_total,
        )
        abp_best.abp_members.append(abp_seg)
    return abp_groups


def abp_merge_parallel_groups(
    abp_groups: Sequence[abpLineGroup], *, abp_angle_tol_deg: float, abp_dist_tol: float
) -> list[abpLineGroup]:
    abp_angle_tol = math.radians(abp_angle_tol_deg)
    for abp_group in abp_groups:
        abp_group.abp_refit()
    abp_pending = sorted(abp_groups, key=lambda abp_g: -abp_g.abp_weight)
    abp_result: list[abpLineGroup] = []
    for abp_group in abp_pending:
        abp_target = None
        for abp_kept in abp_result:
            abp_th, abp_rh = abp__aligned(
                abp_group.abp_theta, abp_group.abp_rho, abp_kept.abp_theta
            )
            if (
                abs(abp_th - abp_kept.abp_theta) <= abp_angle_tol
                and abs(abp_rh - abp_kept.abp_rho) <= abp_dist_tol
            ):
                abp_target = abp_kept
                break
        if abp_target is None:
            abp_result.append(
                abpLineGroup(
                    abp_group.abp_theta,
                    abp_group.abp_rho,
                    abp_group.abp_weight,
                    list(abp_group.abp_members),
                )
            )
            continue
        abp_th, abp_rh = abp__aligned(abp_group.abp_theta, abp_group.abp_rho, abp_target.abp_theta)
        abp_total = abp_target.abp_weight + abp_group.abp_weight
        abp_target.abp_theta = (
            abp_target.abp_theta * abp_target.abp_weight + abp_th * abp_group.abp_weight
        ) / abp_total
        abp_target.abp_rho = (
            abp_target.abp_rho * abp_target.abp_weight + abp_rh * abp_group.abp_weight
        ) / abp_total
        if abp_target.abp_theta < 0 or abp_target.abp_theta >= math.pi:
            abp_target.abp_theta, abp_target.abp_rho = (
                abp_target.abp_theta % math.pi,
                -abp_target.abp_rho,
            )
        abp_target.abp_weight = abp_total
        abp_target.abp_members.extend(abp_group.abp_members)
    for abp_group in abp_result:
        abp_group.abp_refit()
    return abp_result


def abp_merge_intervals(
    abp_intervals: Sequence[tuple[float, float]], abp_gap_tol: float
) -> list[tuple[float, float]]:
    abp_merged: list[tuple[float, float]] = []
    for abp_a, abp_b in sorted(abp_intervals):
        if abp_merged and abp_a - abp_merged[-1][1] <= abp_gap_tol:
            abp_merged[-1] = (abp_merged[-1][0], max(abp_merged[-1][1], abp_b))
        else:
            abp_merged.append((abp_a, abp_b))
    return abp_merged


def abp_occupancy(
    abp_mask: abpMask, abp_group: abpLineGroup, abp_t0: float, abp_t1: float, abp_half_width: float
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    abp_n = max(2, int(abs(abp_t1 - abp_t0)) + 1)
    abp_ts = np.linspace(abp_t0, abp_t1, abp_n)
    abp_dx, abp_dy = abp_group.abp_direction
    abp_nx, abp_ny = abp_group.abp_normal
    abp_offsets = np.linspace(-abp_half_width, abp_half_width, max(3, int(2 * abp_half_width) + 1))
    abp_xs = abp_ts[:, None] * abp_dx + abp_group.abp_rho * abp_nx + abp_offsets[None, :] * abp_nx
    abp_ys = abp_ts[:, None] * abp_dy + abp_group.abp_rho * abp_ny + abp_offsets[None, :] * abp_ny
    abp_xi, abp_yi = abp_xs.round().astype(int), abp_ys.round().astype(int)
    abp_h, abp_w = abp_mask.shape
    abp_ok = (abp_xi >= 0) & (abp_xi < abp_w) & (abp_yi >= 0) & (abp_yi < abp_h)
    abp_hit = np.zeros(abp_xi.shape, dtype=np.bool_)
    abp_hit[abp_ok] = abp_mask[abp_yi[abp_ok], abp_xi[abp_ok]]
    return abp_ts, np.asarray(abp_hit.any(axis=1), dtype=np.bool_)


def abp_longest_empty_run(
    abp_ts: npt.NDArray[np.float64], abp_occupied: npt.NDArray[np.bool_]
) -> tuple[float, float] | None:
    abp_best: tuple[float, float] | None = None
    abp_start: int | None = None
    for abp_i, abp_occ in enumerate([*abp_occupied.tolist(), True]):
        if not abp_occ and abp_start is None:
            abp_start = abp_i
        elif abp_occ and abp_start is not None:
            abp_run = (float(abp_ts[abp_start]), float(abp_ts[abp_i - 1]))
            if abp_best is None or abs(abp_run[1] - abp_run[0]) > abs(abp_best[1] - abp_best[0]):
                abp_best = abp_run
            abp_start = None
    return abp_best


def abp_extend_to_mask_end(
    abp_mask: abpMask,
    abp_group: abpLineGroup,
    abp_t: float,
    abp_direction: float,
    abp_max_dist: float,
    abp_half_width: float,
) -> float:
    abp_ts, abp_occ = abp_occupancy(
        abp_mask, abp_group, abp_t, abp_t + abp_direction * abp_max_dist, abp_half_width
    )
    abp_empty = np.flatnonzero(~abp_occ)
    if abp_empty.size == 0:
        return float(abp_ts[-1])
    return float(abp_ts[max(int(abp_empty[0]) - 1, 0)])


def abp__line_intersection(abp_s1: abpSegment, abp_s2: abpSegment) -> abpPoint | None:
    abp_x1, abp_y1, abp_x2, abp_y2 = (
        abp_s1.abp_start.abp_x,
        abp_s1.abp_start.abp_y,
        abp_s1.abp_end.abp_x,
        abp_s1.abp_end.abp_y,
    )
    abp_x3, abp_y3, abp_x4, abp_y4 = (
        abp_s2.abp_start.abp_x,
        abp_s2.abp_start.abp_y,
        abp_s2.abp_end.abp_x,
        abp_s2.abp_end.abp_y,
    )
    abp_den = (abp_x1 - abp_x2) * (abp_y3 - abp_y4) - (abp_y1 - abp_y2) * (abp_x3 - abp_x4)
    if abs(abp_den) < 1e-9:
        return None
    abp_a = abp_x1 * abp_y2 - abp_y1 * abp_x2
    abp_b = abp_x3 * abp_y4 - abp_y3 * abp_x4
    return abpPoint(
        (abp_a * (abp_x3 - abp_x4) - (abp_x1 - abp_x2) * abp_b) / abp_den,
        (abp_a * (abp_y3 - abp_y4) - (abp_y1 - abp_y2) * abp_b) / abp_den,
    )


def abp__angle_between(abp_s1: abpSegment, abp_s2: abpSegment) -> float:
    abp_a1 = math.atan2(
        abp_s1.abp_end.abp_y - abp_s1.abp_start.abp_y, abp_s1.abp_end.abp_x - abp_s1.abp_start.abp_x
    )
    abp_a2 = math.atan2(
        abp_s2.abp_end.abp_y - abp_s2.abp_start.abp_y, abp_s2.abp_end.abp_x - abp_s2.abp_start.abp_x
    )
    abp_diff = abs(abp_a1 - abp_a2) % math.pi
    return min(abp_diff, math.pi - abp_diff)


def abp__param_on(abp_segment: abpSegment, abp_point: abpPoint) -> float:
    abp_dx, abp_dy = (
        abp_segment.abp_end.abp_x - abp_segment.abp_start.abp_x,
        abp_segment.abp_end.abp_y - abp_segment.abp_start.abp_y,
    )
    abp_length2 = abp_dx * abp_dx + abp_dy * abp_dy
    if abp_length2 == 0:
        return 0.0
    return (
        (abp_point.abp_x - abp_segment.abp_start.abp_x) * abp_dx
        + (abp_point.abp_y - abp_segment.abp_start.abp_y) * abp_dy
    ) / abp_length2


def abp_snap_endpoints(
    abp_segments: Sequence[abpSegment], abp_tol: float, abp_min_angle_deg: float = 30.0
) -> tuple[list[abpSegment], list[tuple[bool, bool]]]:
    abp_min_angle = math.radians(abp_min_angle_deg)
    abp_result = list(abp_segments)
    abp_joined: list[tuple[bool, bool]] = []
    for abp_i, abp_seg in enumerate(abp_segments):
        abp_ends = [abp_seg.abp_start, abp_seg.abp_end]
        abp_flags = [False, False]
        for abp_k in (0, 1):
            abp_endpoint = abp_ends[abp_k]
            abp_best: abpPoint | None = None
            abp_best_d = abp_tol
            for abp_j, abp_other in enumerate(abp_segments):
                if abp_i == abp_j or abp__angle_between(abp_seg, abp_other) < abp_min_angle:
                    continue
                abp_x = abp__line_intersection(abp_seg, abp_other)
                if abp_x is None:
                    continue
                abp_d = abp_endpoint.abp_distance_to(abp_x)
                if abp_d > abp_best_d:
                    continue
                abp_margin = abp_tol / max(abp_other.abp_length, 1e-9)
                if not -abp_margin <= abp__param_on(abp_other, abp_x) <= 1 + abp_margin:
                    continue
                abp_best, abp_best_d = abp_x, abp_d
            if abp_best is not None:
                abp_ends[abp_k] = abp_best
                abp_flags[abp_k] = True
        abp_result[abp_i] = abpSegment(abp_ends[0], abp_ends[1])
        abp_joined.append((abp_flags[0], abp_flags[1]))
    return abp_result, abp_joined


def abp_segment_coverage(
    abp_mask: abpMask, abp_segment: abpSegment, abp_step: float = 2.0
) -> float:
    abp_n = max(2, int(abp_segment.abp_length / abp_step))
    abp_xs = (
        np.linspace(abp_segment.abp_start.abp_x, abp_segment.abp_end.abp_x, abp_n)
        .round()
        .astype(int)
    )
    abp_ys = (
        np.linspace(abp_segment.abp_start.abp_y, abp_segment.abp_end.abp_y, abp_n)
        .round()
        .astype(int)
    )
    abp_h, abp_w = abp_mask.shape
    abp_inside = (abp_xs >= 0) & (abp_xs < abp_w) & (abp_ys >= 0) & (abp_ys < abp_h)
    if not abp_inside.any():
        return 0.0
    return float(abp_mask[abp_ys[abp_inside], abp_xs[abp_inside]].mean() * abp_inside.mean())
