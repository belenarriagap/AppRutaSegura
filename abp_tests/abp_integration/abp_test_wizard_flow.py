from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_images import abp_write_png
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_EDIT,
    abp_STEP_SCALE,
    abpMainWindow,
)
from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan


@pytest.fixture
def abp_plan_file(tmp_path: Path) -> tuple[Path, float]:
    abp_synthetic = abp_generate_plan(1)
    abp_path = tmp_path / "planos" / "colegio ñ.png"
    abp_write_png(abp_path, abp_synthetic.abp_image)
    return abp_path, abp_synthetic.abp_scale_m_per_px


def abp_test_load_scale_detect_save_and_reopen(
    qtbot: QtBot,
    abp_services: abpAppServices,
    abp_plan_file: tuple[Path, float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    abp_path, abp_true_scale = abp_plan_file
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_window, "abp_show_error", abp_errors.append)
    abp_project_id = abp_window.abp_create_project(
        "I.E. Prueba", abpUseType.abp_EDUCATION, "Jr. Lima 1"
    )
    assert abp_project_id is not None

    abp_window.abp_load_page.abp_open_file(abp_path)
    assert abp_window.abp_load_page.abp_image is not None
    assert abp_window.abp_is_dirty

    abp_window.abp_go_to_step(abp_STEP_SCALE)
    abp_px = 10.0 / abp_true_scale
    abp_window.abp_scale_page.abp_set_reference(abpPoint(100, 100), abpPoint(100 + abp_px, 100))
    abp_window.abp_scale_page.abp_meters_spin.setValue(10.0)
    abp_window.abp_scale_page.abp_apply_scale()
    assert abp_window.abp_plan.abp_scale_m_per_px == pytest.approx(abp_true_scale)

    with qtbot.waitSignal(abp_window.abp_editor_page.abp_detection_finished, timeout=60_000):
        abp_window.abp_go_to_step(abp_STEP_EDIT)
        assert not abp_window.abp_editor_page.abp_editor.isEnabled()
    assert abp_window.abp_editor_page.abp_editor.isEnabled()
    abp_plan = abp_window.abp_editor_page.abp_editor.abp_plan()
    assert len(abp_plan.abp_walls) > 4
    assert abp_plan.abp_doors
    assert abp_plan.abp_exits
    assert abp_plan.abp_has_pending_proposals

    assert abp_window.abp_editor_page.abp_editor.abp_confirm_all_action.isEnabled()
    abp_window.abp_editor_page.abp_editor.abp_confirm_kind(None)
    assert not abp_window.abp_editor_page.abp_editor.abp_confirm_all_action.isEnabled()
    assert abp_window.abp_save()
    assert not abp_window.abp_is_dirty
    assert abp_errors == []

    abp_other = abpMainWindow(abp_services)
    qtbot.addWidget(abp_other)
    abp_other.abp_open_project(abp_project_id)
    abp_reopened = abp_other.abp_editor_page.abp_editor.abp_plan()
    assert abp_reopened.abp_walls == abp_window.abp_plan.abp_walls
    assert not abp_reopened.abp_has_pending_proposals
    assert abp_reopened.abp_scale_m_per_px == pytest.approx(abp_true_scale)
    assert abp_other.abp_current_step() == abp_STEP_EDIT
    assert abp_other.abp_editor_page.abp_editor.abp_scene.abp_has_image


def abp_test_loading_new_image_resets_geometry(
    qtbot: QtBot, abp_services: abpAppServices, abp_plan_file: tuple[Path, float]
) -> None:
    abp_path, _ = abp_plan_file
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    abp_window.abp_create_project("Tienda", abpUseType.abp_COMMERCE)
    abp_window.abp_load_page.abp_open_file(abp_path)
    abp_window.abp__plan = abpFloorPlan(abp_scale_m_per_px=0.02)
    abp_window.abp_load_page.abp_open_file(abp_path)
    assert abp_window.abp_plan == abpFloorPlan()


def abp_test_bad_file_reports_error(
    qtbot: QtBot, abp_services: abpAppServices, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_window, "abp_show_error", abp_errors.append)
    abp_window.abp_create_project("Oficina", abpUseType.abp_OFFICE)
    abp_bad = tmp_path / "plano.dwg"
    abp_bad.write_bytes(b"x")
    abp_window.abp_load_page.abp_open_file(abp_bad)
    assert abp_errors
    assert "no soportado" in abp_errors[0]


def abp_test_scale_without_line_reports_error(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_window, "abp_show_error", abp_errors.append)
    abp_window.abp_scale_page.abp_apply_scale()
    assert abp_errors == [abp_window.abp_scale_page.abp__texts.abp_scale_draw_first]


def abp_test_project_service_errors(abp_services: abpAppServices) -> None:
    with pytest.raises(abpUserFacingError, match="nombre"):
        abp_services.abp_projects.abp_create_project("", abpUseType.abp_EDUCATION)
    with pytest.raises(abpUserFacingError, match="ya no existe"):
        abp_services.abp_projects.abp_get_project(999)
    assert abp_services.abp_projects.abp_load_floor(999) is None
    assert (
        abp_services.abp_projects.abp_load_floor_image(abpFloorPlan(abp_image_path="no/existe.png"))
        is None
    )
    abp_blank = np.zeros((10, 10, 3), np.uint8)
    with pytest.raises(abpUserFacingError, match="4 esquinas"):
        abp_services.abp_plans.abp_straighten(abp_blank, [abpPoint(0, 0)])
