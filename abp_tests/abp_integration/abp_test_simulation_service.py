from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from abp_rutasegura.abp_application.abp_errors import abpOperationCancelled, abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_simulation_service import (
    abp_BASE_SCENARIO,
    abp_describe_place,
)
from abp_rutasegura.abp_data.abp_trajectories import abp_load_run
from abp_rutasegura.abp_domain.abp_enums import abpObservationType, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan
from abp_tests.abp_fixtures.abp_simple_plans import abp_SCALE, abp_single_room, abp_two_rooms


def abp__project(abp_services: abpAppServices, abp_plan: abpFloorPlan) -> int:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
    return abp_project_id


def abp_test_full_run_is_saved_and_reloaded(abp_services: abpAppServices) -> None:
    abp_plan = abp_two_rooms()
    abp_project_id = abp__project(abp_services, abp_plan)
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "niño", 30), abpOccupancy("Aula 2", "adulto", 20)),
    )
    assert abp_scenario.abp_name == abp_BASE_SCENARIO
    abp_progress: list[float] = []
    abp_run = abp_services.abp_simulations.abp_run(
        abp_project_id, abp_plan, abp_scenario, abp_progress=abp_progress.append
    )
    assert abp_run.abp_result.abp_completed
    assert abp_run.abp_result.abp_agents_evacuated == 50
    assert abp_progress[-1] == 1.0
    assert abp_run.abp_result.abp_trajectories_path is not None
    assert Path(abp_run.abp_result.abp_trajectories_path).exists()
    assert all(
        abp_o.abp_kind is abpObservationType.abp_CONGESTION for abp_o in abp_run.abp_observations
    )

    abp_stored = abp_load_run(Path(abp_run.abp_result.abp_trajectories_path))
    assert np.array_equal(
        abp_stored.abp_trajectories.abp_positions, abp_run.abp_trajectories.abp_positions
    )
    assert abp_stored.abp_bottlenecks == abp_run.abp_result.abp_bottlenecks

    abp_again = abp_services.abp_simulations.abp_last_run(abp_project_id)
    assert abp_again is not None
    assert abp_again.abp_simulation_id == abp_run.abp_simulation_id
    assert abp_again.abp_result.abp_total_time_s == abp_run.abp_result.abp_total_time_s
    assert np.array_equal(abp_again.abp_result.abp_density_map, abp_run.abp_result.abp_density_map)
    assert abp_again.abp_observations == abp_run.abp_observations
    assert abp_services.abp_simulations.abp_load_scenario(abp_project_id) == abp_scenario


@pytest.mark.parametrize(
    ("abp_plan", "abp_occupants", "abp_message"),
    [
        (dataclasses.replace(abp_single_room(), abp_scale_m_per_px=None), 1, "escala"),
        (abp_single_room(abp_confirmed=False), 1, "ninguna salida confirmada"),
        (dataclasses.replace(abp_single_room(), abp_exits=()), 1, "ninguna salida"),
        (dataclasses.replace(abp_single_room(), abp_rooms=()), 1, "ambientes"),
        (abp_single_room(), 0, "cuántas personas"),
    ],
)
def abp_test_validation_messages(
    abp_services: abpAppServices, abp_plan: abpFloorPlan, abp_occupants: int, abp_message: str
) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project("Local", abpUseType.abp_OFFICE)
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "adulto", abp_occupants),) if abp_occupants else (),
    )
    with pytest.raises(abpUserFacingError, match=abp_message):
        abp_services.abp_simulations.abp_run(abp_project_id, abp_plan, abp_scenario)


def abp_test_cancel(abp_services: abpAppServices) -> None:
    abp_plan = abp_single_room()
    abp_project_id = abp__project(abp_services, abp_plan)
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "adulto", 10),),
    )
    with pytest.raises(abpOperationCancelled):
        abp_services.abp_simulations.abp_run(
            abp_project_id, abp_plan, abp_scenario, abp_should_cancel=lambda: True
        )
    assert abp_services.abp_simulations.abp_last_run(abp_project_id) is None


def abp_test_describe_place() -> None:
    abp_plan = abp_single_room()
    assert (
        abp_describe_place(abp_plan, abp_SCALE, abpPoint(9.6, 3.0))
        == "junto a «Salida 1» de «Aula 1»"
    )
    assert abp_describe_place(abp_plan, abp_SCALE, abpPoint(2.0, 2.0)) == "en «Aula 1»"
    assert (
        abp_describe_place(abp_plan, abp_SCALE, abpPoint(50.0, 50.0))
        == "en un pasillo o zona de circulación"
    )


def abp_test_room_detection_service(abp_services: abpAppServices) -> None:
    abp_plan = dataclasses.replace(abp_two_rooms(), abp_rooms=())
    abp_detected = abp_services.abp_plans.abp_detect_rooms(
        abp_plan, abpUseType.abp_EDUCATION, "Ambiente {number}"
    )
    assert [abp_r.abp_name for abp_r in abp_detected.abp_rooms] == ["Ambiente 1", "Ambiente 2"]
    abp_again = abp_services.abp_plans.abp_detect_rooms(
        abp_detected, abpUseType.abp_EDUCATION, "Ambiente {number}"
    )
    assert len(abp_again.abp_rooms) == 2
    with pytest.raises(abpUserFacingError, match="escala"):
        abp_services.abp_plans.abp_detect_rooms(
            dataclasses.replace(abp_plan, abp_scale_m_per_px=None),
            abpUseType.abp_OFFICE,
            "A{number}",
        )


def abp_test_unconfirmed_proposals_do_not_block(abp_services: abpAppServices) -> None:
    abp_plan = abp_single_room(abp_second_exit=True)
    abp_proposed = dataclasses.replace(abp_plan.abp_exits[1], abp_confirmed=False)
    abp_plan = dataclasses.replace(abp_plan, abp_exits=(abp_plan.abp_exits[0], abp_proposed))
    abp_project_id = abp__project(abp_services, abp_plan)
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "adulto", 10),),
    )
    abp_run = abp_services.abp_simulations.abp_run(abp_project_id, abp_plan, abp_scenario)
    assert abp_run.abp_result.abp_completed
    assert {abp_name for abp_name, _ in abp_run.abp_result.abp_time_per_exit_s} == {"Salida 1"}


def abp_test_detection_keeps_confirmed_exits(abp_services: abpAppServices) -> None:
    from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan

    abp_synthetic = abp_generate_plan(1)
    abp_manual = abpExit(abp_synthetic.abp_exits[0], "Puerta principal")
    abp_plan = abpFloorPlan(
        abp_scale_m_per_px=abp_synthetic.abp_scale_m_per_px, abp_exits=(abp_manual,)
    )
    abp_detected = abp_services.abp_plans.abp_detect(abp_synthetic.abp_image, abp_plan)
    assert abp_detected.abp_exits[0] == abp_manual
    abp_proposals = abp_detected.abp_exits[1:]
    assert all(not abp_e.abp_confirmed for abp_e in abp_proposals)
    assert len(abp_proposals) == len(abp_synthetic.abp_exits) - 1
    assert len({abp_e.abp_name for abp_e in abp_detected.abp_exits}) == len(abp_detected.abp_exits)
