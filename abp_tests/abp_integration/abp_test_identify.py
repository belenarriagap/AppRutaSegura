from __future__ import annotations

import dataclasses
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_identify import (
    abp_accept_door,
    abp_confirm,
    abp_convert,
    abp_identify,
    abp_pending,
    abp_review_items,
)
from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService as abp_P
from abp_rutasegura.abp_application.abp_serialization import abp_plan_from_dict, abp_plan_to_dict
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpCellType, abpElementType, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpStair,
    abpWall,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid
from abp_rutasegura.abp_engines.abp_vision.abp_auto import abp_detect_auto
from abp_rutasegura.abp_engines.abp_vision.abp_metrics import abp_opening_score, abp_wall_score
from abp_rutasegura.abp_engines.abp_vision.abp_obstacles import abp_detect_obstacles
from abp_rutasegura.abp_engines.abp_vision.abp_openings import (
    abp_classify,
    abp_complete_openings,
    abp_opening_near,
)
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_polyline_arcs, abp_read_vector
from abp_rutasegura.abp_engines.abp_vision.abp_quality import abp_assess
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import abp_scale_from_dimensions
from abp_rutasegura.abp_engines.abp_vision.abp_vectorize import abp_vectorize
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpTool
from abp_rutasegura.abp_presentation.abp_main_window import abp_STEP_LOAD, abpMainWindow
from abp_rutasegura.abp_presentation.abp_wizard_pages import abpLoadPlanPage
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp_rect,
    abp_SCALE,
    abp_single_room,
    abp_two_rooms,
)
from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan
from abp_tests.abp_fixtures.abp_vector_plans import (
    abp_DENOMINATOR,
    abp_write_scanned_plan,
    abp_write_vector_plan,
    abpStyle,
)

abp_SCAN_SCALE = 0.0254 / 200 * abp_DENOMINATOR


def abp__summary(abp_plan: abpFloorPlan) -> tuple[list[float], list[float], list[float]]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_rooms = abp_P.abp_detect_rooms(abp_plan, abpUseType.abp_EDUCATION, "A {number}").abp_rooms
    return (
        sorted(round(abp_d.abp_segment.abp_length * abp_scale, 2) for abp_d in abp_plan.abp_doors),
        [round(abp_e.abp_segment.abp_length * abp_scale, 2) for abp_e in abp_plan.abp_exits],
        sorted(round(abp_plan.abp_area_m2(abp_r.abp_area), 1) for abp_r in abp_rooms),
    )


class abpTestDrawingStyles:
    @pytest.mark.parametrize(
        "abp_style",
        [
            abpStyle(),
            abpStyle(abp_walls="relleno"),
            abpStyle(abp_walls="trazo"),
            abpStyle(abp_polyline_arcs=True),
            abpStyle(abp_angle_deg=15),
            abpStyle(abp_stairs=True),
            abpStyle(abp_labels=False),
            abpStyle(
                abp_walls="relleno", abp_polyline_arcs=True, abp_angle_deg=-8, abp_stairs=True
            ),
        ],
        ids=["doble", "relleno", "trazo", "arcos", "girado", "escalera", "sin_rotulos", "todo"],
    )
    def abp_test_vector_styles(self, tmp_path: Path, abp_style: abpStyle) -> None:
        abp_path = abp_write_vector_plan(tmp_path / "p.pdf", abp_style=abp_style)
        abp_loaded = abp_P.abp_load_pdf_page(
            abp_path, 0, abp_hidden_layers=["MOBILIARIO"], abp_remove_colors=True
        )
        abp_plan = abp_P.abp_detect(
            abp_loaded.abp_image,
            abpFloorPlan(abp_scale_m_per_px=abp_loaded.abp_scale_m_per_px),
            abp_vector=abp_loaded.abp_vector,
        )
        abp_doors, abp_exits, abp_rooms = abp__summary(abp_plan)
        assert abp_doors == pytest.approx([0.9, 0.9], abs=0.04)
        assert abp_exits == pytest.approx([1.2], abs=0.04)
        assert abp_rooms == pytest.approx([17.5, 23.2, 23.2], abs=1.2)
        assert len(abp_plan.abp_obstacles) == 4
        assert not any(abp_o.abp_confirmed for abp_o in abp_plan.abp_obstacles)
        assert len(abp_plan.abp_stairs) == int(abp_style.abp_stairs)

    @pytest.mark.parametrize("abp_walls", ["doble", "relleno"])
    def abp_test_scanned_pdf(self, tmp_path: Path, abp_walls: str) -> None:
        abp_path = abp_write_scanned_plan(
            tmp_path / "e.pdf", abp_style=abpStyle(abp_walls=abp_walls)
        )
        assert not abp_P.abp_pdf_pages(abp_path)[0].abp_is_vector
        abp_loaded = abp_P.abp_load_pdf_page(abp_path, 0)
        assert abp_loaded.abp_vector is None
        abp_plan = abp_P.abp_detect(
            abp_loaded.abp_image, abpFloorPlan(abp_scale_m_per_px=abp_SCAN_SCALE)
        )
        abp_doors, abp_exits, abp_rooms = abp__summary(abp_plan)
        assert abp_doors == pytest.approx([0.9, 0.9], abs=0.05)
        assert abp_exits == pytest.approx([1.2], abs=0.05)
        assert abp_rooms == pytest.approx([17.5, 23.2, 23.2], abs=1.2)

    def abp_test_scale_from_dimensions(self, tmp_path: Path) -> None:
        abp_style = abpStyle(abp_dimensions=True)
        abp_path = abp_write_vector_plan(
            tmp_path / "c.pdf", abp_scale_text=False, abp_style=abp_style
        )
        abp_vector = abp_read_vector(abp_path, 0)
        assert abp_vector is not None
        assert abp_vector.abp_scale_denominator is None
        assert abp_scale_from_dimensions(abp_vector) == abp_DENOMINATOR
        assert abp_P.abp_sheet_scale(abp_vector) == pytest.approx(
            0.0254 / abp_vector.abp_dpi * abp_DENOMINATOR
        )
        assert abp_P.abp_sheet_scale(None) is None
        abp_bare = abp_read_vector(
            abp_write_vector_plan(tmp_path / "s.pdf", abp_scale_text=False), 0
        )
        assert abp_P.abp_sheet_scale(abp_bare) is None

    def abp_test_password(self, tmp_path: Path) -> None:
        abp_path = tmp_path / "clave.pdf"
        abp_doc = pymupdf.open()
        abp_doc.new_page()
        abp_doc.save(abp_path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
        abp_doc.close()
        with pytest.raises(abpUserFacingError, match="contraseña"):
            abp_P.abp_pdf_pages(abp_path)

    def abp_test_polyline_arcs(self) -> None:
        abp_t = np.linspace(0, np.pi / 2, 13)
        abp_arc = np.c_[100 + 50 * np.cos(abp_t), 100 + 50 * np.sin(abp_t)]
        abp_line = np.array([[300.0, 100.0], [250.0, 100.0], [200.0, 100.0]])
        abp_found = abp_polyline_arcs(np.vstack([abp_line, abp_arc]))
        assert len(abp_found) == 1
        assert abp_found[0][2][2] == pytest.approx(50, abs=1)
        assert abp_polyline_arcs(abp_line) == []


class abpTestImages:
    @pytest.mark.parametrize("abp_seed", [1, 4, 7])
    @pytest.mark.parametrize("abp_furnished", [False, True])
    def abp_test_synthetic_plans_keep_their_precision(
        self, abp_seed: int, abp_furnished: bool
    ) -> None:
        abp_truth = abp_generate_plan(abp_seed, abp_furnished=abp_furnished)
        abp_found = abp_detect_auto(
            abp_truth.abp_image, abp_scale_m_per_px=abp_truth.abp_scale_m_per_px
        )
        abp_tol = abp_truth.abp_wall_thickness_px
        abp_walls = abp_wall_score(
            [abp_w.abp_segment for abp_w in abp_found.abp_walls], abp_truth.abp_walls, abp_tol
        )
        assert abp_walls.abp_precision >= 0.95
        assert abp_walls.abp_recall >= 0.95
        abp_exits = abp_opening_score(
            [abp_e.abp_segment for abp_e in abp_found.abp_exits], abp_truth.abp_exits, abp_tol
        )
        assert (abp_exits.abp_precision, abp_exits.abp_recall) == (1.0, 1.0)

    def abp_test_without_scale(self) -> None:
        abp_truth = abp_generate_plan(1)
        abp_found = abp_detect_auto(abp_truth.abp_image, abp_scale_m_per_px=None)
        assert abp_found.abp_walls
        assert abp_found.abp_obstacles == ()

    def abp_test_vectorize_finds_lines_and_arcs(self) -> None:
        abp_image = np.full((400, 400, 3), 255, np.uint8)
        cv2.line(abp_image, (20, 20), (380, 20), (0, 0, 0), 2)
        cv2.ellipse(abp_image, (200, 200), (90, 90), 0, 0, 90, (0, 0, 0), 2)
        abp_vector = abp_vectorize(abp_image)
        assert len(abp_vector.abp_segments) > 2
        assert any(
            abs(abp_a[2] - 90) < 4 and abs(abp_a[0] - 200) < 5 for abp_a in abp_vector.abp_arcs
        )
        assert len(abp_vectorize(np.full((50, 50, 3), 255, np.uint8)).abp_segments) == 0


class abpTestOpenings:
    def abp_test_completes_sliding_doors_and_entrances(self) -> None:
        abp_walls = np.array(
            [
                [0, 0, 10, 0],
                [0, 0, 0, 8],
                [10, 0, 10, 8],
                [0, 8, 4, 8],
                [6, 8, 10, 8],
                [0, 4, 4, 4],
                [5.5, 4, 10, 4],
            ],
            np.float64,
        )
        abp_threshold = np.array([[4, 4, 5.5, 4.0]])
        abp_found = abp_complete_openings(abp_walls, [], abp_threshold, np.zeros((0, 7)))
        abp_spans = sorted(
            round(float(np.hypot(abp_s[2] - abp_s[0], abp_s[3] - abp_s[1])), 1)
            for abp_s, abp__c in abp_found
        )
        assert abp_spans == [1.5, 2.0]
        abp_openings = abp_classify(abp_walls, abp_found)
        assert [
            round(float(abp_o.abp_segment[1]), 0) for abp_o in abp_openings if abp_o.abp_outside
        ] == [8.0]
        assert (
            abp_complete_openings(
                abp_walls, [abp_s for abp_s, abp__c in abp_found], abp_threshold, np.zeros((0, 7))
            )
            == []
        )
        assert abp_complete_openings(abp_walls[:1], [], abp_threshold, np.zeros((0, 7))) == []

    def abp_test_windows_are_not_doors(self) -> None:
        abp_walls = np.array(
            [[0, 0, 4, 0], [6, 0, 10, 0], [0, 0, 0, 5], [10, 0, 10, 5], [0, 5, 10, 5]]
        )
        abp_window = np.array([[4, -0.1, 6, -0.1], [4, 0.0, 6, 0.0], [4, 0.1, 6, 0.1]])
        abp_found = abp_complete_openings(
            abp_walls.astype(np.float64), [], abp_window, np.zeros((0, 7))
        )
        assert abp_found == []

    def abp_test_opening_near(self) -> None:
        abp_walls = [(0.0, 0.0, 200.0, 0.0), (250.0, 0.0, 500.0, 0.0)]
        abp_gap = abp_opening_near(abp_walls, (225, 5), abp_SCALE)
        assert abp_gap is not None
        assert sorted((abp_gap[0], abp_gap[2])) == [200.0, 250.0]
        assert abp_opening_near(abp_walls, (225, 400), abp_SCALE) is None
        assert abp_opening_near([], (0, 0), abp_SCALE) is None

    def abp_test_quality(self) -> None:
        abp_plan = abp_two_rooms()
        abp_openings = [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
            abp_e.abp_segment for abp_e in abp_plan.abp_exits
        ]
        abp_good = abp_assess(
            [abp_w.abp_segment for abp_w in abp_plan.abp_walls], abp_openings, abp_SCALE
        )
        assert abp_good.abp_rooms == 2
        assert abp_good.abp_dangling == 0
        abp_doubled = [
            *(abp_w.abp_segment for abp_w in abp_plan.abp_walls),
            *(
                abpSegment(
                    abpPoint(
                        abp_w.abp_segment.abp_start.abp_x + 10,
                        abp_w.abp_segment.abp_start.abp_y + 10,
                    ),
                    abpPoint(
                        abp_w.abp_segment.abp_end.abp_x + 10, abp_w.abp_segment.abp_end.abp_y + 10
                    ),
                )
                for abp_w in abp_plan.abp_walls
            ),
        ]
        assert abp_assess(abp_doubled, abp_openings, abp_SCALE).abp_score < abp_good.abp_score
        assert abp_assess([], [], abp_SCALE).abp_rooms == 0


def abp__furnished() -> tuple[abpFloorPlan, np.ndarray]:
    abp_plan = abp_single_room()
    abp_image = np.full((320, 520, 3), 255, np.uint8)
    cv2.rectangle(abp_image, (150, 100), (250, 150), (60, 60, 60), 2)
    cv2.rectangle(abp_image, (350, 220), (368, 238), (60, 60, 60), 1)
    cv2.putText(abp_image, "AULA", (300, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return abp_plan, abp_image


class abpTestObstacles:
    def abp_test_detects_table_only(self) -> None:
        abp_plan, abp_image = abp__furnished()
        abp_shapes = abp_detect_obstacles(abp_plan, abp_image=abp_image)
        assert len(abp_shapes) == 1
        assert abp_plan.abp_area_m2(abp_shapes[0]) == pytest.approx(2.0, abs=0.35)
        assert abp_detect_obstacles(abpFloorPlan(), abp_image=abp_image) == ()
        assert abp_detect_obstacles(abp_plan) == ()

    def abp_test_unconfirmed_obstacles_do_not_block(self) -> None:
        abp_plan = abp_single_room()
        abp_table = abp_rect(2, 2, 2, 2)
        abp_free = abp_build_grid(
            dataclasses.replace(
                abp_plan, abp_obstacles=(abpObstacle(abp_table, abp_confirmed=False),)
            )
        )
        assert not (abp_free.abp_cells == int(abpCellType.abp_OBSTACLE)).any()
        abp_solid = abp_build_grid(
            dataclasses.replace(abp_plan, abp_obstacles=(abpObstacle(abp_table),))
        )
        assert (abp_solid.abp_cells == int(abpCellType.abp_OBSTACLE)).any()

    def abp_test_persistence(self, abp_services: abpAppServices) -> None:
        abp_plan = dataclasses.replace(
            abp_single_room(),
            abp_obstacles=(
                abpObstacle(abp_rect(1, 1, 1, 1), abp_confirmed=False),
                abpObstacle(abp_rect(4, 1, 1, 1)),
            ),
        )
        abp_project_id = abp_services.abp_projects.abp_create_project("X", abpUseType.abp_EDUCATION)
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
        abp_loaded = abp_services.abp_projects.abp_load_floor(abp_project_id)
        assert abp_loaded is not None
        assert [abp_o.abp_confirmed for abp_o in abp_loaded.abp_obstacles] == [False, True]
        abp_again = abp_plan_from_dict(abp_plan_to_dict(abp_plan))
        assert [abp_o.abp_confirmed for abp_o in abp_again.abp_obstacles] == [False, True]


class abpTestIdentify:
    def abp_test_click_on_a_table(self) -> None:
        abp_plan, abp_image = abp__furnished()
        abp_new = abp_identify(
            abp_plan, abpPoint(200, 125), abpElementType.abp_OBSTACLE, abp_image=abp_image
        )
        assert abp_new is not None
        assert len(abp_new.abp_obstacles) == 1
        abp_stair = abp_identify(
            abp_new, abpPoint(200, 125), abpElementType.abp_STAIR, abp_image=abp_image
        )
        assert abp_stair is not None
        assert (len(abp_stair.abp_obstacles), abp_stair.abp_stairs[0].abp_name) == (0, "Escalera A")
        assert (
            abp_identify(
                abp_plan, abpPoint(60, 60), abpElementType.abp_OBSTACLE, abp_image=abp_image
            )
            is None
        )
        assert (
            abp_identify(abp_plan, abpPoint(60, 60), abpElementType.abp_WALL, abp_image=abp_image)
            is None
        )

    def abp_test_click_on_openings(self) -> None:
        abp_plan = abp_two_rooms()
        abp_door = abp_plan.abp_doors[0].abp_segment.abp_midpoint
        abp_changed = abp_identify(abp_plan, abp_door, abpElementType.abp_EXIT)
        assert abp_changed is not None
        assert (len(abp_changed.abp_doors), len(abp_changed.abp_exits)) == (0, 2)
        assert len({abp_e.abp_name for abp_e in abp_changed.abp_exits}) == 2
        abp_without = dataclasses.replace(abp_plan, abp_doors=())
        abp_added = abp_identify(abp_without, abp_door, abpElementType.abp_DOOR)
        assert abp_added is not None
        assert abp_added.abp_doors[0].abp_segment.abp_length * abp_SCALE == pytest.approx(
            0.9, abs=0.05
        )
        assert abp_identify(abp_without, abpPoint(100, 100), abpElementType.abp_DOOR) is None

    def abp_test_convert_and_confirm(self) -> None:
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=abp_SCALE,
            abp_walls=(abpWall(abpSegment(abpPoint(0, 0), abpPoint(300, 0))),),
            abp_exits=(
                abpExit(
                    abpSegment(abpPoint(300, 0), abpPoint(350, 0)), "Salida 1", abp_confirmed=False
                ),
            ),
            abp_stairs=(abpStair(abp_rect(1, 1, 2, 2), abp_confirmed=False),),
            abp_obstacles=(abpObstacle(abp_rect(4, 1, 1, 1), abp_confirmed=False),),
            abp_doors=(abpDoor(abpSegment(abpPoint(400, 0), abpPoint(445, 0)), 0.5),),
        )
        assert len(abp_pending(abp_plan)) == 3
        abp_kinds = [abp_item.abp_ref[0] for abp_item in abp_review_items(abp_plan)]
        assert abp_kinds == [
            abpElementType.abp_EXIT,
            abpElementType.abp_STAIR,
            abpElementType.abp_DOOR,
            abpElementType.abp_OBSTACLE,
        ]
        abp_done = abp_confirm(abp_plan, abp_pending(abp_plan))
        assert abp_pending(abp_done) == []
        assert abp_done.abp_stairs[0].abp_name == "Escalera A"
        assert abp_accept_door(abp_done, 0).abp_doors[0].abp_confidence == 1.0
        abp_wall = abp_convert(abp_plan, (abpElementType.abp_EXIT, 0), abpElementType.abp_WALL)
        assert (len(abp_wall.abp_walls), len(abp_wall.abp_exits)) == (2, 0)
        abp_opened = abp_convert(abp_plan, (abpElementType.abp_WALL, 0), abpElementType.abp_DOOR)
        assert len(abp_opened.abp_doors) == 2
        abp_zone = abp_convert(
            abp_plan, (abpElementType.abp_OBSTACLE, 0), abpElementType.abp_SAFE_ZONE
        )
        assert len(abp_zone.abp_safe_zones) == 1
        with pytest.raises(ValueError, match="no se puede"):
            abp_convert(abp_plan, (abpElementType.abp_OBSTACLE, 0), abpElementType.abp_DOOR)


class abpTestEditor:
    def abp__editor(self, qtbot: QtBot) -> abpPlanEditor:
        abp_editor = abpPlanEditor()
        qtbot.addWidget(abp_editor)
        abp_plan, abp_image = abp__furnished()
        abp_plan = dataclasses.replace(
            abp_plan,
            abp_exits=(dataclasses.replace(abp_plan.abp_exits[0], abp_confirmed=False),),
            abp_obstacles=tuple(
                abpObstacle(abp_rect(abp_x, 4, 0.6, 0.6), abp_confirmed=False)
                for abp_x in (1, 3, 5)
            ),
            abp_stairs=(abpStair(abp_rect(7, 1, 1.5, 2), abp_confirmed=False),),
        )
        abp_editor.abp_set_plan(abp_plan, abp_image)
        abp_editor.abp_set_sources(abp_image, None)
        return abp_editor

    def abp_test_identify_tool(self, qtbot: QtBot) -> None:
        abp_editor = self.abp__editor(qtbot)
        abp_editor.abp_set_tool(abpTool.abp_IDENTIFY)
        assert abp_editor.abp_identify_combo_action.isVisible()
        abp_notices: list[str] = []
        abp_editor.abp_notice.connect(abp_notices.append)
        abp_editor.abp_view.abp_point_picked.emit(QPointF(200, 125))
        assert len(abp_editor.abp_plan().abp_obstacles) == 4
        assert abp_notices[-1] == "Marcado como obstáculo."
        abp_editor.abp_view.abp_point_picked.emit(QPointF(300, 180))
        assert "no se reconoce" in abp_notices[-1]
        abp_errors: list[str] = []
        abp_editor.abp_error.connect(abp_errors.append)
        abp_editor.abp_set_plan(
            dataclasses.replace(abp_editor.abp_plan(), abp_scale_m_per_px=None), None
        )
        assert not abp_editor.abp_identify_at(abpPoint(1, 1), abpElementType.abp_OBSTACLE)
        assert "escala" in abp_errors[0]

    def abp_test_guided_review(self, qtbot: QtBot) -> None:
        abp_editor = self.abp__editor(qtbot)
        assert "propuestos" in abp_editor.abp_pending_label.text()
        abp_editor.abp_start_review()
        abp_bar = abp_editor.abp_review_bar
        assert not abp_bar.isHidden()
        assert "salida" in abp_bar.abp_question_label.text()
        assert abp_bar.abp_no_button.text() == "No, es muro"
        abp_walls = len(abp_editor.abp_plan().abp_walls)
        abp_bar.abp_answered.emit("no")
        assert (len(abp_editor.abp_plan().abp_exits), len(abp_editor.abp_plan().abp_walls)) == (
            0,
            abp_walls + 1,
        )
        assert "escalera" in abp_bar.abp_question_label.text()
        abp_bar.abp_answered.emit("obstaculo")
        assert (
            len(abp_editor.abp_plan().abp_stairs),
            len(abp_editor.abp_plan().abp_obstacles),
        ) == (0, 4)
        assert not abp_bar.abp_all_button.isHidden()
        abp_bar.abp_answered.emit("saltar")
        abp_bar.abp_answered.emit("no")
        assert len(abp_editor.abp_plan().abp_obstacles) == 3
        abp_bar.abp_answered.emit("todos")
        assert abp_pending(abp_editor.abp_plan()) == []
        assert abp_bar.isHidden()
        abp_editor.abp_start_review()
        assert abp_bar.isHidden()
        abp_editor.abp_undo_stack.undo()
        assert abp_pending(abp_editor.abp_plan())
        abp_editor.abp_start_review()
        abp_bar.abp_answered.emit("si")
        abp_bar.abp_answered.emit("fin")
        assert abp_bar.isHidden()

    def abp_test_confirm_menu_and_context_menu(self, qtbot: QtBot) -> None:
        abp_editor = self.abp__editor(qtbot)
        abp_editor.abp_confirm_kind(abpElementType.abp_OBSTACLE)
        assert all(abp_o.abp_confirmed for abp_o in abp_editor.abp_plan().abp_obstacles)
        assert not abp_editor.abp_plan().abp_exits[0].abp_confirmed
        abp_labels = [
            abp_a.text()
            for abp_a in abp_editor.abp_context_menu((abpElementType.abp_STAIR, 0)).actions()
        ]
        assert {"Confirmar", "Convertir en obstáculo"} <= set(abp_labels)
        abp_editor.abp_convert_element((abpElementType.abp_STAIR, 0), abpElementType.abp_OBSTACLE)
        assert abp_editor.abp_plan().abp_stairs == ()
        abp_editor.abp__on_double_click(QPointF(500, 150))
        assert abp_editor.abp_plan().abp_exits[0].abp_confirmed


class abpTestDragAndDrop:
    def abp_test_drop_image_and_pdf(
        self,
        qtbot: QtBot,
        abp_services: abpAppServices,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        abp_page = abpLoadPlanPage(abp_services.abp_plans)
        qtbot.addWidget(abp_page)
        abp_opened: list[Path] = []
        monkeypatch.setattr(abp_page, "abp_open_pdf", abp_opened.append)
        monkeypatch.setattr(abp_page, "abp_open_file", abp_opened.append)
        for abp_name in ("plano.pdf", "foto.JPG", "nota.txt"):
            abp_path = tmp_path / abp_name
            abp_path.write_bytes(b"x")
            abp_data = QMimeData()
            abp_data.setUrls([QUrl.fromLocalFile(str(abp_path))])
            abp_args = (Qt.DropAction.CopyAction, abp_data, Qt.MouseButton.LeftButton)
            abp_modifiers = Qt.KeyboardModifier.NoModifier
            abp_enter = QDragEnterEvent(QPointF(5, 5).toPoint(), *abp_args, abp_modifiers)
            abp_enter.setAccepted(False)
            abp_page.dragEnterEvent(abp_enter)
            assert abp_enter.isAccepted() == (abp_name != "nota.txt")
            abp_page.dropEvent(QDropEvent(QPointF(5, 5), *abp_args, abp_modifiers))
        assert [abp_p.name for abp_p in abp_opened] == ["plano.pdf", "foto.JPG"]

    def abp_test_window_mentions_pdf(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_window.abp_create_project("X", abpUseType.abp_EDUCATION)
        abp_window.abp_go_to_step(abp_STEP_LOAD)
        assert "PDF" in abp_window.abp_load_page.abp_choose_button.text()
        assert abp_window.abp_load_page.acceptDrops()
