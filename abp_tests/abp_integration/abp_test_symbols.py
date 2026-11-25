from __future__ import annotations

import dataclasses
import math
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_plan_import import abpLoadedPlan
from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService as abp_P
from abp_rutasegura.abp_application.abp_serialization import abp_plan_from_dict, abp_plan_to_dict
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpFloorPlan, abpObstacle, abpSign, abpWall
from abp_rutasegura.abp_domain.abp_vector import abpVectorText
from abp_rutasegura.abp_engines.abp_navigation.abp_evac_tree import abp_evacuation_network
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_polygon_to_m
from abp_rutasegura.abp_engines.abp_navigation.abp_sign_proposals import abp_propose_signs
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea
from abp_rutasegura.abp_engines.abp_vision.abp_inventory import (
    abp_adjust_doors,
    abp_build_inventory,
    abp_furniture_names,
    abp_read_tags,
    abpTag,
)
from abp_rutasegura.abp_engines.abp_vision.abp_obstacles import abp_detect_obstacles
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_read_vector, abp_render_page
from abp_rutasegura.abp_engines.abp_vision.abp_stairs import (
    abp_fan_stairs,
    abp_find_stairs,
    abp_number_chains,
)
from abp_rutasegura.abp_engines.abp_vision.abp_symbols import (
    abp_find_signs,
    abp_kind_of,
    abp_legend_boxes,
    abp_read_legend,
    abpFoundSigns,
)
from abp_rutasegura.abp_presentation.abp_main_window import abp_STEP_EDIT, abpMainWindow
from abp_rutasegura.abp_presentation.abp_pdf_import_dialog import abpPdfImportDialog
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp_rect,
    abp_SCALE,
    abp_single_room,
    abp_two_rooms,
)
from abp_tests.abp_fixtures.abp_vector_plans import (
    abp_ORIGIN,
    abp_SIGN_PLACES,
    abp_write_vector_plan,
    abpStyle,
)

abp_FULL = abpStyle(abp_signs=True, abp_numbered_stairs=True, abp_tags=True)


@pytest.fixture(scope="module")
def abp_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return abp_write_vector_plan(tmp_path_factory.mktemp("pdf") / "senales.pdf", abp_style=abp_FULL)


@pytest.fixture(scope="module")
def abp_loaded(abp_pdf: Path) -> abpLoadedPlan:
    return abp_P.abp_load_pdf_page(
        abp_pdf, 0, abp_hidden_layers=["MOBILIARIO"], abp_remove_colors=True
    )


def abp__meters(abp_p: abpPoint, abp_plan: abpLoadedPlan) -> tuple[float, float]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_dpi = abp_plan.abp_vector.abp_dpi if abp_plan.abp_vector is not None else 200.0
    return (abp_p.abp_x - abp_ORIGIN[0] / 72 * abp_dpi) * abp_scale, (
        abp_p.abp_y - abp_ORIGIN[1] / 72 * abp_dpi
    ) * abp_scale


class abpTestSigns:
    def abp_test_reads_the_legend(self, abp_pdf: Path) -> None:
        abp_vector = abp_read_vector(abp_pdf, 0)
        assert abp_vector is not None
        assert len(abp_legend_boxes(abp_vector)) == 1
        abp_templates = abp_read_legend(abp_vector, abp_render_page(abp_pdf, 0))
        assert [abp_t.abp_kind for abp_t in abp_templates] == [
            abpSignKind.abp_EXTINGUISHER,
            abpSignKind.abp_DIRECTION,
            abpSignKind.abp_PROHIBITION,
        ]
        assert abp_templates[2].abp_label == "Prohibido correr"

    def abp_test_finds_every_sign_with_its_turn(self, abp_loaded: abpLoadedPlan) -> None:
        abp_kinds = Counter(abp_s.abp_kind.value for abp_s in abp_loaded.abp_signs)
        assert abp_kinds == Counter(abp_place[0] for abp_place in abp_SIGN_PLACES)
        for abp_kind, abp_x, abp_y, abp__turn in abp_SIGN_PLACES:
            abp_near = [
                abp_s
                for abp_s in abp_loaded.abp_signs
                if abp_s.abp_kind.value == abp_kind
                and math.dist(abp__meters(abp_s.abp_position, abp_loaded), (abp_x, abp_y)) < 0.25
            ]
            assert len(abp_near) == 1
        abp_arrows = {
            round(abp__meters(abp_s.abp_position, abp_loaded)[0]): abp_s.abp_rotation_deg
            for abp_s in abp_loaded.abp_signs
            if abp_s.abp_kind is abpSignKind.abp_DIRECTION
        }
        assert abp_arrows == {4: 180.0, 6: 270.0}
        abp_texts = [
            abp_s.abp_text
            for abp_s in abp_loaded.abp_signs
            if abp_s.abp_kind is abpSignKind.abp_PROHIBITION
        ]
        assert abp_texts == ["Prohibido correr"]

    def abp_test_meeting_zone_and_crop(self, abp_loaded: abpLoadedPlan) -> None:
        abp_zone = abp_loaded.abp_zones[0]
        assert abp_zone.abp_name == "Zona de reunión"
        assert abp__meters(abp_zone.abp_area.abp_centroid, abp_loaded) == pytest.approx(
            (12.0, 8.5), abs=0.1
        )
        abp_box = abp_P.abp_suggest_crop(abp_loaded)
        assert abp_box is not None
        abp_part = abp_P.abp_crop(abp_loaded, abp_box)
        assert len(abp_part.abp_signs) == len(abp_loaded.abp_signs)
        assert len(abp_part.abp_zones) == 1
        abp_moved = abp_part.abp_signs[0].abp_position
        assert abp_moved.abp_x == pytest.approx(
            abp_loaded.abp_signs[0].abp_position.abp_x - int(abp_box[0]), abs=1
        )
        abp_tiny = abp_P.abp_crop(abp_loaded, (0, 0, 120, 120))
        assert (abp_tiny.abp_signs, abp_tiny.abp_zones) == ((), ())

    def abp_test_plan_without_signs(self, tmp_path: Path) -> None:
        abp_plain = abp_P.abp_load_pdf_page(abp_write_vector_plan(tmp_path / "p.pdf"), 0)
        assert abp_plain.abp_signs == ()
        abp_image = np.full((50, 50, 3), 255, np.uint8)
        assert abp_find_signs(abp_image, None) == abpFoundSigns()

    @pytest.mark.parametrize(
        ("abp_text", "abp_kind"),
        [
            ("ZONA SEGURA EN CASO DE SISMOS", abpSignKind.abp_SAFE_ZONE),
            ("SEÑAL DE ILUMINACIÓN DE EMERGENCIA", abpSignKind.abp_EMERGENCY_LIGHT),
            ("TABLERO DE DISTRIBUCIÓN PELIGRO ELÉCTRICO", abpSignKind.abp_ELECTRIC_RISK),
            ("SEÑAL DIRECCIONAL DE SALIDA", abpSignKind.abp_DIRECTION),
            ("SALIDA", abpSignKind.abp_EXIT),
            ("CUIDADO PISO RESBALOSO", abpSignKind.abp_WARNING),
            ("OBLIGATORIO USAR ALCOHOL EN GEL", abpSignKind.abp_MANDATORY),
            ("Laboratorio", None),
        ],
    )
    def abp_test_keywords(self, abp_text: str, abp_kind: abpSignKind | None) -> None:
        assert abp_kind_of(abp_text) is abp_kind

    def abp_test_every_kind_has_a_drawing(self) -> None:
        assert {abp_k.value for abp_k in abpSignKind} == set(abp_SIGNS)

    def abp_test_capacity_is_not_proposed_twice(self) -> None:
        abp_plan = abp_single_room()
        abp_rooms = [
            abpRoomArea("Aula 1", 0, abp_polygon_to_m(abp_plan.abp_rooms[0].abp_area, abp_SCALE))
        ]
        abp_network = abp_evacuation_network(abp_plan, abp_rooms)
        assert abpSignKind.abp_CAPACITY in [
            abp_s.abp_kind for abp_s in abp_propose_signs(abp_plan, abp_network, {"Aula 1": 9})
        ]
        abp_drawn = dataclasses.replace(
            abp_plan, abp_signs=(abpSign(abpSignKind.abp_CAPACITY, abpPoint(100, 100)),)
        )
        abp_kinds = [
            abp_s.abp_kind for abp_s in abp_propose_signs(abp_drawn, abp_network, {"Aula 1": 9})
        ]
        assert abpSignKind.abp_CAPACITY not in abp_kinds


class abpTestStairs:
    def abp_test_two_flights_with_landing(self, abp_loaded: abpLoadedPlan) -> None:
        abp_plan = abp_P.abp_detect(
            abp_loaded.abp_image,
            abpFloorPlan(abp_scale_m_per_px=abp_loaded.abp_scale_m_per_px),
            abp_vector=abp_loaded.abp_vector,
        )
        assert len(abp_plan.abp_stairs) == 1
        abp_points = [
            abp__meters(abp_v, abp_loaded) for abp_v in abp_plan.abp_stairs[0].abp_area.abp_vertices
        ]
        abp_xs, abp_ys = [abp_p[0] for abp_p in abp_points], [abp_p[1] for abp_p in abp_points]
        assert (min(abp_xs), max(abp_xs)) == pytest.approx((7.4, 10.0), abs=0.15)
        assert (min(abp_ys), max(abp_ys)) == pytest.approx((0.0, 3.6), abs=0.2)

    def abp_test_number_chains(self) -> None:
        abp_texts = [
            abpVectorText(str(abp_i), 100.0, 100.0 + 28 * abp_i, 5, 5, 0) for abp_i in range(1, 8)
        ]
        abp_texts += [abpVectorText("9", 500, 500, 5, 5, 0), abpVectorText("x", 100, 100, 5, 5, 0)]
        abp_chains = abp_number_chains(abp_texts, 0.01)
        assert [abp_n for abp_n, abp__p in abp_chains[0]] == [1, 2, 3, 4, 5, 6, 7]
        assert len(abp_chains) == 1

    def abp_test_fan(self) -> None:
        abp_angles = np.radians([0, 20, 40, 60, 80])
        abp_fan = np.array(
            [[5, 5, 5 + 1.2 * np.cos(abp_a), 5 + 1.2 * np.sin(abp_a)] for abp_a in abp_angles]
        )
        abp_walls = np.array([[0, 0, 10, 0], [10, 0, 10, 10], [10, 10, 0, 10], [0, 10, 0, 0.0]])
        assert len(abp_fan_stairs(abp_fan)) == 1
        assert len(abp_find_stairs(abp_fan, abp_walls)) == 1
        assert abp_fan_stairs(abp_fan[:2]) == []
        assert abp_find_stairs(np.zeros((0, 4)), abp_walls) == []


class abpTestTagsAndInventory:
    def abp_test_reads_tags(self, abp_loaded: abpLoadedPlan) -> None:
        assert abp_loaded.abp_vector is not None
        abp_tags = {
            abp_t.abp_code: abp_t for abp_t in abp_read_tags(abp_loaded.abp_vector.abp_texts)
        }
        assert abp_tags["P - 01"].abp_numbers == (0.9, 2.1)
        assert abp_tags["VEN. 01"].abp_window
        assert abp_tags["VEN. 01"].abp_width_m == 2.0
        assert abpTag("P-9", 0, 0, (), False).abp_width_m is None

    def abp_test_adjusts_doors_to_the_tag(self) -> None:
        abp_wall = abpWall(abpSegment(abpPoint(0, 0), abpPoint(500, 0)))
        abp_door = abpDoor(abpSegment(abpPoint(100, 0), abpPoint(147, 0)), 0.9)
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=abp_SCALE, abp_walls=(abp_wall,), abp_doors=(abp_door,)
        )
        abp_tag = abpTag("P-01", 120, 30, (0.9, 2.1), False)
        abp_fixed = abp_adjust_doors(abp_plan, [abp_tag])
        assert abp_fixed.abp_doors[0].abp_segment.abp_length * abp_SCALE == pytest.approx(0.9)
        assert abp_fixed.abp_doors[0].abp_segment.abp_midpoint == abp_door.abp_segment.abp_midpoint
        abp_far = abp_adjust_doors(abp_plan, [abpTag("P-01", 120, 30, (1.5, 2.1), False)])
        assert abp_far.abp_doors == abp_plan.abp_doors
        assert abp_adjust_doors(abpFloorPlan(), [abp_tag]) == abpFloorPlan()

    def abp_test_inventory(self, abp_loaded: abpLoadedPlan) -> None:
        abp_scale = abp_loaded.abp_scale_m_per_px
        abp_plan = abp_P.abp_detect(
            abp_loaded.abp_image,
            abpFloorPlan(
                abp_scale_m_per_px=abp_scale,
                abp_signs=abp_loaded.abp_signs,
                abp_safe_zones=abp_loaded.abp_zones,
            ),
            abp_vector=abp_loaded.abp_vector,
        )
        abp_elements = abp_P.abp_inventory(abp_plan, abp_loaded.abp_vector)
        abp_counts = Counter(abp_e.abp_kind for abp_e in abp_elements)
        assert abp_counts["puerta"] == 2
        assert abp_counts["salida"] == 1
        assert abp_counts["ventana"] == 1
        assert abp_counts["escalera"] == 1
        assert abp_counts["senal"] == len(abp_SIGN_PLACES)
        assert abp_counts["zona_segura"] == 1
        assert abp_counts["ambiente"] == 3
        abp_doors = {
            abp_e.abp_label: abp_e.abp_detail
            for abp_e in abp_elements
            if abp_e.abp_kind == "puerta"
        }
        assert abp_doors["P - 01"] == "0.90 × 2.10 m en el plano · coincide"
        abp_window = next(abp_e for abp_e in abp_elements if abp_e.abp_kind == "ventana")
        abp_a, abp_b = (abp__meters(abp_p, abp_loaded) for abp_p in abp_window.abp_points)
        assert math.dist(abp_a, abp_b) == pytest.approx(2.0, abs=0.05)
        assert not any(
            abp_o.abp_area.abp_centroid.abp_distance_to(abp_s.abp_position) * (abp_scale or 1) < 0.3
            for abp_o in abp_plan.abp_obstacles
            for abp_s in abp_plan.abp_signs
        )

    def abp_test_tagged_door_without_opening(self, abp_loaded: abpLoadedPlan) -> None:
        abp_wall = abpWall(abpSegment(abpPoint(0, 0), abpPoint(500, 0)))
        abp_far = abpWall(abpSegment(abpPoint(500, 0), abpPoint(500, 400)))
        abp_plan = abpFloorPlan(abp_scale_m_per_px=abp_SCALE, abp_walls=(abp_wall, abp_far))
        assert abp_loaded.abp_vector is not None
        abp_texts = tuple(
            dataclasses.replace(abp_t, abp_x=abp_x, abp_y=abp_y)
            for abp_t, abp_x, abp_y in zip(
                [
                    abp_t
                    for abp_t in abp_loaded.abp_vector.abp_texts
                    if abp_t.abp_text in ("P - 01", "0.90", "2.10")
                ][:3],
                (200, 195, 205),
                (100, 108, 108),
                strict=False,
            )
        )
        abp_vector = dataclasses.replace(abp_loaded.abp_vector, abp_texts=abp_texts)
        abp_doors = [
            abp_e
            for abp_e in abp_build_inventory(abp_plan, abp_vector)
            if abp_e.abp_kind == "puerta"
        ]
        assert [abp_d.abp_label for abp_d in abp_doors] == ["P - 01"]
        assert "sin vano detectado: dibújela" in abp_doors[0].abp_detail

    def abp_test_inventory_without_vector(self) -> None:
        abp_elements = abp_build_inventory(abp_two_rooms())
        assert Counter(abp_e.abp_kind for abp_e in abp_elements)["ambiente"] == 2
        assert abp_build_inventory(abpFloorPlan()) == ()

    def abp_test_warns_when_the_written_area_is_wrong(self, abp_loaded: abpLoadedPlan) -> None:
        assert abp_loaded.abp_vector is not None
        abp_plan = abp_single_room()
        abp_name = abp_plan.abp_rooms[0].abp_name
        abp_room = abp_plan.abp_rooms[0].abp_area.abp_centroid
        abp_texts = (
            abpVectorText(abp_name.upper(), abp_room.abp_x, abp_room.abp_y - 12, 60, 12, 0, "a"),
            abpVectorText("NPT. +0.00", abp_room.abp_x, abp_room.abp_y, 40, 8, 0, "a"),
            abpVectorText("ÁREA= 8.79", abp_room.abp_x, abp_room.abp_y + 14, 40, 8, 0, "a"),
        )
        abp_vector = dataclasses.replace(abp_loaded.abp_vector, abp_texts=abp_texts)
        abp_room_element = next(
            abp_e
            for abp_e in abp_build_inventory(abp_plan, abp_vector)
            if abp_e.abp_kind == "ambiente"
        )
        assert "el plano dice 8.79 m²: verifique" in abp_room_element.abp_detail

    def abp_test_furniture_names(self) -> None:
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=abp_SCALE,
            abp_obstacles=(
                abpObstacle(abp_rect(1, 1, 2, 1)),
                abpObstacle(abp_rect(6, 1, 2, 1)),
                abpObstacle(abp_rect(4, 5, 0.5, 0.5), abp_name="Columna"),
            ),
        )
        abp_texts = [abpVectorText("MESA DE MELAMINA", 100, 110, 60, 6, 0)]
        assert abp_furniture_names(abp_plan, abp_texts) == ("Mesa", "Mesa", "Columna")
        abp_again = abp_plan_from_dict(abp_plan_to_dict(abp_plan))
        assert [abp_o.abp_name for abp_o in abp_again.abp_obstacles] == ["", "", "Columna"]


class abpTestOutlines:
    def abp_test_follows_the_drawn_shape(self) -> None:
        abp_plan = abp_single_room()
        abp_image = np.full((320, 520, 3), 255, np.uint8)
        abp_shape = np.array([[100, 80], [260, 80], [260, 130], [160, 130], [160, 200], [100, 200]])
        cv2.polylines(abp_image, [abp_shape], True, (60, 60, 60), 2)
        abp_outline = abp_detect_obstacles(abp_plan, abp_image=abp_image)
        assert len(abp_outline) == 1
        abp_real = cv2.contourArea(abp_shape.astype(np.float32))
        assert abp_outline[0].abp_area == pytest.approx(abp_real, rel=0.06)
        assert 6 <= len(abp_outline[0].abp_vertices) <= 10

    def abp_test_furniture_against_a_wall(self) -> None:
        abp_plan = abp_single_room()
        abp_image = np.full((320, 520, 3), 255, np.uint8)
        cv2.polylines(
            abp_image,
            [np.array([[100, 0], [100, 45], [180, 45], [180, 0]])],
            False,
            (60, 60, 60),
            2,
        )
        abp_outline = abp_detect_obstacles(abp_plan, abp_image=abp_image)
        assert len(abp_outline) == 1
        assert abp_plan.abp_area_m2(abp_outline[0]) > 0.6


class abpTestWindow:
    def abp_test_signs_reach_the_plan_and_elements_dialog(
        self, qtbot: QtBot, abp_services: abpAppServices, abp_pdf: Path, abp_loaded: abpLoadedPlan
    ) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        assert abp_window.abp_create_project("Señales", abpUseType.abp_EDUCATION) is not None
        abp_window.abp_load_page.abp_use_plan(abp_pdf, 0, 1, abp_loaded)
        assert len(abp_window.abp_plan.abp_signs) == len(abp_SIGN_PLACES)
        assert [abp_z.abp_name for abp_z in abp_window.abp_plan.abp_safe_zones] == [
            "Zona de reunión"
        ]
        with qtbot.waitSignal(abp_window.abp_editor_page.abp_detection_finished, timeout=60_000):
            abp_window.abp_go_to_step(abp_STEP_EDIT)
        abp_page = abp_window.abp_editor_page
        abp_page.abp_show_elements()
        abp_dialog = abp_page.abp_elements_dialog
        assert abp_dialog is not None
        assert abp_dialog.abp_counts()["senal"] == len(abp_SIGN_PLACES)
        abp_dialog.abp_search_edit.setText("extintor")
        abp_groups = [
            abp_dialog.abp_tree.topLevelItem(abp_i)
            for abp_i in range(abp_dialog.abp_tree.topLevelItemCount())
        ]
        abp_shown = [abp_g for abp_g in abp_groups if abp_g is not None and not abp_g.isHidden()]
        assert [abp_g.text(0) for abp_g in abp_shown] == [f"Señales ({len(abp_SIGN_PLACES)})"]
        abp_child = next(
            abp_c
            for abp_c in (abp_shown[0].child(abp_i) for abp_i in range(abp_shown[0].childCount()))
            if abp_c is not None and not abp_c.isHidden()
        )
        assert abp_child.text(0) == "Extintor"
        abp_dialog.abp_tree.setCurrentItem(abp_child)
        assert abp_page.abp_editor.abp_scene.abp__highlight is not None
        abp_wall = next(
            abp_e
            for abp_e in abp_page.abp__plans.abp_inventory(abp_window.abp_plan, None)
            if abp_e.abp_kind == "muro"
        )
        abp_page.abp_editor.abp_highlight(abp_wall)
        abp_page.abp_show_elements()
        assert abp_page.abp_elements_dialog is not abp_dialog
        assert abp_page.abp_elements_dialog is not None
        abp_page.abp_elements_dialog.close()
        assert abp_page.abp_editor.abp_scene.abp__highlight is None

    def abp_test_import_dialog_lists_signs(self, qtbot: QtBot, abp_pdf: Path) -> None:
        abp_dialog = abpPdfImportDialog(abp_P(), abp_pdf)
        qtbot.addWidget(abp_dialog)
        qtbot.waitUntil(lambda: abp_dialog.abp_ok_button.isEnabled(), timeout=60_000)
        assert "Señales reconocidas (5)" in abp_dialog.abp_info_label.text()
        assert "2 Extintor" in abp_dialog.abp_info_label.text()

    def abp_test_rename_obstacles(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_editor = abp_window.abp_editor_page.abp_editor
        abp_plan = dataclasses.replace(
            abp_single_room(),
            abp_obstacles=(abpObstacle(abp_rect(1, 1, 1, 1)), abpObstacle(abp_rect(3, 1, 1, 1))),
        )
        abp_editor.abp_set_plan(abp_plan, None)
        assert abp_editor.abp_rename((abpElementType.abp_OBSTACLE, 0), "Mesa")
        assert abp_editor.abp_rename((abpElementType.abp_OBSTACLE, 1), "Mesa")
        assert [abp_o.abp_name for abp_o in abp_editor.abp_plan().abp_obstacles] == ["Mesa", "Mesa"]
        abp_project_id = abp_services.abp_projects.abp_create_project("X", abpUseType.abp_EDUCATION)
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_editor.abp_plan())
        abp_saved = abp_services.abp_projects.abp_load_floor(abp_project_id)
        assert abp_saved is not None
        assert [abp_o.abp_name for abp_o in abp_saved.abp_obstacles] == ["Mesa", "Mesa"]
