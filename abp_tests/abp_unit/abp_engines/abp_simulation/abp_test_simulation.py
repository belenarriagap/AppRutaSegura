from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpObstacle
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid
from abp_rutasegura.abp_engines.abp_simulation.abp_engine import (
    abp_bilinear,
    abpSimulationCancelled,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_neighbors import abp_neighbor_pairs
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_rutasegura.abp_engines.abp_simulation.abp_population import (
    abp_lognormal_params,
    abp_sample_reaction_times,
    abpPopulationError,
)
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp_rect,
    abp_room_with_patio,
    abp_single_room,
    abp_two_rooms,
)
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import (
    abp_make_simulation,
    abp_PROFILES,
)


class abpTestPopulation:
    def abp_test_lognormal_matches_mean_and_std(self) -> None:
        abp_rng = np.random.default_rng(0)
        abp_samples = abp_sample_reaction_times(abp_rng, 30.0, 10.0, 200_000)
        assert abp_samples.mean() == pytest.approx(30.0, rel=0.02)
        assert abp_samples.std() == pytest.approx(10.0, rel=0.05)
        assert (abp_samples > 0).all()
        abp_mu, abp_sigma = abp_lognormal_params(30.0, 0.0)
        assert abp_sigma == 0.0
        assert math.exp(abp_mu) == pytest.approx(30.0)

    def abp_test_degenerate_reaction_times(self) -> None:
        abp_rng = np.random.default_rng(0)
        assert (abp_sample_reaction_times(abp_rng, 0.0, 5.0, 3) == 0).all()
        assert (abp_sample_reaction_times(abp_rng, 4.0, 0.0, 3) == 4.0).all()
        assert abp_sample_reaction_times(abp_rng, 4.0, 1.0, 0).size == 0

    def abp_test_agents_start_inside_their_room(self) -> None:
        abp_sim = abp_make_simulation(abp_two_rooms(), [abpOccupancy("Aula 1", "niño", 30)])
        assert len(abp_sim.abp_agents) == 30
        abp_xs = abp_sim.abp_agents.abp_position[:, 0]
        assert (abp_xs > 0).all()
        assert (abp_xs < 6).all()
        assert (abp_sim.abp_agents.abp_status == abpAgentStatus.abp_WAITING).all()
        assert (abp_sim.abp_agents.abp_radius == 0.2).all()

    def abp_test_population_errors(self) -> None:
        with pytest.raises(abpPopulationError, match="Aula 9"):
            abp_make_simulation(abp_single_room(), [abpOccupancy("Aula 9", "adulto", 1)])
        with pytest.raises(abpPopulationError, match="astronauta"):
            abp_make_simulation(abp_single_room(), [abpOccupancy("Aula 1", "astronauta", 1)])
        with pytest.raises(abpPopulationError, match="no pueden llegar a ninguna salida"):
            abp_make_simulation(
                abp_single_room(), [abpOccupancy("Aula 1", "adulto", 1)], abp_blocked={"Salida 1"}
            )
        abp_room = abp_single_room()
        abp_leaky = dataclasses.replace(abp_room, abp_walls=abp_room.abp_walls[1:])
        with pytest.raises(abpPopulationError, match="conectado con el exterior"):
            abp_make_simulation(abp_leaky, [abpOccupancy("Aula 1", "adulto", 1)])

    def abp_test_no_occupants(self) -> None:
        abp_sim = abp_make_simulation(abp_single_room(), [abpOccupancy("Aula 1", "adulto", 0)])
        abp_out = abp_sim.abp_run()
        assert abp_out.abp_result.abp_agents_total == 0
        assert abp_out.abp_result.abp_total_time_s == 0.0
        assert abp_out.abp_result.abp_completed


class abpTestNeighbors:
    def abp_test_pairs_match_brute_force(self) -> None:
        abp_rng = np.random.default_rng(3)
        abp_pos = abp_rng.uniform(0, 10, size=(300, 2))
        abp_cutoff = 1.0
        abp_i, abp_j = abp_neighbor_pairs(abp_pos, abp_cutoff)
        abp_found = {
            (int(abp_a), int(abp_b))
            for abp_a, abp_b in zip(abp_i, abp_j, strict=True)
            if np.linalg.norm(abp_pos[abp_a] - abp_pos[abp_b]) < abp_cutoff
        }
        abp_diff = abp_pos[:, None, :] - abp_pos[None, :, :]
        abp_close = np.argwhere(
            (np.linalg.norm(abp_diff, axis=2) < abp_cutoff) & ~np.eye(300, dtype=bool)
        )
        abp_expected = {(int(abp_a), int(abp_b)) for abp_a, abp_b in abp_close}
        assert abp_found == abp_expected

    def abp_test_trivial_inputs(self) -> None:
        abp_i, abp_j = abp_neighbor_pairs(np.zeros((1, 2)), 1.0)
        assert abp_i.size == 0
        assert abp_j.size == 0


class abpTestMovement:
    def abp_test_everyone_evacuates_single_room(self) -> None:
        abp_sim = abp_make_simulation(abp_single_room(), [abpOccupancy("Aula 1", "adulto", 20)])
        abp_progress: list[float] = []
        abp_out = abp_sim.abp_run(abp_progress=abp_progress.append)
        abp_result = abp_out.abp_result
        assert abp_result.abp_completed
        assert abp_result.abp_agents_evacuated == 20
        assert abp_progress[-1] == 1.0
        assert abp_progress == sorted(abp_progress)
        assert np.all(abp_out.abp_evacuation_time_s >= abp_sim.abp_agents.abp_reaction_time)
        assert abp_result.abp_time_per_exit_s[0][0] == "Salida 1"
        assert abp_result.abp_total_time_s == pytest.approx(abp_result.abp_time_per_exit_s[0][1])
        assert abp_result.abp_curve_evacuated[-1] == 20
        assert np.all(np.diff(abp_result.abp_curve_evacuated) >= 0)
        assert abp_out.abp_trajectories.abp_frame_count == len(abp_result.abp_curve_times_s)

    def abp_test_agents_never_walk_through_walls(self) -> None:
        abp_sim = abp_make_simulation(abp_two_rooms(), [abpOccupancy("Aula 1", "niño", 40)])
        abp_walkable = abp_sim.abp_grid.abp_walkable
        while not abp_sim.abp_finished:
            abp_sim.abp_step()
            abp_active = abp_sim.abp_agents.abp_status != abpAgentStatus.abp_EVACUATED
            abp_r, abp_c = abp_sim.abp_grid.abp_to_cell(abp_sim.abp_agents.abp_position[abp_active])
            assert abp_walkable[abp_r, abp_c].all()
        assert abp_sim.abp_agents.abp_evacuated_count == 40

    def abp_test_second_exit_reduces_time(self) -> None:
        abp_occ = [abpOccupancy("Aula 1", "adulto", 60)]
        abp_one = (
            abp_make_simulation(abp_single_room(abp_exit_width=0.9), abp_occ).abp_run().abp_result
        )
        abp_two = (
            abp_make_simulation(abp_single_room(abp_exit_width=0.9, abp_second_exit=True), abp_occ)
            .abp_run()
            .abp_result
        )
        assert abp_two.abp_total_time_s < abp_one.abp_total_time_s
        assert {abp_name for abp_name, _ in abp_two.abp_time_per_exit_s} == {"Salida 1", "Salida 2"}

    @pytest.mark.parametrize("abp_gap_m", [0.8, 1.0])
    def abp_test_wide_agents_pass_narrow_gaps_between_furniture(self, abp_gap_m: float) -> None:
        abp_wide = (*abp_PROFILES, abpPersonProfile("silla", 0.8, 5.0, 2.0, 0.35))
        abp_furniture = (
            abpObstacle(abp_rect(4, 0, 0.6, 1.7)),
            abpObstacle(abp_rect(4, 1.7 + abp_gap_m, 0.6, 4.3 - abp_gap_m)),
            abpObstacle(abp_rect(6.5, 1.5, 1.0, 3.0)),
        )
        abp_plan = dataclasses.replace(abp_single_room(), abp_obstacles=abp_furniture)
        for abp_seed in range(3):
            abp_sim = abp_make_simulation(
                abp_plan,
                [abpOccupancy("Aula 1", "silla", 3)],
                abp_seed=abp_seed,
                abp_profiles=abp_wide,
            )
            assert abp_sim.abp_run().abp_result.abp_completed

    def abp_test_safe_zone_evacuation(self) -> None:
        abp_out = abp_make_simulation(
            abp_room_with_patio(), [abpOccupancy("Aula 1", "adulto", 10)]
        ).abp_run()
        assert abp_out.abp_result.abp_completed
        assert abp_out.abp_result.abp_time_per_exit_s[0][0] == "Patio"

    def abp_test_time_limit_marks_incomplete(self) -> None:
        abp_params = abpSimulationParams(abp_max_time_s=3.0)
        abp_out = abp_make_simulation(
            abp_two_rooms(), [abpOccupancy("Aula 1", "adulto", 20)], abp_params=abp_params
        ).abp_run()
        assert not abp_out.abp_result.abp_completed
        assert abp_out.abp_result.abp_total_time_s == pytest.approx(3.0)
        assert abp_out.abp_result.abp_agents_evacuated < 20

    def abp_test_cancellation(self) -> None:
        abp_sim = abp_make_simulation(abp_single_room(), [abpOccupancy("Aula 1", "adulto", 10)])
        with pytest.raises(abpSimulationCancelled):
            abp_sim.abp_run(abp_should_cancel=lambda: True)

    def abp_test_crowding_creates_bottleneck_near_exit(self) -> None:
        abp_params = abpSimulationParams(abp_congestion_min_duration_s=2.0)
        abp_plan = abp_single_room(abp_exit_width=0.8)
        abp_out = abp_make_simulation(
            abp_plan, [abpOccupancy("Aula 1", "adulto", 80)], abp_params=abp_params
        ).abp_run()
        abp_bottlenecks = abp_out.abp_result.abp_bottlenecks
        assert abp_bottlenecks
        abp_worst = abp_bottlenecks[0]
        assert abp_worst.abp_location.abp_x > 7.0
        assert abp_worst.abp_mean_density >= abp_params.abp_congestion_density
        assert [abp_b.abp_severity for abp_b in abp_bottlenecks] == sorted(
            (abp_b.abp_severity for abp_b in abp_bottlenecks), reverse=True
        )
        assert abp_out.abp_result.abp_density_map.max() > 0


def abp_test_bilinear_interpolation() -> None:
    abp_grid = abp_build_grid(abp_single_room())
    abp_rows, abp_cols = abp_grid.abp_shape
    abp_xs = abp_grid.abp_origin[0] + (np.arange(abp_cols) + 0.5) * abp_grid.abp_cell_size
    abp_field = np.tile(abp_xs, (abp_rows, 1))
    abp_pts = np.array([[3.3, 2.0], [7.71, 4.4]])
    assert abp_bilinear(abp_field, abp_grid, abp_pts) == pytest.approx(abp_pts[:, 0])
    abp_vector = np.stack([abp_field, abp_field * 2], axis=2)
    assert abp_bilinear(abp_vector, abp_grid, abp_pts)[:, 1] == pytest.approx(2 * abp_pts[:, 0])


def abp_test_params_validation() -> None:
    with pytest.raises(ValueError, match="positivos"):
        abpSimulationParams(abp_dt_s=0)
    with pytest.raises(ValueError, match="cuadros"):
        abpSimulationParams(abp_record_every_s=0.01)
    with pytest.raises(ValueError, match="factor"):
        abpSimulationParams(abp_min_speed_factor=0)
