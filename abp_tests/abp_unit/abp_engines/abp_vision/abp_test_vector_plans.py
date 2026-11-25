from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan, abpVectorText
from abp_rutasegura.abp_engines.abp_vision import abp_pdf_vector as abp_pv
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpPlanFileError
from abp_rutasegura.abp_engines.abp_vision.abp_room_labels import (
    abp_label_anchors,
    abp_read_room_labels,
)
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp_detect_vector_plan,
    abp_furniture_segments,
    abp_hatching,
    abp_merge_collinear,
    abp_text_frames,
)
from abp_tests.abp_fixtures.abp_vector_plans import abp_write_vector_plan


@pytest.fixture(scope="module")
def abp_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return abp_write_vector_plan(tmp_path_factory.mktemp("pdf") / "plano.pdf", abp_pages=2)


@pytest.fixture(scope="module")
def abp_vector(abp_pdf: Path) -> abpVectorPlan:
    abp_plan = abp_pv.abp_read_vector(abp_pdf, 0)
    assert abp_plan is not None
    return abp_plan


class abpTestPdf:
    def abp_test_pages(self, abp_pdf: Path) -> None:
        abp_pages = abp_pv.abp_inspect_pdf(abp_pdf)
        assert [abp_p.abp_level for abp_p in abp_pages] == [0, 1]
        assert all(abp_p.abp_is_vector and abp_p.abp_scale_denominator == 50 for abp_p in abp_pages)
        assert "EVACUACI" in abp_pv.abp_plain(abp_pages[0].abp_title)
        assert abp_pages[0].abp_kind == "evacuacion"
        assert {"MUROS", "MOBILIARIO"} <= set(abp_pages[0].abp_layers)

    def abp_test_layer_names(self) -> None:
        assert abp_pv.abp_is_structure_layer("A-MUROS")
        assert abp_pv.abp_is_structure_layer("gris")
        assert not abp_pv.abp_is_structure_layer("92- señalizacion")
        assert not abp_pv.abp_is_structure_layer("EJES")
        assert abp_pv.abp_is_furniture_layer("A-MOVILIARIO COMEDOR")
        assert not abp_pv.abp_is_furniture_layer("MUROS")

    def abp_test_scale_text(self) -> None:
        assert abp_pv.abp_find_scale(["x", "ESC. 1/75"]) == 75
        assert abp_pv.abp_find_scale(["Escala 1:100"]) == 100
        assert abp_pv.abp_find_scale(["sin escala"]) is None

    def abp_test_vector_content(self, abp_vector: abpVectorPlan) -> None:
        assert abp_vector.abp_scale_m_per_px == pytest.approx(0.0254 / abp_vector.abp_dpi * 50)
        assert len(abp_vector.abp_arcs) == 3
        assert abp_vector.abp_filled.any()
        assert any("AULA 101" in abp_t.abp_text for abp_t in abp_vector.abp_texts)

    def abp_test_render_hides_layers_and_colors(self, abp_pdf: Path) -> None:
        abp_full = abp_pv.abp_render_page(abp_pdf, 0)
        abp_clean = abp_pv.abp_render_page(
            abp_pdf, 0, abp_hidden_layers=["MOBILIARIO"], abp_remove_colors=True
        )
        assert abp_full.shape == abp_clean.shape
        abp_green = (abp_full[:, :, 1] > 200) & (abp_full[:, :, 0] < 80)
        assert abp_green.any()
        assert not ((abp_clean[:, :, 1] > 200) & (abp_clean[:, :, 0] < 80)).any()
        assert (abp_clean < 200).sum() < (abp_full < 200).sum()
        assert (abp_pv.abp_thicken_lines(abp_clean) < 200).sum() > (abp_clean < 200).sum()
        assert max(abp_pv.abp_thumbnail(abp_pdf, 1, 120).shape[:2]) == 120

    def abp_test_errors(self, abp_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(abpPlanFileError, match="no existe la 8"):
            abp_pv.abp_read_vector(abp_pdf, 7)
        abp_bad = tmp_path / "x.pdf"
        abp_bad.write_bytes(b"no es pdf")
        with pytest.raises(abpPlanFileError):
            abp_pv.abp_inspect_pdf(abp_bad)

    def abp_test_fit_arc(self) -> None:
        abp_t = np.linspace(0.2, 1.4, 9)
        abp_arc = abp_pv.abp_fit_arc(np.c_[10 + 5 * np.cos(abp_t), 20 + 5 * np.sin(abp_t)])
        assert abp_arc is not None
        assert abp_arc[:3] == pytest.approx((10, 20, 5), abs=1e-6)
        assert abs(abp_arc[4]) == pytest.approx(1.2, abs=1e-6)
        assert abp_pv.abp_fit_arc(np.c_[abp_t, 2 * abp_t]) is None


class abpTestDomain:
    def abp_test_crop_and_layers(self, abp_vector: abpVectorPlan) -> None:
        abp_part = abp_vector.abp_cropped(100, 100, 900, 800)
        assert (abp_part.abp_width, abp_part.abp_height) == (800, 700)
        assert len(abp_part.abp_segments) < len(abp_vector.abp_segments)
        assert all(
            0 <= abp_t.abp_x <= 800 and 0 <= abp_t.abp_y <= 700 for abp_t in abp_part.abp_texts
        )
        assert abp_part.abp_scale_m_per_px == abp_vector.abp_scale_m_per_px
        abp_without = abp_vector.abp_without_layers(["MOBILIARIO"])
        assert len(abp_without.abp_segments) < len(abp_vector.abp_segments)
        assert len(abp_without.abp_arcs) == len(abp_vector.abp_arcs)

    def abp_test_validation(self, abp_vector: abpVectorPlan) -> None:
        with pytest.raises(ValueError, match="inconsistentes"):
            abpVectorPlan(
                1,
                1,
                200,
                (),
                np.zeros((2, 4)),
                np.zeros(1, np.int64),
                np.zeros(2, bool),
                np.zeros((0, 5)),
                np.zeros(0, np.int64),
            )


class abpTestDetection:
    def abp_test_walls_doors_and_exit(self, abp_vector: abpVectorPlan) -> None:
        abp_scale = abp_vector.abp_scale_m_per_px
        assert abp_scale is not None
        abp_found = abp_detect_vector_plan(
            abp_vector, abp_scale, abp_anchors_px=abp_label_anchors(abp_vector.abp_texts)
        )
        abp_widths = sorted(
            round(abp_d.abp_segment.abp_length * abp_scale, 2) for abp_d in abp_found.abp_doors
        )
        assert abp_widths == pytest.approx([0.9, 0.9], abs=0.03)
        assert [
            round(abp_e.abp_segment.abp_length * abp_scale, 2) for abp_e in abp_found.abp_exits
        ] == pytest.approx([1.2], abs=0.03)
        assert not abp_found.abp_exits[0].abp_confirmed
        assert abp_found.abp_bounds is not None
        abp_x0, abp_y0, abp_x1, abp_y1 = (abp_v * abp_scale for abp_v in abp_found.abp_bounds)
        assert abp_x1 - abp_x0 == pytest.approx(10.0, abs=0.2)
        assert abp_y1 - abp_y0 == pytest.approx(7.0, abs=0.2)
        abp_total = sum(abp_w.abp_segment.abp_length for abp_w in abp_found.abp_walls) * abp_scale
        assert abp_total == pytest.approx(10 * 3 + 7 * 2 + 5 - 0.9 * 2 - 1.2, abs=1.0)

    def abp_test_furniture_is_inside_and_not_walls(self, abp_vector: abpVectorPlan) -> None:
        abp_scale = abp_vector.abp_scale_m_per_px
        assert abp_scale is not None
        abp_found = abp_detect_vector_plan(
            abp_vector, abp_scale, abp_anchors_px=abp_label_anchors(abp_vector.abp_texts)
        )
        abp_plan = abpFloorPlan(
            abp_scale_m_per_px=abp_scale,
            abp_walls=abp_found.abp_walls,
            abp_doors=abp_found.abp_doors,
            abp_exits=abp_found.abp_exits,
        )
        abp_desks = abp_furniture_segments(abp_vector, abp_plan)
        assert len(abp_desks) >= 16
        abp_mid = (abp_desks[:, :2] + abp_desks[:, 2:]) / 2
        assert abp_found.abp_bounds is not None
        abp_inside = (abp_mid[:, 0] - abp_found.abp_bounds[0]) * abp_scale
        assert abp_inside.min() > 0.9
        assert abp_inside.max() < 3.6
        assert len(abp_furniture_segments(abp_vector, abpFloorPlan())) == 0

    def abp_test_empty(self, abp_vector: abpVectorPlan) -> None:
        abp_empty = abp_vector.abp_without_layers(abp_vector.abp_layers)
        assert abp_detect_vector_plan(abp_empty, 0.01).abp_bounds is None

    def abp_test_merge_collinear(self) -> None:
        abp_s = np.array([[0, 0, 1, 0], [1.01, 0, 2, 0], [0, 1, 2, 1], [5, 0, 6, 0.0]])
        abp_merged = abp_merge_collinear(abp_s)
        assert len(abp_merged) == 3
        assert max(
            np.hypot(abp_m[2] - abp_m[0], abp_m[3] - abp_m[1]) for abp_m in abp_merged
        ) == pytest.approx(2.0)

    def abp_test_hatching_keeps_lonely_lines(self) -> None:
        abp_hatch = np.array([[0, 0.2 * abp_i, 3, 0.2 * abp_i] for abp_i in range(12)])
        abp_wall = np.array([[5.0, 0, 5.0, 4], [5.15, 0, 5.15, 4]])
        abp_flags = abp_hatching(np.vstack([abp_hatch, abp_wall]))
        assert abp_flags[:12].all()
        assert not abp_flags[12:].any()

    def abp_test_text_frames(self) -> None:
        abp_tag = abpVectorText("P - 01", 1.0, 1.0, 0.5, 0.1, 0.0)
        abp_box = np.array([[0.7, 0.9, 1.3, 0.9], [0.7, 1.1, 1.3, 1.1], [0.7, 0.9, 0.7, 1.1]])
        abp_wall = np.array([[0.0, 3.0, 4.0, 3.0]])
        abp_flags = abp_text_frames(np.vstack([abp_box, abp_wall]), [abp_tag], 1.0)
        assert abp_flags[:3].all()
        assert not abp_flags[3]


class abpTestRoomLabels:
    def abp_test_reads_name_area_and_capacity(self, abp_vector: abpVectorPlan) -> None:
        abp_labels = {abp_q.abp_name: abp_q for abp_q in abp_read_room_labels(abp_vector.abp_texts)}
        assert abp_labels["Aula 101"].abp_capacity == 16
        assert abp_labels["Aula 101"].abp_area_m2 == 24.0
        assert abp_labels["Taller de arte"].abp_capacity == 8
        assert abp_labels["Pasillo"].abp_capacity is None

    def abp_test_two_line_names_and_noise(self) -> None:
        abp_texts = [
            abpVectorText("LABORATORIO DE", 100, 60, 80, 12, 0, "F"),
            abpVectorText("COMPUTO 3", 100, 75, 60, 12, 0, "F"),
            abpVectorText("NPT. +1.50", 100, 90, 50, 10, 0, "F"),
            abpVectorText("PISO CERAMICO 40X40", 100, 100, 60, 6, 0, "G"),
            abpVectorText("ÁREA= 48,96   AFORO= 32", 100, 110, 70, 6, 0, "G"),
            abpVectorText("ESCENARIO", 500, 300, 60, 12, 0, "F"),
            abpVectorText("P - 01", 520, 320, 60, 12, 0, "F"),
        ]
        abp_labels = abp_read_room_labels(abp_texts)
        assert [
            (abp_q.abp_name, abp_q.abp_area_m2, abp_q.abp_capacity) for abp_q in abp_labels
        ] == [
            ("Laboratorio de computo 3", 48.96, 32),
            ("Escenario", None, None),
        ]
        assert len(abp_label_anchors(abp_texts)) == 2
