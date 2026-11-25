from __future__ import annotations

import dataclasses
import math
from enum import Enum
from typing import Any

from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpWall

abp_NODE_TOLERANCE_PX = 0.75
abp_MIN_LENGTH_PX = 3.0
abp_PARALLEL_DEG = 3.0
abp_CROSSING_MIN_DEG = 20.0
abp_GAP_TO_CLOSE_M = 0.3
abp_DUPLICATE_M = 0.12
abp_GAP_TO_CLOSE_PX = 10.0
abp_DUPLICATE_PX = 4.0

abp__FIELDS = {
    abpElementType.abp_WALL: "abp_walls",
    abpElementType.abp_DOOR: "abp_doors",
    abpElementType.abp_EXIT: "abp_exits",
}


class abpSnapKind(Enum):
    abp_NODE = "nodo"
    abp_INTERSECTION = "cruce"
    abp_ON_WALL = "sobre_muro"


@dataclasses.dataclass(frozen=True)
class abpSnapTarget:
    abp_point: abpPoint
    abp_kind: abpSnapKind


@dataclasses.dataclass(frozen=True)
class abpCleanReport:
    abp_plan: abpFloorPlan
    abp_merged: int
    abp_joined: int
    abp_removed: int

    @property
    def abp_changed(self) -> bool:
        return bool(self.abp_merged or self.abp_joined or self.abp_removed)


def abp__vec(abp_seg: abpSegment) -> tuple[float, float]:
    return (
        abp_seg.abp_end.abp_x - abp_seg.abp_start.abp_x,
        abp_seg.abp_end.abp_y - abp_seg.abp_start.abp_y,
    )


def abp__angle_between(abp_a: abpSegment, abp_b: abpSegment) -> float:
    abp_ax, abp_ay = abp__vec(abp_a)
    abp_bx, abp_by = abp__vec(abp_b)
    abp_la, abp_lb = math.hypot(abp_ax, abp_ay), math.hypot(abp_bx, abp_by)
    if abp_la == 0 or abp_lb == 0:
        return 0.0
    return math.degrees(
        math.asin(min(1.0, abs(abp_ax * abp_by - abp_ay * abp_bx) / (abp_la * abp_lb)))
    )


def abp__param(abp_seg: abpSegment, abp_p: abpPoint) -> float:
    abp_dx, abp_dy = abp__vec(abp_seg)
    abp_length2 = abp_dx * abp_dx + abp_dy * abp_dy
    if abp_length2 == 0:
        return 0.0
    return (
        (abp_p.abp_x - abp_seg.abp_start.abp_x) * abp_dx
        + (abp_p.abp_y - abp_seg.abp_start.abp_y) * abp_dy
    ) / abp_length2


def abp__at(abp_seg: abpSegment, abp_t: float) -> abpPoint:
    abp_dx, abp_dy = abp__vec(abp_seg)
    return abpPoint(
        abp_seg.abp_start.abp_x + abp_t * abp_dx, abp_seg.abp_start.abp_y + abp_t * abp_dy
    )


def abp__project(abp_seg: abpSegment, abp_p: abpPoint) -> abpPoint:
    return abp__at(abp_seg, min(1.0, max(0.0, abp__param(abp_seg, abp_p))))


def abp__line_distance(abp_seg: abpSegment, abp_p: abpPoint) -> float:
    return abp_p.abp_distance_to(abp__at(abp_seg, abp__param(abp_seg, abp_p)))


def abp__intersection(abp_a: abpSegment, abp_b: abpSegment) -> abpPoint | None:
    abp_ax, abp_ay = abp__vec(abp_a)
    abp_bx, abp_by = abp__vec(abp_b)
    abp_den = abp_ax * abp_by - abp_ay * abp_bx
    if abs(abp_den) < 1e-9:
        return None
    abp_t = (
        (abp_b.abp_start.abp_x - abp_a.abp_start.abp_x) * abp_by
        - (abp_b.abp_start.abp_y - abp_a.abp_start.abp_y) * abp_bx
    ) / abp_den
    return abp__at(abp_a, abp_t)


def abp__segments(abp_plan: abpFloorPlan) -> list[tuple[abpElementType, int, abpSegment]]:
    abp_out: list[tuple[abpElementType, int, abpSegment]] = []
    for abp_kind, abp_field in abp__FIELDS.items():
        for abp_index, abp_element in enumerate(getattr(abp_plan, abp_field)):
            abp_out.append((abp_kind, abp_index, abp_element.abp_segment))
    return abp_out


def abp_plan_nodes(
    abp_plan: abpFloorPlan, abp_tolerance: float = abp_NODE_TOLERANCE_PX
) -> list[abpPoint]:
    abp_nodes: list[abpPoint] = []
    for _, _, abp_seg in abp__segments(abp_plan):
        for abp_p in (abp_seg.abp_start, abp_seg.abp_end):
            if all(abp_p.abp_distance_to(abp_n) > abp_tolerance for abp_n in abp_nodes):
                abp_nodes.append(abp_p)
    return abp_nodes


def abp_node_at(
    abp_plan: abpFloorPlan, abp_point: abpPoint, abp_tolerance: float
) -> abpPoint | None:
    abp_best: tuple[float, abpPoint] | None = None
    for abp_node in abp_plan_nodes(abp_plan):
        abp_d = abp_node.abp_distance_to(abp_point)
        if abp_d <= abp_tolerance and (abp_best is None or abp_d < abp_best[0]):
            abp_best = (abp_d, abp_node)
    return None if abp_best is None else abp_best[1]


def abp_connected_ends(
    abp_plan: abpFloorPlan, abp_node: abpPoint, abp_tolerance: float = abp_NODE_TOLERANCE_PX
) -> list[abpPoint]:
    abp_ends: list[abpPoint] = []
    for _, _, abp_seg in abp__segments(abp_plan):
        if abp_seg.abp_start.abp_distance_to(abp_node) <= abp_tolerance:
            abp_ends.append(abp_seg.abp_end)
        elif abp_seg.abp_end.abp_distance_to(abp_node) <= abp_tolerance:
            abp_ends.append(abp_seg.abp_start)
    return abp_ends


def abp_snap_point(
    abp_plan: abpFloorPlan,
    abp_point: abpPoint,
    abp_tolerance: float,
    *,
    abp_exclude: abpPoint | None = None,
) -> abpSnapTarget | None:
    def abp_excluded(abp_p: abpPoint) -> bool:
        return (
            abp_exclude is not None and abp_p.abp_distance_to(abp_exclude) <= abp_NODE_TOLERANCE_PX
        )

    abp_nodes = [abp_n for abp_n in abp_plan_nodes(abp_plan) if not abp_excluded(abp_n)]
    abp_near = [
        (abp_n.abp_distance_to(abp_point), abp_n)
        for abp_n in abp_nodes
        if abp_n.abp_distance_to(abp_point) <= abp_tolerance
    ]
    if abp_near:
        return abpSnapTarget(min(abp_near, key=lambda abp_x: abp_x[0])[1], abpSnapKind.abp_NODE)
    abp_walls = [
        abp_w.abp_segment
        for abp_w in abp_plan.abp_walls
        if abp_w.abp_segment.abp_length >= abp_MIN_LENGTH_PX
    ]
    abp_crossings: list[tuple[float, abpPoint]] = []
    for abp_i, abp_a in enumerate(abp_walls):
        for abp_b in abp_walls[abp_i + 1 :]:
            if abp__angle_between(abp_a, abp_b) < abp_CROSSING_MIN_DEG:
                continue
            abp_x = abp__intersection(abp_a, abp_b)
            if (
                abp_x is None
                or abp_x.abp_distance_to(abp_point) > abp_tolerance
                or abp_excluded(abp_x)
            ):
                continue
            if (
                -0.01 <= abp__param(abp_a, abp_x) <= 1.01
                and -0.01 <= abp__param(abp_b, abp_x) <= 1.01
            ):
                abp_crossings.append((abp_x.abp_distance_to(abp_point), abp_x))
    if abp_crossings:
        return abpSnapTarget(
            min(abp_crossings, key=lambda abp_x: abp_x[0])[1], abpSnapKind.abp_INTERSECTION
        )
    abp_on_wall: list[tuple[float, abpPoint]] = []
    for abp_seg in abp_walls:
        abp_q = abp__project(abp_seg, abp_point)
        if abp_q.abp_distance_to(abp_point) <= abp_tolerance and not abp_excluded(abp_q):
            abp_on_wall.append((abp_q.abp_distance_to(abp_point), abp_q))
    if abp_on_wall:
        return abpSnapTarget(
            min(abp_on_wall, key=lambda abp_x: abp_x[0])[1], abpSnapKind.abp_ON_WALL
        )
    return None


def abp_move_node(
    abp_plan: abpFloorPlan,
    abp_node: abpPoint,
    abp_to: abpPoint,
    abp_tolerance: float = abp_NODE_TOLERANCE_PX,
) -> abpFloorPlan:
    def abp_moved(abp_seg: abpSegment) -> abpSegment:
        abp_start = (
            abp_to
            if abp_seg.abp_start.abp_distance_to(abp_node) <= abp_tolerance
            else abp_seg.abp_start
        )
        abp_end = (
            abp_to
            if abp_seg.abp_end.abp_distance_to(abp_node) <= abp_tolerance
            else abp_seg.abp_end
        )
        return abpSegment(abp_start, abp_end)

    abp_changes: dict[str, Any] = {}
    for abp_field in abp__FIELDS.values():
        abp_elements = getattr(abp_plan, abp_field)
        abp_changes[abp_field] = tuple(
            dataclasses.replace(abp_el, abp_segment=abp_moved(abp_el.abp_segment))
            for abp_el in abp_elements
            if abp_moved(abp_el.abp_segment).abp_length >= abp_MIN_LENGTH_PX
        )
    return dataclasses.replace(abp_plan, **abp_changes)


def abp_set_length(
    abp_plan: abpFloorPlan, abp_kind: abpElementType, abp_index: int, abp_length_px: float
) -> abpFloorPlan:
    if abp_kind not in abp__FIELDS or abp_length_px < abp_MIN_LENGTH_PX:
        raise ValueError("Longitud no válida.")
    abp_seg = getattr(abp_plan, abp__FIELDS[abp_kind])[abp_index].abp_segment
    if abp_seg.abp_length == 0:
        raise ValueError("El elemento no tiene dirección.")
    abp_dx, abp_dy = abp__vec(abp_seg)
    abp_factor = abp_length_px / abp_seg.abp_length
    abp_new_end = abpPoint(
        abp_seg.abp_start.abp_x + abp_dx * abp_factor, abp_seg.abp_start.abp_y + abp_dy * abp_factor
    )
    return abp_move_node(abp_plan, abp_seg.abp_end, abp_new_end)


def abp__merge_duplicates(abp_walls: list[abpWall], abp_dup_px: float) -> tuple[list[abpWall], int]:
    abp_merged = 0
    abp_changed = True
    while abp_changed:
        abp_changed = False
        for abp_i in range(len(abp_walls)):
            abp_a = abp_walls[abp_i].abp_segment
            if abp_a.abp_length < abp_MIN_LENGTH_PX:
                continue
            for abp_j in range(abp_i + 1, len(abp_walls)):
                abp_b = abp_walls[abp_j].abp_segment
                if abp__angle_between(abp_a, abp_b) > abp_PARALLEL_DEG:
                    continue
                if (
                    abp__line_distance(abp_a, abp_b.abp_start) > abp_dup_px
                    or abp__line_distance(abp_a, abp_b.abp_end) > abp_dup_px
                ):
                    continue
                abp_t = sorted(
                    (abp__param(abp_a, abp_b.abp_start), abp__param(abp_a, abp_b.abp_end))
                )
                abp_gap = max(abp_t[0] - 1.0, 0.0 - abp_t[1], 0.0) * abp_a.abp_length
                if abp_gap > abp_dup_px:
                    continue
                abp_base = abp_a if abp_a.abp_length >= abp_b.abp_length else abp_b
                abp_ts = [
                    abp__param(abp_base, abp_p)
                    for abp_p in (abp_a.abp_start, abp_a.abp_end, abp_b.abp_start, abp_b.abp_end)
                ]
                abp_union = abpSegment(
                    abp__at(abp_base, min(abp_ts)), abp__at(abp_base, max(abp_ts))
                )
                abp_confidence = max(
                    abp_walls[abp_i].abp_confidence, abp_walls[abp_j].abp_confidence
                )
                abp_walls[abp_i] = abpWall(abp_union, abp_confidence)
                del abp_walls[abp_j]
                abp_merged += 1
                abp_changed = True
                break
            if abp_changed:
                break
    return abp_walls, abp_merged


def abp__is_attached(
    abp_p: abpPoint, abp_own: int, abp_segments: list[abpSegment], abp_openings: list[abpSegment]
) -> bool:
    for abp_k, abp_seg in enumerate(abp_segments):
        if abp_k == abp_own:
            continue
        if (
            abp_p.abp_distance_to(abp_seg.abp_start) <= 1.0
            or abp_p.abp_distance_to(abp_seg.abp_end) <= 1.0
        ):
            return True
        if abp__project(abp_seg, abp_p).abp_distance_to(abp_p) <= 1.0:
            return True
    return any(
        abp_p.abp_distance_to(abp_o.abp_start) <= 1.0 or abp_p.abp_distance_to(abp_o.abp_end) <= 1.0
        for abp_o in abp_openings
    )


def abp_clean_plan(
    abp_plan: abpFloorPlan, *, abp_gap_px: float | None = None, abp_dup_px: float | None = None
) -> abpCleanReport:
    abp_scale = abp_plan.abp_scale_m_per_px
    abp_gap = (
        abp_gap_px
        if abp_gap_px is not None
        else (abp_GAP_TO_CLOSE_M / abp_scale if abp_scale else abp_GAP_TO_CLOSE_PX)
    )
    abp_dup = (
        abp_dup_px
        if abp_dup_px is not None
        else (abp_DUPLICATE_M / abp_scale if abp_scale else abp_DUPLICATE_PX)
    )
    abp_walls, abp_merged = abp__merge_duplicates(list(abp_plan.abp_walls), abp_dup)
    abp_openings = [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]

    abp_joined = 0
    for abp_i in range(len(abp_walls)):
        for abp_end in ("abp_start", "abp_end"):
            abp_segments = [abp_w.abp_segment for abp_w in abp_walls]
            abp_seg = abp_segments[abp_i]
            abp_p: abpPoint = getattr(abp_seg, abp_end)
            if abp_seg.abp_length < abp_MIN_LENGTH_PX or abp__is_attached(
                abp_p, abp_i, abp_segments, abp_openings
            ):
                continue
            abp_best: tuple[float, abpPoint, int | None] | None = None
            for abp_k, abp_other in enumerate(abp_segments):
                if abp_k == abp_i or abp_other.abp_length < abp_MIN_LENGTH_PX:
                    continue
                if abp__angle_between(abp_seg, abp_other) >= abp_CROSSING_MIN_DEG:
                    abp_x = abp__intersection(abp_seg, abp_other)
                    if abp_x is not None and abp_x.abp_distance_to(abp_p) <= abp_gap:
                        abp_margin = abp_gap / abp_other.abp_length
                        abp_inside = -abp_margin <= abp__param(abp_other, abp_x) <= 1 + abp_margin
                        if abp_inside and (
                            abp_best is None or abp_x.abp_distance_to(abp_p) < abp_best[0]
                        ):
                            abp_best = (abp_x.abp_distance_to(abp_p), abp_x, abp_k)
                for abp_q in (abp_other.abp_start, abp_other.abp_end):
                    if abp_q.abp_distance_to(abp_p) <= abp_gap and (
                        abp_best is None or abp_q.abp_distance_to(abp_p) < abp_best[0]
                    ):
                        abp_best = (abp_q.abp_distance_to(abp_p), abp_q, None)
            if abp_best is None:
                continue
            _, abp_target, abp_crossing = abp_best
            abp_walls[abp_i] = dataclasses.replace(
                abp_walls[abp_i],
                abp_segment=abpSegment(abp_target, abp_seg.abp_end)
                if abp_end == "abp_start"
                else abpSegment(abp_seg.abp_start, abp_target),
            )
            if abp_crossing is not None:
                abp_other = abp_walls[abp_crossing].abp_segment
                abp_near_start = abp_other.abp_start.abp_distance_to(
                    abp_target
                ) <= abp_other.abp_end.abp_distance_to(abp_target)
                abp_q = abp_other.abp_start if abp_near_start else abp_other.abp_end
                if abp_q.abp_distance_to(abp_target) <= abp_gap and not abp__is_attached(
                    abp_q, abp_crossing, [abp_w.abp_segment for abp_w in abp_walls], abp_openings
                ):
                    abp_walls[abp_crossing] = dataclasses.replace(
                        abp_walls[abp_crossing],
                        abp_segment=abpSegment(abp_target, abp_other.abp_end)
                        if abp_near_start
                        else abpSegment(abp_other.abp_start, abp_target),
                    )
            abp_joined += 1

    abp_kept = [abp_w for abp_w in abp_walls if abp_w.abp_segment.abp_length >= abp_MIN_LENGTH_PX]
    abp_removed = len(abp_walls) - len(abp_kept)
    return abpCleanReport(
        dataclasses.replace(abp_plan, abp_walls=tuple(abp_kept)),
        abp_merged,
        abp_joined,
        abp_removed,
    )
