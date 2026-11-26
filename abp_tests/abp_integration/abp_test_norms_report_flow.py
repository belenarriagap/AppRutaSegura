from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QComboBox
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_NORMS,
    abp_STEP_REPORT,
    abp_STEP_ROOMS,
    abp_STEP_SIMULATE,
    abpMainWindow,
)
from abp_rutasegura.abp_presentation.abp_norms_page import abp_COL_CATEGORY, abp_COL_STATUS
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_rooms


@pytest.fixture
def abp_window(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> abpMainWindow:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio Norma", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(
        abp_project_id, abp_two_rooms(), np.full((300, 600, 3), 250, np.uint8)
    )
    abp_win = abpMainWindow(abp_services)
    qtbot.addWidget(abp_win)
    monkeypatch.setattr(abp_win, "abp_show_error", lambda abp_message: pytest.fail(abp_message))
    abp_win.abp_open_project(abp_project_id)
    abp_win.abp_go_to_step(abp_STEP_ROOMS)
    abp_win.abp_rooms_page.abp_set_occupants("Aula 1", "niño", 30)
    return abp_win


def abp__status(abp_window: abpMainWindow, abp_row: int) -> str:
    abp_item = abp_window.abp_norms_page.abp_table.item(abp_row, abp_COL_STATUS)
    assert abp_item is not None
    return abp_item.text()


def abp_test_norms_step_shows_capacity_and_category_changes(abp_window: abpMainWindow) -> None:
    abp_window.abp_go_to_step(abp_STEP_NORMS)
    abp_page = abp_window.abp_norms_page
    assert abp_window.abp_stack.currentWidget() is abp_page
    abp_evaluation = abp_page.abp_evaluation
    assert abp_evaluation is not None
    assert abp_evaluation.abp_capacities[0].abp_capacity == 24
    assert abp__status(abp_window, 0) == "Excede el aforo"
    assert not abp_page.abp_warning_banner.isHidden()
    assert "no fueron verificadas" in abp_page.abp_warning_banner.abp_text
    assert any(
        "aforo es 24" in abp_page.abp_observations.item(abp_i).text()
        for abp_i in range(abp_page.abp_observations.count())
    )
    assert abp_window.abp_guide_banner.abp_kind == "warning"
    assert "observación" in abp_window.abp_guide_banner.abp_text
    abp_combo = abp_page.abp_table.cellWidget(0, abp_COL_CATEGORY)
    assert isinstance(abp_combo, QComboBox)
    abp_combo.setCurrentIndex(abp_combo.findData("educacion|sum"))
    assert abp__status(abp_window, 0) == "Correcto"
    assert abp_window.abp_plan.abp_rooms[0].abp_category == "sum"
    assert abp_window.abp_is_dirty


def abp_test_report_step_generates_pdf(
    abp_window: abpMainWindow, qtbot: QtBot, tmp_path: Path
) -> None:
    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    with qtbot.waitSignal(abp_window.abp_simulation_page.abp_run_finished, timeout=120_000):
        abp_window.abp_simulation_page.abp_start_simulation()
    abp_window.abp_go_to_step(abp_STEP_REPORT)
    abp_page = abp_window.abp_report_page
    assert abp_window.abp_stack.currentWidget() is abp_page
    assert "última simulación" in abp_page.abp_status_label.text()
    with qtbot.waitSignal(abp_page.abp_report_ready, timeout=120_000) as abp_blocker:
        abp_page.abp_generate_to(tmp_path / "informe")
    abp_path = abp_blocker.args[0]
    assert isinstance(abp_path, Path)
    assert abp_path.exists()
    assert abp_path.suffix == ".pdf"
    assert abp_page.abp_open_button.isEnabled()
    assert str(abp_path) in abp_page.abp_result_label.text()


def abp_test_report_without_simulation_is_announced(abp_window: abpMainWindow) -> None:
    abp_window.abp_go_to_step(abp_STEP_REPORT)
    assert "Todavía no simuló" in abp_window.abp_report_page.abp_status_label.text()
