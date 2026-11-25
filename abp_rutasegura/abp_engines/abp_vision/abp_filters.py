from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage

abpGrayImage = npt.NDArray[np.uint8]
abpMask = npt.NDArray[np.bool_]

abp_LIGHT_FILL_SATURATION = 70
abp_LIGHT_FILL_VALUE = 150
abp_MIN_THICKNESS_RATIO = 0.65
abp_MIN_NETWORK_SHARE = 0.2


def abp_suppress_light_fills(abp_image: abpRGBImage, abp_gray: abpGrayImage) -> abpGrayImage:
    if abp_image.ndim != 3:
        return abp_gray
    abp_hsv = cv2.cvtColor(abp_image, cv2.COLOR_RGB2HSV)
    abp_light_colored = (abp_hsv[:, :, 1] > abp_LIGHT_FILL_SATURATION) & (
        abp_hsv[:, :, 2] > abp_LIGHT_FILL_VALUE
    )
    abp_out = abp_gray.copy()
    abp_out[abp_light_colored] = 255
    return abp_out


def abp_stroke_thickness(
    abp_binary: abpMask, abp_segment: abpSegment, abp_step: float = 2.0
) -> float:
    abp_dist = np.asarray(
        cv2.distanceTransform(abp_binary.astype(np.uint8), cv2.DIST_L2, 3), np.float32
    )
    return abp__thickness_on(abp_dist, abp_segment, abp_step)


def abp__thickness_on(
    abp_dist: npt.NDArray[np.float32], abp_segment: abpSegment, abp_step: float
) -> float:
    abp_n = max(2, int(abp_segment.abp_length / abp_step))
    abp_ts = np.linspace(0.1, 0.9, abp_n)
    abp_xs = abp_segment.abp_start.abp_x + abp_ts * (
        abp_segment.abp_end.abp_x - abp_segment.abp_start.abp_x
    )
    abp_ys = abp_segment.abp_start.abp_y + abp_ts * (
        abp_segment.abp_end.abp_y - abp_segment.abp_start.abp_y
    )
    abp_h, abp_w = abp_dist.shape
    abp_cols = np.clip(np.round(abp_xs).astype(int), 0, abp_w - 1)
    abp_rows = np.clip(np.round(abp_ys).astype(int), 0, abp_h - 1)
    abp_values = np.zeros(abp_n, dtype=np.float64)
    for abp_dr in (-1, 0, 1):
        for abp_dc in (-1, 0, 1):
            abp_r = np.clip(abp_rows + abp_dr, 0, abp_h - 1)
            abp_c = np.clip(abp_cols + abp_dc, 0, abp_w - 1)
            abp_values = np.maximum(abp_values, abp_dist[abp_r, abp_c])
    return float(2.0 * np.median(abp_values))


def abp_thick_enough(
    abp_binary: abpMask, abp_segments: Sequence[abpSegment], abp_thickness: float
) -> list[bool]:
    abp_dist = np.asarray(
        cv2.distanceTransform(abp_binary.astype(np.uint8), cv2.DIST_L2, 3), np.float32
    )
    return [
        abp__thickness_on(abp_dist, abp_s, 2.0) >= abp_MIN_THICKNESS_RATIO * abp_thickness
        for abp_s in abp_segments
    ]


def abp__angle_mod_90(abp_segment: abpSegment) -> float:
    abp_angle = math.degrees(
        math.atan2(
            abp_segment.abp_end.abp_y - abp_segment.abp_start.abp_y,
            abp_segment.abp_end.abp_x - abp_segment.abp_start.abp_x,
        )
    )
    return abp_angle % 90.0


def abp_dominant_angle(abp_segments: Sequence[abpSegment]) -> float | None:
    if not abp_segments:
        return None
    abp_sx = sum(
        abp_s.abp_length * math.cos(math.radians(4 * abp__angle_mod_90(abp_s)))
        for abp_s in abp_segments
    )
    abp_sy = sum(
        abp_s.abp_length * math.sin(math.radians(4 * abp__angle_mod_90(abp_s)))
        for abp_s in abp_segments
    )
    if abp_sx == 0 and abp_sy == 0:
        return None
    return (math.degrees(math.atan2(abp_sy, abp_sx)) / 4) % 90.0


def abp_aligned(abp_segments: Sequence[abpSegment], abp_tolerance_deg: float) -> list[bool]:
    abp_main = abp_dominant_angle(abp_segments)
    if abp_main is None:
        return [True] * len(abp_segments)
    abp_out = []
    for abp_s in abp_segments:
        abp_diff = abs(abp__angle_mod_90(abp_s) - abp_main) % 90.0
        abp_out.append(min(abp_diff, 90.0 - abp_diff) <= abp_tolerance_deg)
    return abp_out


def abp__point_segment_distance(abp_p: abpPoint, abp_s: abpSegment) -> float:
    abp_dx, abp_dy = (
        abp_s.abp_end.abp_x - abp_s.abp_start.abp_x,
        abp_s.abp_end.abp_y - abp_s.abp_start.abp_y,
    )
    abp_length2 = abp_dx * abp_dx + abp_dy * abp_dy
    if abp_length2 == 0:
        return abp_p.abp_distance_to(abp_s.abp_start)
    abp_t = max(
        0.0,
        min(
            1.0,
            (
                (abp_p.abp_x - abp_s.abp_start.abp_x) * abp_dx
                + (abp_p.abp_y - abp_s.abp_start.abp_y) * abp_dy
            )
            / abp_length2,
        ),
    )
    return abp_p.abp_distance_to(
        abpPoint(abp_s.abp_start.abp_x + abp_t * abp_dx, abp_s.abp_start.abp_y + abp_t * abp_dy)
    )


def abp_touches(abp_a: abpSegment, abp_b: abpSegment, abp_tol: float) -> bool:
    return any(
        abp__point_segment_distance(abp_p, abp_b) <= abp_tol
        for abp_p in (abp_a.abp_start, abp_a.abp_end)
    ) or any(
        abp__point_segment_distance(abp_p, abp_a) <= abp_tol
        for abp_p in (abp_b.abp_start, abp_b.abp_end)
    )


def abp_main_network(
    abp_segments: Sequence[abpSegment], abp_tol: float, abp_links: Sequence[abpSegment] = ()
) -> list[bool]:
    abp_everything = [*abp_segments, *abp_links]
    abp_n = len(abp_everything)
    abp_parent = list(range(abp_n))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = abp_parent[abp_i]
        return abp_i

    for abp_i in range(abp_n):
        for abp_j in range(abp_i + 1, abp_n):
            if abp_touches(abp_everything[abp_i], abp_everything[abp_j], abp_tol):
                abp_parent[abp_find(abp_i)] = abp_find(abp_j)
    abp_totals: dict[int, float] = {}
    for abp_i, abp_s in enumerate(abp_segments):
        abp_totals[abp_find(abp_i)] = abp_totals.get(abp_find(abp_i), 0.0) + abp_s.abp_length
    if not abp_totals:
        return []
    abp_biggest = max(abp_totals.values())
    return [
        abp_totals[abp_find(abp_i)] >= abp_MIN_NETWORK_SHARE * abp_biggest
        for abp_i in range(len(abp_segments))
    ]


def abp_opening_supported(
    abp_opening: abpSegment, abp_walls: Sequence[abpSegment], abp_tol: float
) -> bool:
    return all(
        any(abp__point_segment_distance(abp_p, abp_w) <= abp_tol for abp_w in abp_walls)
        for abp_p in (abp_opening.abp_start, abp_opening.abp_end)
    )
