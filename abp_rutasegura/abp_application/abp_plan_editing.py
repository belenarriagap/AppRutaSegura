from __future__ import annotations

import dataclasses
import math

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpWall

abp_SNAP_DISTANCE_M = 0.8
abp_SNAP_DISTANCE_PX = 30.0
abp_MAX_ANGLE_DEG = 25.0
abp_MIN_LENGTH_PX = 3.0


@dataclasses.dataclass(frozen=True)
class abpSnapResult:
    abp_opening: abpSegment
    abp_walls: tuple[abpWall, ...]
    abp_snapped: bool


def abp__angle(abp_seg: abpSegment) -> float:
    return math.atan2(
        abp_seg.abp_end.abp_y - abp_seg.abp_start.abp_y,
        abp_seg.abp_end.abp_x - abp_seg.abp_start.abp_x,
    )


def abp__angle_diff(abp_a: abpSegment, abp_b: abpSegment) -> float:
    abp_diff = abs(abp__angle(abp_a) - abp__angle(abp_b)) % math.pi
    return min(abp_diff, math.pi - abp_diff)


def abp__param(abp_wall: abpSegment, abp_p: abpPoint) -> float:
    abp_dx, abp_dy = (
        abp_wall.abp_end.abp_x - abp_wall.abp_start.abp_x,
        abp_wall.abp_end.abp_y - abp_wall.abp_start.abp_y,
    )
    abp_length2 = abp_dx * abp_dx + abp_dy * abp_dy
    if abp_length2 == 0:
        return 0.0
    return (
        (abp_p.abp_x - abp_wall.abp_start.abp_x) * abp_dx
        + (abp_p.abp_y - abp_wall.abp_start.abp_y) * abp_dy
    ) / abp_length2


def abp__at(abp_wall: abpSegment, abp_t: float) -> abpPoint:
    return abpPoint(
        abp_wall.abp_start.abp_x + abp_t * (abp_wall.abp_end.abp_x - abp_wall.abp_start.abp_x),
        abp_wall.abp_start.abp_y + abp_t * (abp_wall.abp_end.abp_y - abp_wall.abp_start.abp_y),
    )


def abp__distance_to_line(abp_wall: abpSegment, abp_p: abpPoint) -> float:
    abp_q = abp__at(abp_wall, abp__param(abp_wall, abp_p))
    return abp_p.abp_distance_to(abp_q)


def abp_snap_opening(abp_plan: abpFloorPlan, abp_drawn: abpSegment) -> abpSnapResult:
    abp_tolerance = (
        abp_SNAP_DISTANCE_M / abp_plan.abp_scale_m_per_px
        if abp_plan.abp_scale_m_per_px
        else abp_SNAP_DISTANCE_PX
    )
    abp_best: tuple[float, int, float, float] | None = None
    for abp_index, abp_wall in enumerate(abp_plan.abp_walls):
        abp_seg = abp_wall.abp_segment
        if abp_seg.abp_length < abp_MIN_LENGTH_PX or abp__angle_diff(
            abp_seg, abp_drawn
        ) > math.radians(abp_MAX_ANGLE_DEG):
            continue
        abp_t0 = abp__param(abp_seg, abp_drawn.abp_start)
        abp_t1 = abp__param(abp_seg, abp_drawn.abp_end)
        abp_lo, abp_hi = max(0.0, min(abp_t0, abp_t1)), min(1.0, max(abp_t0, abp_t1))
        if (abp_hi - abp_lo) * abp_seg.abp_length < abp_MIN_LENGTH_PX:
            continue
        abp_distance = abp__distance_to_line(abp_seg, abp_drawn.abp_midpoint)
        if abp_distance <= abp_tolerance and (abp_best is None or abp_distance < abp_best[0]):
            abp_best = (abp_distance, abp_index, abp_lo, abp_hi)
    if abp_best is None:
        return abpSnapResult(abp_drawn, abp_plan.abp_walls, abp_snapped=False)
    _, abp_index, abp_lo, abp_hi = abp_best
    abp_wall = abp_plan.abp_walls[abp_index]
    abp_seg = abp_wall.abp_segment
    abp_opening = abpSegment(abp__at(abp_seg, abp_lo), abp__at(abp_seg, abp_hi))
    abp_pieces = [
        abpWall(
            abpSegment(abp__at(abp_seg, abp_a), abp__at(abp_seg, abp_b)), abp_wall.abp_confidence
        )
        for abp_a, abp_b in ((0.0, abp_lo), (abp_hi, 1.0))
        if (abp_b - abp_a) * abp_seg.abp_length >= abp_MIN_LENGTH_PX
    ]
    abp_walls = (*abp_plan.abp_walls[:abp_index], *abp_pieces, *abp_plan.abp_walls[abp_index + 1 :])
    return abpSnapResult(abp_opening, abp_walls, abp_snapped=True)
