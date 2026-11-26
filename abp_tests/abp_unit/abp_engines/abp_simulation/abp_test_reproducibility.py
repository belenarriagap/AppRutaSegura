from __future__ import annotations

import numpy as np

from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_rooms
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation

abp_OCCUPANCY = [abpOccupancy("Aula 1", "niño", 35), abpOccupancy("Aula 2", "adulto", 25)]


def abp__run(abp_seed: int):
    return abp_make_simulation(abp_two_rooms(), abp_OCCUPANCY, abp_seed=abp_seed).abp_run()


def abp_test_same_seed_gives_identical_results() -> None:
    abp_a, abp_b = abp__run(42), abp__run(42)
    assert abp_a.abp_result.abp_total_time_s == abp_b.abp_result.abp_total_time_s
    assert abp_a.abp_result.abp_time_per_exit_s == abp_b.abp_result.abp_time_per_exit_s
    assert abp_a.abp_result.abp_bottlenecks == abp_b.abp_result.abp_bottlenecks
    for abp_x, abp_y in (
        (abp_a.abp_trajectories.abp_positions, abp_b.abp_trajectories.abp_positions),
        (abp_a.abp_trajectories.abp_status, abp_b.abp_trajectories.abp_status),
        (abp_a.abp_result.abp_density_map, abp_b.abp_result.abp_density_map),
        (abp_a.abp_result.abp_curve_evacuated, abp_b.abp_result.abp_curve_evacuated),
        (abp_a.abp_evacuation_time_s, abp_b.abp_evacuation_time_s),
        (abp_a.abp_exit_index, abp_b.abp_exit_index),
    ):
        assert abp_x.dtype == abp_y.dtype
        assert abp_x.tobytes() == abp_y.tobytes()


def abp_test_different_seed_gives_different_results() -> None:
    abp_a, abp_b = abp__run(1), abp__run(2)
    assert not np.array_equal(
        abp_a.abp_trajectories.abp_positions[0], abp_b.abp_trajectories.abp_positions[0]
    )
