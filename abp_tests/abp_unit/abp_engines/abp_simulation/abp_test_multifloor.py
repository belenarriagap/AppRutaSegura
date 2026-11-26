from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpSafeZone, abpStair, abpWall
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid
from abp_rutasegura.abp_engines.abp_simulation.abp_metrics import abp_floor_clearance
from abp_rutasegura.abp_engines.abp_simulation.abp_multifloor import (
    abp_IN_STAIRS,
    abp_pair_stairs,
    abp_stair_width_m,
    abpMultiFloorError,
    abpMultiFloorSimulation,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_tests.abp_fixtures.abp_simple_plans import abp__seg, abp_rect, abp_two_floor_building
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_PROFILES

abp_PARAMS = abpSimulationParams()


def abp__sim(
    abp_occupancies: list[abpOccupancy], *, abp_seed: int = 3, **abp_kwargs: object
) -> abpMultiFloorSimulation:
    abp_ground, abp_upper = abp_two_floor_building(**abp_kwargs)
    return abpMultiFloorSimulation(
        [abp_upper, abp_ground], abp_occupancies, abp_PROFILES, abp_PARAMS, abp_seed=abp_seed
    )


class abpTestStairs:
    def abp_test_stairs_are_targets_only_on_upper_floors(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        assert abp_build_grid(abp_ground).abp_target_names == ("Salida 1",)
        abp_upper_grid = abp_build_grid(abp_upper, abp_stairs_as_targets=True)
        assert abp_upper_grid.abp_target_names == ("Escalera A",)
        assert abp_upper_grid.abp_stair_of(0) == 0
        assert abp_build_grid(abp_ground, abp_stairs_as_targets=False).abp_stair_of(0) == -1

    def abp_test_pairing_by_name_and_single_fallback(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        assert abp_pair_stairs(abp_upper, abp_ground) == {0: 0}
        abp_renamed = dataclasses.replace(
            abp_ground, abp_stairs=(dataclasses.replace(abp_ground.abp_stairs[0], abp_name="Otra"),)
        )
        assert abp_pair_stairs(abp_upper, abp_renamed) == {0: 0}
        abp_two_below = dataclasses.replace(
            abp_ground,
            abp_stairs=(
                abpStair(abp_rect(0.5, 0.5, 1.2, 2), abp_name="Norte"),
                abpStair(abp_rect(7, 0.5, 1.2, 2), abp_name="Sur"),
            ),
        )
        with pytest.raises(abpMultiFloorError, match="no tiene una escalera correspondiente"):
            abp_pair_stairs(abp_upper, abp_two_below)

    def abp_test_stair_width(self) -> None:
        abp_ground, _ = abp_two_floor_building(abp_stair_width=1.5)
        assert abp_stair_width_m(abp_ground, 0) == pytest.approx(1.5, abs=0.01)


class abpTestEvacuation:
    def abp_test_upper_floor_goes_down_and_everyone_leaves(self) -> None:
        abp_sim = abp__sim(
            [abpOccupancy("Aula 201", "adulto", 20, abp_level=1), abpOccupancy("Hall", "niño", 10)]
        )
        abp_out = abp_sim.abp_run()
        abp_result = abp_out.abp_result
        assert abp_result.abp_completed
        assert abp_result.abp_agents_evacuated == 30
        assert abp_result.abp_time_per_exit_s[0][0] == "Salida 1"
        abp_levels = abp_out.abp_trajectories.abp_level
        assert abp_levels is not None
        assert {int(abp_v) for abp_v in np.unique(abp_levels)} == {abp_IN_STAIRS, 0, 1}
        assert [abp_m.abp_level for abp_m in abp_result.abp_floor_maps] == [0, 1]
        assert abp_result.abp_curve_evacuated[-1] == 30

    def abp_test_agents_stay_inside_walls_on_every_floor(self) -> None:
        abp_sim = abp__sim([abpOccupancy("Aula 201", "adulto", 25, abp_level=1)])
        while not abp_sim.abp_finished:
            abp_sim.abp_step()
            for abp_level, abp_floor in abp_sim.abp_sims.items():
                abp_here = (abp_sim.abp_level == abp_level) & (
                    abp_floor.abp_agents.abp_status != abpAgentStatus.abp_EVACUATED
                )
                abp_r, abp_c = abp_floor.abp_grid.abp_to_cell(
                    abp_floor.abp_agents.abp_position[abp_here]
                )
                assert abp_floor.abp_grid.abp_walkable[abp_r, abp_c].all()
        assert abp_sim.abp_evacuated == 25

    def abp_test_upper_floor_takes_longer_than_ground(self) -> None:
        abp_ground_only = abp__sim([abpOccupancy("Hall", "adulto", 15)]).abp_run().abp_result
        abp_upstairs = (
            abp__sim([abpOccupancy("Aula 201", "adulto", 15, abp_level=1)]).abp_run().abp_result
        )
        abp_travel = abp_PARAMS.abp_stair_travel_m / (1.3 * 1.3 * abp_PARAMS.abp_stair_speed_factor)
        assert abp_upstairs.abp_total_time_s > abp_ground_only.abp_total_time_s + abp_travel * 0.5

    def abp_test_narrow_stair_limits_the_flow(self) -> None:
        abp_people = [abpOccupancy("Aula 201", "adulto", 60, abp_level=1)]
        abp_wide = abp__sim(abp_people, abp_stair_width=2.0).abp_run().abp_result
        abp_narrow = abp__sim(abp_people, abp_stair_width=0.6).abp_run().abp_result
        assert abp_narrow.abp_total_time_s > abp_wide.abp_total_time_s
        assert abp_narrow.abp_total_time_s >= 60 / (abp_PARAMS.abp_stair_specific_flow * 0.6)

    def abp_test_reproducible(self) -> None:
        abp_people = [
            abpOccupancy("Aula 201", "adulto", 20, abp_level=1),
            abpOccupancy("Hall", "niño", 5),
        ]
        abp_a, abp_b = (
            abp__sim(abp_people, abp_seed=9).abp_run(),
            abp__sim(abp_people, abp_seed=9).abp_run(),
        )
        assert abp_a.abp_result.abp_total_time_s == abp_b.abp_result.abp_total_time_s
        assert (
            abp_a.abp_trajectories.abp_positions.tobytes()
            == abp_b.abp_trajectories.abp_positions.tobytes()
        )
        assert abp_a.abp_trajectories.abp_level is not None
        assert abp_b.abp_trajectories.abp_level is not None
        assert (
            abp_a.abp_trajectories.abp_level.tobytes() == abp_b.abp_trajectories.abp_level.tobytes()
        )

    def abp_test_bottlenecks_carry_their_floor(self) -> None:
        abp_params = dataclasses.replace(abp_PARAMS, abp_congestion_min_duration_s=2.0)
        abp_ground, abp_upper = abp_two_floor_building(abp_stair_width=0.6)
        abp_sim = abpMultiFloorSimulation(
            [abp_ground, abp_upper],
            [abpOccupancy("Aula 201", "adulto", 80, abp_level=1)],
            abp_PROFILES,
            abp_params,
            abp_seed=1,
        )
        abp_result = abp_sim.abp_run().abp_result
        assert abp_result.abp_bottlenecks
        assert {abp_b.abp_level for abp_b in abp_result.abp_bottlenecks} <= {0, 1}
        assert any(abp_b.abp_level == 1 for abp_b in abp_result.abp_bottlenecks)


class abpTestErrors:
    def abp_test_lower_floor_without_stair(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        abp_no_stair = dataclasses.replace(abp_ground, abp_stairs=())
        with pytest.raises(abpMultiFloorError, match="no tiene una escalera correspondiente"):
            abpMultiFloorSimulation(
                [abp_no_stair, abp_upper], [], abp_PROFILES, abp_PARAMS, abp_seed=1
            )

    def abp_test_upper_floor_without_stairs_or_exits(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        abp_trapped = dataclasses.replace(abp_upper, abp_stairs=())
        with pytest.raises(abpMultiFloorError, match=r"piso 2 tiene 3 persona.*ninguna escalera"):
            abpMultiFloorSimulation(
                [abp_ground, abp_trapped],
                [abpOccupancy("Aula 201", "adulto", 3, abp_level=1)],
                abp_PROFILES,
                abp_PARAMS,
                abp_seed=1,
            )

    def abp_test_floor_limits(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        with pytest.raises(abpMultiFloorError, match="consecutivos"):
            abpMultiFloorSimulation(
                [abp_ground, dataclasses.replace(abp_upper, abp_level=2)],
                [],
                abp_PROFILES,
                abp_PARAMS,
                abp_seed=1,
            )
        abp_floors = [dataclasses.replace(abp_upper, abp_level=abp_k) for abp_k in range(1, 5)] + [
            abp_ground
        ]
        with pytest.raises(abpMultiFloorError, match="hasta 4 pisos"):
            abpMultiFloorSimulation(abp_floors, [], abp_PROFILES, abp_PARAMS, abp_seed=1)
        with pytest.raises(abpMultiFloorError, match="escala"):
            abpMultiFloorSimulation(
                [abp_ground, dataclasses.replace(abp_upper, abp_scale_m_per_px=None)],
                [],
                abp_PROFILES,
                abp_PARAMS,
                abp_seed=1,
            )
        with pytest.raises(abpMultiFloorError, match="No hay pisos"):
            abpMultiFloorSimulation([], [], abp_PROFILES, abp_PARAMS, abp_seed=1)


class abpTestStairsOnly:
    def abp_test_upper_floor_exits_and_safe_zones_are_not_used(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        abp_tempting = dataclasses.replace(
            abp_upper,
            abp_exits=(abpExit(abp__seg(0, 2.4, 0, 3.6), "Ventana"),),
            abp_safe_zones=(abpSafeZone(abp_rect(1, 4, 2, 1.5), "Terraza"),),
        )
        abp_occupants = [abpOccupancy("Aula 201", "adulto", 12, abp_level=1)]
        abp_out = abpMultiFloorSimulation(
            [abp_ground, abp_tempting], abp_occupants, abp_PROFILES, abp_PARAMS, abp_seed=3
        ).abp_run()
        assert abp_out.abp_result.abp_completed
        assert {abp_name for abp_name, _ in abp_out.abp_result.abp_time_per_exit_s} <= {
            abp_e.abp_name for abp_e in abp_ground.abp_exits
        } | {abp_z.abp_name for abp_z in abp_ground.abp_safe_zones}
        abp_levels = abp_out.abp_trajectories.abp_level
        assert abp_levels is not None
        assert (abp_levels[:, :] <= 0).any(axis=0).all()

    def abp_test_floor_clearance(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        abp_occupants = [
            abpOccupancy("Hall", "adulto", 10, abp_level=0),
            abpOccupancy("Aula 201", "adulto", 8, abp_level=1),
        ]
        abp_out = abpMultiFloorSimulation(
            [abp_ground, abp_upper], abp_occupants, abp_PROFILES, abp_PARAMS, abp_seed=2
        ).abp_run()
        abp_first, abp_second = abp_floor_clearance(abp_out.abp_trajectories)
        assert (abp_first.abp_level, abp_first.abp_people, abp_first.abp_descended) == (0, 10, 10)
        assert (abp_second.abp_level, abp_second.abp_people, abp_second.abp_descended) == (1, 8, 8)
        assert abp_second.abp_cleared_s is not None
        assert abp_first.abp_cleared_s is not None
        assert abp_second.abp_cleared_s < abp_first.abp_cleared_s
        assert abp_first.abp_cleared_s == pytest.approx(
            abp_out.abp_result.abp_total_time_s, abs=1.0
        )

    def abp_test_unreachable_lower_stair(self) -> None:
        abp_ground, abp_upper = abp_two_floor_building()
        abp_box = abp_ground.abp_stairs[0].abp_area.abp_vertices
        abp_xs = [abp_v.abp_x for abp_v in abp_box]
        abp_ys = [abp_v.abp_y for abp_v in abp_box]
        abp_walls = tuple(
            abpWall(abpSegment(abpPoint(abp_a, abp_b), abpPoint(abp_c, abp_d)))
            for abp_a, abp_b, abp_c, abp_d in (
                (min(abp_xs) - 10, min(abp_ys) - 10, max(abp_xs) + 10, min(abp_ys) - 10),
                (max(abp_xs) + 10, min(abp_ys) - 10, max(abp_xs) + 10, max(abp_ys) + 10),
                (max(abp_xs) + 10, max(abp_ys) + 10, min(abp_xs) - 10, max(abp_ys) + 10),
                (min(abp_xs) - 10, max(abp_ys) + 10, min(abp_xs) - 10, min(abp_ys) - 10),
            )
        )
        abp_closed = dataclasses.replace(abp_ground, abp_walls=(*abp_ground.abp_walls, *abp_walls))
        with pytest.raises(abpMultiFloorError, match="no se llega a una salida"):
            abpMultiFloorSimulation(
                [abp_closed, abp_upper],
                [abpOccupancy("Aula 201", "adulto", 2, abp_level=1)],
                abp_PROFILES,
                abp_PARAMS,
                abp_seed=1,
            )
