from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_enums import abpObservationType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_norms import abpNormEvaluation, abpNormRule, abpRoomCapacity
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpRoom
from abp_rutasegura.abp_domain.abp_results import abpObservation, abpRoomRoute
from abp_rutasegura.abp_engines.abp_norms.abp_rules import (
    abp_KIND_ANTIPANIC,
    abp_KIND_MIN_WIDTH,
    abp_KIND_TRAVEL,
    abp_KIND_WIDTH_PER_PERSON,
    abpRule,
    abpRuleSet,
)

abp_DOOR_TOLERANCE_M = 0.6
abp_CORRIDOR_RESOLUTION_M = 0.05


def abp__to_m(abp_p: abpPoint, abp_scale: float) -> abpPoint:
    return abpPoint(abp_p.abp_x * abp_scale, abp_p.abp_y * abp_scale)


def abp__polygon_m(abp_polygon: abpPolygon, abp_scale: float) -> abpPolygon:
    return abpPolygon(tuple(abp__to_m(abp_p, abp_scale) for abp_p in abp_polygon.abp_vertices))


def abp__segment_m(abp_segment: abpSegment, abp_scale: float) -> abpSegment:
    return abpSegment(
        abp__to_m(abp_segment.abp_start, abp_scale), abp__to_m(abp_segment.abp_end, abp_scale)
    )


def abp__distance_to_segment(abp_p: abpPoint, abp_a: abpPoint, abp_b: abpPoint) -> float:
    abp_dx, abp_dy = abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y
    abp_length2 = abp_dx * abp_dx + abp_dy * abp_dy
    abp_t = (
        0.0
        if abp_length2 == 0
        else max(
            0.0,
            min(
                1.0,
                ((abp_p.abp_x - abp_a.abp_x) * abp_dx + (abp_p.abp_y - abp_a.abp_y) * abp_dy)
                / abp_length2,
            ),
        )
    )
    return math.hypot(
        abp_p.abp_x - (abp_a.abp_x + abp_t * abp_dx), abp_p.abp_y - (abp_a.abp_y + abp_t * abp_dy)
    )


def abp_distance_to_boundary(abp_polygon: abpPolygon, abp_p: abpPoint) -> float:
    abp_vertices = abp_polygon.abp_vertices
    return min(
        abp__distance_to_segment(
            abp_p, abp_vertices[abp_i], abp_vertices[(abp_i + 1) % len(abp_vertices)]
        )
        for abp_i in range(len(abp_vertices))
    )


def abp_corridor_width(
    abp_polygon_m: abpPolygon, abp_resolution: float = abp_CORRIDOR_RESOLUTION_M
) -> float:
    abp_xs = [abp_p.abp_x for abp_p in abp_polygon_m.abp_vertices]
    abp_ys = [abp_p.abp_y for abp_p in abp_polygon_m.abp_vertices]
    abp_x0, abp_y0 = min(abp_xs) - 2 * abp_resolution, min(abp_ys) - 2 * abp_resolution
    abp_cols = math.ceil((max(abp_xs) - abp_x0) / abp_resolution) + 3
    abp_rows = math.ceil((max(abp_ys) - abp_y0) / abp_resolution) + 3
    abp_mask = np.zeros((abp_rows, abp_cols), np.uint8)
    abp_pts = np.array(
        [
            [
                round((abp_p.abp_x - abp_x0) / abp_resolution),
                round((abp_p.abp_y - abp_y0) / abp_resolution),
            ]
            for abp_p in abp_polygon_m.abp_vertices
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(abp_mask, [abp_pts], 1)
    abp_dist = cv2.distanceTransform(abp_mask, cv2.DIST_L2, 5)
    return float(2.0 * abp_dist.max() * abp_resolution)


def abp__observation(
    abp_rule: abpRule,
    abp_description: str,
    abp_location: abpPoint | None,
    abp_recommendation: str | None = None,
) -> abpObservation:
    return abpObservation(
        abp_kind=abpObservationType.abp_NORM,
        abp_description=abp_description,
        abp_recommendation=abp_recommendation or abp_rule.abp_recommendation,
        abp_location=abp_location,
        abp_norm=abp_rule.abp_norm,
        abp_article=abp_rule.abp_article,
        abp_verified=abp_rule.abp_verified,
    )


def abp_evaluate(
    abp_plan: abpFloorPlan,
    abp_occupancies: Sequence[abpOccupancy],
    abp_rules: abpRuleSet,
    *,
    abp_exit_occupants: int | None = None,
    abp_routes: Sequence[abpRoomRoute] = (),
) -> abpNormEvaluation:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None:
        raise ValueError("El plano no tiene escala; defínala en el paso 2.")
    abp_used: dict[str, abpRule] = {}
    abp_observations: list[abpObservation] = []

    def abp_use(abp_rule: abpRule) -> abpRule:
        abp_used[abp_rule.abp_id] = abp_rule
        return abp_rule

    abp_counts: dict[str, int] = {}
    for abp_occ in abp_occupancies:
        if abp_occ.abp_level == abp_plan.abp_level:
            abp_counts[abp_occ.abp_room_name] = (
                abp_counts.get(abp_occ.abp_room_name, 0) + abp_occ.abp_count
            )

    abp_doors_m = [abp__segment_m(abp_d.abp_segment, abp_scale) for abp_d in abp_plan.abp_doors]
    abp_exits_m = [
        (abp_e.abp_name, abp__segment_m(abp_e.abp_segment, abp_scale), abp_e.abp_confirmed)
        for abp_e in abp_plan.abp_exits
    ]
    abp_rooms_m = [
        (abp_room, abp__polygon_m(abp_room.abp_area, abp_scale)) for abp_room in abp_plan.abp_rooms
    ]

    def abp_rooms_at(abp_point: abpPoint) -> list[str]:
        return [
            abp_room.abp_name
            for abp_room, abp_poly in abp_rooms_m
            if abp_distance_to_boundary(abp_poly, abp_point) <= abp_DOOR_TOLERANCE_M
        ]

    abp_capacities: list[abpRoomCapacity] = []
    for abp_room, abp_poly in abp_rooms_m:
        abp_capacities.append(
            abp__capacity(
                abp_room,
                abp_poly,
                abp_plan.abp_level,
                abp_counts,
                abp_rules,
                abp_use,
                abp_observations,
            )
        )

    abp_per_person = abp_rules.abp_first(abp_KIND_WIDTH_PER_PERSON, "puerta")
    if abp_per_person is not None:
        abp_factor = abp_per_person.abp_number("metros_por_persona")
        for abp_room, abp_poly in abp_rooms_m:
            abp_people = abp_counts.get(abp_room.abp_name, 0)
            if abp_people == 0:
                continue
            abp_openings = [
                abp_s
                for abp_s in abp_doors_m
                if abp_distance_to_boundary(abp_poly, abp_s.abp_midpoint) <= abp_DOOR_TOLERANCE_M
            ]
            abp_openings += [
                abp_s
                for _, abp_s, _ in abp_exits_m
                if abp_distance_to_boundary(abp_poly, abp_s.abp_midpoint) <= abp_DOOR_TOLERANCE_M
            ]
            abp_available = sum(abp_s.abp_length for abp_s in abp_openings)
            abp_required = abp_people * abp_factor
            abp_use(abp_per_person)
            if abp_available + 1e-9 < abp_required:
                abp_observations.append(
                    abp__observation(
                        abp_per_person,
                        f"Las puertas de «{abp_room.abp_name}» suman {abp_available:.2f} m de ancho y, para "
                        f"{abp_people} personas, se requieren {abp_required:.2f} m.",
                        abp_poly.abp_centroid,
                    )
                )

    abp_door_min = abp_rules.abp_first(abp_KIND_MIN_WIDTH, "puerta")
    if abp_door_min is not None and abp_doors_m:
        abp_minimum = abp_use(abp_door_min).abp_number("metros")
        for abp_seg in abp_doors_m:
            if abp_seg.abp_length + 1e-9 < abp_minimum:
                abp_where = (
                    " y ".join(f"«{abp_n}»" for abp_n in abp_rooms_at(abp_seg.abp_midpoint))
                    or "sin ambiente"
                )
                abp_observations.append(
                    abp__observation(
                        abp_door_min,
                        f"Una puerta de {abp_where} mide {abp_seg.abp_length:.2f} m; el mínimo es "
                        f"{abp_minimum:.2f} m.",
                        abp_seg.abp_midpoint,
                    )
                )
    abp_exit_min = abp_rules.abp_first(abp_KIND_MIN_WIDTH, "salida")
    if abp_exit_min is not None and abp_exits_m:
        abp_minimum = abp_use(abp_exit_min).abp_number("metros")
        for abp_name, abp_seg, _ in abp_exits_m:
            if abp_seg.abp_length + 1e-9 < abp_minimum:
                abp_observations.append(
                    abp__observation(
                        abp_exit_min,
                        f"«{abp_name}» mide {abp_seg.abp_length:.2f} m; el mínimo es {abp_minimum:.2f} m.",
                        abp_seg.abp_midpoint,
                    )
                )
    abp_corridor_min = abp_rules.abp_first(abp_KIND_MIN_WIDTH, "pasillo")
    if abp_corridor_min is not None:
        for abp_room, abp_poly in abp_rooms_m:
            abp_category = abp_rules.abp_category(abp_room.abp_use, abp_room.abp_category)
            if abp_category is None or not abp_category.abp_circulation:
                continue
            abp_minimum = abp_use(abp_corridor_min).abp_number("metros")
            abp_width = abp_corridor_width(abp_poly)
            if abp_width + 1e-9 < abp_minimum:
                abp_observations.append(
                    abp__observation(
                        abp_corridor_min,
                        f"El pasillo «{abp_room.abp_name}» tiene unos {abp_width:.2f} m de ancho libre; el "
                        f"mínimo es {abp_minimum:.2f} m.",
                        abp_poly.abp_centroid,
                    )
                )

    abp_exit_rule = abp_rules.abp_first(abp_KIND_WIDTH_PER_PERSON, "salida")
    abp_total_people = (
        sum(abp_counts.values()) if abp_exit_occupants is None else abp_exit_occupants
    )
    if abp_exit_rule is not None and abp_total_people > 0:
        abp_factor = abp_use(abp_exit_rule).abp_number("metros_por_persona")
        abp_available = sum(
            abp_seg.abp_length for _, abp_seg, abp_confirmed in abp_exits_m if abp_confirmed
        )
        abp_required = abp_total_people * abp_factor
        if abp_available + 1e-9 < abp_required:
            abp_observations.append(
                abp__observation(
                    abp_exit_rule,
                    f"Las salidas confirmadas suman {abp_available:.2f} m de ancho y, para "
                    f"{abp_total_people} personas, se requieren {abp_required:.2f} m.",
                    None,
                )
            )

    abp_antipanic = abp_rules.abp_first(abp_KIND_ANTIPANIC)
    if abp_antipanic is not None:
        abp_threshold = int(abp_antipanic.abp_params["umbral_personas"])
        for abp_room, abp_poly in abp_rooms_m:
            abp_people = abp_counts.get(abp_room.abp_name, 0)
            if abp_people > abp_threshold:
                abp_use(abp_antipanic)
                abp_observations.append(
                    abp__observation(
                        abp_antipanic,
                        f"«{abp_room.abp_name}» tiene {abp_people} personas (más de {abp_threshold}).",
                        abp_poly.abp_centroid,
                    )
                )

    abp_travel = abp_rules.abp_first(abp_KIND_TRAVEL)
    if abp_travel is not None and abp_routes:
        abp_use(abp_travel)
        abp_limit = abp_travel.abp_number("metros")
        for abp_route in abp_routes:
            if abp_route.abp_max_distance_m > abp_limit:
                abp_destination = (
                    f"«{abp_route.abp_target_name}»" if abp_route.abp_target_name else "una salida"
                )
                abp_observations.append(
                    abp__observation(
                        abp_travel,
                        f"Desde el punto más alejado de «{abp_route.abp_room_name}» hasta {abp_destination} "
                        f"se recorren {abp_route.abp_max_distance_m:.1f} m; el máximo es {abp_limit:g} m.",
                        abp_route.abp_farthest_m,
                    )
                )
    return abpNormEvaluation(
        abp_capacities=tuple(abp_capacities),
        abp_observations=tuple(abp_observations),
        abp_rules_used=tuple(
            abp_r.abp_as_domain()
            for abp_r in sorted(abp_used.values(), key=lambda abp_r: abp_r.abp_id)
        ),
        abp_routes=tuple(abp_routes),
    )


def abp__capacity(
    abp_room: abpRoom,
    abp_poly: abpPolygon,
    abp_level: int,
    abp_counts: dict[str, int],
    abp_rules: abpRuleSet,
    abp_use: Callable[[abpRule], abpRule],
    abp_observations: list[abpObservation],
) -> abpRoomCapacity:
    abp_category = abp_rules.abp_category(abp_room.abp_use, abp_room.abp_category)
    abp_area = abp_poly.abp_area
    abp_people = abp_counts.get(abp_room.abp_name, 0)
    if abp_category is None:
        return abpRoomCapacity(
            abp_room.abp_name,
            abp_level,
            abp_room.abp_category,
            "",
            abp_area,
            None,
            None,
            abp_people,
            None,
        )
    abp_rule = abp_use(abp_category.abp_rule)
    abp_capacity = None
    if abp_category.abp_m2_per_person is not None:
        abp_capacity = math.floor(abp_area / abp_category.abp_m2_per_person + 1e-9)
        if abp_people > abp_capacity:
            abp_observations.append(
                abp__observation(
                    abp_rule,
                    f"«{abp_room.abp_name}» tiene {abp_people} personas asignadas y su aforo es {abp_capacity} "
                    f"({abp_area:.1f} m² ÷ {abp_category.abp_m2_per_person:g} m² por persona).",
                    abp_poly.abp_centroid,
                )
            )
    return abpRoomCapacity(
        abp_room_name=abp_room.abp_name,
        abp_level=abp_level,
        abp_category=abp_category.abp_id,
        abp_category_label=abp_category.abp_label,
        abp_area_m2=round(abp_area, 2),
        abp_m2_per_person=abp_category.abp_m2_per_person,
        abp_capacity=abp_capacity,
        abp_occupants=abp_people,
        abp_rule_id=abp_rule.abp_id,
    )


def abp_describe_rules(abp_rules: Sequence[abpNormRule]) -> list[str]:
    return [
        f"{abp_r.abp_id} — {abp_r.abp_description} ({abp_r.abp_citation})" for abp_r in abp_rules
    ]
