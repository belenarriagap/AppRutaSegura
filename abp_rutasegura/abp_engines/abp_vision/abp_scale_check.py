from __future__ import annotations

import math

import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan
from abp_rutasegura.abp_engines.abp_navigation.abp_rooms import abp_detect_rooms
from abp_rutasegura.abp_engines.abp_vision.abp_layered import (
    abp_detect_layered_plan,
    abp_DOORS,
    abp_has_layers,
    abp_layer_ids,
)
from abp_rutasegura.abp_engines.abp_vision.abp_room_labels import (
    abp_label_anchors,
    abp_read_room_labels,
)

abp_USUAL_LEAF_M = 0.85
abp_LEAF_RANGE_M = (0.6, 1.08)
abp_MIN_ROOMS = 2
abp_AGREEMENT = 0.12


def abp_scale_factor(abp_vector: abpVectorPlan, abp_scale: float) -> float | None:
    if not abp_has_layers(abp_vector, abp_scale):
        return None
    abp_labels = [
        abp_q for abp_q in abp_read_room_labels(abp_vector.abp_texts) if abp_q.abp_area_m2
    ]
    if len(abp_labels) < abp_MIN_ROOMS:
        return None
    abp_first = abp__by_doors(abp_vector, abp_scale)
    abp_trial = abp_scale * abp_first
    abp_found = abp_detect_layered_plan(
        abp_vector, abp_trial, abp_anchors_px=abp_label_anchors(abp_vector.abp_texts)
    )
    abp_plan = abpFloorPlan(
        abp_scale_m_per_px=abp_trial,
        abp_walls=abp_found.abp_walls,
        abp_doors=abp_found.abp_doors,
        abp_exits=abp_found.abp_exits,
    )
    try:
        abp_rooms = abp_detect_rooms(abp_plan)
    except ValueError:
        return None
    abp_ratios: list[float] = []
    for abp_polygon in abp_rooms:
        abp_inside = [
            abp_q
            for abp_q in abp_labels
            if abp__inside(abp_polygon, abpPoint(abp_q.abp_x, abp_q.abp_y))
        ]
        if len(abp_inside) == 1 and abp_inside[0].abp_area_m2:
            abp_ratios.append(
                math.sqrt(abp_inside[0].abp_area_m2 / abp_plan.abp_area_m2(abp_polygon))
            )
    if len(abp_ratios) < abp_MIN_ROOMS:
        return None
    abp_middle = float(np.median(abp_ratios))
    abp_close = [
        abp_r for abp_r in abp_ratios if abs(abp_r - abp_middle) <= abp_AGREEMENT * abp_middle
    ]
    if len(abp_close) < max(abp_MIN_ROOMS, 0.5 * len(abp_ratios)):
        return None
    return abp_first * float(np.mean(abp_close))


def abp__by_doors(abp_vector: abpVectorPlan, abp_scale: float) -> float:
    abp_ids = abp_layer_ids(abp_vector, abp_DOORS)
    abp_arcs = abp_vector.abp_arcs[np.isin(abp_vector.abp_arc_layer, abp_ids)]
    abp_sweep = np.degrees(np.abs(abp_arcs[:, 4])) if len(abp_arcs) else np.zeros(0)
    abp_radii = (
        abp_arcs[(abp_sweep > 60) & (abp_sweep < 120), 2] * abp_scale
        if len(abp_arcs)
        else np.zeros(0)
    )
    abp_radii = abp_radii[(abp_radii > 0.25) & (abp_radii < 2.5)]
    if len(abp_radii) < 3:
        return 1.0
    abp_typical = float(np.median(abp_radii))
    abp_inside = abp_LEAF_RANGE_M[0] <= abp_typical <= abp_LEAF_RANGE_M[1]
    return 1.0 if abp_inside else abp_USUAL_LEAF_M / abp_typical


def abp__inside(abp_polygon: abpPolygon, abp_p: abpPoint) -> bool:
    abp_inside = False
    abp_v = abp_polygon.abp_vertices
    for abp_a, abp_b in zip(abp_v, (*abp_v[1:], abp_v[0]), strict=True):
        if (abp_a.abp_y > abp_p.abp_y) != (abp_b.abp_y > abp_p.abp_y) and abp_p.abp_x < (
            abp_b.abp_x - abp_a.abp_x
        ) * (abp_p.abp_y - abp_a.abp_y) / (abp_b.abp_y - abp_a.abp_y) + abp_a.abp_x:
            abp_inside = not abp_inside
    return abp_inside
