from __future__ import annotations

import pytest

from abp_rutasegura.abp_application.abp_nodes import (
    abp_clean_plan,
    abp_connected_ends,
    abp_move_node,
    abp_node_at,
    abp_plan_nodes,
    abp_set_length,
    abp_snap_point,
    abpSnapKind,
)
from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpExit, abpFloorPlan, abpWall
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpPopulationError
from abp_tests.abp_fixtures.abp_simple_plans import abp__seg, abp_single_room
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation


def abp__s(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


def abp__corner_plan() -> abpFloorPlan:
    return abpFloorPlan(
        abp_scale_m_per_px=0.02,
        abp_walls=(abpWall(abp__s(0, 0, 100, 0)), abpWall(abp__s(100, 0, 100, 80))),
        abp_doors=(abpDoor(abp__s(-40, 0, 0, 0)),),
    )


class abpTestNodes:
    def abp_test_nodes_are_shared_endpoints(self) -> None:
        abp_nodes = abp_plan_nodes(abp__corner_plan())
        assert abpPoint(100, 0) in abp_nodes
        assert len(abp_nodes) == 4
        assert abp_node_at(abp__corner_plan(), abpPoint(99, 1), 3) == abpPoint(100, 0)
        assert abp_node_at(abp__corner_plan(), abpPoint(50, 30), 3) is None
        assert sorted(
            abp_connected_ends(abp__corner_plan(), abpPoint(100, 0)), key=lambda abp_p: abp_p.abp_x
        ) == [
            abpPoint(0, 0),
            abpPoint(100, 80),
        ]

    def abp_test_moving_a_node_keeps_the_corner_closed(self) -> None:
        abp_moved = abp_move_node(abp__corner_plan(), abpPoint(100, 0), abpPoint(120, -5))
        assert abp_moved.abp_walls[0].abp_segment == abp__s(0, 0, 120, -5)
        assert abp_moved.abp_walls[1].abp_segment == abp__s(120, -5, 100, 80)
        abp_wider = abp_move_node(abp__corner_plan(), abpPoint(0, 0), abpPoint(10, 0))
        assert abp_wider.abp_doors[0].abp_segment == abp__s(-40, 0, 10, 0)
        assert abp_wider.abp_walls[0].abp_segment == abp__s(10, 0, 100, 0)

    def abp_test_collapsed_elements_disappear(self) -> None:
        abp_collapsed = abp_move_node(abp__corner_plan(), abpPoint(100, 80), abpPoint(100, 0))
        assert len(abp_collapsed.abp_walls) == 1

    def abp_test_set_exact_length(self) -> None:
        abp_plan = abp_set_length(abp__corner_plan(), abpElementType.abp_WALL, 0, 150)
        assert abp_plan.abp_walls[0].abp_segment == abp__s(0, 0, 150, 0)
        assert abp_plan.abp_walls[1].abp_segment.abp_start == abpPoint(150, 0)
        with pytest.raises(ValueError, match="Longitud"):
            abp_set_length(abp_plan, abpElementType.abp_WALL, 0, 0)


class abpTestSnap:
    def abp_test_preference_node_then_crossing_then_wall(self) -> None:
        abp_plan = abpFloorPlan(
            abp_walls=(abpWall(abp__s(0, 50, 200, 50)), abpWall(abp__s(100, 0, 100, 200)))
        )
        abp_node = abp_snap_point(abp_plan, abpPoint(2, 52), 5)
        assert abp_node is not None
        assert (abp_node.abp_kind, abp_node.abp_point) == (abpSnapKind.abp_NODE, abpPoint(0, 50))
        abp_cross = abp_snap_point(abp_plan, abpPoint(103, 48), 5)
        assert abp_cross is not None
        assert abp_cross.abp_kind is abpSnapKind.abp_INTERSECTION
        assert abp_cross.abp_point.abp_x == pytest.approx(100)
        assert abp_cross.abp_point.abp_y == pytest.approx(50)
        abp_on = abp_snap_point(abp_plan, abpPoint(150, 53), 5)
        assert abp_on is not None
        assert (abp_on.abp_kind, abp_on.abp_point) == (abpSnapKind.abp_ON_WALL, abpPoint(150, 50))
        assert abp_snap_point(abp_plan, abpPoint(150, 80), 5) is None

    def abp_test_a_moving_node_does_not_snap_to_itself(self) -> None:
        abp_plan = abp__corner_plan()
        abp_target = abp_snap_point(abp_plan, abpPoint(101, 1), 5, abp_exclude=abpPoint(100, 0))
        assert abp_target is None or abp_target.abp_point != abpPoint(100, 0)


class abpTestCleanPlan:
    def abp_test_merges_duplicates_but_not_walls_split_by_a_door(self) -> None:
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=0.02,
            abp_walls=(
                abpWall(abp__s(0, 0, 100, 0)),
                abpWall(abp__s(60, 1, 180, 1)),
                abpWall(abp__s(230, 0, 300, 0)),
            ),
            abp_doors=(abpDoor(abp__s(180, 0, 230, 0)),),
        )
        abp_report = abp_clean_plan(abp_plan)
        assert abp_report.abp_merged == 1
        assert len(abp_report.abp_plan.abp_walls) == 2
        abp_first = abp_report.abp_plan.abp_walls[0].abp_segment
        assert min(abp_first.abp_start.abp_x, abp_first.abp_end.abp_x) == pytest.approx(0, abs=1)
        assert max(abp_first.abp_start.abp_x, abp_first.abp_end.abp_x) == pytest.approx(180, abs=1)
        assert abp_report.abp_plan.abp_doors == abp_plan.abp_doors

    def abp_test_closes_open_corners_and_t_junctions(self) -> None:
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=0.02,
            abp_walls=(
                abpWall(abp__s(0, 0, 95, 0)),
                abpWall(abp__s(100, 6, 100, 100)),
                abpWall(abp__s(0, 100, 100, 100)),
                abpWall(abp__s(50, 100, 50, 108)),
                abpWall(abp__s(0, 0, 0, 100)),
                abpWall(abp__s(50, 5, 50, 60)),
            ),
        )
        abp_report = abp_clean_plan(abp_plan)
        assert abp_report.abp_joined >= 2
        abp_walls = [abp_w.abp_segment for abp_w in abp_report.abp_plan.abp_walls]
        assert abp__s(0, 0, 100, 0) in abp_walls
        assert any(abp_s.abp_start == abpPoint(100, 0) for abp_s in abp_walls)
        assert any(
            abp_s.abp_start.abp_x == pytest.approx(50) and abp_s.abp_start.abp_y == pytest.approx(0)
            for abp_s in abp_walls
        )

    def abp_test_wide_gaps_are_left_alone(self) -> None:
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=0.02,
            abp_walls=(abpWall(abp__s(0, 0, 60, 0)), abpWall(abp__s(100, 0, 200, 0))),
        )
        abp_report = abp_clean_plan(abp_plan)
        assert not abp_report.abp_changed
        assert abp_report.abp_plan == abp_plan

    def abp_test_cleaning_fixes_an_open_outline(self) -> None:
        abp_room = abp_single_room()
        abp_walls = list(abp_room.abp_walls)
        abp_walls[0] = abpWall(abp__seg(0.8, 0, 10, 0))
        abp_broken = abpFloorPlan(
            abp_scale_m_per_px=abp_room.abp_scale_m_per_px,
            abp_walls=tuple(abp_walls),
            abp_exits=abp_room.abp_exits,
            abp_rooms=abp_room.abp_rooms,
        )
        with pytest.raises(abpPopulationError, match="exterior"):
            abp_make_simulation(abp_broken, [abpOccupancy("Aula 1", "adulto", 5)])
        abp_fixed = abp_clean_plan(abp_broken, abp_gap_px=50).abp_plan
        assert (
            abp_make_simulation(abp_fixed, [abpOccupancy("Aula 1", "adulto", 5)])
            .abp_run()
            .abp_result.abp_completed
        )
        assert abp_fixed.abp_exits == (abpExit(abp_room.abp_exits[0].abp_segment, "Salida 1"),)
