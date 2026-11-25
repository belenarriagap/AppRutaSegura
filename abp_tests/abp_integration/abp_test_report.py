from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pymupdf
import pytest

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpObservationType, abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_rooms


def abp__pdf_text(abp_path: Path) -> tuple[str, int]:
    with pymupdf.open(abp_path) as abp_doc:
        abp_text = "\n".join(abp_page.get_text() for abp_page in abp_doc)
        abp_images = sum(len(abp_page.get_images()) for abp_page in abp_doc)
    return " ".join(abp_text.split()), abp_images


@pytest.fixture
def abp_project(abp_services: abpAppServices) -> int:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "I.E. N.º 123 «San Martín»", abpUseType.abp_EDUCATION, "Jr. Lima 456"
    )
    abp_image = np.full((320, 640, 3), 245, np.uint8)
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_two_rooms(), abp_image)
    return abp_project_id


def abp__scenario(abp_services: abpAppServices, abp_project_id: int, abp_children: int):
    return dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(
            abpOccupancy("Aula 1", "niño", abp_children),
            abpOccupancy("Aula 2", "adulto", 10),
        ),
    )


def abp_test_report_with_simulation(
    abp_services: abpAppServices, abp_project: int, tmp_path: Path
) -> None:
    abp_scenario = abp__scenario(abp_services, abp_project, 60)
    abp_plan = abp_services.abp_projects.abp_load_floor(abp_project)
    assert abp_plan is not None
    abp_run = abp_services.abp_simulations.abp_run(abp_project, abp_plan, abp_scenario)
    assert all(
        abp_o.abp_kind is abpObservationType.abp_CONGESTION for abp_o in abp_run.abp_observations
    )
    with abp_services.abp_database.abp_unit_of_work() as abp_uow:
        abp_stored = abp_uow.abp_simulations.abp_observations(abp_run.abp_simulation_id)
    assert any(
        abp_o.abp_kind is abpObservationType.abp_NORM and "aforo es 24" in abp_o.abp_description
        for abp_o in abp_stored
    )

    abp_path = abp_services.abp_reports.abp_generate(abp_project, tmp_path / "informes" / "informe")
    assert abp_path.suffix == ".pdf"
    abp_text, abp_images = abp__pdf_text(abp_path)
    assert "Informe de evacuación ante sismo" in abp_text
    assert "I.E. N.º 123 «San Martín»" in abp_text
    assert "Tiempo total estimado de evacuación" in abp_text
    assert "«Aula 1» tiene 60 personas asignadas y su aforo es 24" in abp_text
    assert "RNE A.040" in abp_text
    assert "regla no verificada" in abp_text
    assert "Advertencia" in abp_text
    assert "Semilla: 2026" in abp_text
    assert "(provisional)" in abp_text
    assert " ".join(abp_TEXTS.abp_legal_disclaimer.split()) in abp_text
    assert abp_images >= 2


def abp_test_report_without_simulation(
    abp_services: abpAppServices, abp_project: int, tmp_path: Path
) -> None:
    abp_services.abp_simulations.abp_save_scenario(
        abp_project, abp__scenario(abp_services, abp_project, 10)
    )
    abp_path = abp_services.abp_reports.abp_generate(abp_project, tmp_path / "sin_simular.pdf")
    abp_text, abp_images = abp__pdf_text(abp_path)
    assert "Todavía no se ha simulado" in abp_text
    assert "Aforo calculado: 48 personas" in abp_text
    assert abp_images == 1


def abp_test_report_requires_scale(abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project("Tienda", abpUseType.abp_COMMERCE)
    with pytest.raises(abpUserFacingError, match="escala"):
        abp_services.abp_reports.abp_generate(abp_project_id, tmp_path / "x.pdf")


def abp_test_norms_service(abp_services: abpAppServices) -> None:
    abp_categories = abp_services.abp_norms.abp_categories(abpUseType.abp_EDUCATION)
    assert abp_categories[0] == ("aula", "Aula")
    assert ("pasillo", "Pasillo o circulación") in abp_categories
    abp_evaluation = abp_services.abp_norms.abp_evaluate(abp_two_rooms(), None)
    assert abp_evaluation.abp_total_occupants == 0
    assert abp_evaluation.abp_total_capacity == 48
    with pytest.raises(abpUserFacingError, match="escala"):
        abp_services.abp_norms.abp_evaluate(
            dataclasses.replace(abp_two_rooms(), abp_scale_m_per_px=None), None
        )


def abp_test_report_compares_scenarios(
    abp_services: abpAppServices, abp_project: int, tmp_path: Path
) -> None:
    abp_plan = abp_services.abp_projects.abp_load_floor(abp_project)
    assert abp_plan is not None
    abp_base = abp__scenario(abp_services, abp_project, 20)
    abp_services.abp_simulations.abp_save_scenario(abp_project, abp_base)
    abp_services.abp_simulations.abp_run(abp_project, abp_plan, abp_base)
    abp_path = abp_services.abp_reports.abp_generate(abp_project, tmp_path / "solo_base.pdf")
    assert "Comparación de escenarios" not in abp__pdf_text(abp_path)[0]
    abp_variant = abp_services.abp_simulations.abp_save_variant(
        abp_project, "Doble aforo", abp_base, 200, set()
    )
    abp_services.abp_simulations.abp_run(abp_project, abp_plan, abp_variant)
    abp_text, _ = abp__pdf_text(
        abp_services.abp_reports.abp_generate(abp_project, tmp_path / "comparacion.pdf")
    )
    assert "Comparación de escenarios" in abp_text
    assert "Doble aforo" in abp_text
    assert "Escenario base" in abp_text
    assert "Reglas normativas usadas" in abp_text
