from __future__ import annotations

import math
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpExit, abpFloorPlan, abpStair, abpWall
from abp_rutasegura.abp_domain.abp_vector import (
    abpBoolArray,
    abpFloatArray,
    abpVectorPlan,
    abpVectorText,
)
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import (
    abp_is_furniture_layer,
    abp_is_structure_layer,
    abp_is_wall_layer,
    abp_plain,
)

abp_WALL_MIN_M, abp_WALL_MAX_M = 0.07, 0.46
abp_SEED_LENGTH_M = 0.6
abp_MIN_PIECE_M = 0.22
abp_DOOR_MIN_M, abp_DOOR_MAX_M = 0.6, 2.6
abp_ARC_RADIUS_M = (0.35, 1.5)
abp_ARC_SWEEP_DEG = (45.0, 130.0)
abp_COLUMN_GAP_M = 0.55
abp_NETWORK_TOL_M = 0.4
abp_MIN_NETWORK_SHARE = 0.12
abp_JAMB_REACH_M = 0.75
abp_CORNER_REACH_M = 1.15
abp_WINDOW_MAX_M = 4.5
abp_DIMENSION = re.compile(r"^(\d{1,2}[.,]\d{1,2})\s*m?$", re.IGNORECASE)
abp_DIMENSION_SCALES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500)
abp_STAIR_TREAD_M = (0.20, 0.40)
abp_MIN_WALL_LAYER_M = 12.0
abp_MIN_WALLS_M = 6.0
abp_SINGLE_LINE_MIN_M = 0.8
abp_TAG = re.compile(r"^(?:(?:P|PC|PV|V|VEN|VE|M|MP)\s*[-.]?\s*\d{1,3}|\d{1,2}[.,]\d{2})$")


@dataclass(frozen=True)
class abpVectorDetection:
    abp_walls: tuple[abpWall, ...]
    abp_doors: tuple[abpDoor, ...]
    abp_exits: tuple[abpExit, ...]
    abp_stairs: tuple[abpStair, ...]
    abp_bounds: tuple[float, float, float, float] | None


def abp__lengths(abp_s: abpFloatArray) -> abpFloatArray:
    return np.asarray(np.hypot(abp_s[:, 2] - abp_s[:, 0], abp_s[:, 3] - abp_s[:, 1]), np.float64)


def abp__angles(abp_s: abpFloatArray) -> abpFloatArray:
    return np.asarray(
        np.degrees(np.arctan2(abp_s[:, 3] - abp_s[:, 1], abp_s[:, 2] - abp_s[:, 0])) % 180.0
    )


def abp__angle_diff(abp_a: abpFloatArray, abp_b: float) -> abpFloatArray:
    return np.asarray(np.abs((abp_a - abp_b + 90.0) % 180.0 - 90.0), np.float64)


def abp__unit(abp_s: abpFloatArray) -> tuple[abpFloatArray, abpFloatArray]:
    abp_d = abp_s[2:] - abp_s[:2]
    abp_u = abp_d / max(float(np.hypot(abp_d[0], abp_d[1])), 1e-9)
    return abp_u, np.array([-abp_u[1], abp_u[0]])


def abp_point_segments_distance(abp_p: abpFloatArray, abp_s: abpFloatArray) -> abpFloatArray:
    abp_a, abp_d = abp_s[:, :2], abp_s[:, 2:] - abp_s[:, :2]
    abp_l2 = np.maximum((abp_d**2).sum(axis=1), 1e-12)
    abp_t = np.clip(((abp_p - abp_a) * abp_d).sum(axis=1) / abp_l2, 0.0, 1.0)
    abp_q = abp_a + abp_t[:, None] * abp_d
    return np.asarray(np.hypot(abp_p[0] - abp_q[:, 0], abp_p[1] - abp_q[:, 1]), np.float64)


def abp_merge_collinear(
    abp_s: abpFloatArray,
    *,
    abp_angle_deg: float = 1.0,
    abp_offset: float = 0.015,
    abp_gap: float = 0.02,
) -> abpFloatArray:
    abp_s = abp_s[abp__lengths(abp_s) > 1e-6]
    if len(abp_s) == 0:
        return abp_s
    abp_angles = abp__angles(abp_s)
    abp_order = np.argsort(-abp__lengths(abp_s), kind="stable")
    abp_used = np.zeros(len(abp_s), bool)
    abp_out: list[abpFloatArray] = []
    abp_by_angle = np.argsort(abp_angles, kind="stable")
    abp_wrapped = np.concatenate([abp_by_angle] * 3)
    abp_turned = np.concatenate(
        [abp_angles[abp_by_angle] + abp_turn for abp_turn in (-180.0, 0.0, 180.0)]
    )
    for abp_i in abp_order:
        if abp_used[abp_i]:
            continue
        abp_u, abp_n = abp__unit(abp_s[abp_i])
        abp_angle = float(abp_angles[abp_i])
        abp_first = np.searchsorted(abp_turned, abp_angle - abp_angle_deg - 1e-9)
        abp_last = np.searchsorted(abp_turned, abp_angle + abp_angle_deg + 1e-9, side="right")
        abp_idx = np.sort(abp_wrapped[abp_first:abp_last])
        abp_idx = abp_idx[~abp_used[abp_idx]]
        abp_near = (
            (abp__angle_diff(abp_angles[abp_idx], abp_angle) <= abp_angle_deg)
            & (np.abs((abp_s[abp_idx, :2] - abp_s[abp_i, :2]) @ abp_n) < abp_offset)
            & (np.abs((abp_s[abp_idx, 2:] - abp_s[abp_i, :2]) @ abp_n) < abp_offset)
        )
        abp_idx = abp_idx[abp_near]
        abp_t = np.sort(
            np.c_[
                (abp_s[abp_idx, :2] - abp_s[abp_i, :2]) @ abp_u,
                (abp_s[abp_idx, 2:] - abp_s[abp_i, :2]) @ abp_u,
            ],
            axis=1,
        )
        abp_by_start = np.argsort(abp_t[:, 0], kind="stable")
        abp_lo, abp_hi = 0.0, float((abp_s[abp_i, 2:] - abp_s[abp_i, :2]) @ abp_u)
        abp_members = {int(abp_i)}
        for abp_k in abp_by_start:
            if abp_t[abp_k, 0] <= abp_hi + abp_gap and abp_t[abp_k, 1] >= abp_lo - abp_gap:
                abp_hi = max(abp_hi, float(abp_t[abp_k, 1]))
                abp_members.add(int(abp_idx[abp_k]))
        for abp_k in abp_by_start[::-1]:
            if abp_t[abp_k, 1] >= abp_lo - abp_gap and abp_t[abp_k, 0] <= abp_hi + abp_gap:
                abp_lo = min(abp_lo, float(abp_t[abp_k, 0]))
                abp_members.add(int(abp_idx[abp_k]))
        abp_used[list(abp_members)] = True
        abp_out.append(
            np.concatenate([abp_s[abp_i, :2] + abp_lo * abp_u, abp_s[abp_i, :2] + abp_hi * abp_u])
        )
    return np.array(abp_out, np.float64).reshape(-1, 4)


def abp__inside_box(
    abp_s: abpFloatArray, abp_center: abpFloatArray, abp_half: abpFloatArray, abp_angle: float
) -> abpBoolArray:
    abp_c, abp_si = math.cos(math.radians(abp_angle)), math.sin(math.radians(abp_angle))
    abp_u, abp_v = np.array([abp_c, abp_si]), np.array([-abp_si, abp_c])
    abp_ok = np.ones(len(abp_s), bool)
    for abp_k in (0, 2):
        abp_d = abp_s[:, abp_k : abp_k + 2] - abp_center
        abp_ok &= (np.abs(abp_d @ abp_u) <= abp_half[0]) & (np.abs(abp_d @ abp_v) <= abp_half[1])
    return np.asarray(abp_ok, np.bool_)


def abp_text_frames(
    abp_s: abpFloatArray, abp_texts: Collection[abpVectorText], abp_scale: float
) -> abpBoolArray:
    abp_out = np.zeros(len(abp_s), bool)
    if len(abp_s) == 0:
        return abp_out
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    abp_mid = (abp_s[:, :2] + abp_s[:, 2:]) / 2
    for abp_t in abp_texts:
        abp_center = np.array([abp_t.abp_x, abp_t.abp_y]) * abp_scale
        abp_size = abp_t.abp_size * abp_scale
        abp_half = np.array([abp_t.abp_width / 2 * abp_scale + 1.1 * abp_size, 1.1 * abp_size])
        abp_squared = np.minimum(
            abp__angle_diff(abp_angles, abp_t.abp_angle_deg % 180.0),
            abp__angle_diff(abp_angles, (abp_t.abp_angle_deg + 90) % 180.0),
        )
        abp_out |= (abp_squared < 1.5) & abp__inside_box(
            abp_s, abp_center, abp_half, abp_t.abp_angle_deg
        )
        if not abp_TAG.match(abp_plain(abp_t.abp_text)):
            continue
        abp_rad = math.radians(abp_t.abp_angle_deg)
        abp_u, abp_v = (
            np.array([math.cos(abp_rad), math.sin(abp_rad)]),
            np.array([-math.sin(abp_rad), math.cos(abp_rad)]),
        )
        abp_offset = (abp_mid - abp_center) @ abp_v
        abp_rows = (
            (np.abs((abp_mid - abp_center) @ abp_u) <= abp_length / 2 + 0.5 * abp_size)
            & (np.abs(abp_offset) < 2.2 * abp_size)
            & (abp__angle_diff(abp_angles, abp_t.abp_angle_deg % 180.0) < 2)
            & (abp_length < 22 * abp_size)
        )
        abp_idx = np.flatnonzero(abp_rows)
        if len(abp_idx) < 2:
            continue
        abp_span = np.sort(
            np.c_[
                (abp_s[abp_idx, :2] - abp_center) @ abp_u, (abp_s[abp_idx, 2:] - abp_center) @ abp_u
            ],
            axis=1,
        )
        abp_alike = np.array(
            [(np.abs(abp_span - abp_x).max(axis=1) < 0.3 * abp_size).sum() for abp_x in abp_span]
        )
        abp_group = abp_idx[
            np.abs(abp_span - abp_span[int(np.argmax(abp_alike))]).max(axis=1) < 0.3 * abp_size
        ]
        if not ((abp_offset[abp_group] > 0).any() and (abp_offset[abp_group] < 0).any()):
            continue
        abp_ends = np.vstack([abp_s[abp_group, :2], abp_s[abp_group, 2:]]) - abp_center
        abp_x, abp_y = abp_ends @ abp_u, abp_ends @ abp_v
        abp_box_center = (
            abp_center
            + abp_u * (abp_x.min() + abp_x.max()) / 2
            + abp_v * (abp_y.min() + abp_y.max()) / 2
        )
        abp_box_half = (
            np.array([abp_x.max() - abp_x.min(), abp_y.max() - abp_y.min()]) / 2 + 0.4 * abp_size
        )
        abp_out |= abp__inside_box(abp_s, abp_box_center, abp_box_half, abp_t.abp_angle_deg)
    return np.asarray(abp_out, np.bool_)


def abp_dimension_lines(
    abp_s: abpFloatArray, abp_texts: Collection[abpVectorText], abp_scale: float
) -> abpBoolArray:
    abp_out = np.zeros(len(abp_s), bool)
    if len(abp_s) == 0:
        return abp_out
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    for abp_t in abp_texts:
        abp_value = abp_dimension_value(abp_t.abp_text)
        if abp_value is None:
            continue
        abp_center = np.array([abp_t.abp_x, abp_t.abp_y]) * abp_scale
        abp_near = abp_point_segments_distance(abp_center, abp_s) < 2.5 * abp_t.abp_size * abp_scale
        for abp_i in np.flatnonzero(
            abp_near & (np.abs(abp_length - abp_value) < 0.04 * abp_value + 0.02)
        ):
            abp_u, abp_n = abp__unit(abp_s[abp_i])
            abp_along = float((abp_center - abp_s[abp_i, :2]) @ abp_u) / abp_length[abp_i]
            abp_parallel = (
                float(
                    abp__angle_diff(abp_angles[abp_i : abp_i + 1], abp_t.abp_angle_deg % 180.0)[0]
                )
                < 5
            )
            if not abp_parallel or not 0.25 < abp_along < 0.75:
                continue
            abp_off = np.abs(((abp_s[:, :2] + abp_s[:, 2:]) / 2 - abp_s[abp_i, :2]) @ abp_n)
            abp_pair = (abp_off > 0.03) & (abp_off < 0.35) & (abp_length > 0.8 * abp_length[abp_i])
            abp_out[abp_i] = not (
                abp_pair & (abp__angle_diff(abp_angles, float(abp_angles[abp_i])) < 2)
            ).any()
    return np.asarray(abp_out, np.bool_)


def abp_dimension_value(abp_text: str) -> float | None:
    abp_found = abp_DIMENSION.match(abp_text.strip())
    if not abp_found:
        return None
    abp_value = float(abp_found[1].replace(",", "."))
    return abp_value if 0.3 <= abp_value <= 60.0 else None


def abp_scale_from_dimensions(abp_vector: abpVectorPlan) -> int | None:
    abp_per_px = 0.0254 / abp_vector.abp_dpi
    abp_lines = abp_vector.abp_segments[~abp_vector.abp_filled]
    abp_lines = abp_lines[abp__lengths(abp_lines) > 0.005 / abp_per_px]
    if len(abp_lines) == 0:
        return None
    abp_length, abp_angles = abp__lengths(abp_lines), abp__angles(abp_lines)
    abp_votes: dict[int, int] = {}
    abp_total = 0
    for abp_t in abp_vector.abp_texts:
        abp_value = abp_dimension_value(abp_t.abp_text)
        if abp_value is None:
            continue
        abp_total += 1
        abp_center = np.array([abp_t.abp_x, abp_t.abp_y])
        abp_near = abp_point_segments_distance(abp_center, abp_lines) < 2.5 * abp_t.abp_size
        abp_near &= abp__angle_diff(abp_angles, abp_t.abp_angle_deg % 180.0) < 5
        abp_real: set[int] = set()
        for abp_i in np.flatnonzero(abp_near):
            abp_u, abp__n = abp__unit(abp_lines[abp_i])
            if (
                abs(float((abp_center - abp_lines[abp_i, :2]) @ abp_u) / abp_length[abp_i] - 0.5)
                > 0.2
            ):
                continue
            abp_meters = float(abp_length[abp_i]) * abp_per_px * np.array(abp_DIMENSION_SCALES)
            abp_fits = np.flatnonzero(np.abs(abp_meters - abp_value) < 0.02 * abp_value)
            abp_real.update(abp_DIMENSION_SCALES[abp_k] for abp_k in abp_fits.tolist())
        for abp_denominator in abp_real:
            abp_votes[abp_denominator] = abp_votes.get(abp_denominator, 0) + 1
    if not abp_votes:
        return None
    abp_best = max(abp_votes, key=lambda abp_d: abp_votes[abp_d])
    return (
        abp_best
        if abp_votes[abp_best] >= 3
        or (abp_votes[abp_best] >= 2 and abp_votes[abp_best] >= 0.5 * abp_total)
        else None
    )


def abp_hatching(abp_s: abpFloatArray) -> abpBoolArray:
    abp_n = len(abp_s)
    abp_out = np.zeros(abp_n, bool)
    if abp_n == 0:
        return abp_out
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    abp_steps = np.zeros(abp_n)
    abp_candidates = abp_length > 0.25
    for abp_i in np.flatnonzero(abp_candidates):
        abp_u, abp_normal = abp__unit(abp_s[abp_i])
        abp_idx = np.flatnonzero(
            abp_candidates & (abp__angle_diff(abp_angles, float(abp_angles[abp_i])) < 0.8)
        )
        abp_rel = (abp_s[abp_idx, :2] + abp_s[abp_idx, 2:]) / 2 - abp_s[abp_i, :2]
        abp_along = abp_rel @ abp_u
        abp_reach = (abp_along > -abp_length[abp_idx] / 2 - 0.1) & (
            abp_along < abp_length[abp_i] + abp_length[abp_idx] / 2 + 0.1
        )
        abp_off = (abp_rel @ abp_normal)[abp_reach]
        abp_gaps = np.abs(abp_off[np.abs(abp_off) > 0.02])
        if len(abp_gaps) < 5:
            continue
        abp_step = float(abp_gaps.min())
        if abp_step > 0.6:
            continue
        abp_hits = sum(
            bool((np.abs(abp_off - abp_k * abp_step) < 0.1 * abp_step).any())
            for abp_k in (-3, -2, -1, 1, 2, 3)
        )
        abp_steps[abp_i] = abp_step
        abp_out[abp_i] = abp_hits >= 5 or (abp_hits >= 4 and abp_length[abp_i] > 0.6)
    abp_core = np.flatnonzero(abp_out)
    for abp_i in np.flatnonzero(abp_candidates & ~abp_out):
        abp_u, abp_normal = abp__unit(abp_s[abp_i])
        abp_idx = abp_core[abp__angle_diff(abp_angles[abp_core], float(abp_angles[abp_i])) < 0.8]
        abp_rel = (abp_s[abp_idx, :2] + abp_s[abp_idx, 2:]) / 2 - abp_s[abp_i, :2]
        abp_along = abp_rel @ abp_u
        abp_reach = (abp_along > -abp_length[abp_idx] / 2 - 0.1) & (
            abp_along < abp_length[abp_i] + abp_length[abp_idx] / 2 + 0.1
        )
        abp_similar = abp_reach & (abp_length[abp_idx] > 0.6 * abp_length[abp_i])
        abp_off, abp_step_of = (abp_rel @ abp_normal)[abp_similar], abp_steps[abp_idx][abp_similar]
        abp_one = np.abs(np.abs(abp_off) - abp_step_of) < 0.12 * abp_step_of
        abp_two = np.abs(np.abs(abp_off) - 2 * abp_step_of) < 0.12 * abp_step_of
        abp_both_sides = bool((abp_off[np.abs(abp_off) < 1.6 * abp_step_of] > 0).any()) and bool(
            (abp_off[np.abs(abp_off) < 1.6 * abp_step_of] < 0).any()
        )
        abp_out[abp_i] = abp_both_sides or bool(abp_one.any() and abp_two.any())
    return np.asarray(abp_out, np.bool_)


def abp_sheet_frame(abp_s: abpFloatArray, abp_width: float, abp_height: float) -> abpBoolArray:
    abp_length = abp__lengths(abp_s)
    abp_xm, abp_ym = (abp_s[:, 0] + abp_s[:, 2]) / 2, (abp_s[:, 1] + abp_s[:, 3]) / 2
    abp_vertical = np.abs(abp_s[:, 0] - abp_s[:, 2]) < 1e-3 * abp_width
    abp_horizontal = np.abs(abp_s[:, 1] - abp_s[:, 3]) < 1e-3 * abp_height
    abp_side = (
        (np.minimum(abp_xm, abp_width - abp_xm) < 0.06 * abp_width)
        & abp_vertical
        & (abp_length > 0.5 * abp_height)
    )
    abp_top = (
        (np.minimum(abp_ym, abp_height - abp_ym) < 0.06 * abp_height)
        & abp_horizontal
        & (abp_length > 0.5 * abp_width)
    )
    return np.asarray(abp_side | abp_top, np.bool_)


def abp_regular_patterns(abp_s: abpFloatArray) -> tuple[abpBoolArray, list[abpFloatArray]]:
    abp_n = len(abp_s)
    abp_flagged = np.zeros(abp_n, bool)
    abp_stairs: list[abpFloatArray] = []
    if abp_n == 0:
        return abp_flagged, abp_stairs
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    abp_candidates = (abp_length > 0.45) & (abp_length < 6.0)
    abp_done = np.zeros(abp_n, bool)
    for abp_i in np.flatnonzero(abp_candidates):
        if abp_done[abp_i]:
            continue
        abp_u, abp_normal = abp__unit(abp_s[abp_i])
        abp_similar = (
            abp_candidates
            & (abp__angle_diff(abp_angles, float(abp_angles[abp_i])) < 2.5)
            & (np.abs(abp_length - abp_length[abp_i]) < 0.12 * abp_length[abp_i])
        )
        abp_idx = np.flatnonzero(abp_similar)
        abp_mid = (abp_s[abp_idx, :2] + abp_s[abp_idx, 2:]) / 2 - (
            abp_s[abp_i, :2] + abp_s[abp_i, 2:]
        ) / 2
        abp_idx = abp_idx[
            np.abs(abp_mid @ abp_u) < 0.18 * abp_length[abp_i] + 0.35 * np.abs(abp_mid @ abp_normal)
        ]
        if len(abp_idx) < 4:
            continue
        abp_mid = (abp_s[abp_idx, :2] + abp_s[abp_idx, 2:]) / 2 - (
            abp_s[abp_i, :2] + abp_s[abp_i, 2:]
        ) / 2
        abp_off = abp_mid @ abp_normal
        abp_order = np.argsort(abp_off, kind="stable")
        abp_idx, abp_off = abp_idx[abp_order], abp_off[abp_order]
        abp_keep = np.r_[True, np.diff(abp_off) > 0.02]
        abp_idx_all, abp_idx, abp_off = abp_idx, abp_idx[abp_keep], abp_off[abp_keep]
        abp_here = int(np.argmin(np.abs(abp_off)))
        abp_run = abp__regular_run(abp_off, abp_here)
        if abp_run is None:
            continue
        abp_lo, abp_hi, abp_step = abp_run
        if abp_hi - abp_lo < 3 or abp_off[abp_hi] - abp_off[abp_lo] < 0.7:
            continue
        abp_members = abp_idx[abp_lo : abp_hi + 1]
        abp_flagged[abp_members] = True
        abp_done[abp_members] = True
        for abp_j in abp_idx_all:
            if np.abs(abp_s[abp_members] - abp_s[abp_j]).sum(axis=1).min() < 0.1:
                abp_flagged[abp_j] = abp_done[abp_j] = True
        if (
            abp_STAIR_TREAD_M[0] <= abp_step <= abp_STAIR_TREAD_M[1]
            and 0.8 <= abp_length[abp_i] <= 3.6
        ):
            abp_stairs.append(abp__bounding(abp_s[abp_members], abp_u, abp_normal))
    return abp_flagged, abp_stairs


def abp__regular_run(abp_off: abpFloatArray, abp_here: int) -> tuple[int, int, float] | None:
    abp_gaps = np.diff(abp_off)
    if len(abp_gaps) == 0:
        return None
    abp_near = [
        abp_g
        for abp_k, abp_g in enumerate(abp_gaps)
        if abs(abp_k - abp_here) <= 2 and abp_g <= abp_STAIR_TREAD_M[1]
    ]
    if not abp_near:
        return None
    abp_step = float(np.median(abp_near))
    abp_lo = abp_hi = abp_here
    while abp_hi < len(abp_gaps) and abs(abp_gaps[abp_hi] - abp_step) < 0.25 * abp_step:
        abp_hi += 1
    while abp_lo > 0 and abs(abp_gaps[abp_lo - 1] - abp_step) < 0.25 * abp_step:
        abp_lo -= 1
    return abp_lo, abp_hi, abp_step


def abp__bounding(
    abp_s: abpFloatArray, abp_u: abpFloatArray, abp_n: abpFloatArray
) -> abpFloatArray:
    abp_points = np.vstack([abp_s[:, :2], abp_s[:, 2:]])
    abp_a, abp_b = abp_points @ abp_u, abp_points @ abp_n
    return np.array(
        [
            abp_u * abp_a.min() + abp_n * abp_b.min(),
            abp_u * abp_a.max() + abp_n * abp_b.min(),
            abp_u * abp_a.max() + abp_n * abp_b.max(),
            abp_u * abp_a.min() + abp_n * abp_b.max(),
        ]
    )


def abp_wall_axes(abp_s: abpFloatArray) -> abpFloatArray:
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    abp_mid = (abp_s[:, :2] + abp_s[:, 2:]) / 2
    abp_out: list[abpFloatArray] = []
    for abp_i in np.argsort(-abp_length, kind="stable"):
        if abp_length[abp_i] < abp_MIN_PIECE_M:
            break
        abp_u, abp_n = abp__unit(abp_s[abp_i])
        abp_off = (abp_mid - abp_s[abp_i, :2]) @ abp_n
        abp_close = (
            (abp__angle_diff(abp_angles, float(abp_angles[abp_i])) < 2.0)
            & (np.abs(abp_off) >= abp_WALL_MIN_M)
            & (np.abs(abp_off) <= abp_WALL_MAX_M)
            & (abp_length >= abp_MIN_PIECE_M)
        )
        for abp_side in (1.0, -1.0):
            abp_idx = np.flatnonzero(abp_close & (abp_off * abp_side > 0))
            abp_idx = abp_idx[np.argsort(np.abs(abp_off[abp_idx]), kind="stable")]
            abp_covered: list[tuple[float, float]] = []
            for abp_j in abp_idx:
                abp_t = np.sort(
                    [
                        (abp_s[abp_j, :2] - abp_s[abp_i, :2]) @ abp_u,
                        (abp_s[abp_j, 2:] - abp_s[abp_i, :2]) @ abp_u,
                    ]
                )
                abp_a, abp_b = (
                    max(float(abp_t[0]), 0.0),
                    min(float(abp_t[1]), float(abp_length[abp_i])),
                )
                if abp_b - abp_a < abp_MIN_PIECE_M:
                    continue
                for abp_x, abp_y in abp__subtract((abp_a, abp_b), abp_covered):
                    if abp_i < abp_j:
                        abp_c = abp_s[abp_i, :2] + abp_n * abp_off[abp_j] / 2
                        abp_out.append(
                            np.r_[abp_c + abp_u * abp_x, abp_c + abp_u * abp_y, abs(abp_off[abp_j])]
                        )
                abp_covered.append((abp_a, abp_b))
    return np.array(abp_out, np.float64).reshape(-1, 5)


def abp__subtract(
    abp_interval: tuple[float, float], abp_covered: Collection[tuple[float, float]]
) -> list[tuple[float, float]]:
    abp_free = [abp_interval]
    for abp_x, abp_y in abp_covered:
        abp_pieces = [
            abp_q
            for abp_a, abp_b in abp_free
            for abp_q in ((abp_a, min(abp_b, abp_x)), (max(abp_a, abp_y), abp_b))
        ]
        abp_free = [abp_q for abp_q in abp_pieces if abp_q[1] - abp_q[0] >= abp_MIN_PIECE_M]
    return abp_free


def abp_collapse_parallel(abp_axes: abpFloatArray) -> abpFloatArray:
    if len(abp_axes) == 0:
        return abp_axes[:, :4]
    abp_s = abp_axes[:, :4]
    abp_length, abp_angles = abp__lengths(abp_s), abp__angles(abp_s)
    abp_parent = np.arange(len(abp_s))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = int(abp_parent[abp_i])
        return abp_i

    for abp_i in range(len(abp_s)):
        abp_u, abp_n = abp__unit(abp_s[abp_i])
        abp_near = np.flatnonzero(
            (abp__angle_diff(abp_angles, float(abp_angles[abp_i])) < 3.0)
            & (np.abs(((abp_s[:, :2] + abp_s[:, 2:]) / 2 - abp_s[abp_i, :2]) @ abp_n) < 0.26)
        )
        for abp_j in abp_near:
            if abp_j <= abp_i:
                continue
            abp_t = np.sort(
                [
                    (abp_s[abp_j, :2] - abp_s[abp_i, :2]) @ abp_u,
                    (abp_s[abp_j, 2:] - abp_s[abp_i, :2]) @ abp_u,
                ]
            )
            if min(float(abp_t[1]), float(abp_length[abp_i])) - max(float(abp_t[0]), 0.0) > 0.1:
                abp_parent[abp_find(abp_i)] = abp_find(int(abp_j))
    abp_groups: dict[int, list[int]] = {}
    for abp_i in range(len(abp_s)):
        abp_groups.setdefault(abp_find(abp_i), []).append(abp_i)
    abp_out: list[abpFloatArray] = []
    for abp_members in abp_groups.values():
        abp_m = np.array(abp_members)
        abp_main = abp_m[np.argmax(abp_length[abp_m])]
        abp_u, abp_n = abp__unit(abp_s[abp_main])
        abp_mids = ((abp_s[abp_m, :2] + abp_s[abp_m, 2:]) / 2 - abp_s[abp_main, :2]) @ abp_n
        abp_half = abp_axes[abp_m, 4] / 2
        abp_center = float(((abp_mids - abp_half).min() + (abp_mids + abp_half).max()) / 2)
        abp_t = np.c_[
            (abp_s[abp_m, :2] - abp_s[abp_main, :2]) @ abp_u,
            (abp_s[abp_m, 2:] - abp_s[abp_main, :2]) @ abp_u,
        ]
        for abp_a, abp_b in abp__union(np.sort(abp_t, axis=1), 0.05):
            abp_base = abp_s[abp_main, :2] + abp_n * abp_center
            abp_out.append(np.r_[abp_base + abp_u * abp_a, abp_base + abp_u * abp_b])
    return np.array(abp_out, np.float64).reshape(-1, 4)


def abp__union(abp_intervals: abpFloatArray, abp_gap: float) -> list[tuple[float, float]]:
    abp_out: list[tuple[float, float]] = []
    for abp_a, abp_b in abp_intervals[np.argsort(abp_intervals[:, 0], kind="stable")]:
        if abp_out and abp_a <= abp_out[-1][1] + abp_gap:
            abp_out[-1] = (abp_out[-1][0], max(abp_out[-1][1], float(abp_b)))
        else:
            abp_out.append((float(abp_a), float(abp_b)))
    return abp_out


def abp_main_network(
    abp_s: abpFloatArray,
    abp_links: abpFloatArray,
    abp_anchors: abpFloatArray,
    abp_tol: float = abp_NETWORK_TOL_M,
) -> abpBoolArray:
    abp_everything = np.vstack([abp_s, abp_links]) if len(abp_links) else abp_s
    abp_n = len(abp_everything)
    abp_parent = list(range(abp_n))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = abp_parent[abp_i]
        return abp_i

    for abp_i in range(abp_n):
        for abp_end in (abp_everything[abp_i, :2], abp_everything[abp_i, 2:]):
            for abp_j in np.flatnonzero(
                abp_point_segments_distance(abp_end, abp_everything) <= abp_tol
            ):
                abp_parent[abp_find(abp_i)] = abp_find(int(abp_j))
    abp_length = abp__lengths(abp_s)
    abp_totals: dict[int, float] = {}
    abp_members: dict[int, list[int]] = {}
    for abp_i in range(len(abp_s)):
        abp_root = abp_find(abp_i)
        if abp_length[abp_i] >= abp_SEED_LENGTH_M:
            abp_totals[abp_root] = abp_totals.get(abp_root, 0.0) + float(abp_length[abp_i])
        abp_members.setdefault(abp_root, []).append(abp_i)
    if not abp_totals:
        return np.zeros(len(abp_s), np.bool_)
    abp_boxes: dict[int, tuple[abpFloatArray, abpFloatArray]] = {}
    abp_inside: dict[int, int] = {}
    for abp_root in abp_totals:
        abp_points = np.vstack([abp_s[abp_members[abp_root], :2], abp_s[abp_members[abp_root], 2:]])
        abp_lo, abp_hi = abp_points.min(axis=0) - 0.5, abp_points.max(axis=0) + 0.5
        abp_boxes[abp_root] = (abp_lo, abp_hi)
        abp_inside[abp_root] = (
            int(((abp_anchors >= abp_lo) & (abp_anchors <= abp_hi)).all(axis=1).sum())
            if len(abp_anchors)
            else 0
        )
    abp_best = max(
        abp_totals, key=lambda abp_root: abp_totals[abp_root] * (1 + 3 * abp_inside[abp_root])
    )
    abp_lo, abp_hi = abp_boxes[abp_best]
    abp_good = {abp_best}
    for abp_root, abp_total in abp_totals.items():
        abp_points = np.vstack([abp_s[abp_members[abp_root], :2], abp_s[abp_members[abp_root], 2:]])
        abp_overlaps = (
            float(((abp_points >= abp_lo) & (abp_points <= abp_hi)).all(axis=1).mean()) > 0.6
        )
        abp_wing = abp_inside[abp_root] > 0
        abp_share = abp_total >= abp_MIN_NETWORK_SHARE * abp_totals[abp_best]
        if (abp_share and (abp_overlaps or abp_wing)) or (abp_overlaps and abp_total >= 1.5):
            abp_good.add(abp_root)
    return np.array([abp_find(abp_i) in abp_good for abp_i in range(len(abp_s))], np.bool_)


def abp_close_small_gaps(abp_s: abpFloatArray) -> abpFloatArray:
    return (
        abp_merge_collinear(abp_s, abp_angle_deg=4.0, abp_offset=0.14, abp_gap=abp_COLUMN_GAP_M)
        if len(abp_s)
        else abp_s
    )


def abp_door_arcs(
    abp_vector: abpVectorPlan, abp_scale: float, abp_hidden: Collection[str]
) -> abpFloatArray:
    if len(abp_vector.abp_arcs) == 0:
        return np.zeros((0, 7))
    abp_hidden_ids = [
        abp_i for abp_i, abp_name in enumerate(abp_vector.abp_layers) if abp_name in abp_hidden
    ]
    abp_a = abp_vector.abp_arcs
    abp_r = abp_a[:, 2] * abp_scale
    abp_sweep = np.degrees(np.abs(abp_a[:, 4]))
    abp_ok = (
        (abp_r >= abp_ARC_RADIUS_M[0])
        & (abp_r <= abp_ARC_RADIUS_M[1])
        & (abp_sweep >= abp_ARC_SWEEP_DEG[0])
        & (abp_sweep <= abp_ARC_SWEEP_DEG[1])
        & ~np.isin(abp_vector.abp_arc_layer, abp_hidden_ids)
    )
    abp_a, abp_r = abp_a[abp_ok], abp_r[abp_ok]
    abp_c = abp_a[:, :2] * abp_scale
    abp_start = np.c_[np.cos(abp_a[:, 3]), np.sin(abp_a[:, 3])] * abp_r[:, None] + abp_c
    abp_end = (
        np.c_[np.cos(abp_a[:, 3] + abp_a[:, 4]), np.sin(abp_a[:, 3] + abp_a[:, 4])] * abp_r[:, None]
        + abp_c
    )
    return np.asarray(np.c_[abp_c, abp_r, abp_start, abp_end], np.float64)


def abp_doors_from_arcs(
    abp_arcs: abpFloatArray, abp_walls: abpFloatArray
) -> list[tuple[abpFloatArray, float]]:
    abp_out: list[tuple[abpFloatArray, float]] = []
    abp_single = list(range(len(abp_arcs)))
    for abp_i in range(len(abp_arcs)):
        for abp_j in range(abp_i + 1, len(abp_arcs)):
            if (
                abp_i in abp_single
                and abp_j in abp_single
                and abp__double_door(abp_arcs[abp_i], abp_arcs[abp_j])
            ):
                abp_out.append(
                    (
                        abp__onto_wall(np.r_[abp_arcs[abp_i][:2], abp_arcs[abp_j][:2]], abp_walls),
                        0.95,
                    )
                )
                abp_single.remove(abp_i)
                abp_single.remove(abp_j)
    if len(abp_walls) == 0:
        return abp_out
    abp_angles = abp__angles(abp_walls)
    for abp_i in abp_single:
        abp_hinge = abp_arcs[abp_i][:2]
        abp_dist = abp_point_segments_distance(abp_hinge, abp_walls)
        abp_best: tuple[float, abpFloatArray] | None = None
        for abp_end in (abp_arcs[abp_i][3:5], abp_arcs[abp_i][5:7]):
            abp_direction = (
                math.degrees(math.atan2(abp_end[1] - abp_hinge[1], abp_end[0] - abp_hinge[0]))
                % 180.0
            )
            for abp_wall in np.flatnonzero(abp_dist < 0.45):
                abp__u, abp_n = abp__unit(abp_walls[abp_wall])
                abp_diff = float(
                    abp__angle_diff(abp_angles[abp_wall : abp_wall + 1], abp_direction)[0]
                )
                abp_off = abs(float((abp_end - abp_walls[abp_wall, :2]) @ abp_n))
                abp_cost = abp_diff / 20 + abp_off / 0.5 + float(abp_dist[abp_wall]) / 0.45
                if (
                    abp_diff <= 20
                    and abp_off < 0.5
                    and (abp_best is None or abp_cost < abp_best[0])
                ):
                    abp_best = (abp_cost, abp_end)
        if abp_best is not None:
            abp_out.append((abp__onto_wall(np.r_[abp_hinge, abp_best[1]], abp_walls), 0.95))
    return abp_out


def abp__double_door(abp_a: abpFloatArray, abp_b: abpFloatArray) -> bool:
    abp_ra, abp_rb = float(abp_a[2]), float(abp_b[2])
    abp_hinges = float(np.hypot(*(abp_a[:2] - abp_b[:2])))
    if (
        abs(abp_ra - abp_rb) > 0.2 * max(abp_ra, abp_rb)
        or abs(abp_hinges - abp_ra - abp_rb) > 0.2 * abp_hinges
    ):
        return False
    return any(
        float(np.hypot(*(abp_p - abp_q))) < 0.35
        for abp_p in (abp_a[3:5], abp_a[5:7])
        for abp_q in (abp_b[3:5], abp_b[5:7])
    )


def abp__onto_wall(abp_segment: abpFloatArray, abp_walls: abpFloatArray) -> abpFloatArray:
    abp_angle = float(abp__angles(abp_segment[None, :])[0])
    abp_near = abp__angle_diff(abp__angles(abp_walls), abp_angle) < 15
    if not abp_near.any():
        return abp_segment
    abp_candidates = abp_walls[abp_near]
    abp_d = np.minimum(
        abp_point_segments_distance(abp_segment[:2], abp_candidates),
        abp_point_segments_distance(abp_segment[2:], abp_candidates),
    )
    abp_j = int(np.argmin(abp_d))
    if abp_d[abp_j] > 0.5:
        return abp_segment
    abp_u, abp__n = abp__unit(abp_candidates[abp_j])
    abp_base = abp_candidates[abp_j, :2]
    abp_ends = [
        abp_base + abp_u * float((abp_p - abp_base) @ abp_u)
        for abp_p in (abp_segment[:2], abp_segment[2:])
    ]
    return np.asarray(np.concatenate(abp_ends), np.float64)


def abp_gaps_between_walls(
    abp_walls: abpFloatArray, abp_taken: Collection[abpFloatArray]
) -> list[tuple[abpFloatArray, float]]:
    abp_out: list[tuple[abpFloatArray, float]] = []
    abp_angles, abp_length = abp__angles(abp_walls), abp__lengths(abp_walls)
    for abp_i in range(len(abp_walls)):
        abp_u, abp_n = abp__unit(abp_walls[abp_i])
        for abp_j in range(abp_i + 1, len(abp_walls)):
            if min(abp_length[abp_i], abp_length[abp_j]) < 0.5:
                continue
            if (
                float(abp__angle_diff(abp_angles[abp_j : abp_j + 1], float(abp_angles[abp_i]))[0])
                > 5
            ):
                continue
            abp_t = np.array(
                [
                    (abp_walls[abp_j, abp_k : abp_k + 2] - abp_walls[abp_i, :2]) @ abp_u
                    for abp_k in (0, 2)
                ]
            )
            abp_off = np.array(
                [
                    (abp_walls[abp_j, abp_k : abp_k + 2] - abp_walls[abp_i, :2]) @ abp_n
                    for abp_k in (0, 2)
                ]
            )
            for abp_mine, abp_near in (
                (float(abp_length[abp_i]), int(np.argmin(abp_t))),
                (0.0, int(np.argmax(abp_t))),
            ):
                abp_gap = abp_t[abp_near] - abp_mine if abp_mine > 0 else -abp_t[abp_near]
                if not abp_DOOR_MIN_M <= abp_gap <= abp_DOOR_MAX_M or abs(abp_off[abp_near]) > 0.18:
                    continue
                abp_a = abp_walls[abp_i, :2] + abp_u * abp_mine
                abp_b = abp_walls[abp_j, 2 * abp_near : 2 * abp_near + 2]
                abp_segment = np.r_[abp_a, abp_b]
                abp_middle = (abp_a + abp_b) / 2
                abp_others = np.delete(abp_walls, [abp_i, abp_j], axis=0)
                if (
                    len(abp_others)
                    and abp_point_segments_distance(abp_middle, abp_others).min() < 0.25
                ):
                    continue
                if any(
                    abp_point_segments_distance(abp_middle, abp_x[None, :])[0] < 0.6
                    for abp_x in abp_taken
                ):
                    continue
                abp_out.append((abp_segment, 0.5))
    return abp_out


def abp_detect_vector_plan(
    abp_vector: abpVectorPlan,
    abp_scale: float,
    *,
    abp_hidden_layers: Collection[str] = (),
    abp_anchors_px: abpFloatArray | None = None,
    abp_stroke_px: float = 0.0,
) -> abpVectorDetection:
    abp_offset = max(0.015, 1.3 * abp_stroke_px * abp_scale)
    abp_hidden = set(abp_hidden_layers) | {
        abp_n for abp_n in abp_vector.abp_layers if not abp_is_structure_layer(abp_n)
    }
    abp_hidden_ids = [
        abp_i for abp_i, abp_name in enumerate(abp_vector.abp_layers) if abp_name in abp_hidden
    ]
    abp_keep = ~abp_vector.abp_filled & ~np.isin(abp_vector.abp_segment_layer, abp_hidden_ids)
    abp_raw, abp_width, abp_layer = (
        abp_vector.abp_segments[abp_keep],
        abp_vector.abp_segment_width[abp_keep],
        abp_vector.abp_segment_layer[abp_keep],
    )
    abp_ok = ~abp_sheet_frame(abp_raw, abp_vector.abp_width, abp_vector.abp_height)
    abp_raw, abp_width, abp_layer = (
        abp_raw[abp_ok] * abp_scale,
        abp_width[abp_ok] * abp_scale,
        abp_layer[abp_ok],
    )
    abp_ok = (abp__lengths(abp_raw) > 0.03) & ~abp_text_frames(
        abp_raw, abp_vector.abp_texts, abp_scale
    )
    abp_raw, abp_width, abp_layer = abp_raw[abp_ok], abp_width[abp_ok], abp_layer[abp_ok]
    abp_dims = abp_dimension_lines(abp_raw, abp_vector.abp_texts, abp_scale)
    abp_raw, abp_width, abp_layer = abp_raw[~abp_dims], abp_width[~abp_dims], abp_layer[~abp_dims]
    abp_wall_ids = [
        abp_i for abp_i, abp_name in enumerate(abp_vector.abp_layers) if abp_is_wall_layer(abp_name)
    ]
    abp_of_walls = np.isin(abp_layer, abp_wall_ids)
    abp_thick = abp_width >= abp_WALL_MIN_M * 0.8
    abp_by_layer = float(abp__lengths(abp_raw[abp_of_walls]).sum()) >= abp_MIN_WALL_LAYER_M
    abp_lines = abp_merge_collinear(
        abp__with_big_arcs(abp_raw[~abp_thick], abp_vector, abp_scale, abp_hidden_ids),
        abp_offset=abp_offset,
        abp_gap=2 * abp_offset,
    )
    abp_pattern, abp__series = abp_regular_patterns(abp_lines)
    abp_pattern |= abp_hatching(abp_lines)
    abp_source = abp_lines[~abp_pattern]
    if abp_by_layer:
        abp_source = abp_merge_collinear(
            abp__with_big_arcs(
                abp_raw[~abp_thick & abp_of_walls], abp_vector, abp_scale, abp_hidden_ids
            )
        )
        abp_stairs_there, abp__boxes = abp_regular_patterns(abp_source)
        abp_source = abp_source[~(abp_stairs_there | abp_hatching(abp_source))]
    abp_pairs = abp_wall_axes(abp_source)
    abp_solid = abp_merge_collinear(
        abp_raw[abp_thick & (abp_of_walls | (not abp_by_layer))], abp_gap=0.05, abp_offset=0.05
    )
    abp_pairs = np.vstack([abp_pairs, np.c_[abp_solid, np.full(len(abp_solid), abp_WALL_MIN_M)]])
    abp_axes = abp_collapse_parallel(abp_pairs)
    abp_axes = abp_axes[abp__lengths(abp_axes) >= abp_MIN_PIECE_M]
    if float(abp__lengths(abp_axes).sum()) < abp_MIN_WALLS_M:
        abp_axes = np.vstack([abp_axes, abp__single_lines(abp_lines[~abp_pattern])])
    if len(abp_axes) == 0:
        return abpVectorDetection((), (), (), (), None)
    abp_arcs = abp_door_arcs(abp_vector, abp_scale, abp_hidden)
    abp_links = (
        np.vstack(
            [np.r_[abp_a[:2], abp_a[abp_k : abp_k + 2]] for abp_a in abp_arcs for abp_k in (3, 5)]
        )
        if len(abp_arcs)
        else abp_arcs[:, :4]
    )
    abp_anchors = np.zeros((0, 2)) if abp_anchors_px is None else abp_anchors_px * abp_scale
    if len(abp_anchors) == 0 and len(abp_arcs):
        abp_anchors = abp_arcs[:, :2]
    abp_axes = abp_axes[abp_main_network(abp_axes, abp_links, abp_anchors)]
    abp_axes = abp__drop_loose(abp__drop_shadows(abp__drop_loose(abp_axes)))
    abp_walls = abp__drop_shadows(abp_close_small_gaps(abp__align_steps(abp_axes)))
    abp_openings = [
        abp_d
        for abp_d in abp_doors_from_arcs(abp_arcs, abp_walls)
        if abp_DOOR_MIN_M * 0.8 <= float(abp__lengths(abp_d[0][None, :])[0]) <= abp_DOOR_MAX_M
        and all(
            float(abp_point_segments_distance(abp_e, abp_walls).min()) < 0.6
            for abp_e in (abp_d[0][:2], abp_d[0][2:])
        )
    ]
    abp_leaves = [abp_d[0] for abp_d in abp_openings]
    abp_walls = abp__cut_openings(abp_walls, abp_leaves)
    abp_walls = abp__close_windows(
        abp__drop_ticks(abp_walls, abp_leaves), abp_lines[~abp_pattern], abp_leaves
    )
    abp_walls = abp__snap(
        abp_close_small_gaps(abp__cut_openings(abp_walls, abp_leaves)), abp_leaves
    )
    abp_walls = abp__cut_openings(abp_walls, abp_leaves)
    abp_openings = [
        abp_d for abp_d in abp_openings if abp__ends_near(abp_d[0], abp_walls, abp_JAMB_REACH_M)
    ]
    abp_leaves = [abp_d[0] for abp_d in abp_openings]
    abp_openings += abp_gaps_between_walls(abp_walls, abp_leaves)
    abp_walls = abp__join_free_ends(abp_walls, [abp_d[0] for abp_d in abp_openings])
    return abp_as_detection(abp_walls, abp_openings, abp_scale)


def abp_as_detection(
    abp_walls: abpFloatArray, abp_openings: Sequence[tuple[abpFloatArray, float]], abp_scale: float
) -> abpVectorDetection:
    abp_segments = [abp_d[0] for abp_d in abp_openings]
    abp_outside = set(abp__propose_exits(abp_walls, abp_segments))
    abp_px = 1.0 / abp_scale
    abp_points = (
        np.vstack([abp_walls[:, :2], abp_walls[:, 2:]]) if len(abp_walls) else np.zeros((1, 2))
    )
    abp_lo, abp_hi = abp_points.min(axis=0) * abp_px, abp_points.max(axis=0) * abp_px
    return abpVectorDetection(
        abp_walls=tuple(abpWall(abp__segment(abp_w * abp_px)) for abp_w in abp_walls),
        abp_doors=tuple(
            abpDoor(abp__segment(abp_d * abp_px), abp_conf)
            for abp_i, (abp_d, abp_conf) in enumerate(abp_openings)
            if abp_i not in abp_outside
        ),
        abp_exits=tuple(
            abpExit(
                abp__segment(abp_d * abp_px), abp_name=f"Salida {abp_k + 1}", abp_confirmed=False
            )
            for abp_k, (abp_d, abp__conf) in enumerate(
                abp_openings[abp_i] for abp_i in sorted(abp_outside)
            )
        ),
        abp_stairs=(),
        abp_bounds=(float(abp_lo[0]), float(abp_lo[1]), float(abp_hi[0]), float(abp_hi[1])),
    )


def abp_plan_lines(
    abp_vector: abpVectorPlan, abp_scale: float, abp_walls: abpFloatArray
) -> abpFloatArray:
    abp_ids = [
        abp_i
        for abp_i, abp_name in enumerate(abp_vector.abp_layers)
        if not abp_is_structure_layer(abp_name)
    ]
    abp_raw = abp_vector.abp_segments[
        ~abp_vector.abp_filled & ~np.isin(abp_vector.abp_segment_layer, abp_ids)
    ]
    abp_raw = (
        abp_raw[~abp_sheet_frame(abp_raw, abp_vector.abp_width, abp_vector.abp_height)] * abp_scale
    )
    if len(abp_walls):
        abp_points = np.vstack([abp_walls[:, :2], abp_walls[:, 2:]])
        abp_lo, abp_hi = abp_points.min(axis=0) - 0.5, abp_points.max(axis=0) + 0.5
        abp_near = (np.maximum(abp_raw[:, :2], abp_raw[:, 2:]) >= abp_lo).all(axis=1)
        abp_raw = abp_raw[
            abp_near & (np.minimum(abp_raw[:, :2], abp_raw[:, 2:]) <= abp_hi).all(axis=1)
        ]
    abp_raw = abp_raw[abp__lengths(abp_raw) > 0.03]
    abp_raw = abp_raw[~abp_text_frames(abp_raw, abp_vector.abp_texts, abp_scale)]
    return abp_merge_collinear(abp_raw) if len(abp_raw) else abp_raw


def abp_furniture_segments(abp_vector: abpVectorPlan, abp_plan: abpFloorPlan) -> abpFloatArray:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None or not abp_plan.abp_walls:
        return np.zeros((0, 4))
    abp_ids = [
        abp_i
        for abp_i, abp_name in enumerate(abp_vector.abp_layers)
        if not abp_is_structure_layer(abp_name) and not abp_is_furniture_layer(abp_name)
    ]
    abp_raw = (
        abp_vector.abp_segments[
            ~abp_vector.abp_filled & ~np.isin(abp_vector.abp_segment_layer, abp_ids)
        ]
        * abp_scale
    )
    abp_walls = np.array(
        [
            (
                abp_w.abp_segment.abp_start.abp_x,
                abp_w.abp_segment.abp_start.abp_y,
                abp_w.abp_segment.abp_end.abp_x,
                abp_w.abp_segment.abp_end.abp_y,
            )
            for abp_w in abp_plan.abp_walls
        ]
    )
    abp_walls = abp_walls * abp_scale
    abp_lo = np.minimum(abp_walls[:, :2], abp_walls[:, 2:]).min(axis=0)
    abp_hi = np.maximum(abp_walls[:, :2], abp_walls[:, 2:]).max(axis=0)
    abp_inside = ((abp_raw[:, :2] >= abp_lo) & (abp_raw[:, 2:] >= abp_lo)).all(axis=1)
    abp_inside &= ((abp_raw[:, :2] <= abp_hi) & (abp_raw[:, 2:] <= abp_hi)).all(axis=1)
    abp_raw = abp_raw[abp_inside & (abp__lengths(abp_raw) > 0.05)]
    abp_raw = abp_raw[~abp_text_frames(abp_raw, abp_vector.abp_texts, abp_scale)]
    if len(abp_raw) == 0:
        return abp_raw
    abp_lines = abp_merge_collinear(abp_raw)
    abp_pattern, abp__stairs = abp_regular_patterns(abp_lines)
    abp_lines = abp_lines[
        ~(abp_pattern | abp_hatching(abp_lines)) & (abp__lengths(abp_lines) < 4.0)
    ]
    abp_mid = (abp_lines[:, :2] + abp_lines[:, 2:]) / 2
    abp_away = np.full(len(abp_lines), np.inf)
    for abp_w in abp_walls:
        abp_away = np.minimum(abp_away, abp__points_to_segment(abp_mid, abp_w))
    for abp_x in [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]:
        abp_center = np.array([abp_x.abp_midpoint.abp_x, abp_x.abp_midpoint.abp_y]) * abp_scale
        abp_near = np.hypot(abp_mid[:, 0] - abp_center[0], abp_mid[:, 1] - abp_center[1])
        abp_away[abp_near < abp_leaf_reach(abp_x.abp_length * abp_scale) + 0.1] = 0.0
    abp_facing = np.zeros(len(abp_lines), bool)
    abp_angle = abp__angles(abp_lines)
    for abp_w in abp_walls:
        abp_close = abp__points_to_segment(abp_mid, abp_w) < 0.3
        abp_facing |= abp_close & (
            abp__angle_diff(abp_angle, float(abp__angles(abp_w[None, :])[0])) < 6
        )
    abp_lines = abp_lines[(abp_away > 0.13) & ~(abp_facing & (abp__lengths(abp_lines) > 0.5))]
    abp_pieces = abp_lines[abp__solid_pieces(abp_lines)]
    return np.asarray(
        np.vstack([abp_pieces, abp__furniture_arcs(abp_vector, abp_scale, abp_ids, abp_walls)])
        / abp_scale
    )


def abp_leaf_reach(abp_width_m: float) -> float:
    return abp_width_m if abp_width_m <= 1.05 else min(abp_width_m / 2 + 0.2, 1.4)


def abp__furniture_arcs(
    abp_vector: abpVectorPlan,
    abp_scale: float,
    abp_hidden: Collection[int],
    abp_walls: abpFloatArray,
) -> abpFloatArray:
    abp_out: list[abpFloatArray] = []
    abp_lo = np.minimum(abp_walls[:, :2], abp_walls[:, 2:]).min(axis=0)
    abp_hi = np.maximum(abp_walls[:, :2], abp_walls[:, 2:]).max(axis=0)
    for abp_arc, abp_layer in zip(abp_vector.abp_arcs, abp_vector.abp_arc_layer, strict=True):
        abp_r = abp_arc[2] * abp_scale
        abp_center = abp_arc[:2] * abp_scale
        if (
            abp_layer in abp_hidden
            or not 0.36 < abp_r < 2.0
            or not ((abp_center > abp_lo) & (abp_center < abp_hi)).all()
        ):
            continue
        if abs(math.degrees(abp_arc[4])) < 150:
            continue
        abp_t = abp_arc[3] + abp_arc[4] * np.linspace(0, 1, 25)
        abp_p = abp_center + abp_r * np.c_[np.cos(abp_t), np.sin(abp_t)]
        abp_out.append(np.c_[abp_p[:-1], abp_p[1:]])
    return np.vstack(abp_out) if abp_out else np.zeros((0, 4))


def abp__solid_pieces(abp_s: abpFloatArray) -> abpBoolArray:
    abp_parent = list(range(len(abp_s)))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = abp_parent[abp_i]
        return abp_i

    for abp_i in range(len(abp_s)):
        for abp_end in (abp_s[abp_i, :2], abp_s[abp_i, 2:]):
            for abp_j in np.flatnonzero(abp_point_segments_distance(abp_end, abp_s) < 0.04):
                abp_parent[abp_find(abp_i)] = abp_find(int(abp_j))
    abp_groups: dict[int, list[int]] = {}
    for abp_i in range(len(abp_s)):
        abp_groups.setdefault(abp_find(abp_i), []).append(abp_i)
    abp_out = np.zeros(len(abp_s), bool)
    for abp_members in abp_groups.values():
        abp_points = np.vstack([abp_s[abp_members, :2], abp_s[abp_members, 2:]])
        abp_out[abp_members] = (
            len(abp_members) >= 4 and float(np.ptp(abp_points, axis=0).min()) >= 0.25
        )
    return np.asarray(abp_out, np.bool_)


def abp__points_to_segment(abp_points: abpFloatArray, abp_s: abpFloatArray) -> abpFloatArray:
    abp_a, abp_d = abp_s[:2], abp_s[2:] - abp_s[:2]
    abp_t = np.clip(((abp_points - abp_a) @ abp_d) / max(float(abp_d @ abp_d), 1e-12), 0.0, 1.0)
    abp_q = abp_a + abp_t[:, None] * abp_d
    return np.asarray(
        np.hypot(abp_points[:, 0] - abp_q[:, 0], abp_points[:, 1] - abp_q[:, 1]), np.float64
    )


def abp__single_lines(abp_lines: abpFloatArray) -> abpFloatArray:
    return abp_lines[abp__lengths(abp_lines) >= abp_SINGLE_LINE_MIN_M]


def abp__segment(abp_s: abpFloatArray) -> abpSegment:
    return abpSegment(
        abpPoint(float(abp_s[0]), float(abp_s[1])), abpPoint(float(abp_s[2]), float(abp_s[3]))
    )


def abp__with_big_arcs(
    abp_raw: abpFloatArray,
    abp_vector: abpVectorPlan,
    abp_scale: float,
    abp_hidden_ids: Collection[int],
) -> abpFloatArray:
    abp_chords: list[abpFloatArray] = []
    for abp_arc, abp_layer in zip(abp_vector.abp_arcs, abp_vector.abp_arc_layer, strict=True):
        abp_radius = abp_arc[2] * abp_scale
        if abp_radius < 2.5 or abp_layer in abp_hidden_ids:
            continue
        abp_n = max(1, round(abs(abp_arc[4]) * abp_radius / 0.5))
        abp_a = abp_arc[3] + abp_arc[4] * np.linspace(0, 1, abp_n + 1)
        abp_p = (abp_arc[:2] + abp_arc[2] * np.c_[np.cos(abp_a), np.sin(abp_a)]) * abp_scale
        abp_chords.append(np.c_[abp_p[:-1], abp_p[1:]])
    return np.vstack([abp_raw, *abp_chords]) if abp_chords else abp_raw


def abp__drop_loose(abp_axes: abpFloatArray) -> abpFloatArray:
    abp_length = abp__lengths(abp_axes)
    abp_long_ones = abp_axes[abp_length >= abp_SEED_LENGTH_M]
    if len(abp_long_ones) == 0:
        return abp_axes
    abp_angles = abp__angles(abp_long_ones)
    abp_keep = abp_length >= abp_SEED_LENGTH_M
    for abp_i in np.flatnonzero(~abp_keep):
        abp_a, abp_b = abp_axes[abp_i, :2], abp_axes[abp_i, 2:]
        abp_da, abp_db = (
            abp_point_segments_distance(abp_a, abp_long_ones),
            abp_point_segments_distance(abp_b, abp_long_ones),
        )
        abp_same = (
            abp__angle_diff(abp_angles, float(abp__angles(abp_axes[abp_i : abp_i + 1])[0])) < 6
        )
        abp_continues = bool((abp_same & (np.minimum(abp_da, abp_db) < 0.5)).any())
        abp_joins = bool(abp_da.min() < 0.25 and abp_db.min() < 0.25)
        abp_keep[abp_i] = abp_continues or abp_joins
    for abp_i in np.flatnonzero(abp_keep & (abp_length < 1.5)):
        abp_others = np.delete(abp_axes, abp_i, axis=0)
        if len(abp_others):
            abp_ends = (abp_axes[abp_i, :2], abp_axes[abp_i, 2:])
            abp_keep[abp_i] = (
                min(
                    float(abp_point_segments_distance(abp_e, abp_others).min())
                    for abp_e in abp_ends
                )
                < 0.35
            )
    return abp_axes[abp_keep]


def abp__drop_shadows(abp_axes: abpFloatArray) -> abpFloatArray:
    abp_length, abp_angles = abp__lengths(abp_axes), abp__angles(abp_axes)
    abp_keep = np.ones(len(abp_axes), bool)
    for abp_i in range(len(abp_axes)):
        for abp_j in np.flatnonzero((abp_length > 1.6 * abp_length[abp_i]) & abp_keep):
            if (
                float(abp__angle_diff(abp_angles[abp_j : abp_j + 1], float(abp_angles[abp_i]))[0])
                > 5
            ):
                continue
            abp_u, abp_n = abp__unit(abp_axes[abp_j])
            abp_t = np.sort(
                [
                    float((abp_e - abp_axes[abp_j, :2]) @ abp_u)
                    for abp_e in (abp_axes[abp_i, :2], abp_axes[abp_i, 2:])
                ]
            )
            abp_off = [
                abs(float((abp_e - abp_axes[abp_j, :2]) @ abp_n))
                for abp_e in (abp_axes[abp_i, :2], abp_axes[abp_i, 2:])
            ]
            abp_overlap = min(float(abp_t[1]), float(abp_length[abp_j])) - max(float(abp_t[0]), 0.0)
            if abp_overlap > 0.6 * abp_length[abp_i] and max(abp_off) < 0.6:
                abp_keep[abp_i] = False
                break
    return abp_axes[abp_keep]


def abp__drop_ticks(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    abp_length = abp__lengths(abp_walls)
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]
    abp_keep = np.ones(len(abp_walls), bool)
    for abp_i in np.argsort(abp_length, kind="stable"):
        if abp_length[abp_i] > 1.2:
            break
        abp_rest = abp_keep.copy()
        abp_rest[abp_i] = False
        abp_others = abp_walls[abp_rest]
        abp_longer = abp_walls[abp_rest & (abp_length > abp_length[abp_i])]
        if len(abp_longer) == 0:
            continue
        abp_ends = (abp_walls[abp_i, :2], abp_walls[abp_i, 2:])
        if any(
            float(np.hypot(*(abp_e - abp_j))) < 0.25 for abp_e in abp_ends for abp_j in abp_jambs
        ):
            continue
        abp__u, abp_n = abp__unit(abp_walls[abp_i])
        abp_signed = np.c_[
            (abp_longer[:, :2] - abp_walls[abp_i, :2]) @ abp_n,
            (abp_longer[:, 2:] - abp_walls[abp_i, :2]) @ abp_n,
        ]
        abp_middle = abp_point_segments_distance((abp_ends[0] + abp_ends[1]) / 2, abp_longer)
        abp_crossing = bool(
            (
                (abp_signed[:, 0] * abp_signed[:, 1] < 0) & (abp_middle < 0.3 * abp_length[abp_i])
            ).any()
        )
        abp_free = sum(
            float(abp_point_segments_distance(abp_e, abp_others).min()) > 0.12 for abp_e in abp_ends
        )
        if (abp_crossing and abp_free) or (abp_length[abp_i] < 0.8 and abp_free):
            abp_keep[abp_i] = False
    return abp_walls[abp_keep]


def abp__align_steps(abp_walls: abpFloatArray) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    abp_length, abp_angles = abp__lengths(abp_walls), abp__angles(abp_walls)
    for abp_i in np.argsort(abp_length, kind="stable"):
        if abp_length[abp_i] > 3.0:
            break
        abp_best: tuple[float, int] | None = None
        for abp_j in np.flatnonzero(abp_length > abp_length[abp_i]):
            if (
                float(abp__angle_diff(abp_angles[abp_j : abp_j + 1], float(abp_angles[abp_i]))[0])
                > 6
            ):
                continue
            abp_gap = min(
                float(np.hypot(*(abp_p - abp_q)))
                for abp_p in (abp_walls[abp_i, :2], abp_walls[abp_i, 2:])
                for abp_q in (abp_walls[abp_j, :2], abp_walls[abp_j, 2:])
            )
            if abp_gap < 0.6 and (abp_best is None or abp_gap < abp_best[0]):
                abp_best = (abp_gap, int(abp_j))
        if abp_best is None:
            continue
        abp__u, abp_n = abp__unit(abp_walls[abp_best[1]])
        abp_off = float(
            ((abp_walls[abp_i, :2] + abp_walls[abp_i, 2:]) / 2 - abp_walls[abp_best[1], :2]) @ abp_n
        )
        if 0.02 < abs(abp_off) < 0.32:
            abp_walls[abp_i] -= np.tile(abp_n * abp_off, 2)
    return abp_walls


def abp__ends_near(abp_opening: abpFloatArray, abp_walls: abpFloatArray, abp_reach: float) -> bool:
    if len(abp_walls) == 0:
        return False
    abp_ends = (abp_opening[:2], abp_opening[2:])
    return all(
        float(abp_point_segments_distance(abp_e, abp_walls).min()) <= abp_reach
        for abp_e in abp_ends
    )


def abp__close_windows(
    abp_walls: abpFloatArray, abp_lines: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]
    abp_line_angles = abp__angles(abp_lines)
    for abp_i in range(len(abp_walls)):
        for abp_k in (2, 0):
            abp_e = abp_walls[abp_i, abp_k : abp_k + 2].copy()
            abp_others = np.delete(abp_walls, abp_i, axis=0)
            if (
                len(abp_others) == 0
                or float(abp_point_segments_distance(abp_e, abp_others).min()) < 0.2
            ):
                continue
            if any(float(np.hypot(*(abp_e - abp_j))) < 0.35 for abp_j in abp_jambs):
                continue
            abp_u, abp_n = abp__unit(abp_walls[abp_i])
            abp_u = abp_u if abp_k == 2 else -abp_u
            abp_reach = abp__first_hit(abp_e, abp_u, abp_others)
            if abp_reach is None or not 0.2 <= abp_reach <= abp_WINDOW_MAX_M:
                continue
            abp_same = (
                abp__angle_diff(
                    abp_line_angles, float(abp__angles(abp_walls[abp_i : abp_i + 1])[0])
                )
                < 8
            )
            abp_near = abp_lines[
                abp_same
                & (np.abs(((abp_lines[:, :2] + abp_lines[:, 2:]) / 2 - abp_e) @ abp_n) < 0.5)
            ]
            abp_t = np.sort(
                np.c_[(abp_near[:, :2] - abp_e) @ abp_u, (abp_near[:, 2:] - abp_e) @ abp_u], axis=1
            )
            abp_t = np.clip(abp_t, 0.0, abp_reach)
            abp_covered = (
                sum(abp_b - abp_a for abp_a, abp_b in abp__union(abp_t, 0.02))
                if len(abp_t)
                else 0.0
            )
            if abp_covered >= 0.8 * abp_reach:
                abp_walls[abp_i, abp_k : abp_k + 2] = abp_e + abp_u * abp_reach
    return abp_walls


def abp__first_hit(
    abp_e: abpFloatArray, abp_u: abpFloatArray, abp_walls: abpFloatArray
) -> float | None:
    abp_n = np.array([-abp_u[1], abp_u[0]])
    abp_best: float | None = None
    for abp_w in abp_walls:
        abp_a, abp_b = (abp_w[:2] - abp_e) @ abp_n, (abp_w[2:] - abp_e) @ abp_n
        abp_ta, abp_tb = (abp_w[:2] - abp_e) @ abp_u, (abp_w[2:] - abp_e) @ abp_u
        if abp_a * abp_b < 0:
            abp_t = float(abp_ta + (abp_tb - abp_ta) * abp_a / (abp_a - abp_b))
        elif min(abs(abp_a), abs(abp_b)) < 0.6:
            abp_t = float(abp_ta if abs(abp_a) < abs(abp_b) else abp_tb)
        else:
            continue
        if abp_t > 0.1 and (abp_best is None or abp_t < abp_best):
            abp_best = abp_t
    return abp_best


def abp__snap(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray], abp_tol: float = 0.35
) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]
    for abp_i in range(len(abp_walls)):
        for abp_k in (0, 2):
            abp_e = abp_walls[abp_i, abp_k : abp_k + 2]
            if any(float(np.hypot(*(abp_e - abp_j))) < 0.05 for abp_j in abp_jambs):
                continue
            abp_d = abp_point_segments_distance(abp_e, abp_walls)
            abp_d[abp_i] = np.inf
            for abp_j in np.argsort(abp_d, kind="stable"):
                if abp_d[abp_j] > abp_tol:
                    break
                abp_point = abp__corner(abp_walls[abp_i], abp_walls[abp_j], abp_e, abp_tol * 1.4)
                if abp_point is None:
                    continue
                abp_walls[abp_i, abp_k : abp_k + 2] = abp_point
                for abp_m in (0, 2):
                    if (
                        float(np.hypot(*(abp_walls[abp_j, abp_m : abp_m + 2] - abp_point)))
                        < abp_tol
                    ):
                        abp_walls[abp_j, abp_m : abp_m + 2] = abp_point
                break
    return abp_walls[abp__lengths(abp_walls) > 0.1]


def abp__join_free_ends(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    abp_walls = abp__touch_next_wall(
        abp__corners_of_free_ends(abp_walls, abp_openings), abp_openings
    )
    abp_extra: list[abpFloatArray] = []
    for abp_o in abp_openings:
        for abp_e in (abp_o[:2], abp_o[2:]):
            if len(abp_walls) == 0:
                continue
            abp_j = int(np.argmin(abp_point_segments_distance(abp_e, abp_walls)))
            abp_w = abp_walls[abp_j]
            abp_t = float(
                np.clip(
                    (abp_e - abp_w[:2])
                    @ (abp_w[2:] - abp_w[:2])
                    / ((abp_w[2:] - abp_w[:2]) ** 2).sum(),
                    0,
                    1,
                )
            )
            abp_q = abp_w[:2] + abp_t * (abp_w[2:] - abp_w[:2])
            if 0.05 < float(np.hypot(*(abp_e - abp_q))) < abp_JAMB_REACH_M:
                abp_extra.append(np.r_[abp_e, abp_q])
    return (
        np.vstack([abp_walls, *[abp_x[None, :] for abp_x in abp_extra]]) if abp_extra else abp_walls
    )


def abp__touch_next_wall(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]
    for abp_i in range(len(abp_walls)):
        for abp_k in (0, 2):
            abp_e = abp_walls[abp_i, abp_k : abp_k + 2].copy()
            abp_others = np.delete(abp_walls, abp_i, axis=0)
            if (
                len(abp_others) == 0
                or float(abp_point_segments_distance(abp_e, abp_others).min()) < 0.05
            ):
                continue
            if any(float(np.hypot(*(abp_e - abp_j))) < 0.3 for abp_j in abp_jambs):
                continue
            abp_u, abp__n = abp__unit(abp_walls[abp_i])
            abp_reach = abp_ray_hit(abp_e, abp_u if abp_k == 2 else -abp_u, abp_others)
            if abp_reach is not None and abp_reach < abp_DOOR_MIN_M:
                abp_walls[abp_i, abp_k : abp_k + 2] = (
                    abp_e + (abp_u if abp_k == 2 else -abp_u) * abp_reach
                )
    return abp_walls


def abp_ray_hit(
    abp_e: abpFloatArray, abp_u: abpFloatArray, abp_walls: abpFloatArray
) -> float | None:
    abp_n = np.array([-abp_u[1], abp_u[0]])
    abp_a, abp_b = (abp_walls[:, :2] - abp_e) @ abp_n, (abp_walls[:, 2:] - abp_e) @ abp_n
    abp_ta, abp_tb = (abp_walls[:, :2] - abp_e) @ abp_u, (abp_walls[:, 2:] - abp_e) @ abp_u
    abp_slack = 0.2
    abp_cross = (
        (np.minimum(abp_a, abp_b) <= abp_slack)
        & (np.maximum(abp_a, abp_b) >= -abp_slack)
        & (np.abs(abp_a - abp_b) > 0.2)
    )
    if not abp_cross.any():
        return None
    abp_t = np.clip(abp_a / np.where(np.abs(abp_a - abp_b) < 1e-9, 1e-9, abp_a - abp_b), 0, 1)
    abp_along = abp_ta + (abp_tb - abp_ta) * abp_t
    abp_along = abp_along[abp_cross & (abp_along > 0.02)]
    return float(abp_along.min()) if len(abp_along) else None


def abp__corners_of_free_ends(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]

    def abp_is_free(abp_i: int, abp_k: int) -> bool:
        abp_e = abp_walls[abp_i, abp_k : abp_k + 2]
        abp_others = np.delete(abp_walls, abp_i, axis=0)
        return not any(float(np.hypot(*(abp_e - abp_j))) < 0.1 for abp_j in abp_jambs) and (
            len(abp_others) == 0
            or float(abp_point_segments_distance(abp_e, abp_others).min()) > 0.05
        )

    abp_free = [
        (abp_i, abp_k)
        for abp_i in range(len(abp_walls))
        for abp_k in (0, 2)
        if abp_is_free(abp_i, abp_k)
    ]
    abp_pairs = sorted(
        (
            float(
                np.hypot(
                    *(abp_walls[abp_i, abp_k : abp_k + 2] - abp_walls[abp_j, abp_m : abp_m + 2])
                )
            ),
            abp_i,
            abp_k,
            abp_j,
            abp_m,
        )
        for abp_index, (abp_i, abp_k) in enumerate(abp_free)
        for abp_j, abp_m in abp_free[abp_index + 1 :]
        if abp_i != abp_j
    )
    abp_used: set[tuple[int, int]] = set()
    for abp_distance, abp_i, abp_k, abp_j, abp_m in abp_pairs:
        if abp_distance > abp_CORNER_REACH_M:
            break
        if (abp_i, abp_k) in abp_used or (abp_j, abp_m) in abp_used:
            continue
        abp_e = abp_walls[abp_i, abp_k : abp_k + 2].copy()
        abp_point = abp__corner(abp_walls[abp_i], abp_walls[abp_j], abp_e, abp_CORNER_REACH_M)
        if (
            abp_point is None
            or float(np.hypot(*(abp_point - abp_walls[abp_j, abp_m : abp_m + 2])))
            > abp_CORNER_REACH_M
        ):
            continue
        abp_walls[abp_i, abp_k : abp_k + 2] = abp_point
        abp_walls[abp_j, abp_m : abp_m + 2] = abp_point
        abp_used |= {(abp_i, abp_k), (abp_j, abp_m)}
    return abp_walls


def abp__corner(
    abp_a: abpFloatArray, abp_b: abpFloatArray, abp_e: abpFloatArray, abp_tol: float
) -> abpFloatArray | None:
    abp_ua, abp__na = abp__unit(abp_a)
    abp__ub, abp_nb = abp__unit(abp_b)
    abp_across = float(abp_ua @ abp_nb)
    if abs(abp_across) < math.sin(math.radians(12)):
        abp_ends = (abp_b[:2], abp_b[2:])
        abp_near = min(abp_ends, key=lambda abp_p: float(np.hypot(*(abp_p - abp_e))))
        abp_far = abp_b[2:] if abp_near is abp_ends[0] else abp_b[:2]
        abp_back = abp_a[2:] if float(np.hypot(*(abp_a[:2] - abp_e))) < 1e-9 else abp_a[:2]
        if float((abp_far - abp_near) @ (abp_back - abp_e)) > 0:
            return None
        return (abp_near + abp_e) / 2 if float(np.hypot(*(abp_near - abp_e))) < abp_tol else None
    abp_point = abp_a[:2] + abp_ua * float((abp_b[:2] - abp_a[:2]) @ abp_nb) / abp_across
    return np.asarray(abp_point) if float(np.hypot(*(abp_point - abp_e))) < abp_tol else None


def abp__propose_exits(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> list[int]:
    if len(abp_walls) == 0 or not abp_openings:
        return []
    abp_cell = 0.1
    abp_everything = np.vstack([abp_walls, np.array(list(abp_openings))])
    abp_lo = np.minimum(abp_everything[:, :2], abp_everything[:, 2:]).min(axis=0) - 2.0
    abp_hi = np.maximum(abp_everything[:, :2], abp_everything[:, 2:]).max(axis=0) + 2.0
    abp_w, abp_h = (int(abp_v) for abp_v in np.ceil((abp_hi - abp_lo) / abp_cell))
    abp_mask = np.zeros((abp_h, abp_w), np.uint8)
    for abp_x in abp_everything:
        abp_a, abp_b = (abp_x[:2] - abp_lo) / abp_cell, (abp_x[2:] - abp_lo) / abp_cell
        cv2.line(abp_mask, (int(abp_a[0]), int(abp_a[1])), (int(abp_b[0]), int(abp_b[1])), 1, 2)
    abp_flood = abp_mask.copy()
    cv2.floodFill(abp_flood, None, (0, 0), (2,))
    abp_out: list[int] = []
    for abp_index, abp_o in enumerate(abp_openings):
        abp__u, abp_n = abp__unit(abp_o)
        abp_middle = (abp_o[:2] + abp_o[2:]) / 2
        abp_sides = []
        for abp_sign in (1.0, -1.0):
            abp_x, abp_y = (abp_middle + abp_n * abp_sign * 0.6 - abp_lo) / abp_cell
            abp_sides.append(int(abp_flood[int(abp_y), int(abp_x)]) == 2)
        if abp_sides[0] != abp_sides[1]:
            abp_out.append(abp_index)
    return abp_out


def abp__cut_openings(
    abp_walls: abpFloatArray, abp_openings: Collection[abpFloatArray]
) -> abpFloatArray:
    for abp_o in abp_openings:
        abp_pieces: list[abpFloatArray] = []
        for abp_w in abp_walls:
            abp_u, abp_n = abp__unit(abp_w)
            abp_size = float((abp_w[2:] - abp_w[:2]) @ abp_u)
            abp_off = np.abs([(abp_p - abp_w[:2]) @ abp_n for abp_p in (abp_o[:2], abp_o[2:])])
            abp_t = np.sort(
                [float((abp_p - abp_w[:2]) @ abp_u) for abp_p in (abp_o[:2], abp_o[2:])]
            )
            abp_same = (
                float(
                    abp__angle_diff(
                        abp__angles(abp_o[None, :]), float(abp__angles(abp_w[None, :])[0])
                    )[0]
                )
                < 10
            )
            if (
                not abp_same
                or abp_off.max() > 0.3
                or abp_t[1] <= 0.05
                or abp_t[0] >= abp_size - 0.05
            ):
                abp_pieces.append(abp_w)
                continue
            for abp_a, abp_b in ((0.0, float(abp_t[0])), (float(abp_t[1]), abp_size)):
                if abp_b - abp_a >= 0.1:
                    abp_pieces.append(np.r_[abp_w[:2] + abp_u * abp_a, abp_w[:2] + abp_u * abp_b])
        abp_walls = np.array(abp_pieces, np.float64).reshape(-1, 4)
    return abp_walls
