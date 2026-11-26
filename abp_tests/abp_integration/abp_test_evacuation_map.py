from __future__ import annotations

import dataclasses
from pathlib import Path

import pymupdf
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_report_service import abpMapOptions
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_data.abp_report_pdf import abp_FONT, abp_font_file
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_presentation.abp_evacuation_map_dialog import abpEvacuationMapDialog
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp_room_with_patio,
    abp_two_floor_building,
    abp_two_rooms,
)

abp_T = abp_TEXTS.abp_report
abp_OPTIONS = abpMapOptions(
    abp_paper="A4",
    abp_you_are_here=((0, "Aula 1"),),
    abp_responsible="Brigada del local",
    abp_phones=abp_T.abp_map_default_phones,
    abp_meeting_point="Losa deportiva",
    abp_instructions=abp_T.abp_map_default_instructions,
    abp_disclaimer=abp_T.abp_map_disclaimer,
)


def abp__text(abp_path: Path) -> str:
    with pymupdf.open(abp_path) as abp_doc:
        return "\n".join(str(abp_page.get_text()) for abp_page in abp_doc)


def abp_test_map_pdf_has_everything(abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio Norma", abpUseType.abp_EDUCATION, "Jr. Lima 1"
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_two_rooms())
    abp_path = abp_services.abp_reports.abp_generate_map(
        abp_project_id, tmp_path / "mapa", abp_OPTIONS
    )
    assert abp_path.suffix == ".pdf"
    abp_text = abp__text(abp_path)
    for abp_expected in (
        "PLANO DE EVACUACIÓN",
        "Colegio Norma",
        "SALIDA",
        "USTED ESTÁ AQUÍ",
        "LEYENDA",
        "EN CASO DE SISMO",
        "Losa deportiva",
        "116",
        "Brigada del local",
        "ITSE",
        "AULA 1",
    ):
        assert abp_expected in abp_text, abp_expected
    abp_content = abp_services.abp_reports.abp_map_content(abp_project_id, abp_OPTIONS)
    assert [abp_r.abp_room_name for abp_r in abp_content.abp_floors[0].abp_routes] == [
        "Aula 1",
        "Aula 2",
    ]
    with pymupdf.open(abp_path) as abp_doc:
        assert abp_doc[0].rect.width > abp_doc[0].rect.height


def abp_test_one_page_per_floor_and_safe_zones(
    abp_services: abpAppServices, tmp_path: Path
) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project("Edificio", abpUseType.abp_OFFICE)
    abp_floors = abp_two_floor_building()
    for abp_plan in abp_floors:
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
    abp_path = abp_services.abp_reports.abp_generate_map(
        abp_project_id, tmp_path / "pisos.pdf", dataclasses.replace(abp_OPTIONS, abp_paper="A3")
    )
    with pymupdf.open(abp_path) as abp_doc:
        assert abp_doc.page_count == len(abp_floors)
        assert "Piso 2" in str(abp_doc[1].get_text())
    abp_patio_id = abp_services.abp_projects.abp_create_project("Tienda", abpUseType.abp_COMMERCE)
    abp_services.abp_projects.abp_save_floor(abp_patio_id, abp_room_with_patio())
    abp_patio_path = abp_services.abp_reports.abp_generate_map(
        abp_patio_id, tmp_path / "patio.pdf", abp_OPTIONS
    )
    assert "ZONA SEGURA" in abp__text(abp_patio_path)


def abp_test_map_needs_scale_and_a_way_out(abp_services: abpAppServices, tmp_path: Path) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Sin salida", abpUseType.abp_OFFICE
    )
    abp_services.abp_projects.abp_save_floor(
        abp_project_id, dataclasses.replace(abp_two_rooms(), abp_exits=())
    )
    with pytest.raises(abpUserFacingError, match="salidas confirmadas"):
        abp_services.abp_reports.abp_generate_map(abp_project_id, tmp_path / "x.pdf", abp_OPTIONS)
    abp_empty = abp_services.abp_projects.abp_create_project("Vacío", abpUseType.abp_OFFICE)
    with pytest.raises(abpUserFacingError, match="escala"):
        abp_services.abp_reports.abp_generate_map(abp_empty, tmp_path / "y.pdf", abp_OPTIONS)


def abp_test_dialog_collects_options(qtbot: QtBot) -> None:
    abp_dialog = abpEvacuationMapDialog([abp_two_rooms()], abp_responsible="Directora")
    qtbot.addWidget(abp_dialog)
    abp_dialog.abp_paper_combo.setCurrentText("A4")
    abp_dialog.abp_here_combos[0].setCurrentIndex(2)
    abp_dialog.abp_meeting_edit.setText("Patio")
    abp_dialog.abp_instructions_edit.setPlainText("Primero\n\nSegundo  ")
    abp_options = abp_dialog.abp_options()
    assert abp_options.abp_paper == "A4"
    assert abp_options.abp_you_are_here == ((0, "Aula 2"),)
    assert abp_options.abp_responsible == "Directora"
    assert abp_options.abp_phones == abp_T.abp_map_default_phones
    assert abp_options.abp_instructions == ("Primero", "Segundo")
    assert abp_options.abp_disclaimer == abp_T.abp_map_disclaimer


def abp_test_map_is_black_and_gray_except_routes_and_signs(
    abp_services: abpAppServices, tmp_path: Path
) -> None:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio Norma", abpUseType.abp_EDUCATION, "Jr. Lima 1"
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_two_rooms())
    abp_path = abp_services.abp_reports.abp_generate_map(
        abp_project_id, tmp_path / "mapa", abp_OPTIONS
    )
    abp_allowed = {"#1e8a4c"} | {
        abp_shape.abp_color.lower()
        for abp_art in abp_SIGNS.values()
        for abp_shape in abp_art.abp_shapes
    }
    with pymupdf.open(abp_path) as abp_doc:
        abp_fonts = {
            abp_span["font"]
            for abp_block in abp_doc[0].get_text("dict")["blocks"]
            for abp_line in abp_block.get("lines", [])
            for abp_span in abp_line["spans"]
        }
        abp_colors = {
            tuple(round(abp_v * 255) for abp_v in abp_color)
            for abp_drawing in abp_doc[0].get_drawings()
            for abp_color in (abp_drawing.get("fill"), abp_drawing.get("color"))
            if abp_color
        }
    abp_family = abp_font_file(abp_FONT).stem.lower()
    abp_expected = "arial" if abp_family.startswith("arial") else abp_family.split("-")[0][:8]
    assert all(abp_expected in abp_f.lower().replace(" ", "") for abp_f in abp_fonts), abp_fonts
    for abp_r, abp_g, abp_b in abp_colors:
        abp_gray = max(abp_r, abp_g, abp_b) - min(abp_r, abp_g, abp_b) <= 2
        assert abp_gray or f"#{abp_r:02x}{abp_g:02x}{abp_b:02x}" in abp_allowed, (
            abp_r,
            abp_g,
            abp_b,
        )
