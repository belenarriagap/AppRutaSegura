from __future__ import annotations

import dataclasses
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_plan_import import (
    abp__checked_scale,
    abp_rotate_point,
    abpLoadedPlan,
)
from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService as abp_P
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetOptions, abpSheetService
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpSafeZone, abpSign, abpWall
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan
from abp_rutasegura.abp_engines.abp_cad import abp_reader
from abp_rutasegura.abp_engines.abp_navigation.abp_evac_tree import abp_is_circulation
from abp_rutasegura.abp_engines.abp_vision.abp_layered import abp_has_layers
from abp_rutasegura.abp_engines.abp_vision.abp_symbols import abp_catalog, abp_find_signs
from abp_rutasegura.abp_presentation.abp_cad_import_dialog import abpCadImportDialog
from abp_rutasegura.abp_presentation.abp_evacuation_sheet_dialog import abpEvacuationSheetDialog
from abp_rutasegura.abp_presentation.abp_main_window import abp_STEP_EDIT, abpMainWindow
from abp_rutasegura.abp_presentation.abp_pdf_import_dialog import abpPdfImportDialog
from abp_tests.abp_fixtures.abp_cad_plans import abp_SIGNS, abp_write_dxf
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_two_rooms
from abp_tests.abp_fixtures.abp_vector_plans import abp_write_vector_plan, abpStyle


@pytest.fixture(scope="module")
def abp_dxf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return abp_write_dxf(tmp_path_factory.mktemp("cad") / "colegio.dxf")


@pytest.fixture(scope="module")
def abp_loaded(abp_dxf: Path) -> abpLoadedPlan:
    abp_pdf = abp_P.abp_cad_to_pdf(abp_dxf)
    abp_info = abp_P.abp_pdf_pages(abp_pdf)[0]
    return abp_P.abp_load_pdf_page(
        abp_pdf,
        0,
        abp_hidden_layers=abp_P.abp_suggested_hidden_layers(abp_info),
        abp_remove_colors=True,
    )


def abp__detected(abp_plan: abpLoadedPlan) -> abpFloorPlan:
    abp_start = abpFloorPlan(
        abp_scale_m_per_px=abp_plan.abp_scale_m_per_px, abp_signs=abp_plan.abp_signs
    )
    abp_found = abp_P.abp_detect(abp_plan.abp_image, abp_start, abp_vector=abp_plan.abp_vector)
    return abp_P.abp_detect_rooms(
        abp_found,
        abpUseType.abp_EDUCATION,
        "Ambiente {number}",
        abp_labels=abp_P.abp_room_labels(abp_plan.abp_vector),
    )


class abpTestCadReader:
    def abp_test_accepts_autocad_files(self, abp_dxf: Path) -> None:
        assert {".dwg", ".dxf"} <= set(abp_P.abp_supported_suffixes())
        assert abp_P.abp_is_cad(Path("X.DWG"))
        assert abp_P.abp_cad_sheets(abp_dxf) == ("L-01",)

    def abp_test_scale_comes_from_the_drawing(
        self, abp_dxf: Path, abp_loaded: abpLoadedPlan
    ) -> None:
        abp_vector = abp_loaded.abp_vector
        assert abp_vector is not None
        assert abp_vector.abp_exact_scale
        assert abp_vector.abp_scale_denominator == pytest.approx(50.0, rel=0.001)
        assert any("ESC" in abp_t.abp_text for abp_t in abp_vector.abp_texts)
        assert abp_loaded.abp_written_scale is None

    def abp_test_millimetres(self, tmp_path: Path) -> None:
        abp_path = abp_write_dxf(tmp_path / "mm.dxf", abp_units=1000.0)
        abp_page = abp_P.abp_pdf_pages(abp_P.abp_cad_to_pdf(abp_path))[0]
        assert abp_page.abp_scale_denominator == pytest.approx(50.0, rel=0.001)

    def abp_test_reads_walls_doors_exit_and_rooms(self, abp_loaded: abpLoadedPlan) -> None:
        assert abp_loaded.abp_vector is not None
        assert abp_has_layers(abp_loaded.abp_vector, abp_loaded.abp_scale_m_per_px or 1.0)
        abp_plan = abp__detected(abp_loaded)
        abp_rooms = {
            abp_r.abp_name: abp_plan.abp_area_m2(abp_r.abp_area) for abp_r in abp_plan.abp_rooms
        }
        assert set(abp_rooms) == {"Aula 1", "Aula 2", "Pasillo"}
        assert abp_rooms["Aula 1"] == pytest.approx(28.7, rel=0.08)
        assert len(abp_plan.abp_doors) == 2
        assert len(abp_plan.abp_exits) == 1
        abp_width = abp_plan.abp_exits[0].abp_segment.abp_length * (
            abp_plan.abp_scale_m_per_px or 1.0
        )
        assert abp_width == pytest.approx(1.4, abs=0.1)

    def abp_test_signs_are_blocks_explained_by_the_legend(self, abp_loaded: abpLoadedPlan) -> None:
        abp_kinds = Counter(abp_s.abp_kind for abp_s in abp_loaded.abp_signs)
        assert abp_kinds[abpSignKind.abp_EXTINGUISHER] == sum(
            abp_n == "EXTINTOR" for abp_n, abp__x, abp__y in abp_SIGNS
        )
        assert abp_kinds[abpSignKind.abp_EMERGENCY_LIGHT] == 1

    def abp_test_drawing_without_sheets(self, tmp_path: Path) -> None:
        abp_path = abp_write_dxf(tmp_path / "modelo.dxf", abp_layouts=0)
        assert abp_P.abp_cad_sheets(abp_path) == ("Model",)
        abp_page = abp_P.abp_pdf_pages(abp_P.abp_cad_to_pdf(abp_path))[0]
        assert max(abp_page.abp_width_mm, abp_page.abp_height_mm) == pytest.approx(804, abs=2)
        assert abp_page.abp_scale_denominator is not None

    def abp_test_several_sheets(self, tmp_path: Path) -> None:
        abp_path = abp_write_dxf(tmp_path / "dos.dxf", abp_layouts=2)
        assert abp_P.abp_cad_sheets(abp_path) == ("L-01", "L-02")
        assert len(abp_P.abp_pdf_pages(abp_P.abp_cad_to_pdf(abp_path, ["L-02"]))) == 1

    def abp_test_errors_are_explained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        abp_bad = tmp_path / "malo.dxf"
        abp_bad.write_text("no es un dxf", encoding="utf-8")
        with pytest.raises(abpUserFacingError, match="DXF"):
            abp_P.abp_cad_sheets(abp_bad)
        with pytest.raises(abpUserFacingError):
            abp_P.abp_cad_to_pdf(tmp_path / "no_existe.dxf")
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(abpUserFacingError, match="Guardar como"):
            abp_P.abp_cad_sheets(tmp_path / "plano.dwg")

    @pytest.mark.skipif(sys.platform != "win32", reason="el lector de DWG es de Windows")
    def abp_test_dwg(self, abp_dxf: Path, tmp_path: Path) -> None:
        abp_dwg = tmp_path / "colegio.dwg"
        abp_done = subprocess.run(
            [str(abp_reader.abp_TOOL), "--dwg", str(abp_dxf), str(abp_dwg)], check=False
        )
        assert abp_done.returncode == 0
        assert abp_P.abp_cad_sheets(abp_dwg) == ("L-01",)
        abp_pdf = abp_P.abp_cad_to_pdf(abp_dwg)
        abp_plan = abp_P.abp_load_pdf_page(abp_pdf, 0)
        assert abp_plan.abp_vector is not None
        assert abp_plan.abp_vector.abp_scale_denominator == pytest.approx(50.0, rel=0.001)
        assert len(abp__detected(abp_plan).abp_walls) >= 6
        abp_broken = tmp_path / "roto.dwg"
        abp_broken.write_bytes(b"AC1032" + b"\0" * 200)
        with pytest.raises(abpUserFacingError, match="No se pudo leer el DWG"):
            abp_P.abp_cad_sheets(abp_broken)


class abpTestScaleCheck:
    def abp_test_fixes_a_wrong_scale(self, abp_loaded: abpLoadedPlan) -> None:
        assert abp_loaded.abp_vector is not None
        abp_wrong = dataclasses.replace(
            abp_loaded.abp_vector, abp_scale_denominator=75.0, abp_exact_scale=False
        )
        abp_fixed, abp_written = abp__checked_scale(abp_wrong)
        assert abp_written == 75.0
        assert abp_fixed.abp_scale_denominator == pytest.approx(50.0, rel=0.06)

    def abp_test_leaves_a_right_scale(self, abp_loaded: abpLoadedPlan) -> None:
        assert abp_loaded.abp_vector is not None
        abp_right = dataclasses.replace(abp_loaded.abp_vector, abp_exact_scale=False)
        assert abp__checked_scale(abp_right) == (abp_right, None)


class abpTestRotation:
    def abp_test_four_turns_are_identity(self, abp_loaded: abpLoadedPlan) -> None:
        abp_turned = abp_loaded
        for _ in range(4):
            abp_turned = abp_P.abp_rotate(abp_turned, 1)
        assert np.array_equal(abp_turned.abp_image, abp_loaded.abp_image)
        assert abp_turned.abp_vector is not None
        assert abp_loaded.abp_vector is not None
        assert np.allclose(abp_turned.abp_vector.abp_segments, abp_loaded.abp_vector.abp_segments)
        for abp_a, abp_b in zip(abp_turned.abp_signs, abp_loaded.abp_signs, strict=True):
            assert abp_a.abp_position.abp_distance_to(abp_b.abp_position) < 1e-6
        assert abp_P.abp_rotate(abp_loaded, 0) is abp_loaded

    def abp_test_vector_matches_the_image(self, abp_loaded: abpLoadedPlan) -> None:
        abp_once = abp_P.abp_rotate(abp_loaded, 1)
        assert abp_once.abp_vector is not None
        abp_h, abp_w = abp_once.abp_image.shape[:2]
        assert (abp_once.abp_vector.abp_width, abp_once.abp_vector.abp_height) == pytest.approx(
            (abp_w, abp_h), abs=1.5
        )
        abp_plan = abp__detected(abp_once)
        assert {abp_r.abp_name for abp_r in abp_plan.abp_rooms} == {"Aula 1", "Aula 2", "Pasillo"}
        assert abp_P.abp_suggested_turns(abp_once) == 3
        assert abp_P.abp_suggested_turns(abp_loaded) == 0

    def abp_test_plan_and_arrows_turn(self) -> None:
        abp_plan = dataclasses.replace(
            abp_two_rooms(),
            abp_signs=(
                abpSign(abpSignKind.abp_DIRECTION, abpPoint(10, 20), 0.0),
                abpSign(abpSignKind.abp_EXIT, abpPoint(10, 20), 0.0),
            ),
            abp_safe_zones=(abpSafeZone(abp_rect(1, 1, 1, 1), "Z"),),
        )
        abp_turned = abp_P.abp_rotate_plan(abp_plan, (800, 400), 1)
        assert abp_turned.abp_signs[0].abp_position == abpPoint(380, 10)
        assert [abp_s.abp_rotation_deg for abp_s in abp_turned.abp_signs] == [90.0, 0.0]
        assert abp_turned.abp_area_m2(abp_turned.abp_rooms[0].abp_area) == pytest.approx(
            abp_plan.abp_area_m2(abp_plan.abp_rooms[0].abp_area)
        )
        abp_back = abp_P.abp_rotate_plan(abp_turned, (400, 800), 3)
        for abp_a, abp_b in zip(abp_back.abp_walls, abp_plan.abp_walls, strict=True):
            assert abp_a.abp_segment.abp_start.abp_distance_to(abp_b.abp_segment.abp_start) < 1e-6
        assert abp_rotate_point(abpPoint(0, 0), 10, 5, 2) == abpPoint(10, 5)


class abpTestCatalog:
    def abp_test_known_symbols_without_legend(self) -> None:
        abp_kinds = {abp_t.abp_kind for abp_t in abp_catalog()}
        assert {
            abpSignKind.abp_EXTINGUISHER,
            abpSignKind.abp_STRETCHER,
            abpSignKind.abp_SMOKE_DETECTOR,
        } <= abp_kinds
        abp_image = np.full((700, 1000, 3), 255, np.uint8)
        abp_wanted = ("extintor", "botiquin", "zona_segura", "prohibicion")
        for abp_k, abp_name in enumerate(abp_wanted):
            abp_template = next(
                abp_t for abp_t in abp_catalog() if abp_t.abp_kind.value == abp_name
            )
            abp_part = cv2.copyMakeBorder(
                abp_template.abp_image, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255)
            )
            abp_h, abp_w = abp_part.shape[:2]
            abp_image[200 : 200 + abp_h, 120 + 200 * abp_k : 120 + 200 * abp_k + abp_w] = abp_part
        abp_empty = abpVectorPlan(
            1000,
            700,
            200.0,
            (),
            np.zeros((0, 4)),
            np.zeros(0, np.int64),
            np.zeros(0, np.bool_),
            np.zeros((0, 5)),
            np.zeros(0, np.int64),
        )
        abp_found = Counter(
            abp_s.abp_kind.value for abp_s in abp_find_signs(abp_image, abp_empty).abp_signs
        )
        assert abp_found == Counter(abp_wanted)

    def abp_test_route_badges_are_not_signs(self) -> None:
        abp_image = np.full((400, 600, 3), 255, np.uint8)
        for abp_x in (100, 250, 400):
            cv2.circle(abp_image, (abp_x, 200), 26, (230, 0, 0), 3)
            cv2.putText(abp_image, "1", (abp_x - 8, 210), 0, 0.9, (230, 0, 0), 2)
        abp_empty = abpVectorPlan(
            600,
            400,
            200.0,
            (),
            np.zeros((0, 4)),
            np.zeros(0, np.int64),
            np.zeros(0, np.bool_),
            np.zeros((0, 5)),
            np.zeros(0, np.int64),
        )
        assert abp_find_signs(abp_image, abp_empty).abp_signs == ()


class abpTestSheet:
    @staticmethod
    def abp__project(abp_services: abpAppServices) -> int:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Colegio", abpUseType.abp_EDUCATION
        )
        abp_base = abp_two_rooms()
        abp_south = abpExit(abp_base.abp_exits[0].abp_segment, "Salida principal")
        abp_plan = dataclasses.replace(
            abp_base,
            abp_exits=(abp_south, *abp_base.abp_exits[1:]),
            abp_safe_zones=(
                abpSafeZone(abp_rect(16, 2, 2, 2), "Zona 1"),
                abpSafeZone(abp_rect(16, 6, 2, 2), "Zona 2"),
            ),
        )
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
        abp_scenario = abp_services.abp_simulations.abp_load_scenario(abp_project_id)
        abp_services.abp_simulations.abp_save_scenario(
            abp_project_id,
            dataclasses.replace(
                abp_scenario,
                abp_occupancies=tuple(
                    abpOccupancy(abp_r.abp_name, "adulto", 20) for abp_r in abp_plan.abp_rooms
                ),
            ),
        )
        return abp_project_id

    @pytest.mark.parametrize(
        ("abp_orientation", "abp_tables", "abp_width"),
        [("vertical", "auto", 841.89), ("horizontal", "abajo", 1190.55), ("auto", "auto", None)],
    )
    def abp_test_orientation_and_tables(
        self,
        abp_services: abpAppServices,
        tmp_path: Path,
        abp_orientation: str,
        abp_tables: str,
        abp_width: float | None,
    ) -> None:
        abp_project_id = self.abp__project(abp_services)
        abp_options = abpSheetOptions(
            abp_orientation=abp_orientation, abp_tables=abp_tables, abp_people_source="ocupantes"
        )
        abp_content = abp_services.abp_sheets.abp_content(abp_project_id, abp_options)
        assert [abp_r.abp_route_id for abp_r in abp_content.abp_routes] == ["R1", "R2"]
        assert {abp_r.abp_room_name for abp_r in abp_content.abp_routes} == {
            abp_r.abp_name for abp_r in abp_content.abp_floors[0].abp_plan.abp_rooms
        }
        assert sum(abp_z.abp_people for abp_z in abp_content.abp_zones) == 40
        abp_path = abp_services.abp_sheets.abp_generate(
            abp_project_id, tmp_path / "l.pdf", abp_options
        )
        with pymupdf.open(abp_path) as abp_doc:
            abp_text = abp_doc[0].get_text()
            if abp_width is not None:
                assert abp_doc[0].rect.width == pytest.approx(abp_width, abs=1)
        assert "LEYENDA" in abp_text
        assert "ZONAS DE REUNIÓN" in abp_text

    def abp_test_chosen_exit(self) -> None:
        abp_base = abp_two_rooms()
        abp_west = abp_base.abp_walls[2].abp_segment
        abp_x, abp_third = abp_west.abp_start.abp_x, abp_west.abp_length / 3
        abp_y = min(abp_west.abp_start.abp_y, abp_west.abp_end.abp_y)
        abp_far = abpExit(
            abpSegment(abpPoint(abp_x, abp_y + abp_third), abpPoint(abp_x, abp_y + 2 * abp_third)),
            "Otra",
        )
        abp_ends = ((abp_y, abp_y + abp_third), (abp_y + 2 * abp_third, abp_y + 3 * abp_third))
        abp_pieces = tuple(
            abpWall(abpSegment(abpPoint(abp_x, abp_a), abpPoint(abp_x, abp_b)))
            for abp_a, abp_b in abp_ends
        )
        abp_walls = (*abp_base.abp_walls[:2], *abp_base.abp_walls[3:], *abp_pieces)
        abp_plan = dataclasses.replace(
            abp_base, abp_walls=abp_walls, abp_exits=(*abp_base.abp_exits, abp_far)
        )
        abp_auto = abpSheetService.abp_network(abp_plan, {})
        abp_room = abp_plan.abp_rooms[0].abp_name
        abp_used = {abp_e.abp_room_name: abp_e.abp_target_name for abp_e in abp_auto.abp_escapes}
        abp_other = next(
            abp_e.abp_name for abp_e in abp_plan.abp_exits if abp_e.abp_name != abp_used[abp_room]
        )
        abp_rooms = tuple(
            dataclasses.replace(
                abp_r, abp_exit_name=abp_other if abp_r.abp_name == abp_room else ""
            )
            for abp_r in abp_plan.abp_rooms
        )
        abp_chosen = abpSheetService.abp_network(
            dataclasses.replace(abp_plan, abp_rooms=abp_rooms), {}
        )
        assert {abp_e.abp_room_name: abp_e.abp_target_name for abp_e in abp_chosen.abp_escapes}[
            abp_room
        ] == abp_other

    def abp_test_dialog_and_window_keep_the_choice(
        self, qtbot: QtBot, abp_services: abpAppServices
    ) -> None:
        abp_dialog = abpEvacuationSheetDialog(
            abp_rooms=[("Aula 1", ""), ("Aula 2", "B")], abp_exits=["A", "B"]
        )
        qtbot.addWidget(abp_dialog)
        assert abp_dialog.abp_exit_choices() == {"Aula 1": "", "Aula 2": "B"}
        abp_dialog.abp_set_exit("Aula 1", "A")
        abp_dialog.abp_orientation_combo.setCurrentIndex(2)
        abp_dialog.abp_identify_combo.setCurrentIndex(1)
        abp_options = abp_dialog.abp_options()
        assert (abp_options.abp_orientation, abp_options.abp_identify) == ("vertical", "salida")
        assert abp_dialog.abp_exit_choices()["Aula 1"] == "A"
        abp_alone = abpEvacuationSheetDialog(abp_rooms=[("Aula 1", "")], abp_exits=["A"])
        qtbot.addWidget(abp_alone)
        assert abp_alone.abp_exit_choices() == {}

        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_project_id = self.abp__project(abp_services)
        abp_window.abp_open_project(abp_project_id)
        abp_name = abp_window.abp_plan.abp_rooms[0].abp_name
        abp_fingerprint = abp_services.abp_simulations.abp_fingerprint(
            abp_window.abp_plan, abp_window.abp_rooms_page.abp_scenario
        )
        abp_window.abp__on_exits_chosen({abp_name: "Salida principal"})
        abp_saved = abp_services.abp_projects.abp_load_floor(abp_project_id)
        assert abp_saved is not None
        assert abp_saved.abp_rooms[0].abp_exit_name == "Salida principal"
        assert abp_fingerprint == abp_services.abp_simulations.abp_fingerprint(
            abp_saved, abp_window.abp_rooms_page.abp_scenario
        )

    def abp_test_circulation(self) -> None:
        assert abp_is_circulation("Pasillo (2)")
        assert abp_is_circulation("Hall escalera")
        assert not abp_is_circulation("Laboratorio de cómputo")


class abpTestWindows:
    def abp_test_one_sheet_converts_at_once(self, qtbot: QtBot, abp_dxf: Path) -> None:
        abp_dialog = abpCadImportDialog(abp_P(), abp_dxf)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(lambda: abp_dialog.abp_pdf_path is not None, timeout=60_000)
        assert abp_dialog.abp_pdf_path is not None
        assert abp_dialog.abp_pdf_path.name == "colegio.pdf"

    def abp_test_choose_sheets(self, qtbot: QtBot, tmp_path: Path) -> None:
        abp_path = abp_write_dxf(tmp_path / "dos.dxf", abp_layouts=2)
        abp_dialog = abpCadImportDialog(abp_P(), abp_path)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(abp_dialog.abp_ok_button.isEnabled, timeout=60_000)
        assert abp_dialog.abp_chosen() == ("L-01",)
        abp_dialog.abp_check_all()
        abp_dialog.abp_convert()
        qtbot.waitUntil(lambda: abp_dialog.abp_pdf_path is not None, timeout=60_000)
        assert abp_dialog.abp_pdf_path is not None
        assert len(abp_P.abp_pdf_pages(abp_dialog.abp_pdf_path)) == 2

    def abp_test_bad_file(self, qtbot: QtBot, tmp_path: Path) -> None:
        abp_bad = tmp_path / "malo.dxf"
        abp_bad.write_text("nada", encoding="utf-8")
        abp_dialog = abpCadImportDialog(abp_P(), abp_bad)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(lambda: bool(abp_dialog.abp_error_message), timeout=60_000)
        assert "DXF" in abp_dialog.abp_status_label.text()

    def abp_test_import_dialog_rotates(self, qtbot: QtBot, tmp_path: Path) -> None:
        abp_pdf = abp_write_vector_plan(tmp_path / "p.pdf", abp_style=abpStyle())
        abp_dialog = abpPdfImportDialog(abp_P(), abp_pdf)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(abp_dialog.abp_ok_button.isEnabled, timeout=60_000)
        abp_before = abp_dialog.abp_result_plan()
        abp_dialog.abp_rotate(1)
        abp_after = abp_dialog.abp_result_plan()
        assert abp_before is not None
        assert abp_after is not None
        abp_h, abp_w = abp_before.abp_image.shape[:2]
        assert abp_after.abp_image.shape[:2] == pytest.approx((abp_w, abp_h), abs=2)
        abp_dialog.abp_rotate(3)
        abp_again = abp_dialog.abp_result_plan()
        assert abp_again is not None
        assert abp_again.abp_image.shape[:2] == pytest.approx((abp_h, abp_w), abs=2)

    def abp_test_editor_rotates_the_plan(
        self, qtbot: QtBot, abp_services: abpAppServices, abp_dxf: Path, abp_loaded: abpLoadedPlan
    ) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_project_id = abp_window.abp_create_project("Giro", abpUseType.abp_EDUCATION)
        assert abp_project_id is not None
        abp_window.abp_load_page.abp_use_plan(abp_dxf, 0, 1, abp_loaded)
        with qtbot.waitSignal(abp_window.abp_editor_page.abp_detection_finished, timeout=60_000):
            abp_window.abp_go_to_step(abp_STEP_EDIT)
        abp_window.abp_editor_page.abp_editor.abp_confirm_kind(abpElementType.abp_EXIT)
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]
        abp_window.abp_editor_page.abp_rotate_button.click()
        abp_saved = abp_services.abp_projects.abp_load_floor(abp_project_id)
        assert abp_saved is not None
        abp_image = abp_services.abp_projects.abp_load_floor_image(abp_saved)
        assert abp_image is not None
        assert abp_image.shape[:2] == (abp_w, abp_h)
        abp_vector = abp_services.abp_projects.abp_load_floor_vector(abp_saved)
        assert abp_vector is not None
        assert abp_vector.abp_width == pytest.approx(abp_h, abs=1.5)
        abp_rooms = abp_P.abp_detect_rooms(abp_saved, abpUseType.abp_EDUCATION, "A {number}")
        assert len(abp_rooms.abp_rooms) == 3
