from __future__ import annotations

import dataclasses

import pytest

from abp_rutasegura.abp_application.abp_plan_editing import abp_snap_opening
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpWall
from abp_tests.abp_fixtures.abp_simple_plans import abp__seg, abp_single_room
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation


def abp__closed_room() -> abpFloorPlan:
    abp_base = abp_single_room()
    return dataclasses.replace(
        abp_base, abp_walls=(*abp_base.abp_walls, abpWall(abp__seg(10, 2.4, 10, 3.6))), abp_exits=()
    )


def abp_test_opening_is_moved_onto_the_wall_and_cuts_it() -> None:
    abp_plan = abpFloorPlan(abp_scale_m_per_px=0.02, abp_walls=(abpWall(abp__seg(0, 0, 10, 0)),))
    abp_drawn = abp__seg(3, 0.4, 4.2, 0.45)
    abp_snap = abp_snap_opening(abp_plan, abp_drawn)
    assert abp_snap.abp_snapped
    assert abp_snap.abp_opening.abp_start.abp_y == pytest.approx(0)
    assert abp_snap.abp_opening.abp_end.abp_y == pytest.approx(0)
    assert abp_snap.abp_opening.abp_length == pytest.approx(1.2 * 50, abs=1)
    assert [abp_w.abp_segment for abp_w in abp_snap.abp_walls] == [
        abpSegment(abpPoint(0, 0), abp_snap.abp_opening.abp_start),
        abpSegment(abp_snap.abp_opening.abp_end, abpPoint(500, 0)),
    ]


def abp_test_far_or_perpendicular_strokes_are_left_alone() -> None:
    abp_plan = abpFloorPlan(abp_scale_m_per_px=0.02, abp_walls=(abpWall(abp__seg(0, 0, 10, 0)),))
    abp_far = abp__seg(3, 2, 4, 2)
    assert not abp_snap_opening(abp_plan, abp_far).abp_snapped
    abp_across = abp__seg(3, -1, 3, 1)
    assert not abp_snap_opening(abp_plan, abp_across).abp_snapped
    assert abp_snap_opening(abp_plan, abp_far).abp_walls == abp_plan.abp_walls


def abp_test_opening_at_the_end_of_a_wall_keeps_one_piece() -> None:
    abp_plan = abpFloorPlan(abp_scale_m_per_px=0.02, abp_walls=(abpWall(abp__seg(0, 0, 10, 0)),))
    abp_snap = abp_snap_opening(abp_plan, abp__seg(9, 0.1, 11, 0.1))
    assert abp_snap.abp_opening.abp_end == abpPoint(500, 0)
    assert len(abp_snap.abp_walls) == 1


def abp_test_manually_drawn_exit_off_the_wall_now_works() -> None:
    abp_plan = abp__closed_room()
    abp_drawn = abp__seg(10.6, 2.4, 10.6, 3.6)
    abp_snap = abp_snap_opening(abp_plan, abp_drawn)
    assert abp_snap.abp_snapped
    abp_fixed = dataclasses.replace(
        abp_plan,
        abp_walls=abp_snap.abp_walls,
        abp_exits=(abpExit(abp_snap.abp_opening, "Salida 1"),),
    )
    abp_result = (
        abp_make_simulation(abp_fixed, [abpOccupancy("Aula 1", "adulto", 10)]).abp_run().abp_result
    )
    assert abp_result.abp_completed
