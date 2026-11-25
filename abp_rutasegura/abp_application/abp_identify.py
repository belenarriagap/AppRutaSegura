from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_application.abp_plan_editing import abp_snap_opening
from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService
from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpSafeZone,
    abpStair,
    abpWall,
)
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_openings import abp_opening_near

abpElementRef = tuple[abpElementType, int]
abpImage = npt.NDArray[np.uint8]

abp_FIELDS = {
    abpElementType.abp_WALL: "abp_walls",
    abpElementType.abp_DOOR: "abp_doors",
    abpElementType.abp_EXIT: "abp_exits",
    abpElementType.abp_STAIR: "abp_stairs",
    abpElementType.abp_OBSTACLE: "abp_obstacles",
    abpElementType.abp_SAFE_ZONE: "abp_safe_zones",
    abpElementType.abp_SIGN: "abp_signs",
}
abp_CONFIRMABLE = (abpElementType.abp_EXIT, abpElementType.abp_STAIR, abpElementType.abp_OBSTACLE)
abp_AREAS = (abpElementType.abp_OBSTACLE, abpElementType.abp_STAIR, abpElementType.abp_SAFE_ZONE)
abp_OPENINGS = (abpElementType.abp_DOOR, abpElementType.abp_EXIT)
abp_CONVERSIONS: dict[abpElementType, tuple[abpElementType, ...]] = {
    abpElementType.abp_DOOR: (abpElementType.abp_EXIT, abpElementType.abp_WALL),
    abpElementType.abp_EXIT: (abpElementType.abp_DOOR, abpElementType.abp_WALL),
    abpElementType.abp_WALL: (abpElementType.abp_DOOR, abpElementType.abp_EXIT),
    abpElementType.abp_OBSTACLE: (abpElementType.abp_STAIR, abpElementType.abp_SAFE_ZONE),
    abpElementType.abp_STAIR: (abpElementType.abp_OBSTACLE, abpElementType.abp_SAFE_ZONE),
    abpElementType.abp_SAFE_ZONE: (abpElementType.abp_OBSTACLE, abpElementType.abp_STAIR),
}
abp_LOW_CONFIDENCE = 0.7
abp_REACH_M = 1.2


@dataclass(frozen=True, slots=True)
class abpReviewItem:
    abp_ref: abpElementRef
    abp_center: abpPoint
    abp_reach: float


def abp_identify(
    abp_plan: abpFloorPlan,
    abp_point: abpPoint,
    abp_kind: abpElementType,
    *,
    abp_image: abpImage | None = None,
    abp_vector: abpVectorPlan | None = None,
) -> abpFloorPlan | None:
    if abp_kind in abp_OPENINGS:
        return abp__identify_opening(abp_plan, abp_point, abp_kind)
    if abp_kind not in abp_AREAS:
        return None
    abp_existing = abp__area_at(abp_plan, abp_point)
    if abp_existing is not None:
        return (
            abp__confirm_one(abp_plan, abp_existing)
            if abp_existing[0] is abp_kind
            else abp_convert(abp_plan, abp_existing, abp_kind)
        )
    abp_shape = abpPlanImportService.abp_shape_at(abp_plan, abp_point, abp_image, abp_vector)
    return abp__add_area(abp_plan, abp_shape, abp_kind) if abp_shape is not None else None


def abp__identify_opening(
    abp_plan: abpFloorPlan, abp_point: abpPoint, abp_kind: abpElementType
) -> abpFloorPlan | None:
    abp_scale = abp_plan.abp_scale_m_per_px or 0.02
    abp_reach = abp_REACH_M / abp_scale
    abp_best: tuple[float, abpElementRef] | None = None
    for abp_other in abp_OPENINGS:
        for abp_index, abp_element in enumerate(getattr(abp_plan, abp_FIELDS[abp_other])):
            abp_away = abp__distance(abp_point, abp_element.abp_segment)
            if abp_away <= abp_reach and (abp_best is None or abp_away < abp_best[0]):
                abp_best = (abp_away, (abp_other, abp_index))
    if abp_best is not None:
        abp_ref = abp_best[1]
        return (
            abp__confirm_one(abp_plan, abp_ref)
            if abp_ref[0] is abp_kind
            else abp_convert(abp_plan, abp_ref, abp_kind)
        )
    abp_gap = abp_opening_near(
        [
            (
                abp_w.abp_segment.abp_start.abp_x,
                abp_w.abp_segment.abp_start.abp_y,
                abp_w.abp_segment.abp_end.abp_x,
                abp_w.abp_segment.abp_end.abp_y,
            )
            for abp_w in abp_plan.abp_walls
        ],
        (abp_point.abp_x, abp_point.abp_y),
        abp_scale,
    )
    if abp_gap is None:
        return None
    abp_opening = abpSegment(abpPoint(abp_gap[0], abp_gap[1]), abpPoint(abp_gap[2], abp_gap[3]))
    return abp__add_opening(abp_plan, abp_opening, abp_kind)


def abp__add_opening(
    abp_plan: abpFloorPlan, abp_opening: abpSegment, abp_kind: abpElementType
) -> abpFloorPlan:
    if abp_kind is abpElementType.abp_DOOR:
        return dataclasses.replace(abp_plan, abp_doors=(*abp_plan.abp_doors, abpDoor(abp_opening)))
    return dataclasses.replace(
        abp_plan, abp_exits=(*abp_plan.abp_exits, abpExit(abp_opening, abp__exit_name(abp_plan)))
    )


def abp__add_area(
    abp_plan: abpFloorPlan, abp_shape: abpPolygon, abp_kind: abpElementType
) -> abpFloorPlan:
    if abp_kind is abpElementType.abp_OBSTACLE:
        return dataclasses.replace(
            abp_plan, abp_obstacles=(*abp_plan.abp_obstacles, abpObstacle(abp_shape))
        )
    if abp_kind is abpElementType.abp_STAIR:
        abp_stair = abpStair(abp_shape, abp_name=abp__stair_name(abp_plan))
        return dataclasses.replace(abp_plan, abp_stairs=(*abp_plan.abp_stairs, abp_stair))
    return dataclasses.replace(
        abp_plan, abp_safe_zones=(*abp_plan.abp_safe_zones, abpSafeZone(abp_shape))
    )


def abp__area_at(abp_plan: abpFloorPlan, abp_point: abpPoint) -> abpElementRef | None:
    for abp_kind in abp_AREAS:
        for abp_index, abp_element in enumerate(getattr(abp_plan, abp_FIELDS[abp_kind])):
            if abp__contains(abp_element.abp_area, abp_point):
                return abp_kind, abp_index
    return None


def abp_convert(
    abp_plan: abpFloorPlan, abp_ref: abpElementRef, abp_kind: abpElementType
) -> abpFloorPlan:
    abp_old, abp_index = abp_ref
    abp_elements = getattr(abp_plan, abp_FIELDS[abp_old])
    if abp_kind not in abp_CONVERSIONS.get(abp_old, ()) or not 0 <= abp_index < len(abp_elements):
        raise ValueError(
            f"Un elemento «{abp_old.value}» no se puede convertir en «{abp_kind.value}»."
        )
    abp_element = abp_elements[abp_index]
    abp_rest: dict[str, Any] = {
        abp_FIELDS[abp_old]: tuple(
            abp_e for abp_i, abp_e in enumerate(abp_elements) if abp_i != abp_index
        )
    }
    abp_without = dataclasses.replace(abp_plan, **abp_rest)
    if abp_kind is abpElementType.abp_WALL:
        return dataclasses.replace(
            abp_without, abp_walls=(*abp_without.abp_walls, abpWall(abp_element.abp_segment))
        )
    if abp_kind in abp_OPENINGS:
        if abp_old is abpElementType.abp_WALL:
            abp_snap = abp_snap_opening(abp_without, abp_element.abp_segment)
            return abp__add_opening(
                dataclasses.replace(abp_without, abp_walls=abp_snap.abp_walls),
                abp_snap.abp_opening,
                abp_kind,
            )
        return abp__add_opening(abp_without, abp_element.abp_segment, abp_kind)
    return abp__add_area(abp_without, abp_element.abp_area, abp_kind)


def abp_pending(
    abp_plan: abpFloorPlan, abp_kinds: Iterable[abpElementType] = abp_CONFIRMABLE
) -> list[abpElementRef]:
    return [
        (abp_kind, abp_i)
        for abp_kind in abp_kinds
        for abp_i, abp_e in enumerate(getattr(abp_plan, abp_FIELDS[abp_kind]))
        if not abp_e.abp_confirmed
    ]


def abp_confirm(abp_plan: abpFloorPlan, abp_refs: Iterable[abpElementRef]) -> abpFloorPlan:
    abp_wanted: dict[abpElementType, set[int]] = {}
    for abp_kind, abp_index in abp_refs:
        if abp_kind in abp_CONFIRMABLE:
            abp_wanted.setdefault(abp_kind, set()).add(abp_index)
    abp_changes: dict[str, Any] = {}
    for abp_kind, abp_indices in abp_wanted.items():
        abp_changes[abp_FIELDS[abp_kind]] = tuple(
            dataclasses.replace(abp_e, abp_confirmed=True)
            if abp_i in abp_indices and not abp_e.abp_confirmed
            else abp_e
            for abp_i, abp_e in enumerate(getattr(abp_plan, abp_FIELDS[abp_kind]))
        )
    abp_named = dataclasses.replace(abp_plan, **abp_changes)
    if abpElementType.abp_STAIR not in abp_wanted:
        return abp_named
    for abp_i, abp_stair in enumerate(abp_named.abp_stairs):
        if abp_stair.abp_confirmed and not abp_stair.abp_name:
            abp_stairs = list(abp_named.abp_stairs)
            abp_stairs[abp_i] = dataclasses.replace(abp_stair, abp_name=abp__stair_name(abp_named))
            abp_named = dataclasses.replace(abp_named, abp_stairs=tuple(abp_stairs))
    return abp_named


def abp__confirm_one(abp_plan: abpFloorPlan, abp_ref: abpElementRef) -> abpFloorPlan:
    return abp_confirm(abp_plan, [abp_ref]) if abp_ref[0] in abp_CONFIRMABLE else abp_plan


def abp_review_items(abp_plan: abpFloorPlan) -> list[abpReviewItem]:
    abp_scale = abp_plan.abp_scale_m_per_px or 0.02
    abp_refs = [*abp_pending(abp_plan, (abpElementType.abp_EXIT, abpElementType.abp_STAIR))]
    abp_refs += [
        (abpElementType.abp_DOOR, abp_i)
        for abp_i, abp_d in enumerate(abp_plan.abp_doors)
        if abp_d.abp_confidence < abp_LOW_CONFIDENCE
    ]
    abp_refs += abp_pending(abp_plan, (abpElementType.abp_OBSTACLE,))
    abp_items: list[abpReviewItem] = []
    for abp_kind, abp_index in abp_refs:
        abp_element = getattr(abp_plan, abp_FIELDS[abp_kind])[abp_index]
        if abp_kind in abp_OPENINGS:
            abp_center, abp_size = (
                abp_element.abp_segment.abp_midpoint,
                abp_element.abp_segment.abp_length,
            )
        else:
            abp_center = abp_element.abp_area.abp_centroid
            abp_size = (
                max(
                    abp_center.abp_distance_to(abp_v) for abp_v in abp_element.abp_area.abp_vertices
                )
                * 2
            )
        abp_items.append(
            abpReviewItem((abp_kind, abp_index), abp_center, abp_size / 2 + 2.5 / abp_scale)
        )
    return abp_items


def abp_accept_door(abp_plan: abpFloorPlan, abp_index: int) -> abpFloorPlan:
    abp_doors = list(abp_plan.abp_doors)
    abp_doors[abp_index] = dataclasses.replace(abp_doors[abp_index], abp_confidence=1.0)
    return dataclasses.replace(abp_plan, abp_doors=tuple(abp_doors))


def abp__exit_name(abp_plan: abpFloorPlan) -> str:
    abp_used = {abp_e.abp_name for abp_e in abp_plan.abp_exits}
    abp_number = 1
    while f"Salida {abp_number}" in abp_used:
        abp_number += 1
    return f"Salida {abp_number}"


def abp__stair_name(abp_plan: abpFloorPlan) -> str:
    abp_used = {abp_s.abp_name for abp_s in abp_plan.abp_stairs}
    for abp_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if f"Escalera {abp_letter}" not in abp_used:
            return f"Escalera {abp_letter}"
    return f"Escalera {len(abp_plan.abp_stairs) + 1}"


def abp__distance(abp_p: abpPoint, abp_s: abpSegment) -> float:
    abp_dx, abp_dy = (
        abp_s.abp_end.abp_x - abp_s.abp_start.abp_x,
        abp_s.abp_end.abp_y - abp_s.abp_start.abp_y,
    )
    abp_t = (
        (abp_p.abp_x - abp_s.abp_start.abp_x) * abp_dx
        + (abp_p.abp_y - abp_s.abp_start.abp_y) * abp_dy
    ) / max(abp_dx * abp_dx + abp_dy * abp_dy, 1e-9)
    abp_t = min(max(abp_t, 0.0), 1.0)
    return math.hypot(
        abp_p.abp_x - abp_s.abp_start.abp_x - abp_t * abp_dx,
        abp_p.abp_y - abp_s.abp_start.abp_y - abp_t * abp_dy,
    )


def abp__contains(abp_polygon: abpPolygon, abp_p: abpPoint) -> bool:
    abp_inside = False
    abp_vertices = abp_polygon.abp_vertices
    for abp_a, abp_b in zip(abp_vertices, (*abp_vertices[1:], abp_vertices[0]), strict=True):
        if (abp_a.abp_y > abp_p.abp_y) != (abp_b.abp_y > abp_p.abp_y) and abp_p.abp_x < (
            abp_b.abp_x - abp_a.abp_x
        ) * (abp_p.abp_y - abp_a.abp_y) / (abp_b.abp_y - abp_a.abp_y) + abp_a.abp_x:
            abp_inside = not abp_inside
    return abp_inside
