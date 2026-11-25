from __future__ import annotations

import time

import pytest

from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_tests.abp_fixtures.abp_simple_plans import abp_single_room
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation

abp_MIN_STEPS_PER_SECOND_500 = 20.0
abp_STEPS = 50


def abp__big_room() -> abpFloorPlan:
    return abp_single_room(
        abp_width=30.0, abp_height=20.0, abp_exit_width=1.8, abp_second_exit=True
    )


def abp_steps_per_second(abp_agents: int) -> float:
    abp_sim = abp_make_simulation(
        abp__big_room(), [abpOccupancy("Aula 1", "adulto", abp_agents)], abp_seed=5
    )
    abp_sim.abp_agents.abp_reaction_time[:] = 0.0
    for _ in range(3):
        abp_sim.abp_step()
    abp_start = time.perf_counter()
    for _ in range(abp_STEPS):
        abp_sim.abp_step()
    return abp_STEPS / (time.perf_counter() - abp_start)


@pytest.mark.benchmark
@pytest.mark.parametrize("abp_agents", [100, 300, 500, 1000])
def abp_test_engine_speed(abp_agents: int) -> None:
    abp_rate = abp_steps_per_second(abp_agents)
    print(f"\n{abp_agents:>5} agentes: {abp_rate:8.1f} pasos/s")
    if abp_agents == 500:
        assert abp_rate >= abp_MIN_STEPS_PER_SECOND_500
