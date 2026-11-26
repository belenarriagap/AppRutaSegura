from __future__ import annotations

import math

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan

abp_RESOLUTION_M = 0.1
abp_MIN_AREA_M2 = 2.0


def abp_detect_rooms(
    abp_plan: abpFloorPlan,
    *,
    abp_resolution_m: float = abp_RESOLUTION_M,
    abp_min_area_m2: float = abp_MIN_AREA_M2,
) -> list[abpPolygon]:
    if abp_plan.abp_scale_m_per_px is None:
        raise ValueError("El plano no tiene escala; defínala en el paso 2.")
    abp_segments = [abp_w.abp_segment for abp_w in abp_plan.abp_walls] + [
        abp_d.abp_segment for abp_d in abp_plan.abp_doors
    ]
    abp_segments += [abp_e.abp_segment for abp_e in abp_plan.abp_exits]
    if not abp_segments:
        return []
    abp_cell_px = max(1.0, abp_resolution_m / abp_plan.abp_scale_m_per_px)
    abp_xs = [abp_p.abp_x for abp_s in abp_segments for abp_p in (abp_s.abp_start, abp_s.abp_end)]
    abp_ys = [abp_p.abp_y for abp_s in abp_segments for abp_p in (abp_s.abp_start, abp_s.abp_end)]
    abp_x0, abp_y0 = min(abp_xs) - 3 * abp_cell_px, min(abp_ys) - 3 * abp_cell_px
    abp_cols = math.ceil((max(abp_xs) - abp_x0) / abp_cell_px) + 4
    abp_rows = math.ceil((max(abp_ys) - abp_y0) / abp_cell_px) + 4
    abp_barrier = np.zeros((abp_rows, abp_cols), np.uint8)

    def abp_cv_point(abp_p: abpPoint) -> tuple[int, int]:
        return round((abp_p.abp_x - abp_x0) / abp_cell_px * 16), round(
            (abp_p.abp_y - abp_y0) / abp_cell_px * 16
        )

    for abp_seg in abp_segments:
        cv2.line(
            abp_barrier,
            abp_cv_point(abp_seg.abp_start),
            abp_cv_point(abp_seg.abp_end),
            1,
            2,
            cv2.LINE_8,
            4,
        )

    abp_free = (abp_barrier == 0).astype(np.uint8)
    abp_count, abp_labels, abp_stats, _ = cv2.connectedComponentsWithStats(abp_free, connectivity=4)
    abp_border = set(
        np.unique(
            np.concatenate([abp_labels[0], abp_labels[-1], abp_labels[:, 0], abp_labels[:, -1]])
        )
    )
    abp_min_cells = abp_min_area_m2 / (abp_resolution_m * abp_resolution_m)
    abp_polygons: list[tuple[float, float, abpPolygon]] = []
    for abp_label in range(1, abp_count):
        if abp_label in abp_border or abp_stats[abp_label, cv2.CC_STAT_AREA] < abp_min_cells:
            continue
        abp_region = (abp_labels == abp_label).astype(np.uint8)
        abp_region = cv2.dilate(abp_region, np.ones((3, 3), np.uint8))
        abp_contours, _ = cv2.findContours(abp_region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        abp_contour = max(abp_contours, key=cv2.contourArea)
        abp_approx = cv2.approxPolyDP(abp_contour, 1.5, True).reshape(-1, 2)
        if len(abp_approx) < 3:
            continue
        abp_vertices = tuple(
            abpPoint(abp_x0 + float(abp_x) * abp_cell_px, abp_y0 + float(abp_y) * abp_cell_px)
            for abp_x, abp_y in abp_approx
        )
        abp_poly = abpPolygon(abp_vertices)
        abp_polygons.append(
            (
                round(abp_poly.abp_centroid.abp_y / (2 / abp_plan.abp_scale_m_per_px)),
                abp_poly.abp_centroid.abp_x,
                abp_poly,
            )
        )
    abp_polygons.sort(key=lambda abp_item: (abp_item[0], abp_item[1]))
    return [abp_poly for _, _, abp_poly in abp_polygons]
