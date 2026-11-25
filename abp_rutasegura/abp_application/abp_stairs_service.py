from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpStair
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid
from abp_rutasegura.abp_engines.abp_navigation.abp_stairs import (
    abp_edge_index,
    abp_edges,
    abp_stair_role,
    abpStairRole,
)

abp_SIDES: tuple[str, ...] = ("izquierda", "derecha", "arriba", "abajo")
abp__DIRECTIONS = {
    "izquierda": (-1.0, 0.0),
    "derecha": (1.0, 0.0),
    "arriba": (0.0, -1.0),
    "abajo": (0.0, 1.0),
}


def abp_stair_roles(abp_plan: abpFloorPlan, *, abp_upper_floor: bool) -> list[str]:
    abp_closed: set[int] = set()
    if abp_plan.abp_is_scaled and abp_plan.abp_walls and not abp_upper_floor:
        try:
            abp_closed = set(abp_build_grid(abp_plan).abp_closed_stairs)
        except ValueError:
            abp_closed = set(range(len(abp_plan.abp_stairs)))
    abp_out: list[str] = []
    for abp_index, abp_stair in enumerate(abp_plan.abp_stairs):
        abp_role = abp_stair_role(abp_stair, abp_upper_floor=abp_upper_floor)
        if not abp_stair.abp_confirmed:
            abp_out.append("pendiente")
        elif abp_role is not None:
            abp_out.append(abp_role.value)
        else:
            abp_out.append(
                (
                    abpStairRole.abp_CLOSED if abp_index in abp_closed else abpStairRole.abp_PASS
                ).value
            )
    return abp_out


def abp_entry_side(abp_stair: abpStair) -> str:
    if abp_stair.abp_entry is None:
        return ""
    abp_normal = abp__outward(abp_stair, abp_edge_index(abp_stair.abp_area, abp_stair.abp_entry))
    return max(abp_SIDES, key=lambda abp_s: abp__dot(abp_normal, abp__DIRECTIONS[abp_s]))


def abp_with_entry_side(abp_stair: abpStair, abp_side: str) -> abpStair:
    if abp_side not in abp__DIRECTIONS:
        return dataclasses.replace(abp_stair, abp_entry=None)
    abp_sides = abp_edges(abp_stair.abp_area)
    abp_best = max(
        range(len(abp_sides)),
        key=lambda abp_k: (
            round(abp__dot(abp__outward(abp_stair, abp_k), abp__DIRECTIONS[abp_side]), 3),
            abp_sides[abp_k][0].abp_distance_to(abp_sides[abp_k][1]),
        ),
    )
    abp_a, abp_b = abp_sides[abp_best]
    return dataclasses.replace(
        abp_stair,
        abp_entry=abpPoint((abp_a.abp_x + abp_b.abp_x) / 2, (abp_a.abp_y + abp_b.abp_y) / 2),
    )


def abp_entry_arrow(abp_stair: abpStair) -> tuple[abpPoint, abpPoint] | None:
    if abp_stair.abp_entry is None:
        return None
    abp_a, abp_b = abp_edges(abp_stair.abp_area)[
        abp_edge_index(abp_stair.abp_area, abp_stair.abp_entry)
    ]
    abp_middle = abpPoint((abp_a.abp_x + abp_b.abp_x) / 2, (abp_a.abp_y + abp_b.abp_y) / 2)
    abp_center = abp_stair.abp_area.abp_centroid
    return abp_middle, abpPoint(
        (abp_middle.abp_x + abp_center.abp_x) / 2, (abp_middle.abp_y + abp_center.abp_y) / 2
    )


def abp_names_below(abp_floors: Sequence[abpFloorPlan], abp_level: int) -> list[str]:
    abp_below = next((abp_f for abp_f in abp_floors if abp_f.abp_level == abp_level - 1), None)
    if abp_below is None:
        return []
    abp_skip = (abpStairUse.abp_SAME_FLOOR, abpStairUse.abp_OUTSIDE, abpStairUse.abp_CLOSED)
    return [
        abp_s.abp_name
        for abp_s in abp_below.abp_stairs
        if abp_s.abp_name and abp_s.abp_confirmed and abp_s.abp_use not in abp_skip
    ]


def abp__outward(abp_stair: abpStair, abp_index: int) -> tuple[float, float]:
    abp_a, abp_b = abp_edges(abp_stair.abp_area)[abp_index]
    abp_center = abp_stair.abp_area.abp_centroid
    abp_nx, abp_ny = -(abp_b.abp_y - abp_a.abp_y), abp_b.abp_x - abp_a.abp_x
    abp_middle = ((abp_a.abp_x + abp_b.abp_x) / 2, (abp_a.abp_y + abp_b.abp_y) / 2)
    if (
        abp_nx * (abp_middle[0] - abp_center.abp_x) + abp_ny * (abp_middle[1] - abp_center.abp_y)
        < 0
    ):
        abp_nx, abp_ny = -abp_nx, -abp_ny
    abp_length = math.hypot(abp_nx, abp_ny) or 1.0
    return abp_nx / abp_length, abp_ny / abp_length


def abp__dot(abp_a: tuple[float, float], abp_b: tuple[float, float]) -> float:
    return abp_a[0] * abp_b[0] + abp_a[1] * abp_b[1]
