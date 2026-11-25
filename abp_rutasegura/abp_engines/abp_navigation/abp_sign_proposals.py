from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence

from abp_rutasegura.abp_domain.abp_enums import abpSignKind
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSign
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork

abp_SIDE_M = 0.55
abp_APART_M = 2.5
abp_MIN_TURN_DEG = 30.0


def abp_propose_signs(
    abp_plan: abpFloorPlan, abp_network: abpEvacuationNetwork, abp_people: Mapping[str, int]
) -> tuple[abpSign, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None:
        return ()
    abp_found: list[abpSign] = []

    def abp_add(
        abp_kind: abpSignKind,
        abp_x: float,
        abp_y: float,
        abp_rotation: float = 0.0,
        abp_text: str = "",
    ) -> None:
        abp_position = abpPoint(abp_x / abp_scale, abp_y / abp_scale)
        abp_apart = abp_APART_M if abp_kind is abpSignKind.abp_DIRECTION else 1.0
        for abp_index, abp_other in enumerate((*abp_plan.abp_signs, *abp_found)):
            abp_away = abp_other.abp_position.abp_distance_to(abp_position) * abp_scale
            if abp_kind is abpSignKind.abp_CAPACITY and abp_index < len(abp_plan.abp_signs):
                abp_apart = 2.0
            if abp_other.abp_kind is abp_kind and abp_away < abp_apart:
                return
            if abp_kind is abpSignKind.abp_DIRECTION and abp_away < 0.9:
                return
        abp_found.append(abpSign(abp_kind, abp_position, abp_rotation, abp_text))

    abp_ends = {
        abp_b.abp_target_name: abp_b.abp_points_m
        for abp_b in abp_network.abp_branches
        if abp_b.abp_target_name
    }
    for abp_exit_ in abp_plan.abp_exits:
        abp_points = abp_ends.get(abp_exit_.abp_name)
        if abp_points is None or len(abp_points) < 2:
            continue
        abp_ux, abp_uy = abp__direction(abp_points[-2], abp_points[-1])
        abp_s, abp_e = abp_exit_.abp_segment.abp_start, abp_exit_.abp_segment.abp_end
        abp_half = abp_exit_.abp_segment.abp_length * abp_scale / 2
        abp_wx, abp_wy = abp__direction(abp_s, abp_e)
        abp_x, abp_y = abp_points[-1].abp_x - abp_ux * 0.1, abp_points[-1].abp_y - abp_uy * 0.1
        abp_side = abp__wall_side(abp_plan, abp_x, abp_y, abp_wx, abp_wy, abp_half + 0.75)
        abp_add(
            abpSignKind.abp_EXIT,
            abp_x + abp_side * abp_wx * (abp_half + 0.75),
            abp_y + abp_side * abp_wy * (abp_half + 0.75),
        )
    abp_stairs = {abp_st.abp_name for abp_st in abp_plan.abp_stairs if abp_st.abp_name}
    for abp_name, abp_points in abp_ends.items():
        if abp_name in abp_stairs and len(abp_points) >= 2:
            abp_ux, abp_uy = abp__direction(abp_points[-2], abp_points[-1])
            abp_add(
                abpSignKind.abp_STAIRS,
                abp_points[-1].abp_x - abp_ux * 0.6 - abp_uy * 0.7,
                abp_points[-1].abp_y - abp_uy * 0.6 + abp_ux * 0.7,
            )
    for abp_branch in sorted(abp_network.abp_branches, key=lambda abp_b: not abp_b.abp_trunk):
        for abp_a, abp_p, abp_b in zip(
            abp_branch.abp_points_m,
            abp_branch.abp_points_m[1:],
            abp_branch.abp_points_m[2:],
            strict=False,
        ):
            abp_u, abp_v = abp__direction(abp_a, abp_p), abp__direction(abp_p, abp_b)
            abp_turn = math.degrees(
                math.atan2(
                    abp_u[0] * abp_v[1] - abp_u[1] * abp_v[0],
                    abp_u[0] * abp_v[0] + abp_u[1] * abp_v[1],
                )
            )
            if abs(abp_turn) < abp_MIN_TURN_DEG:
                continue
            abp_nx, abp_ny = abp_u[0] - abp_v[0], abp_u[1] - abp_v[1]
            abp_size = math.hypot(abp_nx, abp_ny) or 1.0
            abp_angle = math.degrees(math.atan2(abp_v[1], abp_v[0]))
            abp_add(
                abpSignKind.abp_DIRECTION,
                abp_p.abp_x + abp_nx / abp_size * abp_SIDE_M,
                abp_p.abp_y + abp_ny / abp_size * abp_SIDE_M,
                round(abp_angle / 15) * 15.0 % 360,
            )
    abp_doors = [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]
    for abp_escape in abp_network.abp_escapes:
        abp_count = abp_people.get(abp_escape.abp_room_name, 0)
        if not abp_count or abp__has_capacity_sign(abp_plan, abp_escape.abp_room_name):
            continue
        for abp_before, abp_p in itertools.pairwise(abp_escape.abp_path_m):
            abp_door = next(
                (
                    abp_d
                    for abp_d in abp_doors
                    if math.hypot(
                        abp_d.abp_midpoint.abp_x * abp_scale - abp_p.abp_x,
                        abp_d.abp_midpoint.abp_y * abp_scale - abp_p.abp_y,
                    )
                    < 1e-6
                ),
                None,
            )
            if abp_door is None:
                continue
            abp_ux, abp_uy = abp__direction(abp_before, abp_p)
            abp_wx, abp_wy = abp__direction(abp_door.abp_start, abp_door.abp_end)
            abp_half = abp_door.abp_length * abp_scale / 2
            abp_x, abp_y = abp_p.abp_x - abp_ux * 0.1, abp_p.abp_y - abp_uy * 0.1
            abp_is_exit = any(abp_e.abp_segment is abp_door for abp_e in abp_plan.abp_exits)
            abp_side = abp__wall_side(
                abp_plan, abp_x, abp_y, abp_wx, abp_wy, abp_half + 0.5, abp_prefer=-1.0
            )
            abp_reach = abp_half + (0.5 if not abp_is_exit else 0.55)
            abp_taken = abpPoint(
                (abp_x + abp_side * abp_wx * abp_reach) / abp_scale,
                (abp_y + abp_side * abp_wy * abp_reach) / abp_scale,
            )
            if any(
                abp_s.abp_position.abp_distance_to(abp_taken) * abp_scale < 0.9
                for abp_s in (*abp_plan.abp_signs, *abp_found)
            ):
                abp_reach += 1.3
            abp_add(
                abpSignKind.abp_CAPACITY,
                abp_x + abp_side * abp_wx * abp_reach,
                abp_y + abp_side * abp_wy * abp_reach,
                abp_text=str(abp_count),
            )
            break
    return tuple(abp_found)


def abp__has_capacity_sign(abp_plan: abpFloorPlan, abp_room_name: str) -> bool:
    abp_room = next(
        (abp_r for abp_r in abp_plan.abp_rooms if abp_r.abp_name == abp_room_name), None
    )
    if abp_room is None:
        return False
    abp_xs, abp_ys = (
        [abp_v.abp_x for abp_v in abp_room.abp_area.abp_vertices],
        [abp_v.abp_y for abp_v in abp_room.abp_area.abp_vertices],
    )
    abp_pad = 0.5 / (abp_plan.abp_scale_m_per_px or 1.0)
    return any(
        abp_s.abp_kind is abpSignKind.abp_CAPACITY
        and min(abp_xs) - abp_pad <= abp_s.abp_position.abp_x <= max(abp_xs) + abp_pad
        and min(abp_ys) - abp_pad <= abp_s.abp_position.abp_y <= max(abp_ys) + abp_pad
        for abp_s in abp_plan.abp_signs
    )


def abp__wall_side(
    abp_plan: abpFloorPlan,
    abp_x: float,
    abp_y: float,
    abp_wx: float,
    abp_wy: float,
    abp_reach: float,
    abp_prefer: float = 1.0,
) -> float:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0

    def abp_gap(abp_side: float) -> float:
        abp_px, abp_py = (
            (abp_x + abp_side * abp_wx * abp_reach) / abp_scale,
            (abp_y + abp_side * abp_wy * abp_reach) / abp_scale,
        )
        abp_best = math.inf
        for abp_wall in abp_plan.abp_walls:
            abp_a, abp_b = abp_wall.abp_segment.abp_start, abp_wall.abp_segment.abp_end
            abp_dx, abp_dy = abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y
            abp_t = ((abp_px - abp_a.abp_x) * abp_dx + (abp_py - abp_a.abp_y) * abp_dy) / max(
                abp_dx * abp_dx + abp_dy * abp_dy, 1e-9
            )
            abp_t = min(max(abp_t, 0.0), 1.0)
            abp_best = min(
                abp_best,
                math.hypot(
                    abp_px - abp_a.abp_x - abp_t * abp_dx, abp_py - abp_a.abp_y - abp_t * abp_dy
                )
                * abp_scale,
            )
        return abp_best

    return abp_prefer if abp_gap(abp_prefer) <= abp_gap(-abp_prefer) + 0.15 else -abp_prefer


def abp__direction(abp_a: abpPoint, abp_b: abpPoint) -> tuple[float, float]:
    abp_length = math.hypot(abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y) or 1.0
    return (abp_b.abp_x - abp_a.abp_x) / abp_length, (abp_b.abp_y - abp_a.abp_y) / abp_length


def abp_sign_kinds(abp_signs: Sequence[abpSign]) -> tuple[abpSignKind, ...]:
    return tuple(dict.fromkeys(abp_s.abp_kind for abp_s in abp_signs))
