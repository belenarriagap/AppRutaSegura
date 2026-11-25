from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import abp_to_gray
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp_furniture_segments,
    abp_leaf_reach,
)

abp_CELL_M = 0.02
abp_DETAIL_M, abp_MAX_VERTICES = 0.04, 60
abp_MIN_SIDE_M, abp_MIN_LONG_M, abp_MIN_AREA_M2 = 0.3, 0.45, 0.16
abp_MAX_AREA_M2 = 12.0
abp_CHAIR_M = 0.3
abp_RECTANGLE = 0.9
abp_SOLID = 0.35
abp_WORD_M, abp_WORD_SOLID = 0.6, 0.8
abp_WORD_AREA_M2, abp_WORD_SOLID_SMALL = 0.3, 0.92
abp_TEXT_M = 0.35
abp_NOOK_M2 = 1.3
abpMask = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class abpObstacleParams:
    abp_min_area_m2: float = abp_MIN_AREA_M2
    abp_max_area_m2: float = abp_MAX_AREA_M2
    abp_trim_chairs: bool = True
    abp_skip_words: bool = True


def abp_detect_obstacles(
    abp_plan: abpFloorPlan,
    *,
    abp_image: abpRGBImage | None = None,
    abp_vector: abpVectorPlan | None = None,
    abp_params: abpObstacleParams | None = None,
) -> tuple[abpPolygon, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None or not abp_plan.abp_walls or (abp_image is None and abp_vector is None):
        return ()
    abp_params = abp_params or abpObstacleParams(abp_skip_words=abp_vector is None)
    abp_area = abp__work_area(abp_plan)
    abp_zoom = abp_scale / abp_CELL_M
    if abp_vector is not None:
        abp_ink = abp__ink_from_segments(
            abp_furniture_segments(abp_vector, abp_plan), abp_area, abp_zoom
        )
    else:
        assert abp_image is not None
        abp_ink = abp__ink_from_image(abp_image, abp_area, abp_zoom)
    abp_blocked = abp__wall_mask(abp_plan, abp_area, abp_zoom, abp_ink.shape)
    abp_inside = abp__inside_building(abp_plan, abp_area, abp_zoom, abp_ink.shape)
    abp_ink = abp__fill_nooks(abp_ink, abp_blocked)
    abp_ink[(abp_blocked > 0) | (abp_inside == 0)] = 0
    return tuple(
        abpPolygon(
            tuple(
                abpPoint(abp_x / abp_zoom + abp_area[0], abp_y / abp_zoom + abp_area[1])
                for abp_x, abp_y in abp_shape
            )
        )
        for abp_shape in abp__shapes(abp_ink, abp_params)
    )


def abp_shape_at(
    abp_plan: abpFloorPlan,
    abp_point: abpPoint,
    *,
    abp_image: abpRGBImage | None = None,
    abp_vector: abpVectorPlan | None = None,
) -> abpPolygon | None:
    if abp_plan.abp_scale_m_per_px is None or (abp_image is None and abp_vector is None):
        return None
    abp_loose = abpObstacleParams(
        abp_min_area_m2=0.02, abp_max_area_m2=400.0, abp_trim_chairs=False
    )
    abp_best: tuple[float, abpPolygon] | None = None
    for abp_polygon in abp_detect_obstacles(
        abp_plan, abp_image=abp_image, abp_vector=abp_vector, abp_params=abp_loose
    ):
        abp_contour = np.array(
            [(abp_v.abp_x, abp_v.abp_y) for abp_v in abp_polygon.abp_vertices], np.float32
        ).reshape(-1, 1, 2)
        abp_away = (
            cv2.pointPolygonTest(abp_contour, (abp_point.abp_x, abp_point.abp_y), True)
            * abp_plan.abp_scale_m_per_px
        )
        if abp_away >= -0.15 and (abp_best is None or abp_polygon.abp_area < abp_best[0]):
            abp_best = (abp_polygon.abp_area, abp_polygon)
    return abp_best[1] if abp_best is not None else None


def abp__work_area(abp_plan: abpFloorPlan) -> tuple[float, float, float, float]:
    abp_xs = [
        abp_p.abp_x
        for abp_w in abp_plan.abp_walls
        for abp_p in (abp_w.abp_segment.abp_start, abp_w.abp_segment.abp_end)
    ]
    abp_ys = [
        abp_p.abp_y
        for abp_w in abp_plan.abp_walls
        for abp_p in (abp_w.abp_segment.abp_start, abp_w.abp_segment.abp_end)
    ]
    abp_pad = 0.5 / (abp_plan.abp_scale_m_per_px or 1.0)
    return (
        min(abp_xs) - abp_pad,
        min(abp_ys) - abp_pad,
        max(abp_xs) + abp_pad,
        max(abp_ys) + abp_pad,
    )


def abp__shape(abp_area: tuple[float, float, float, float], abp_zoom: float) -> tuple[int, int]:
    return (
        max(1, int((abp_area[3] - abp_area[1]) * abp_zoom) + 1),
        max(1, int((abp_area[2] - abp_area[0]) * abp_zoom) + 1),
    )


def abp__ink_from_image(
    abp_image: abpRGBImage, abp_area: tuple[float, float, float, float], abp_zoom: float
) -> abpMask:
    abp_rows, abp_cols = abp__shape(abp_area, abp_zoom)
    abp_to_cells = np.array(
        [[abp_zoom, 0, -abp_area[0] * abp_zoom], [0, abp_zoom, -abp_area[1] * abp_zoom]], np.float64
    )
    abp_gray = abp_to_gray(abp_image)
    abp_dark = abp_gray
    if abp_zoom < 1:
        abp_size = max(1, round(1 / abp_zoom))
        abp_dark = np.asarray(
            cv2.erode(abp_gray, np.ones((abp_size, abp_size), np.uint8)), np.uint8
        )
    abp_paper = float(np.percentile(abp_gray, 90))
    abp_small = cv2.warpAffine(
        abp_dark,
        abp_to_cells,
        (abp_cols, abp_rows),
        flags=cv2.INTER_LINEAR,
        borderValue=int(abp_paper),
    )
    abp_ink = (abp_small < abp_paper - 45).astype(np.uint8)
    if abp_image.ndim == 3:
        abp_saturation = cv2.cvtColor(abp_image, cv2.COLOR_RGB2HSV)[:, :, 1]
        abp_color = cv2.warpAffine(
            abp_saturation, abp_to_cells, (abp_cols, abp_rows), flags=cv2.INTER_LINEAR
        )
        abp_ink |= (abp_color > 40).astype(np.uint8)
    return np.asarray(abp_ink, np.uint8)


def abp__ink_from_segments(
    abp_segments: abpFloatArray, abp_area: tuple[float, float, float, float], abp_zoom: float
) -> abpMask:
    abp_ink = np.zeros(abp__shape(abp_area, abp_zoom), np.uint8)
    for abp_x1, abp_y1, abp_x2, abp_y2 in abp_segments:
        cv2.line(
            abp_ink,
            (round((abp_x1 - abp_area[0]) * abp_zoom), round((abp_y1 - abp_area[1]) * abp_zoom)),
            (round((abp_x2 - abp_area[0]) * abp_zoom), round((abp_y2 - abp_area[1]) * abp_zoom)),
            1,
            1,
        )
    return abp_ink


def abp__fill_nooks(abp_ink: abpMask, abp_blocked: abpMask) -> abpMask:
    abp_closed = cv2.morphologyEx(abp_ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    abp_free = ((abp_closed == 0) & (abp_blocked == 0)).astype(np.uint8)
    abp__count, abp_labels, abp_stats, _ = cv2.connectedComponentsWithStats(
        abp_free, connectivity=4
    )
    abp_area = abp_stats[:, cv2.CC_STAT_AREA] * abp_CELL_M**2
    abp_small = abp_area < abp_NOOK_M2
    abp_small[0] = False
    abp_ring = cv2.dilate(abp_closed, np.ones((5, 5), np.uint8)) > 0
    abp_touching = np.bincount(abp_labels[abp_ring], minlength=len(abp_area))
    abp_perimeter = np.maximum(4 * np.sqrt(abp_stats[:, cv2.CC_STAT_AREA]), 1)
    abp_small &= abp_touching > 0.5 * abp_perimeter
    return np.asarray(abp_closed | abp_small[abp_labels].astype(np.uint8), np.uint8)


def abp__line(
    abp_mask: abpMask,
    abp_s: abpSegment,
    abp_area: tuple[float, float, float, float],
    abp_zoom: float,
    abp_width: int,
) -> None:
    abp_a = (
        round((abp_s.abp_start.abp_x - abp_area[0]) * abp_zoom),
        round((abp_s.abp_start.abp_y - abp_area[1]) * abp_zoom),
    )
    abp_b = (
        round((abp_s.abp_end.abp_x - abp_area[0]) * abp_zoom),
        round((abp_s.abp_end.abp_y - abp_area[1]) * abp_zoom),
    )
    cv2.line(abp_mask, abp_a, abp_b, 1, abp_width)


def abp__wall_mask(
    abp_plan: abpFloorPlan,
    abp_area: tuple[float, float, float, float],
    abp_zoom: float,
    abp_shape: tuple[int, ...],
) -> abpMask:
    abp_mask = np.zeros(abp_shape, np.uint8)
    for abp_wall in abp_plan.abp_walls:
        abp__line(abp_mask, abp_wall.abp_segment, abp_area, abp_zoom, round(0.34 / abp_CELL_M))
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    for abp_s in [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]:
        abp_reach = abp_leaf_reach(abp_s.abp_length * abp_scale)
        abp__line(abp_mask, abp_s, abp_area, abp_zoom, round(2 * abp_reach / abp_CELL_M))
    for abp_stair in abp_plan.abp_stairs:
        abp_points = [
            ((abp_v.abp_x - abp_area[0]) * abp_zoom, (abp_v.abp_y - abp_area[1]) * abp_zoom)
            for abp_v in abp_stair.abp_area.abp_vertices
        ]
        cv2.fillPoly(abp_mask, [np.array(abp_points, np.int32)], 1)
    return abp_mask


def abp__inside_building(
    abp_plan: abpFloorPlan,
    abp_area: tuple[float, float, float, float],
    abp_zoom: float,
    abp_shape: tuple[int, ...],
) -> abpMask:
    abp_mask = np.zeros(abp_shape, np.uint8)
    abp_points = [
        ((abp_p.abp_x - abp_area[0]) * abp_zoom, (abp_p.abp_y - abp_area[1]) * abp_zoom)
        for abp_w in abp_plan.abp_walls
        for abp_p in (abp_w.abp_segment.abp_start, abp_w.abp_segment.abp_end)
    ]
    abp_hull = cv2.convexHull(np.array(abp_points, np.float32)).astype(np.int32)
    cv2.fillPoly(abp_mask, [abp_hull], 1)
    return abp_mask


def abp__shapes(abp_ink: abpMask, abp_params: abpObstacleParams) -> list[list[tuple[float, float]]]:
    abp_joined = cv2.morphologyEx(abp_ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    abp_contours, _ = cv2.findContours(abp_joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    abp_out: list[list[tuple[float, float]]] = []
    for abp_contour in abp_contours:
        for abp_piece in abp__pieces(np.asarray(abp_contour, np.int32), abp_params):
            abp_shape = abp__simplify(abp_piece, abp_params)
            if abp_shape is not None:
                abp_out.append(abp_shape)
    return abp_out


def abp__pieces(
    abp_contour: npt.NDArray[np.int32], abp_params: abpObstacleParams
) -> Sequence[npt.NDArray[np.int32]]:
    abp_x, abp_y, abp_w, abp_h = cv2.boundingRect(abp_contour)
    if max(abp_w, abp_h) * abp_CELL_M < abp_TEXT_M:
        return []
    abp_pad = 4
    abp_filled = np.zeros((abp_h + 2 * abp_pad, abp_w + 2 * abp_pad), np.uint8)
    cv2.drawContours(
        abp_filled, [abp_contour], -1, 1, cv2.FILLED, offset=(abp_pad - abp_x, abp_pad - abp_y)
    )
    abp_area = float(abp_filled.sum()) * abp_CELL_M**2
    if abp_area < abp_params.abp_min_area_m2:
        return []
    if abp_params.abp_trim_chairs:
        abp_size = max(3, round(abp_CHAIR_M / abp_CELL_M) | 1)
        abp_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (abp_size, abp_size))
        abp_core = cv2.morphologyEx(abp_filled, cv2.MORPH_OPEN, abp_kernel)
        if float(abp_core.sum()) * abp_CELL_M**2 >= 0.45 * abp_area:
            abp_filled = np.asarray(abp_core, np.uint8)
    abp_found, _ = cv2.findContours(abp_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    abp_back = np.array([abp_x - abp_pad, abp_y - abp_pad], np.int32)
    return [np.asarray(abp_c + abp_back, np.int32) for abp_c in abp_found]


def abp__simplify(
    abp_contour: npt.NDArray[np.int32], abp_params: abpObstacleParams
) -> list[tuple[float, float]] | None:
    abp_area = float(cv2.contourArea(abp_contour)) * abp_CELL_M**2
    (abp__cx, abp__cy), (abp_w, abp_h), abp__angle = abp_box = cv2.minAreaRect(abp_contour)
    abp_short, abp_long_side = min(abp_w, abp_h) * abp_CELL_M, max(abp_w, abp_h) * abp_CELL_M
    if not abp_params.abp_min_area_m2 <= abp_area <= abp_params.abp_max_area_m2:
        return None
    if abp_params.abp_trim_chairs and (
        abp_short < abp_MIN_SIDE_M or abp_long_side < abp_MIN_LONG_M
    ):
        return None
    abp_hull = float(cv2.contourArea(cv2.convexHull(abp_contour))) * abp_CELL_M**2
    if abp_params.abp_skip_words and abp_params.abp_trim_chairs:
        abp_solid = abp_WORD_SOLID if abp_area > abp_WORD_AREA_M2 else abp_WORD_SOLID_SMALL
        if abp_short < abp_WORD_M and abp_area < abp_solid * abp_hull:
            return None
    if abp_short <= 0 or abp_area < abp_SOLID * abp_short * abp_long_side:
        return None
    if abp_area >= abp_RECTANGLE * abp_short * abp_long_side:
        return [(float(abp_x), float(abp_y)) for abp_x, abp_y in cv2.boxPoints(abp_box)]
    abp_detail = abp_DETAIL_M
    abp_simple = cv2.approxPolyDP(abp_contour, abp_detail / abp_CELL_M, True).reshape(-1, 2)
    while len(abp_simple) > abp_MAX_VERTICES:
        abp_detail *= 1.5
        abp_simple = cv2.approxPolyDP(abp_contour, abp_detail / abp_CELL_M, True).reshape(-1, 2)
    if len(abp_simple) < 3:
        return None
    return [(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_simple]
