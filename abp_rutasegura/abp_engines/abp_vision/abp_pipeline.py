from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpExit, abpWall
from abp_rutasegura.abp_engines.abp_vision.abp_doors import (
    abp_building_outline,
    abp_corner_gaps,
    abp_door_confidence,
    abp_is_on_outline,
)
from abp_rutasegura.abp_engines.abp_vision.abp_filters import (
    abp_aligned,
    abp_main_network,
    abp_opening_supported,
    abp_suppress_light_fills,
    abp_thick_enough,
)
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import (
    abp_binarize,
    abp_estimate_wall_thickness,
    abp_to_gray,
)
from abp_rutasegura.abp_engines.abp_vision.abp_walls import (
    abp_extend_to_mask_end,
    abp_group_collinear,
    abp_hough_segments,
    abp_longest_empty_run,
    abp_merge_intervals,
    abp_merge_parallel_groups,
    abp_occupancy,
    abp_segment_coverage,
    abp_snap_endpoints,
    abp_wall_mask,
)


@dataclass(frozen=True, slots=True)
class abpVisionParams:
    abp_scale_m_per_px: float | None = None
    abp_wall_thickness_px: float | None = None
    abp_door_min_m: float = 0.6
    abp_door_max_m: float = 2.4
    abp_exit_max_m: float = 4.0
    abp_door_min_thickness_factor: float = 3.5
    abp_door_max_thickness_factor: float = 16.0
    abp_angle_tol_deg: float = 3.0
    abp_furniture_filters: bool = True
    abp_orthogonal_only: bool = True
    abp_orthogonal_tol_deg: float = 6.0


@dataclass(frozen=True, slots=True)
class abpDetectionResult:
    abp_walls: tuple[abpWall, ...]
    abp_doors: tuple[abpDoor, ...]
    abp_exits: tuple[abpExit, ...]
    abp_wall_thickness_px: float


abp_EDGE_CORRECTION_PX = 1.0

abp_EMPTY_RESULT = abpDetectionResult((), (), (), 0.0)


def abp_detect_plan(
    abp_image: abpRGBImage, abp_params: abpVisionParams | None = None
) -> abpDetectionResult:
    abp_params = abp_params or abpVisionParams()
    abp_gray = abp_to_gray(abp_image)
    if abp_params.abp_furniture_filters:
        abp_gray = abp_suppress_light_fills(abp_image, abp_gray)
    abp_binary = abp_binarize(abp_gray)
    abp_thickness = abp_params.abp_wall_thickness_px or abp_estimate_wall_thickness(abp_binary)
    if abp_thickness < 2.0:
        return abp_EMPTY_RESULT
    if abp_params.abp_scale_m_per_px:
        abp_door_min = abp_params.abp_door_min_m / abp_params.abp_scale_m_per_px
        abp_door_max = abp_params.abp_door_max_m / abp_params.abp_scale_m_per_px
        abp_exit_max = abp_params.abp_exit_max_m / abp_params.abp_scale_m_per_px
    else:
        abp_door_min = abp_params.abp_door_min_thickness_factor * abp_thickness
        abp_door_max = abp_params.abp_door_max_thickness_factor * abp_thickness
        abp_exit_max = abp_door_max * abp_params.abp_exit_max_m / abp_params.abp_door_max_m

    abp_mask = abp_wall_mask(abp_binary, abp_thickness)
    abp_segments = abp_hough_segments(
        abp_mask,
        abp_min_length=max(2.0 * abp_thickness, 10.0),
        abp_max_gap=max(2.0, min(abp_thickness, 0.4 * abp_door_min)),
    )
    if len(abp_segments) == 0:
        return abpDetectionResult((), (), (), abp_thickness)

    abp_dist_tol = max(0.6 * abp_thickness, 3.0)
    abp_groups = abp_merge_parallel_groups(
        abp_group_collinear(
            abp_segments, abp_angle_tol_deg=abp_params.abp_angle_tol_deg, abp_dist_tol=abp_dist_tol
        ),
        abp_angle_tol_deg=abp_params.abp_angle_tol_deg,
        abp_dist_tol=abp_dist_tol,
    )
    abp_half_width = max(1.0, abp_thickness / 4)
    abp_raw_walls: list[abpSegment] = []
    abp_gap_doors: list[abpSegment] = []
    abp_gap_ends: set[tuple[int, int]] = set()
    for abp_group in abp_groups:
        abp_intervals = [
            list(abp_iv)
            for abp_iv in abp_merge_intervals(abp_group.abp_intervals(), 0.7 * abp_door_min)
        ]
        abp_pieces: list[list[float]] = [abp_intervals[0]]
        abp_door_after: list[bool] = []
        for abp_nxt in abp_intervals[1:]:
            abp_prev = abp_pieces[-1]
            abp_run = abp_longest_empty_run(
                *abp_occupancy(abp_mask, abp_group, abp_prev[1], abp_nxt[0], abp_half_width)
            )
            if abp_run is None or abp_run[1] - abp_run[0] < 0.75 * abp_door_min:
                abp_prev[1] = abp_nxt[1]
                continue
            abp_prev[1], abp_nxt[0] = (
                abp_run[0] - abp_EDGE_CORRECTION_PX,
                abp_run[1] + abp_EDGE_CORRECTION_PX,
            )
            abp_pieces.append(abp_nxt)
            abp_door_after.append(abp_run[1] - abp_run[0] <= 1.1 * abp_exit_max)
        abp_pieces[0][0] = abp_extend_to_mask_end(
            abp_mask, abp_group, abp_pieces[0][0], -1.0, 1.5 * abp_thickness, abp_half_width
        )
        abp_pieces[-1][1] = abp_extend_to_mask_end(
            abp_mask, abp_group, abp_pieces[-1][1], 1.0, 1.5 * abp_thickness, abp_half_width
        )
        abp_first = len(abp_raw_walls)
        abp_raw_walls.extend(
            abpSegment(abp_group.abp_point_at(abp_a), abp_group.abp_point_at(abp_b))
            for abp_a, abp_b in abp_pieces
        )
        for abp_k, abp_is_door in enumerate(abp_door_after):
            abp_gap_ends.update({(abp_first + abp_k, 1), (abp_first + abp_k + 1, 0)})
            if abp_is_door:
                abp_gap_doors.append(
                    abpSegment(
                        abp_group.abp_point_at(abp_pieces[abp_k][1]),
                        abp_group.abp_point_at(abp_pieces[abp_k + 1][0]),
                    )
                )

    abp_walls, abp_joined = abp_snap_endpoints(abp_raw_walls, abp_tol=1.5 * abp_thickness)
    abp_free_ends = [
        (abp_i, abp_end)
        for abp_i, abp_flags in enumerate(abp_joined)
        for abp_end, abp_is_joined in enumerate(abp_flags)
        if not abp_is_joined and (abp_i, abp_end) not in abp_gap_ends
    ]
    abp_openings = abp_gap_doors + abp_corner_gaps(
        abp_walls,
        abp_free_ends,
        abp_mask,
        abp_thickness=abp_thickness,
        abp_min_px=abp_door_min,
        abp_max_px=abp_exit_max,
    )
    abp_walls = [abp_seg for abp_seg in abp_walls if abp_seg.abp_length >= abp_thickness]
    if abp_params.abp_furniture_filters and abp_walls:
        abp_walls = [
            abp_w
            for abp_w, abp_ok in zip(
                abp_walls, abp_thick_enough(abp_binary, abp_walls, abp_thickness), strict=True
            )
            if abp_ok
        ]
        if abp_params.abp_orthogonal_only:
            abp_keep = abp_aligned(abp_walls, abp_params.abp_orthogonal_tol_deg)
            abp_walls = [abp_w for abp_w, abp_ok in zip(abp_walls, abp_keep, strict=True) if abp_ok]
        abp_network = abp_main_network(
            abp_walls, abp_tol=1.5 * abp_thickness, abp_links=abp_gap_doors
        )
        abp_walls = [abp_w for abp_w, abp_ok in zip(abp_walls, abp_network, strict=True) if abp_ok]
        abp_openings = [
            abp_o
            for abp_o in abp_openings
            if abp_opening_supported(abp_o, abp_walls, abp_tol=1.5 * abp_thickness)
        ]

    abp_thick = max(3, round(abp_thickness) | 1)
    abp_residual = abp_binary & ~(
        cv2.dilate(abp_mask.astype(np.uint8), np.ones((abp_thick, abp_thick), np.uint8)) > 0
    )
    abp_outline = abp_building_outline(abp_mask, abp_close_px=int(abp_door_max * 1.2))
    abp_doors: list[abpDoor] = []
    abp_exits: list[abpExit] = []
    for abp_opening in abp_openings:
        if abp_outline is not None and abp_is_on_outline(
            abp_outline, abp_opening.abp_midpoint, 1.5 * abp_thickness
        ):
            abp_exits.append(
                abpExit(abp_opening, abp_name=f"Salida {len(abp_exits) + 1}", abp_confirmed=False)
            )
        elif abp_opening.abp_length <= 1.1 * abp_door_max:
            abp_doors.append(
                abpDoor(abp_opening, round(abp_door_confidence(abp_residual, abp_opening), 3))
            )

    abp_tolerant = cv2.dilate(abp_mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    abp_detected_walls = tuple(
        abpWall(abp_seg, round(min(1.0, abp_segment_coverage(abp_tolerant, abp_seg)), 3))
        for abp_seg in abp_walls
    )
    return abpDetectionResult(abp_detected_walls, tuple(abp_doors), tuple(abp_exits), abp_thickness)
