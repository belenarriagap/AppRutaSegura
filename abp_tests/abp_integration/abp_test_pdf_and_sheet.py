from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_plan_import import (
    abp_label_inside,
    abpLoadedPlan,
    abpPlanImportService,
)
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_sheet_service import abp_format_time, abpSheetOptions
from abp_rutasegura.abp_data.abp_evacuation_sheet import abp_best_scale
from abp_rutasegura.abp_data.abp_vector_files import (
    abp_load_vector,
    abp_save_vector,
    abp_vector_path,
)
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSafeZone, abpSign, abpStair
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpTool
from abp_rutasegura.abp_presentation.abp_evacuation_sheet_dialog import abpEvacuationSheetDialog
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_EDIT,
    abp_STEP_REPORT,
    abp_STEP_ROOMS,
    abp_STEP_SCALE,
    abpMainWindow,
)
from abp_rutasegura.abp_presentation.abp_pdf_import_dialog import abpCropFrame, abpPdfImportDialog
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_single_room, abp_two_rooms
from abp_tests.abp_fixtures.abp_vector_plans import abp_write_vector_plan

abp_P = abpPlanImportService


@pytest.fixture(scope="module")
def abp_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return abp_write_vector_plan(tmp_path_factory.mktemp("pdf") / "plano.pdf", abp_pages=2)


@pytest.fixture(scope="module")
def abp_loaded(abp_pdf: Path) -> abpLoadedPlan:
    abp_page = abp_P.abp_pdf_pages(abp_pdf)[0]
    abp_plan = abp_P.abp_load_pdf_page(
        abp_pdf,
        0,
        abp_hidden_layers=abp_P.abp_suggested_hidden_layers(abp_page),
        abp_remove_colors=True,
    )
    abp_rect_px = abp_P.abp_suggest_crop(abp_plan)
    assert abp_rect_px is not None
    return abp_P.abp_crop(abp_plan, abp_rect_px)


class abpTestImportService:
    def abp_test_crop_keeps_only_the_drawing(self, abp_loaded: abpLoadedPlan) -> None:
        abp_scale = abp_loaded.abp_scale_m_per_px
        assert abp_scale is not None
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]
        assert abp_w * abp_scale == pytest.approx(13.2, abs=0.3)
        assert abp_h * abp_scale < 12.0
        assert abp_loaded.abp_vector is not None
        assert "MOBILIARIO" in abp_loaded.abp_vector.abp_layers

    def abp_test_full_detection(self, abp_loaded: abpLoadedPlan) -> None:
        abp_plan = abp_P.abp_detect(
            abp_loaded.abp_image,
            abpFloorPlan(abp_scale_m_per_px=abp_loaded.abp_scale_m_per_px),
            abp_vector=abp_loaded.abp_vector,
        )
        assert len(abp_plan.abp_doors) == 2
        assert [abp_e.abp_name for abp_e in abp_plan.abp_exits] == ["Salida 1"]
        abp_plan = dataclasses.replace(
            abp_plan, abp_exits=(dataclasses.replace(abp_plan.abp_exits[0], abp_confirmed=True),)
        )
        abp_labels = abp_P.abp_room_labels(abp_loaded.abp_vector)
        abp_plan = abp_P.abp_detect_rooms(
            abp_plan, abpUseType.abp_EDUCATION, "Ambiente {number}", abp_labels=abp_labels
        )
        assert {abp_r.abp_name for abp_r in abp_plan.abp_rooms} == {
            "Aula 101",
            "Taller de arte",
            "Pasillo",
        }
        abp_areas = {
            abp_r.abp_name: abp_plan.abp_area_m2(abp_r.abp_area) for abp_r in abp_plan.abp_rooms
        }
        assert abp_areas["Aula 101"] == pytest.approx(24.0, abs=1.5)
        abp_again = abp_P.abp_detect(
            abp_loaded.abp_image, abp_plan, abp_vector=abp_loaded.abp_vector
        )
        assert [(abp_e.abp_name, abp_e.abp_confirmed) for abp_e in abp_again.abp_exits] == [
            ("Salida 1", True)
        ]
        abp_room = next(abp_r for abp_r in abp_plan.abp_rooms if abp_r.abp_name == "Taller de arte")
        abp_label = abp_label_inside(abp_room.abp_area, abp_labels)
        assert abp_label is not None
        assert abp_label.abp_capacity == 8
        abp_same = [dataclasses.replace(abp_q, abp_name="Aula") for abp_q in abp_labels]
        abp_repeated = abp_P.abp_detect_rooms(
            dataclasses.replace(abp_plan, abp_rooms=()),
            abpUseType.abp_EDUCATION,
            "A {number}",
            abp_labels=abp_same,
        )
        assert len({abp_r.abp_name for abp_r in abp_repeated.abp_rooms}) == 3

    def abp_test_without_scale_or_labels(self, tmp_path: Path) -> None:
        abp_path = abp_write_vector_plan(tmp_path / "x.pdf", abp_scale_text=False)
        abp_plan = abp_P.abp_load_pdf_page(abp_path, 0)
        assert abp_plan.abp_scale_m_per_px is None
        assert abp_P.abp_suggest_crop(abp_plan) is None
        assert abp_P.abp_room_labels(None) == ()

    def abp_test_errors(self, abp_loaded: abpLoadedPlan, tmp_path: Path) -> None:
        with pytest.raises(abpUserFacingError, match="demasiado pequeño"):
            abp_P.abp_crop(abp_loaded, (0, 0, 10, 10))
        abp_bad = tmp_path / "malo.pdf"
        abp_bad.write_bytes(b"x")
        for abp_call in (
            abp_P.abp_pdf_pages,
            lambda abp_p: abp_P.abp_load_pdf_page(abp_p, 0),
            lambda abp_p: abp_P.abp_pdf_thumbnail(abp_p, 0),
        ):
            with pytest.raises(abpUserFacingError):
                abp_call(abp_bad)
        assert abp_P.abp_is_pdf(Path("A.PDF"))

    def abp_test_vector_file(self, abp_loaded: abpLoadedPlan, tmp_path: Path) -> None:
        assert abp_loaded.abp_vector is not None
        abp_path = abp_vector_path(tmp_path / "piso_0.png")
        abp_save_vector(abp_path, abp_loaded.abp_vector)
        abp_again = abp_load_vector(abp_path)
        assert abp_again is not None
        assert np.array_equal(abp_again.abp_segments, abp_loaded.abp_vector.abp_segments)
        assert abp_again.abp_texts == abp_loaded.abp_vector.abp_texts
        assert abp_again.abp_scale_denominator == 50
        abp_path.write_bytes(b"roto")
        assert abp_load_vector(abp_path) is None
        assert abp_load_vector(tmp_path / "no.npz") is None


class abpTestDialogAndWindow:
    def abp_test_crop_frame(self, qtbot: QtBot) -> None:
        abp_frame = abpCropFrame(QRectF(0, 0, 1000, 800))
        abp_frame.abp_set_rect(QRectF(100, 100, 5000, 300))
        assert abp_frame.abp_rect == QRectF(100, 100, 900, 300)
        abp_frame.abp_move_corner(0, QPointF(50, 150))
        assert abp_frame.abp_rect.topLeft() == QPointF(50, 150)
        abp_frame.abp_move_corner(2, QPointF(0, 0))
        assert abp_frame.abp_rect.width() >= 60

    def abp_test_dialog(self, qtbot: QtBot, abp_pdf: Path) -> None:
        abp_dialog = abpPdfImportDialog(abp_P(), abp_pdf)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(lambda: abp_dialog.abp_ok_button.isEnabled(), timeout=60_000)
        assert abp_dialog.abp_page_list.count() == 2
        assert abp_dialog.abp_page.abp_level == 0
        assert abp_dialog.abp_clean_check.isChecked()
        assert "Escala 1/50" in abp_dialog.abp_info_label.text()
        assert "Aula 101" in abp_dialog.abp_info_label.text()
        assert "MOBILIARIO" in abp_dialog.abp_hidden_layers()
        abp_plan = abp_dialog.abp_result_plan()
        assert abp_plan is not None
        assert abp_plan.abp_vector is not None
        abp_full = abp_dialog.abp_loaded
        assert abp_full is not None
        assert abp_plan.abp_image.shape[1] < abp_full.abp_image.shape[1]
        abp_dialog.abp_crop_check.setChecked(False)
        assert abp_dialog.abp_result_plan() is abp_full
        abp_dialog.abp_crop_check.setChecked(True)
        abp_dialog.abp_set_crop((0, 0, 20, 20))
        abp_dialog.accept()
        assert abp_dialog.result() != QDialog.DialogCode.Accepted
        assert "pequeño" in abp_dialog.abp_info_label.text()
        abp_dialog.abp_reset_crop()
        abp_item = abp_dialog.abp_layers.item(0)
        assert abp_item is not None
        with qtbot.waitSignal(abp_dialog.abp_preview_ready, timeout=60_000):
            abp_item.setCheckState(
                Qt.CheckState.Unchecked
                if abp_item.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
        with qtbot.waitSignal(abp_dialog.abp_preview_ready, timeout=60_000):
            abp_dialog.abp_page_list.setCurrentRow(1)
        assert abp_dialog.abp_page.abp_level == 1
        abp_dialog.accept()
        assert abp_dialog.result() == QDialog.DialogCode.Accepted

    def abp_test_window_flow(
        self,
        qtbot: QtBot,
        abp_services: abpAppServices,
        abp_pdf: Path,
        abp_loaded: abpLoadedPlan,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        monkeypatch.setattr(
            abp_window, "abp_show_error", lambda abp_message: pytest.fail(abp_message)
        )
        abp_project_id = abp_window.abp_create_project("Colegio PDF", abpUseType.abp_EDUCATION)
        assert abp_project_id is not None
        abp_window.abp_load_page.abp_use_plan(abp_pdf, 0, 2, abp_loaded)
        assert abp_window.abp_plan.abp_scale_m_per_px == pytest.approx(
            abp_loaded.abp_scale_m_per_px
        )
        abp_window.abp_go_to_step(abp_STEP_SCALE)
        assert "1/50" in abp_window.abp_scale_page.abp_result_label.text()
        abp_scale = abp_window.abp_plan.abp_scale_m_per_px
        assert abp_scale is not None
        abp_window.abp_scale_page.abp_set_reference(abpPoint(0, 0), abpPoint(2 / abp_scale, 0))
        assert "2.00 m" in abp_window.abp_scale_page.abp_result_label.text()
        with qtbot.waitSignal(abp_window.abp_editor_page.abp_detection_finished, timeout=60_000):
            abp_window.abp_go_to_step(abp_STEP_EDIT)
        assert abp_window.abp_editor_page.abp_diagonal_check.isHidden()
        abp_window.abp_editor_page.abp_editor.abp_confirm_all_exits()
        abp_window.abp_go_to_step(abp_STEP_ROOMS)
        abp_window.abp_rooms_page.abp_detect_rooms()
        assert not abp_window.abp_rooms_page.abp_plan_occupants_button.isHidden()
        abp_window.abp_rooms_page.abp_use_plan_occupants()
        assert abp_window.abp_rooms_page.abp_scenario.abp_total_occupants == 24
        abp_window.abp_go_to_step(abp_STEP_EDIT)
        abp_window.abp_editor_page.abp_propose_signs()
        abp_kinds = {abp_s.abp_kind for abp_s in abp_window.abp_plan.abp_signs}
        assert {abpSignKind.abp_EXIT, abpSignKind.abp_CAPACITY} <= abp_kinds
        abp_window.abp_editor_page.abp_propose_signs()
        assert abp_window.abp_save()
        abp_saved = abp_services.abp_projects.abp_load_floor(abp_project_id)
        assert abp_saved is not None
        assert abp_saved.abp_signs == abp_window.abp_plan.abp_signs
        assert abp_services.abp_projects.abp_load_floor_vector(abp_saved) is not None
        abp_copy = abp_services.abp_archive.abp_import_bytes(
            abp_services.abp_archive.abp_export_bytes(abp_project_id)
        )
        abp_copied = abp_services.abp_projects.abp_load_floor(abp_copy)
        assert abp_copied is not None
        assert abp_copied.abp_signs == abp_saved.abp_signs
        assert abp_services.abp_projects.abp_load_floor_vector(abp_copied) is not None
        monkeypatch.setattr(
            "abp_rutasegura.abp_presentation.abp_report_page.QDesktopServices.openUrl",
            lambda abp__url: True,
        )
        abp_window.abp_go_to_step(abp_STEP_REPORT)
        abp_path = abp_window.abp_report_page.abp_generate_sheet_to(
            tmp_path / "lamina", abpSheetOptions()
        )
        assert abp_path is not None
        assert abp_path.exists()
        assert str(abp_path) in abp_window.abp_report_page.abp_sheet_result_label.text()
        abp_window.abp_load_page.abp_straighten_button.setChecked(True)
        for abp_x, abp_y in ((10, 10), (600, 10), (600, 500), (10, 500)):
            abp_window.abp_load_page.abp_add_corner(QPointF(abp_x, abp_y))
        assert abp_window.abp_load_page.abp_vector is None
        abp_window.abp_load_page.abp_undo_straighten()
        assert abp_window.abp_load_page.abp_vector is not None


class abpTestSignsInEditor:
    def abp_test_place_move_rotate_and_delete(self, qtbot: QtBot) -> None:
        abp_editor = abpPlanEditor()
        qtbot.addWidget(abp_editor)
        abp_editor.abp_set_plan(abp_single_room(), None)
        abp_editor.abp_set_tool(abpTool.abp_SIGN)
        assert abp_editor.abp_sign_combo_action.isVisible()
        abp_editor.abp_sign_combo.setCurrentIndex(abp_editor.abp_sign_combo.findData("direccion"))
        abp_editor.abp_view.abp_point_picked.emit(QPointF(100, 100))
        assert abp_editor.abp_plan().abp_signs == (
            abpSign(abpSignKind.abp_DIRECTION, abpPoint(100, 100)),
        )
        assert len(abp_editor.abp_scene.abp_items_of(abpElementType.abp_SIGN)) == 1
        abp_editor.abp_set_tool(abpTool.abp_SELECT)
        abp_editor.abp_scene.abp_select_only((abpElementType.abp_SIGN, 0))
        abp_editor.abp_rotation_spin.setValue(90)
        assert abp_editor.abp_plan().abp_signs[0].abp_rotation_deg == 90
        abp_found = abp_editor.abp__find_node(QPointF(104, 98))
        assert abp_found is not None
        abp_editor.abp_view.abp_node_moved.emit(abp_found[0], QPointF(150, 120))
        assert abp_editor.abp_plan().abp_signs[0].abp_position == abpPoint(150, 120)
        abp_editor.abp_add_sign(abpSignKind.abp_CAPACITY, abpPoint(300, 200))
        abp_editor.abp_scene.abp_select_only((abpElementType.abp_SIGN, 1))
        abp_editor.abp_sign_text_edit.setText("25")
        abp_editor.abp__on_sign_text_edited()
        assert abp_editor.abp_plan().abp_signs[1].abp_text == "25"
        abp_editor.abp_delete([(abpElementType.abp_SIGN, 0)])
        assert len(abp_editor.abp_plan().abp_signs) == 1
        abp_editor.abp_undo_stack.undo()
        assert len(abp_editor.abp_plan().abp_signs) == 2
        abp_editor.abp_view.grab()
        abp_editor.abp_scene.abp_set_layer_visible(abpElementType.abp_SIGN, False)
        assert abp_editor.abp__sign_at(QPointF(300, 200)) is None

    def abp_test_signs_do_not_outdate_the_simulation(self, abp_services: abpAppServices) -> None:
        abp_project_id = abp_services.abp_projects.abp_create_project("X", abpUseType.abp_EDUCATION)
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_single_room())
        abp_scenario = abp_services.abp_simulations.abp_load_scenario(abp_project_id)
        abp_plan = abp_single_room()
        abp_signed = dataclasses.replace(
            abp_plan, abp_signs=(abpSign(abpSignKind.abp_EXIT, abpPoint(1, 1)),)
        )
        abp_before = abp_services.abp_simulations.abp_fingerprint(abp_plan, abp_scenario)
        assert abp_services.abp_simulations.abp_fingerprint(abp_signed, abp_scenario) == abp_before


def abp__text(abp_path: Path, abp_page: int = 0) -> str:
    with pymupdf.open(abp_path) as abp_doc:
        return str(abp_doc[abp_page].get_text())


class abpTestSheet:
    def abp__project(self, abp_services: abpAppServices, abp_plan: abpFloorPlan) -> int:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Colegio Lámina", abpUseType.abp_EDUCATION, "Jr. 1"
        )
        abp_services.abp_projects.abp_save_floor(
            abp_project_id, abp_plan, np.full((300, 600, 3), 240, np.uint8)
        )
        abp_scenario = abp_services.abp_simulations.abp_load_scenario(abp_project_id)
        abp_occupancies = tuple(
            abpOccupancy(abp_r.abp_name, "adulto", 20) for abp_r in abp_plan.abp_rooms
        )
        abp_services.abp_simulations.abp_save_scenario(
            abp_project_id, dataclasses.replace(abp_scenario, abp_occupancies=abp_occupancies)
        )
        return abp_project_id

    @pytest.mark.parametrize(("abp_paper", "abp_underlay"), [("A3", "original"), ("A4", "limpio")])
    def abp_test_single_floor(
        self, abp_services: abpAppServices, tmp_path: Path, abp_paper: str, abp_underlay: str
    ) -> None:
        abp_plan = dataclasses.replace(
            abp_two_rooms(), abp_safe_zones=(abpSafeZone(abp_rect(16, 2, 2, 2), "Zona de reunión"),)
        )
        abp_project_id = self.abp__project(abp_services, abp_plan)
        abp_options = abpSheetOptions(
            abp_paper=abp_paper,
            abp_underlay=abp_underlay,
            abp_people_source="ocupantes",
            abp_specialist="Ing. Ruiz",
            abp_identify="salida",
            abp_north_deg=30,
            abp_note="Nota de prueba",
        )
        abp_content = abp_services.abp_sheets.abp_content(abp_project_id, abp_options)
        abp_floor = abp_content.abp_floors[0]
        assert {abp_n.abp_people for abp_n in abp_floor.abp_notes} == {20}
        for abp_note in abp_floor.abp_notes:
            abp_expected = (
                abp_note.abp_people / (abp_note.abp_door_width_m * 1.3)
                + abp_note.abp_distance_m / 0.6
            )
            assert abp_note.abp_time_s == pytest.approx(abp_expected, abs=0.02)
        abp_worst = max(abp_n.abp_time_s for abp_n in abp_floor.abp_notes)
        assert abp_content.abp_routes[0].abp_time_s == abp_worst
        assert abp_content.abp_routes[0].abp_people == 40
        abp_path = abp_services.abp_sheets.abp_generate(
            abp_project_id, tmp_path / "lamina", abp_options
        )
        abp_text = abp__text(abp_path)
        for abp_piece in ("LEYENDA", "TIEMPOS DE EVACUACIÓN", "ING. RUIZ", "ES-01", "R1", "PRIMER"):
            assert abp_piece in abp_text.upper()
        assert "ruta más crítica" in abp_text
        assert "Nota de prueba" in abp_text
        assert "K = 1.3" in abp_text
        with pymupdf.open(abp_path) as abp_doc:
            abp_size = {"A3": 1190.55, "A4": 841.89}[abp_paper]
            assert abp_doc[0].rect.width == pytest.approx(abp_size, abs=1)

    def abp_test_capacity_source_and_fixed_scale(
        self, abp_services: abpAppServices, tmp_path: Path
    ) -> None:
        abp_project_id = self.abp__project(abp_services, abp_two_rooms())
        abp_options = abpSheetOptions(abp_scale=100)
        abp_content = abp_services.abp_sheets.abp_content(abp_project_id, abp_options)
        assert {abp_n.abp_people for abp_n in abp_content.abp_floors[0].abp_notes} == {24}
        assert "1/100" in abp__text(
            abp_services.abp_sheets.abp_generate(abp_project_id, tmp_path / "x.pdf", abp_options)
        )

    def abp_test_two_floors(self, abp_services: abpAppServices, tmp_path: Path) -> None:
        abp_stairs = (abpStair(abp_rect(7, 1, 2, 2), abp_name="Escalera A"),)
        abp_low = dataclasses.replace(abp_single_room(), abp_stairs=abp_stairs)
        abp_room = dataclasses.replace(abp_low.abp_rooms[0], abp_name="Aula 2")
        abp_high = dataclasses.replace(abp_low, abp_level=1, abp_rooms=(abp_room,))
        abp_project_id = self.abp__project(abp_services, abp_low)
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_high)
        abp_content = abp_services.abp_sheets.abp_content(abp_project_id, abpSheetOptions())
        assert len(abp_content.abp_floors) == 2
        abp_up = abp_content.abp_floors[1].abp_notes[0]
        abp_down = abp_content.abp_floors[0].abp_notes[0]
        assert abp_up.abp_exit_name == "Salida 1"
        assert abp_up.abp_distance_m > abp_down.abp_distance_m
        abp_path = abp_services.abp_sheets.abp_generate(
            abp_project_id, tmp_path / "dos.pdf", abpSheetOptions()
        )
        assert "SEGUNDO NIVEL" in abp__text(abp_path, 1)
        assert "ES-02" in abp__text(abp_path, 1)

    def abp_test_errors(self, abp_services: abpAppServices, tmp_path: Path) -> None:
        abp_empty = abp_services.abp_projects.abp_create_project("Vacío", abpUseType.abp_EDUCATION)
        with pytest.raises(abpUserFacingError, match="cargue el plano"):
            abp_services.abp_sheets.abp_generate(abp_empty, tmp_path / "a.pdf", abpSheetOptions())
        abp_pending = self.abp__project(abp_services, abp_single_room(abp_confirmed=False))
        with pytest.raises(abpUserFacingError, match="salidas confirmadas"):
            abp_services.abp_sheets.abp_content(abp_pending, abpSheetOptions())
        abp_no_rooms = self.abp__project(
            abp_services, dataclasses.replace(abp_single_room(), abp_rooms=())
        )
        with pytest.raises(abpUserFacingError, match="ambientes"):
            abp_services.abp_sheets.abp_content(abp_no_rooms, abpSheetOptions())

    def abp_test_helpers(self) -> None:
        assert abp_format_time(110.3) == "1 min 50 seg"
        assert abp_format_time(36.2) == "36 seg"
        assert abp_best_scale(10, 5, 1000, 1000) == 50
        assert abp_best_scale(5000, 5, 10, 10) == 1000

    def abp_test_dialog(self, qtbot: QtBot) -> None:
        abp_dialog = abpEvacuationSheetDialog(
            abp_specialist="Ana Pérez", abp_has_meeting_zone=False
        )
        qtbot.addWidget(abp_dialog)
        abp_options = abp_dialog.abp_options()
        assert (abp_options.abp_paper, abp_options.abp_scale, abp_options.abp_specialist) == (
            "A3",
            None,
            "Ana Pérez",
        )
        assert "NTP 399.010-1" in abp_options.abp_note
        abp_dialog.abp_paper_combo.setCurrentText("A1")
        abp_dialog.abp_scale_combo.setCurrentIndex(abp_dialog.abp_scale_combo.findData(75))
        abp_dialog.abp_speed_spin.setValue(0.8)
        abp_dialog.abp_people_combo.setCurrentIndex(1)
        abp_changed = abp_dialog.abp_options()
        assert (
            abp_changed.abp_paper,
            abp_changed.abp_scale,
            abp_changed.abp_speed,
            abp_changed.abp_people_source,
        ) == (
            "A1",
            75,
            0.8,
            "ocupantes",
        )
        abp_again = abpEvacuationSheetDialog(abp_previous=abp_changed)
        qtbot.addWidget(abp_again)
        assert abp_again.abp_options() == abp_changed
