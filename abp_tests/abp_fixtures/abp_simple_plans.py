from __future__ import annotations

from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpRoom,
    abpSafeZone,
    abpWall,
)

abp_PX_PER_M = 50.0
abp_SCALE = 1.0 / abp_PX_PER_M


def abp__p(abp_x_m: float, abp_y_m: float) -> abpPoint:
    return abpPoint(abp_x_m * abp_PX_PER_M, abp_y_m * abp_PX_PER_M)


def abp__seg(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abp__p(abp_x1, abp_y1), abp__p(abp_x2, abp_y2))


def abp_rect(abp_x: float, abp_y: float, abp_w: float, abp_h: float) -> abpPolygon:
    return abpPolygon(
        (
            abp__p(abp_x, abp_y),
            abp__p(abp_x + abp_w, abp_y),
            abp__p(abp_x + abp_w, abp_y + abp_h),
            abp__p(abp_x, abp_y + abp_h),
        )
    )


def abp_single_room(
    abp_width: float = 10.0,
    abp_height: float = 6.0,
    abp_exit_width: float = 1.2,
    *,
    abp_second_exit: bool = False,
    abp_confirmed: bool = True,
) -> abpFloorPlan:
    abp_y0 = abp_height / 2 - abp_exit_width / 2
    abp_y1 = abp_height / 2 + abp_exit_width / 2
    abp_walls = [
        abp__seg(0, 0, abp_width, 0),
        abp__seg(0, abp_height, abp_width, abp_height),
        abp__seg(abp_width, 0, abp_width, abp_y0),
        abp__seg(abp_width, abp_y1, abp_width, abp_height),
    ]
    abp_exits = [abpExit(abp__seg(abp_width, abp_y0, abp_width, abp_y1), "Salida 1", abp_confirmed)]
    if abp_second_exit:
        abp_walls += [abp__seg(0, 0, 0, abp_y0), abp__seg(0, abp_y1, 0, abp_height)]
        abp_exits.append(abpExit(abp__seg(0, abp_y0, 0, abp_y1), "Salida 2", abp_confirmed))
    else:
        abp_walls.append(abp__seg(0, 0, 0, abp_height))
    return abpFloorPlan(
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=tuple(abpWall(abp_w) for abp_w in abp_walls),
        abp_exits=tuple(abp_exits),
        abp_rooms=(
            abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp_rect(0, 0, abp_width, abp_height)),
        ),
    )


def abp_two_rooms() -> abpFloorPlan:
    abp_walls = [
        abp__seg(0, 0, 12, 0),
        abp__seg(0, 6, 12, 6),
        abp__seg(0, 0, 0, 6),
        abp__seg(12, 0, 12, 2.4),
        abp__seg(12, 3.6, 12, 6),
        abp__seg(6, 0, 6, 2.55),
        abp__seg(6, 3.45, 6, 6),
    ]
    return abpFloorPlan(
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=tuple(abpWall(abp_w) for abp_w in abp_walls),
        abp_doors=(abpDoor(abp__seg(6, 2.55, 6, 3.45)),),
        abp_exits=(abpExit(abp__seg(12, 2.4, 12, 3.6), "Salida principal"),),
        abp_rooms=(
            abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp_rect(0, 0, 6, 6)),
            abpRoom("Aula 2", abpUseType.abp_EDUCATION, abp_rect(6, 0, 6, 6)),
        ),
    )


def abp_room_with_patio() -> abpFloorPlan:
    abp_plan = abp_single_room()
    abp_walls = [abp_w for abp_w in abp_plan.abp_walls] + [abpWall(abp__seg(10, 2.4, 10, 3.6))]
    return abpFloorPlan(
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=tuple(abp_walls),
        abp_safe_zones=(abpSafeZone(abp_rect(7, 1, 2, 2), "Patio"),),
        abp_rooms=abp_plan.abp_rooms,
    )


def abp_two_floor_building(
    abp_stair_name: str = "Escalera A", abp_stair_width: float = 1.2
) -> tuple[abpFloorPlan, abpFloorPlan]:
    from abp_rutasegura.abp_domain.abp_plan import abpStair

    abp_ground = abp_single_room()
    abp_stair = abpStair(abp_rect(0.5, 0.5, abp_stair_width, 2.0), abp_name=abp_stair_name)
    abp_ground = abpFloorPlan(
        abp_level=0,
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=abp_ground.abp_walls,
        abp_exits=abp_ground.abp_exits,
        abp_stairs=(abp_stair,),
        abp_rooms=(abpRoom("Hall", abpUseType.abp_EDUCATION, abp_rect(0, 0, 10, 6)),),
    )
    abp_closed = [
        abpWall(abp__seg(0, 0, 10, 0)),
        abpWall(abp__seg(0, 6, 10, 6)),
        abpWall(abp__seg(0, 0, 0, 6)),
        abpWall(abp__seg(10, 0, 10, 6)),
    ]
    abp_upper = abpFloorPlan(
        abp_level=1,
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=tuple(abp_closed),
        abp_stairs=(abp_stair,),
        abp_rooms=(abpRoom("Aula 201", abpUseType.abp_EDUCATION, abp_rect(0, 0, 10, 6)),),
    )
    return abp_ground, abp_upper
