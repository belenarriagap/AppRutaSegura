from __future__ import annotations

import dataclasses
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_serialization import (
    abp_plan_from_dict,
    abp_plan_to_dict,
    abp_scenario_from_dict,
    abp_scenario_to_dict,
)
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_simulation_service import abp_BASE_SCENARIO
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSafeZone, abpStair
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill, abpScenario
from abp_rutasegura.abp_presentation.abp_main_window import abpMainWindow
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_two_floor_building, abp_two_rooms

abp_IMAGE = np.full((60, 80, 3), 200, np.uint8)


def abp__full_project(abp_services: abpAppServices) -> int:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio Norma", abpUseType.abp_EDUCATION, "Jr. 1"
    )
    abp_plan = dataclasses.replace(
        abp_two_rooms(),
        abp_safe_zones=(abpSafeZone(abp_rect(1, 1, 1, 1), "Patio"),),
        abp_stairs=(abpStair(abp_rect(4, 4, 1, 1), abp_name="Escalera A"),),
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan, abp_IMAGE)
    abp_base = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "niño", 20), abpOccupancy("Aula 2", "adulto", 3)),
        abp_runs=3,
    )
    abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_base)
    abp_services.abp_simulations.abp_save_variant(
        abp_project_id, "Noche", abp_base, 50, {"Patio"}, abp_reaction_factor=2
    )
    with abp_services.abp_database.abp_unit_of_work() as abp_uow:
        abp_uow.abp_drills.abp_add(
            abp_project_id, abpRealDrill(date(2026, 5, 31), 40, 180.0, (("Salida", 170.0),))
        )
    abp_services.abp_simulations.abp_run(
        abp_project_id, abp_plan, dataclasses.replace(abp_base, abp_runs=1)
    )
    abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_base)
    return abp_project_id


def abp_test_serialization_round_trip() -> None:
    abp_plan = dataclasses.replace(abp_two_floor_building()[1], abp_scale_m_per_px=0.02)
    assert abp_plan_from_dict(json.loads(json.dumps(abp_plan_to_dict(abp_plan)))) == abp_plan
    abp_scenario = abpScenario(
        "X", 7, (abpOccupancy("A", "adulto", 3, abp_level=1),), frozenset({"S"}), "d", 1.5, 0.8, 4
    )
    assert (
        abp_scenario_from_dict(json.loads(json.dumps(abp_scenario_to_dict(abp_scenario))))
        == abp_scenario
    )


def abp_test_export_import_keeps_everything(abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_project_id = abp__full_project(abp_services)
    abp_path = abp_services.abp_archive.abp_export_project(abp_project_id, tmp_path / "respaldo")
    assert abp_path.suffix == ".rutasegura"
    with zipfile.ZipFile(abp_path) as abp_archive:
        assert set(abp_archive.namelist()) == {"proyecto.json", "planos/piso_0.png"}
    abp_imported = abp_services.abp_archive.abp_import_project(abp_path)
    assert abp_imported != abp_project_id
    abp_original = abp_services.abp_projects.abp_load_floors(abp_project_id)[0]
    abp_copy = abp_services.abp_projects.abp_load_floors(abp_imported)[0]
    assert dataclasses.replace(abp_copy, abp_image_path=None) == dataclasses.replace(
        abp_original, abp_image_path=None
    )
    abp_image = abp_services.abp_projects.abp_load_floor_image(abp_copy)
    assert abp_image is not None
    assert abp_image.shape == abp_IMAGE.shape
    abp_names = [
        abp_s.abp_name for abp_s in abp_services.abp_simulations.abp_list_scenarios(abp_imported)
    ]
    assert abp_names == [abp_BASE_SCENARIO, "Noche"]
    abp_noche = abp_services.abp_simulations.abp_load_scenario(abp_imported, "Noche")
    assert abp_noche.abp_reaction_factor == 2
    assert abp_noche.abp_blocked_exits == frozenset({"Patio"})
    assert abp_services.abp_simulations.abp_load_scenario(abp_imported).abp_runs == 3
    with abp_services.abp_database.abp_unit_of_work() as abp_uow:
        assert [abp_d for _, abp_d in abp_uow.abp_drills.abp_list_all(abp_imported)] == [
            abpRealDrill(date(2026, 5, 31), 40, 180.0, (("Salida", 170.0),))
        ]
    assert abp_services.abp_simulations.abp_last_run(abp_imported) is None
    assert abp_services.abp_simulations.abp_last_run(abp_project_id) is not None


def abp_test_duplicate_and_delete(abp_services: abpAppServices) -> None:
    abp_project_id = abp__full_project(abp_services)
    abp_copy_id = abp_services.abp_archive.abp_duplicate_project(abp_project_id)
    assert (
        abp_services.abp_projects.abp_get_project(abp_copy_id).abp_name == "Colegio Norma (copia)"
    )
    abp_runs_dir = abp_services.abp_simulations.abp_project_runs_dir(abp_project_id)
    abp_images_dir = abp_services.abp_projects.abp_image_path(abp_project_id, 0).parent
    assert abp_runs_dir.is_dir()
    assert abp_images_dir.is_dir()
    abp_services.abp_archive.abp_delete_project(abp_project_id)
    with pytest.raises(abpUserFacingError, match="ya no existe"):
        abp_services.abp_projects.abp_get_project(abp_project_id)
    assert not abp_runs_dir.exists()
    assert not abp_images_dir.exists()
    abp_copy_plan = abp_services.abp_projects.abp_load_floors(abp_copy_id)[0]
    assert abp_services.abp_projects.abp_load_floor_image(abp_copy_plan) is not None


def abp_test_invalid_files_are_rejected(abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_bad = tmp_path / "x.rutasegura"
    abp_bad.write_bytes(b"no es un zip")
    with pytest.raises(abpUserFacingError, match="no es un proyecto"):
        abp_services.abp_archive.abp_import_project(abp_bad)
    abp_buffer = io.BytesIO()
    with zipfile.ZipFile(abp_buffer, "w") as abp_archive:
        abp_archive.writestr("proyecto.json", json.dumps({"formato": "otro"}))
    with pytest.raises(abpUserFacingError, match="no es un proyecto"):
        abp_services.abp_archive.abp_import_bytes(abp_buffer.getvalue())
    abp_newer = io.BytesIO()
    with zipfile.ZipFile(abp_newer, "w") as abp_archive:
        abp_archive.writestr(
            "proyecto.json", json.dumps({"formato": "rutasegura-proyecto", "version": 99})
        )
    with pytest.raises(abpUserFacingError, match="versión más nueva"):
        abp_services.abp_archive.abp_import_bytes(abp_newer.getvalue())
    assert abp_services.abp_projects.abp_list_projects() == []


def abp_test_window_actions(qtbot: QtBot, abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    assert not abp_window.abp_export_action.isEnabled()
    abp_project_id = abp_window.abp_create_project("Oficina Central", abpUseType.abp_OFFICE)
    assert abp_project_id is not None
    abp_services.abp_projects.abp_save_floor(abp_project_id, abpFloorPlan(abp_scale_m_per_px=0.02))
    assert abp_window.abp_export_action.isEnabled()
    abp_saved = abp_window.abp_export_project(abp_project_id, tmp_path / "of")
    assert abp_saved is not None
    assert abp_saved.exists()
    abp_copy_id = abp_window.abp_duplicate_project(abp_project_id)
    assert abp_copy_id is not None
    assert abp_window.abp_project_id == abp_copy_id
    abp_menu = abp_window.abp_recent_menu(abp_project_id)
    assert len([abp_a for abp_a in abp_menu.actions() if not abp_a.isSeparator()]) == 4
    abp_window.abp_delete_project(abp_copy_id)
    assert abp_window.abp_project_id is None
    assert abp_window.abp_stack.currentWidget() is abp_window.abp_welcome_page
    assert abp_window.abp_recent_list.count() == 1
    abp_imported = abp_window.abp_import_project(abp_saved)
    assert abp_imported is not None
    assert abp_window.abp_project_id == abp_imported
