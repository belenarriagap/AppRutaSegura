from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import pytest
from PySide6.QtWidgets import QTableWidget
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_simulation_service import (
    abp_BASE_SCENARIO,
    abp_scale_occupancies,
)
from abp_rutasegura.abp_domain.abp_calibration import abpCalibrationResult
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill
from abp_rutasegura.abp_engines.abp_calibration.abp_grid_search import abp_scale_profiles
from abp_rutasegura.abp_presentation.abp_calibration_dialog import abpCalibrationDialog
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_ROOMS,
    abp_STEP_SIMULATE,
    abpMainWindow,
)
from abp_rutasegura.abp_presentation.abp_scenario_dialogs import (
    abpScenarioChoice,
    abpScenarioDialog,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_single_room

abp_PLAN = abp_single_room(abp_exit_width=0.9, abp_second_exit=True)


@pytest.fixture
def abp_window(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> abpMainWindow:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(
        abp_project_id, abp_PLAN, np.full((320, 520, 3), 250, np.uint8)
    )
    abp_win = abpMainWindow(abp_services)
    qtbot.addWidget(abp_win)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_win, "abp_show_error", abp_errors.append)
    abp_win.abp_errors = abp_errors
    abp_win.abp_open_project(abp_project_id)
    abp_win.abp_go_to_step(abp_STEP_ROOMS)
    abp_win.abp_rooms_page.abp_set_occupants("Aula 1", "adulto", 150)
    abp_win.abp_go_to_step(abp_STEP_SIMULATE)
    return abp_win


def abp__cell(abp_table: QTableWidget, abp_row: int, abp_col: int) -> str:
    abp_item = abp_table.item(abp_row, abp_col)
    assert abp_item is not None
    return abp_item.text()


def abp__run(abp_window: abpMainWindow, qtbot: QtBot, abp_name: str) -> None:
    abp_page = abp_window.abp_simulation_page
    abp_page.abp_select_scenario(abp_name)
    with qtbot.waitSignal(abp_page.abp_run_finished, timeout=120_000):
        abp_page.abp_start_simulation()


def abp_test_variants_compare_and_delete(abp_window: abpMainWindow, qtbot: QtBot) -> None:
    abp_page = abp_window.abp_simulation_page
    assert abp_page.abp_scenario_names == [abp_BASE_SCENARIO]
    assert not abp_page.abp_edit_button.isEnabled()
    assert abp_page.abp_create_variant(
        abpScenarioChoice("Sin salida 2", 100, frozenset({"Salida 2"}))
    )
    assert abp_page.abp_scenario_names == [abp_BASE_SCENARIO, "Sin salida 2"]
    assert abp_page.abp_current_scenario.abp_blocked_exits == frozenset({"Salida 2"})
    assert abp_page.abp_edit_button.isEnabled()
    assert abp_page.abp_current_run is None

    abp__run(abp_window, qtbot, abp_BASE_SCENARIO)
    abp__run(abp_window, qtbot, "Sin salida 2")
    assert abp_page.abp_current_run is not None
    abp_blocked_time = abp_page.abp_current_run.abp_result.abp_total_time_s
    abp_page.abp_select_scenario(abp_BASE_SCENARIO)
    assert abp_page.abp_current_run is not None
    assert abp_page.abp_current_run.abp_result.abp_total_time_s < abp_blocked_time

    abp_dialog = abp_page.abp_comparison_dialog()
    assert abp_dialog is not None
    qtbot.addWidget(abp_dialog)
    assert abp_dialog.abp_available == [abp_BASE_SCENARIO, "Sin salida 2"]
    abp_cells = {
        abp__cell(abp_dialog.abp_table, abp_r, 0): abp__cell(abp_dialog.abp_table, abp_r, 3)
        for abp_r in range(abp_dialog.abp_table.rowCount())
    }
    assert abp_cells["Tiempo para evacuar al 90 %"].startswith("+")
    assert "Tiempo por «Salida 2»" in abp_cells
    abp_dialog.abp_play_both()
    assert all(abp_v.abp_is_playing for abp_v in abp_dialog.abp_viewers)

    abp_page.abp_select_scenario("Sin salida 2")
    assert abp_page.abp_update_current_variant(abpScenarioChoice("Doble aforo", 200, frozenset()))
    assert abp_page.abp_scenario_names == [abp_BASE_SCENARIO, "Doble aforo"]
    assert abp_page.abp_current_scenario.abp_total_occupants == 300
    abp_page.abp_seed_spin.setValue(99)
    assert getattr(abp_window, "abp_errors") == []
    abp_page.abp_delete_current_variant()
    assert abp_page.abp_scenario_names == [abp_BASE_SCENARIO]


def abp_test_invalid_variant_reports_error(abp_window: abpMainWindow) -> None:
    assert not abp_window.abp_simulation_page.abp_create_variant(
        abpScenarioChoice(abp_BASE_SCENARIO, 100, frozenset())
    )
    assert getattr(abp_window, "abp_errors")


def abp_test_comparison_needs_two_runs(abp_window: abpMainWindow, qtbot: QtBot) -> None:
    abp_dialog = abp_window.abp_simulation_page.abp_comparison_dialog()
    assert abp_dialog is not None
    qtbot.addWidget(abp_dialog)
    assert abp_dialog.abp_available == []
    assert "al menos dos" in abp_dialog.abp_message.text()
    assert not abp_dialog.abp_play_button.isEnabled()


def abp_test_scenario_dialog_values(qtbot: QtBot) -> None:
    abp_dialog = abpScenarioDialog(
        ["Salida 1", "Salida 2"],
        40,
        abp_name="X",
        abp_percent=150,
        abp_blocked=frozenset({"Salida 1"}),
    )
    qtbot.addWidget(abp_dialog)
    assert abp_dialog.abp_values() == ("X", 150, frozenset({"Salida 1"}))
    assert "60 personas" in abp_dialog.abp_result_label.text()


def abp_test_calibration_dialog(
    abp_window: abpMainWindow, abp_services: abpAppServices, qtbot: QtBot
) -> None:
    abp_empty = abp_window.abp_calibration_dialog()
    assert abp_empty is not None
    qtbot.addWidget(abp_empty)
    with qtbot.waitSignal(abp_empty.abp_failed):
        abp_empty.abp_start()
    assert "tiempo total" in abp_empty.abp_status_label.text()
    abp_scenario = abp_window.abp_scenario
    assert abp_scenario is not None
    abp_drill_scenario = dataclasses.replace(
        abp_scenario, abp_occupancies=abp_scale_occupancies(abp_scenario.abp_occupancies, 30)
    )
    abp_truth = abp_services.abp_simulations.abp_simulate(
        abp_PLAN,
        abp_drill_scenario,
        abp_scale_profiles(abp_services.abp_simulations.abp_profiles(), 1.5, 1.0),
    ).abp_result
    abp_dialog = abpCalibrationDialog(
        abp_services.abp_calibration,
        abp_window.abp_project_id or 0,
        abp_window.abp_plan,
        abp_scenario,
        abp_grid=((1.0, 1.5), (1.0,)),
    )
    qtbot.addWidget(abp_dialog)
    abp_dialog.abp_set_drill(
        abpRealDrill(
            date(2026, 10, 8), 30, round(abp_truth.abp_total_time_s), abp_truth.abp_time_per_exit_s
        )
    )
    assert abp_dialog.abp_drill().abp_participants == 30
    with qtbot.waitSignal(abp_dialog.abp_calibrated, timeout=120_000) as abp_blocker:
        abp_dialog.abp_start()
    abp_result = abp_blocker.args[0]
    assert isinstance(abp_result, abpCalibrationResult)
    assert abp_result.abp_best.abp_reaction_factor == 1.5
    assert "Tiempos de reacción × 1.5" in abp_dialog.abp_result_label.text()
    assert abp_dialog.abp_apply_button.isEnabled()
    abp_before = abp_services.abp_simulations.abp_profiles()[0].abp_reaction_mean_s
    with qtbot.waitSignal(abp_dialog.abp_applied):
        abp_dialog.abp_apply()
    assert abp_services.abp_simulations.abp_profiles()[0].abp_reaction_mean_s == pytest.approx(
        abp_before * 1.5
    )
    assert not abp_dialog.abp_apply_button.isEnabled()
