from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import numpy as np
import pymupdf
import pytest

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill, abpScenario
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_floor_building


@pytest.fixture
def abp_building(abp_services: abpAppServices) -> tuple[int, abpScenario]:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio de dos pisos", abpUseType.abp_EDUCATION
    )
    abp_ground, abp_upper = abp_two_floor_building()
    abp_image = np.full((320, 520, 3), 250, np.uint8)
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_ground, abp_image)
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_upper, abp_image)
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(
            abpOccupancy("Hall", "adulto", 10),
            abpOccupancy("Aula 201", "niño", 25, abp_level=1),
        ),
    )
    abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_scenario)
    return abp_project_id, abp_scenario


def abp_test_run_store_and_reload(
    abp_services: abpAppServices, abp_building: tuple[int, abpScenario]
) -> None:
    abp_project_id, abp_scenario = abp_building
    abp_floors = abp_services.abp_projects.abp_load_floors(abp_project_id)
    assert [abp_f.abp_level for abp_f in abp_floors] == [0, 1]
    assert abp_floors[1].abp_stairs[0].abp_name == "Escalera A"
    abp_run = abp_services.abp_simulations.abp_run(abp_project_id, abp_floors, abp_scenario)
    assert abp_run.abp_result.abp_completed
    assert abp_run.abp_result.abp_agents_total == 35
    assert [abp_m.abp_level for abp_m in abp_run.abp_result.abp_floor_maps] == [0, 1]
    assert abp_run.abp_scale_of(1) == pytest.approx(0.02)

    abp_again = abp_services.abp_simulations.abp_last_run(abp_project_id)
    assert abp_again is not None
    assert [abp_m.abp_level for abp_m in abp_again.abp_result.abp_floor_maps] == [0, 1]
    assert abp_again.abp_trajectories.abp_level is not None
    assert abp_again.abp_floor_scales == ((0, 0.02), (1, 0.02))
    assert abp_again.abp_result.abp_total_time_s == abp_run.abp_result.abp_total_time_s


def abp_test_building_norms(
    abp_services: abpAppServices, abp_building: tuple[int, abpScenario]
) -> None:
    abp_project_id, abp_scenario = abp_building
    abp_floors = abp_services.abp_projects.abp_load_floors(abp_project_id)
    abp_crowded = dataclasses.replace(
        abp_scenario, abp_occupancies=(abpOccupancy("Aula 201", "niño", 300, abp_level=1),)
    )
    abp_evaluation = abp_services.abp_norms.abp_evaluate_building(abp_floors, abp_crowded)
    abp_texts = [abp_o.abp_description for abp_o in abp_evaluation.abp_observations]
    assert any(
        abp_t.startswith("Piso 1: Las salidas confirmadas suman 1.20 m") for abp_t in abp_texts
    )
    assert not any(abp_t.startswith("Piso 2: Las salidas confirmadas") for abp_t in abp_texts)
    assert any(abp_t.startswith("Piso 2: «Aula 201» tiene 300 personas") for abp_t in abp_texts)
    assert {abp_c.abp_level for abp_c in abp_evaluation.abp_capacities} == {0, 1}


def abp_test_report_has_one_heatmap_per_floor(
    abp_services: abpAppServices, abp_building: tuple[int, abpScenario], tmp_path: Path
) -> None:
    abp_project_id, abp_scenario = abp_building
    abp_services.abp_simulations.abp_run(
        abp_project_id, abp_services.abp_projects.abp_load_floors(abp_project_id), abp_scenario
    )
    abp_path = abp_services.abp_reports.abp_generate(abp_project_id, tmp_path / "edificio.pdf")
    with pymupdf.open(abp_path) as abp_doc:
        abp_text = " ".join(" ".join(abp_page.get_text() for abp_page in abp_doc).split())
    assert "Mapa de calor de congestión — Piso 1" in abp_text
    assert "Mapa de calor de congestión — Piso 2" in abp_text


def abp_test_validation_and_calibration(
    abp_services: abpAppServices, abp_building: tuple[int, abpScenario]
) -> None:
    abp_project_id, abp_scenario = abp_building
    abp_ground, abp_upper = abp_services.abp_projects.abp_load_floors(abp_project_id)
    abp_without_stair = dataclasses.replace(abp_ground, abp_stairs=())
    with pytest.raises(
        abpUserFacingError, match="no tiene una escalera correspondiente en el piso 1"
    ):
        abp_services.abp_simulations.abp_simulate([abp_without_stair, abp_upper], abp_scenario)
    with pytest.raises(abpUserFacingError, match="El piso 2 no tiene escala"):
        abp_services.abp_simulations.abp_simulate(
            [abp_ground, dataclasses.replace(abp_upper, abp_scale_m_per_px=None)], abp_scenario
        )
    abp_drill = abpRealDrill(date(2026, 10, 8), 35, 90.0)
    abp_result = abp_services.abp_calibration.abp_calibrate(
        abp_project_id,
        [abp_ground, abp_upper],
        abp_scenario,
        abp_drill,
        abp_reaction_factors=(1.0,),
        abp_speed_factors=(1.0,),
    )
    assert abp_result.abp_best.abp_reaction_factor == 1.0
