from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_enums import abpCellType
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpFloorPlan, abpWall
from abp_rutasegura.abp_engines.abp_navigation.abp_astar import abp_astar, abp_path_length
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import (
    abp_direction_field,
    abp_distance_field,
    abp_wall_distance,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid
from abp_rutasegura.abp_engines.abp_navigation.abp_rooms import abp_detect_rooms
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp__seg,
    abp_room_with_patio,
    abp_single_room,
    abp_two_rooms,
)


class abpTestGrid:
    def abp_test_room_is_enclosed_and_exit_is_target(self) -> None:
        abp_grid = abp_build_grid(abp_single_room())
        assert abp_grid.abp_target_names == ("Salida 1",)
        assert abp_grid.abp_targets.sum() >= 2
        abp_inside = abp_grid.abp_to_cell(np.array([[5.0, 3.0]]))
        assert abp_grid.abp_cells[abp_inside][0] == abpCellType.abp_FREE
        abp_outside = abp_grid.abp_to_cell(np.array([[-0.8, -0.8]]))
        assert abp_grid.abp_cells[abp_outside][0] == abpCellType.abp_OUTSIDE
        assert abp_grid.abp_cells[0, 0] == abpCellType.abp_OUTSIDE

    def abp_test_blocked_and_unconfirmed_exits_are_sealed(self) -> None:
        abp_blocked = abp_build_grid(abp_single_room(), abp_blocked_exits={"Salida 1"})
        assert abp_blocked.abp_target_names == ()
        assert not abp_blocked.abp_targets.any()
        abp_inside = abp_blocked.abp_to_cell(np.array([[5.0, 3.0]]))
        assert abp_blocked.abp_cells[abp_inside][0] == abpCellType.abp_FREE
        abp_unconfirmed = abp_build_grid(abp_single_room(abp_confirmed=False))
        assert not abp_unconfirmed.abp_targets.any()

    def abp_test_door_touching_an_exterior_wall_does_not_open_it(self) -> None:
        abp_base = abp_two_rooms()
        abp_door = abpDoor(abp__seg(6, -0.1, 6, 0.9))
        abp_walls = tuple(
            abp_w for abp_w in abp_base.abp_walls if abp_w.abp_segment != abp__seg(6, 0, 6, 2.55)
        )
        abp_plan = dataclasses.replace(
            abp_base,
            abp_walls=(*abp_walls, abpWall(abp__seg(6, 0.9, 6, 2.55))),
            abp_doors=(*abp_base.abp_doors, abp_door),
        )
        abp_grid = abp_build_grid(abp_plan)
        abp_inside = abp_grid.abp_to_cell(np.array([[3.0, 3.0], [6.0, 0.5]]))
        assert abp_grid.abp_cells[abp_inside][0] == abpCellType.abp_FREE
        assert abp_grid.abp_cells[abp_inside][1] == abpCellType.abp_DOOR
        abp_dist = abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )
        assert np.isfinite(abp_dist[abp_inside]).all()

    def abp_test_interior_safe_zone_is_a_target(self) -> None:
        abp_grid = abp_build_grid(abp_room_with_patio())
        assert abp_grid.abp_target_names == ("Patio",)
        abp_cell = abp_grid.abp_to_cell(np.array([[8.0, 2.0]]))
        assert abp_grid.abp_cells[abp_cell][0] == abpCellType.abp_SAFE_ZONE
        assert abp_grid.abp_target_ids[abp_cell][0] == 0

    def abp_test_requires_scale_and_content(self) -> None:
        with pytest.raises(ValueError, match="escala"):
            abp_build_grid(dataclasses.replace(abp_single_room(), abp_scale_m_per_px=None))
        with pytest.raises(ValueError, match="vacío"):
            abp_build_grid(abpFloorPlan(abp_scale_m_per_px=0.02))

    def abp_test_polygon_mask_and_cell_centers(self) -> None:
        abp_grid = abp_build_grid(abp_two_rooms())
        abp_room = abp_two_rooms().abp_rooms[0]
        from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_polygon_to_m

        abp_mask = abp_grid.abp_polygon_mask(abp_polygon_to_m(abp_room.abp_area, 0.02))
        abp_area = abp_mask.sum() * abp_grid.abp_cell_size**2
        assert abp_area == pytest.approx(36.0, rel=0.15)
        abp_r, abp_c = abp_grid.abp_to_cell(np.array([[1.0, 1.0]]))
        abp_center = abp_grid.abp_cell_centers(abp_r, abp_c)[0]
        assert abs(abp_center[0] - 1.0) <= abp_grid.abp_cell_size / 2 + 1e-9


class abpTestFields:
    def abp_test_distance_in_open_space(self) -> None:
        abp_walkable = np.ones((5, 10), bool)
        abp_targets = np.zeros((5, 10), bool)
        abp_targets[:, 9] = True
        abp_dist = abp_distance_field(abp_walkable, abp_targets, 0.4)
        assert abp_dist[2, 0] == pytest.approx(9 * 0.4)
        assert abp_dist[2, 9] == 0.0

    def abp_test_diagonal_cost_and_no_corner_cutting(self) -> None:
        abp_walkable = np.ones((3, 3), bool)
        abp_targets = np.zeros((3, 3), bool)
        abp_targets[0, 0] = True
        assert abp_distance_field(abp_walkable, abp_targets, 1.0)[1, 1] == pytest.approx(
            math.sqrt(2)
        )
        abp_walkable[0, 1] = False
        assert abp_distance_field(abp_walkable, abp_targets, 1.0)[1, 1] == pytest.approx(2.0)

    def abp_test_unreachable_is_infinite(self) -> None:
        abp_walkable = np.ones((3, 5), bool)
        abp_walkable[:, 2] = False
        abp_targets = np.zeros((3, 5), bool)
        abp_targets[1, 0] = True
        abp_dist = abp_distance_field(abp_walkable, abp_targets, 1.0)
        assert np.isinf(abp_dist[1, 4])

    def abp_test_directions_point_to_exit(self) -> None:
        abp_grid = abp_build_grid(abp_single_room())
        abp_dist = abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )
        abp_directions = abp_direction_field(abp_dist, abp_grid.abp_walkable)
        abp_r, abp_c = abp_grid.abp_to_cell(np.array([[2.0, 3.0]]))
        abp_dx, abp_dy = abp_directions[abp_r[0], abp_c[0]]
        assert abp_dx > 0.9
        assert abs(math.hypot(abp_dx, abp_dy) - 1.0) < 1e-6
        abp_inside = abp_grid.abp_walkable & ~abp_grid.abp_targets
        assert np.isfinite(abp_dist[abp_inside]).all()

    def abp_test_wall_distance(self) -> None:
        abp_walkable = np.ones((7, 7), bool)
        abp_walkable[:, 0] = False
        abp_dist, abp_grad = abp_wall_distance(abp_walkable, 0.4)
        assert abp_dist[3, 1] < abp_dist[3, 5]
        assert abp_grad[3, 3, 0] > 0.9


class abpTestAStar:
    def abp_test_matches_distance_field(self) -> None:
        abp_grid = abp_build_grid(abp_two_rooms())
        abp_dist = abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )
        abp_start = tuple(int(abp_v[0]) for abp_v in abp_grid.abp_to_cell(np.array([[1.0, 1.0]])))
        abp_goal_cells = np.argwhere(abp_grid.abp_targets)
        abp_goal = (int(abp_goal_cells[0][0]), int(abp_goal_cells[0][1]))
        abp_path = abp_astar(abp_grid.abp_walkable, (abp_start[0], abp_start[1]), abp_goal)
        assert abp_path is not None
        assert abp_path[0] == (abp_start[0], abp_start[1])
        assert abp_path[-1] == abp_goal
        assert (
            abp_path_length(abp_path, abp_grid.abp_cell_size)
            >= abp_dist[abp_start[0], abp_start[1]] - 1e-6
        )

    def abp_test_no_path_and_trivial_cases(self) -> None:
        abp_walkable = np.ones((3, 5), bool)
        abp_walkable[:, 2] = False
        assert abp_astar(abp_walkable, (1, 0), (1, 4)) is None
        assert abp_astar(abp_walkable, (1, 0), (1, 0)) == [(1, 0)]
        assert abp_astar(abp_walkable, (1, 2), (1, 0)) is None


class abpTestRooms:
    def abp_test_two_rooms_are_found(self) -> None:
        abp_plan = abp_two_rooms()
        abp_rooms = abp_detect_rooms(abp_plan)
        assert len(abp_rooms) == 2
        abp_areas = sorted(abp_plan.abp_area_m2(abp_r) for abp_r in abp_rooms)
        assert abp_areas[0] == pytest.approx(36.0, rel=0.1)
        assert abp_areas[1] == pytest.approx(36.0, rel=0.1)
        assert abp_rooms[0].abp_centroid.abp_x < abp_rooms[1].abp_centroid.abp_x

    def abp_test_requires_scale_and_handles_empty_plan(self) -> None:
        with pytest.raises(ValueError, match="escala"):
            abp_detect_rooms(abpFloorPlan())
        assert abp_detect_rooms(abpFloorPlan(abp_scale_m_per_px=0.02)) == []
