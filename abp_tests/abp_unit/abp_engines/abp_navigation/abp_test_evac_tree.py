from __future__ import annotations

import dataclasses
import itertools
import math

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_enums import abpSignKind, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpRoom, abpSafeZone, abpStair
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork
from abp_rutasegura.abp_engines.abp_navigation.abp_evac_tree import (
    abp_evacuation_network,
    abp_evacuation_time,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_polygon_to_m, abp_segment_to_m
from abp_rutasegura.abp_engines.abp_navigation.abp_sign_proposals import abp_propose_signs
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp_rect,
    abp_SCALE,
    abp_single_room,
    abp_two_rooms,
)


def abp__rooms(abp_plan: abpFloorPlan) -> list[abpRoomArea]:
    assert abp_plan.abp_scale_m_per_px is not None
    return [
        abpRoomArea(
            abp_r.abp_name,
            abp_plan.abp_level,
            abp_polygon_to_m(abp_r.abp_area, abp_plan.abp_scale_m_per_px),
        )
        for abp_r in abp_plan.abp_rooms
    ]


def abp__crosses_walls(abp_plan: abpFloorPlan, abp_network: abpEvacuationNetwork) -> bool:
    abp_walls = [abp_segment_to_m(abp_w.abp_segment, abp_SCALE) for abp_w in abp_plan.abp_walls]

    def abp_side(abp_a: abpPoint, abp_b: abpPoint, abp_p: abpPoint) -> float:
        return (abp_b.abp_x - abp_a.abp_x) * (abp_p.abp_y - abp_a.abp_y) - (
            abp_b.abp_y - abp_a.abp_y
        ) * (abp_p.abp_x - abp_a.abp_x)

    for abp_branch in abp_network.abp_branches:
        for abp_a, abp_b in itertools.pairwise(abp_branch.abp_points_m):
            for abp_w in abp_walls:
                if (
                    abp_side(abp_a, abp_b, abp_w.abp_start) * abp_side(abp_a, abp_b, abp_w.abp_end)
                    < -1e-6
                    and abp_side(abp_w.abp_start, abp_w.abp_end, abp_a)
                    * abp_side(abp_w.abp_start, abp_w.abp_end, abp_b)
                    < -1e-6
                ):
                    return True
    return False


class abpTestTime:
    @pytest.mark.parametrize(
        ("abp_people", "abp_width", "abp_distance", "abp_expected"),
        [(32, 1.3, 54.82, 110.30), (1, 0.9, 22.30, 38.02)],
    )
    def abp_test_matches_reference_sheet(
        self, abp_people: int, abp_width: float, abp_distance: float, abp_expected: float
    ) -> None:
        assert abp_evacuation_time(abp_people, abp_width, abp_distance, 1.3, 0.6) == pytest.approx(
            abp_expected, abs=0.01
        )

    def abp_test_invalid(self) -> None:
        with pytest.raises(ValueError, match="positivos"):
            abp_evacuation_time(10, 0, 5, 1.3, 0.6)


class abpTestNetwork:
    def abp_test_single_room(self) -> None:
        abp_plan = abp_single_room()
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan))
        assert abp_network.abp_branches
        abp_escape = abp_network.abp_escapes[0]
        assert (abp_escape.abp_room_name, abp_escape.abp_target_name) == ("Aula 1", "Salida 1")
        assert abp_escape.abp_door_width_m == pytest.approx(1.2)
        assert 9.0 < abp_escape.abp_distance_m < 15.0
        assert abp_escape.abp_path_m[-1].abp_distance_to(abpPoint(10.0, 3.0)) < 1e-6
        assert any(abp_b.abp_target_name == "Salida 1" for abp_b in abp_network.abp_branches)
        assert not abp__crosses_walls(abp_plan, abp_network)

    def abp_test_branches_are_parallel_to_walls(self) -> None:
        abp_plan = abp_single_room(abp_width=12, abp_height=8)
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan))
        abp_long_ones = [
            (abp_a, abp_b)
            for abp_branch in abp_network.abp_branches
            for abp_a, abp_b in itertools.pairwise(abp_branch.abp_points_m)
            if abp_a.abp_distance_to(abp_b) > 1.5
        ]
        assert abp_long_ones
        for abp_a, abp_b in abp_long_ones:
            abp_angle = (
                math.degrees(math.atan2(abp_b.abp_y - abp_a.abp_y, abp_b.abp_x - abp_a.abp_x)) % 90
            )
            assert min(abp_angle, 90 - abp_angle) < 8

    def abp_test_goes_through_doors(self) -> None:
        abp_plan = abp_two_rooms()
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan))
        abp_door = abp_segment_to_m(abp_plan.abp_doors[0].abp_segment, abp_SCALE)
        abp_escapes = {abp_e.abp_room_name: abp_e for abp_e in abp_network.abp_escapes}
        abp_far = max(abp_escapes.values(), key=lambda abp_e: abp_e.abp_distance_m)
        assert any(
            abp_p.abp_distance_to(abp_door.abp_midpoint) < 1e-6 for abp_p in abp_far.abp_path_m
        )
        assert abp_far.abp_door_width_m == pytest.approx(abp_door.abp_length, abs=0.01)
        assert not abp__crosses_walls(abp_plan, abp_network)

    def abp_test_blocked_exit_and_no_exit(self) -> None:
        abp_plan = abp_single_room(abp_second_exit=True)
        abp_network = abp_evacuation_network(
            abp_plan, abp__rooms(abp_plan), abp_blocked_exits=["Salida 1"]
        )
        assert {abp_e.abp_target_name for abp_e in abp_network.abp_escapes} == {"Salida 2"}
        abp_closed = abp_evacuation_network(
            abp_single_room(), abp__rooms(abp_plan), abp_blocked_exits=["Salida 1"]
        )
        assert abp_closed.abp_escapes == ()

    def abp_test_furniture_moves_the_route(self) -> None:
        abp_plan = abp_single_room(abp_width=10, abp_height=6)
        abp_desk = np.array([[2, 3, 8, 3], [2, 2.6, 8, 2.6], [2, 3.4, 8, 3.4], [2, 2.6, 2, 3.4]])
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan), abp_clutter_m=abp_desk)
        for abp_branch in abp_network.abp_branches:
            for abp_a, abp_b in itertools.pairwise(abp_branch.abp_points_m):
                for abp_t in np.linspace(0, 1, 20):
                    abp_x, abp_y = (
                        abp_a.abp_x + abp_t * (abp_b.abp_x - abp_a.abp_x),
                        abp_a.abp_y + abp_t * (abp_b.abp_y - abp_a.abp_y),
                    )
                    assert not (2.5 < abp_x < 7.5 and 2.7 < abp_y < 3.3)

    def abp_test_meeting_point_outside(self) -> None:
        abp_plan = dataclasses.replace(
            abp_single_room(), abp_safe_zones=(abpSafeZone(abp_rect(14, 2, 2, 2), "Patio"),)
        )
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan))
        abp_links = dict(abp_network.abp_meeting_links)
        assert abp_links["Salida 1"][0].abp_distance_to(abpPoint(10.0, 3.0)) < 1e-6
        assert abp_network.abp_escapes[0].abp_meeting_distance_m == pytest.approx(4.0, abs=0.5)

    def abp_test_upper_floor_goes_to_stairs(self) -> None:
        abp_plan = dataclasses.replace(
            abp_single_room(),
            abp_level=1,
            abp_stairs=(abpStair(abp_rect(7, 1, 2, 2), abp_name="Escalera A"),),
        )
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan), abp_upper_floor=True)
        assert abp_network.abp_escapes[0].abp_target_name == "Escalera A"
        assert abp_network.abp_meeting_links == ()

    def abp_test_reproducible(self) -> None:
        abp_plan = abp_two_rooms()
        assert abp_evacuation_network(abp_plan, abp__rooms(abp_plan)) == abp_evacuation_network(
            abp_plan, abp__rooms(abp_plan)
        )

    def abp_test_unreachable_room_is_skipped(self) -> None:
        abp_plan = abp_single_room()
        abp_outside = abpRoom("Aparte", abpUseType.abp_EDUCATION, abp_rect(30, 30, 3, 3))
        abp_plan = dataclasses.replace(abp_plan, abp_rooms=(*abp_plan.abp_rooms, abp_outside))
        assert [
            abp_e.abp_room_name
            for abp_e in abp_evacuation_network(abp_plan, abp__rooms(abp_plan)).abp_escapes
        ] == ["Aula 1"]


class abpTestSigns:
    def abp_test_proposals(self) -> None:
        abp_plan = abp_two_rooms()
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan))
        abp_signs = abp_propose_signs(
            abp_plan, abp_network, {abp_r.abp_name: 20 for abp_r in abp_plan.abp_rooms}
        )
        abp_kinds = [abp_s.abp_kind for abp_s in abp_signs]
        assert abp_kinds.count(abpSignKind.abp_EXIT) == 1
        assert abp_kinds.count(abpSignKind.abp_CAPACITY) == 2
        assert {
            abp_s.abp_text for abp_s in abp_signs if abp_s.abp_kind is abpSignKind.abp_CAPACITY
        } == {"20"}
        abp_again = abp_propose_signs(
            dataclasses.replace(abp_plan, abp_signs=abp_signs), abp_network, {}
        )
        assert abp_again == ()
        assert abp_propose_signs(abpFloorPlan(), abp_network, {}) == ()

    def abp_test_stairs_sign(self) -> None:
        abp_plan = dataclasses.replace(
            abp_single_room(),
            abp_level=1,
            abp_stairs=(abpStair(abp_rect(7, 1, 2, 2), abp_name="Escalera A"),),
        )
        abp_network = abp_evacuation_network(abp_plan, abp__rooms(abp_plan), abp_upper_floor=True)
        assert abpSignKind.abp_STAIRS in [
            abp_s.abp_kind for abp_s in abp_propose_signs(abp_plan, abp_network, {})
        ]
