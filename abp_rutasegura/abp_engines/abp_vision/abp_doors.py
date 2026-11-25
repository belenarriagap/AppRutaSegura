from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpMask


def abp_arc_score(
    abp_residual: abpMask, abp_gap: abpSegment, abp_samples: int = 24, abp_radius_px: int = 2
) -> float:
    if abp_gap.abp_length < 2:
        return 0.0
    abp_near = (
        cv2.dilate(abp_residual.astype(np.uint8), np.ones((2 * abp_radius_px + 1,) * 2, np.uint8))
        > 0
    )
    abp_h, abp_w = abp_near.shape
    abp_ux = (abp_gap.abp_end.abp_x - abp_gap.abp_start.abp_x) / abp_gap.abp_length
    abp_uy = (abp_gap.abp_end.abp_y - abp_gap.abp_start.abp_y) / abp_gap.abp_length
    abp_phis = np.linspace(0.15, math.pi / 2 - 0.15, abp_samples)
    abp_best = 0.0
    for abp_hinge, abp_sign_u in ((abp_gap.abp_start, 1.0), (abp_gap.abp_end, -1.0)):
        for abp_side in (1.0, -1.0):
            abp_nx, abp_ny = -abp_uy * abp_side, abp_ux * abp_side
            abp_xs = abp_hinge.abp_x + abp_gap.abp_length * (
                np.cos(abp_phis) * abp_ux * abp_sign_u + np.sin(abp_phis) * abp_nx
            )
            abp_ys = abp_hinge.abp_y + abp_gap.abp_length * (
                np.cos(abp_phis) * abp_uy * abp_sign_u + np.sin(abp_phis) * abp_ny
            )
            abp_xi, abp_yi = abp_xs.round().astype(int), abp_ys.round().astype(int)
            abp_ok = (abp_xi >= 0) & (abp_xi < abp_w) & (abp_yi >= 0) & (abp_yi < abp_h)
            if abp_ok.any():
                abp_best = max(
                    abp_best, float(abp_near[abp_yi[abp_ok], abp_xi[abp_ok]].sum()) / abp_samples
                )
    return abp_best


def abp_door_confidence(abp_residual: abpMask, abp_gap: abpSegment) -> float:
    return min(1.0, 0.45 + 0.55 * abp_arc_score(abp_residual, abp_gap))


def abp_building_outline(abp_wall_mask: abpMask, abp_close_px: int) -> npt.NDArray[np.int32] | None:
    if not abp_wall_mask.any():
        return None
    abp_k = max(3, abp_close_px | 1)
    abp_pad = abp_k + 2
    abp_padded = np.pad(abp_wall_mask.astype(np.uint8), abp_pad)
    abp_closed = cv2.morphologyEx(
        abp_padded, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (abp_k, abp_k))
    )
    abp_contours, _ = cv2.findContours(abp_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not abp_contours:
        return None
    return np.asarray(max(abp_contours, key=cv2.contourArea), dtype=np.int32) - abp_pad


def abp_is_on_outline(
    abp_outline: npt.NDArray[np.int32], abp_point: abpPoint, abp_tol: float
) -> bool:
    abp_dist = cv2.pointPolygonTest(
        abp_outline, (float(abp_point.abp_x), float(abp_point.abp_y)), True
    )
    return abs(float(abp_dist)) <= abp_tol


def abp_corner_gaps(
    abp_walls: Sequence[abpSegment],
    abp_free_ends: Sequence[tuple[int, int]],
    abp_wall_mask: abpMask,
    *,
    abp_thickness: float,
    abp_min_px: float,
    abp_max_px: float,
) -> list[abpSegment]:
    abp_gaps: list[abpSegment] = []
    for abp_idx, abp_end in abp_free_ends:
        abp_wall = abp_walls[abp_idx]
        abp_tip, abp_base = (
            (abp_wall.abp_start, abp_wall.abp_end)
            if abp_end == 0
            else (abp_wall.abp_end, abp_wall.abp_start)
        )
        if abp_wall.abp_length < 1:
            continue
        abp_ux, abp_uy = (
            (abp_tip.abp_x - abp_base.abp_x) / abp_wall.abp_length,
            (abp_tip.abp_y - abp_base.abp_y) / abp_wall.abp_length,
        )
        abp_best: abpSegment | None = None
        abp_best_s = abp_max_px * 1.1
        for abp_j, abp_other in enumerate(abp_walls):
            if abp_j == abp_idx:
                continue
            abp_ox, abp_oy = (
                abp_other.abp_end.abp_x - abp_other.abp_start.abp_x,
                abp_other.abp_end.abp_y - abp_other.abp_start.abp_y,
            )
            abp_olen = math.hypot(abp_ox, abp_oy)
            if abp_olen < 1 or abs(
                abp_ux * abp_ox / abp_olen + abp_uy * abp_oy / abp_olen
            ) > math.cos(math.radians(60)):
                continue
            abp_den = abp_ux * abp_oy - abp_uy * abp_ox
            if abs(abp_den) < 1e-9:
                continue
            abp_s = (
                (abp_other.abp_start.abp_x - abp_tip.abp_x) * abp_oy
                - (abp_other.abp_start.abp_y - abp_tip.abp_y) * abp_ox
            ) / abp_den
            abp_r = (
                (abp_other.abp_start.abp_x - abp_tip.abp_x) * abp_uy
                - (abp_other.abp_start.abp_y - abp_tip.abp_y) * abp_ux
            ) / abp_den
            abp_margin = abp_thickness / abp_olen
            if not -abp_margin <= abp_r <= 1 + abp_margin:
                continue
            abp_face = abp_s - abp_thickness / 2
            if abp_min_px * 0.75 <= abp_face <= abp_best_s:
                abp_end_pt = abpPoint(
                    abp_tip.abp_x + abp_ux * abp_face, abp_tip.abp_y + abp_uy * abp_face
                )
                abp_candidate = abpSegment(abp_tip, abp_end_pt)
                abp_n = max(2, int(abp_face / 2))
                abp_xs = (
                    np.linspace(abp_tip.abp_x + abp_ux * abp_thickness, abp_end_pt.abp_x, abp_n)
                    .round()
                    .astype(int)
                )
                abp_ys = (
                    np.linspace(abp_tip.abp_y + abp_uy * abp_thickness, abp_end_pt.abp_y, abp_n)
                    .round()
                    .astype(int)
                )
                abp_h, abp_w = abp_wall_mask.shape
                abp_ok = (abp_xs >= 0) & (abp_xs < abp_w) & (abp_ys >= 0) & (abp_ys < abp_h)
                if abp_ok.any() and abp_wall_mask[abp_ys[abp_ok], abp_xs[abp_ok]].mean() < 0.2:
                    abp_best, abp_best_s = abp_candidate, abp_face
        if abp_best is not None:
            abp_gaps.append(abp_best)
    return abp_gaps
