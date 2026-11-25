from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtWidgets import QSpinBox
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_ROOMS,
    abp_STEP_SIMULATE,
    abpMainWindow,
)
from abp_rutasegura.abp_presentation.abp_rooms_page import abp_FIRST_PROFILE_COL
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_rooms


@pytest.fixture
def abp_window(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> abpMainWindow:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(
        abp_project_id, dataclasses.replace(abp_two_rooms(), abp_rooms=())
    )
    abp_win = abpMainWindow(abp_services)
    qtbot.addWidget(abp_win)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_win, "abp_show_error", abp_errors.append)
    abp_win.abp_errors = abp_errors
    abp_win.abp_open_project(abp_project_id)
    return abp_win


def abp_test_rooms_occupants_simulate_and_reopen(
    abp_window: abpMainWindow, abp_services: abpAppServices, qtbot: QtBot
) -> None:
    abp_window.abp_go_to_step(abp_STEP_ROOMS)
    abp_rooms = abp_window.abp_rooms_page
    assert abp_window.abp_stack.currentWidget() is abp_rooms
    abp_rooms.abp_detect_rooms()
    abp_profiles = [abp_p.abp_name for abp_p in abp_services.abp_simulations.abp_profiles()]
    abp_child_col = abp_FIRST_PROFILE_COL + abp_profiles.index("niño")
    for abp_row, abp_count in ((0, 20), (1, 15)):
        abp_spin = abp_rooms.abp_table.cellWidget(abp_row, abp_child_col)
        assert isinstance(abp_spin, QSpinBox)
        abp_spin.setValue(abp_count)
    assert abp_window.abp_is_dirty

    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    assert not abp_window.abp_is_dirty
    abp_page = abp_window.abp_simulation_page
    abp_page.abp_seed_spin.setValue(77)
    with qtbot.waitSignal(abp_page.abp_run_finished, timeout=120_000):
        abp_page.abp_start_simulation()
    abp_run = abp_page.abp_current_run
    assert abp_run is not None
    assert abp_run.abp_result.abp_agents_total == 35
    assert abp_run.abp_result.abp_completed
    assert abp_run.abp_result.abp_seed == 77
    assert "Tiempo total" in abp_page.abp_summary_label.text()
    assert abp_page.abp_bottleneck_list.count() >= 1
    assert abp_page.abp_viewer.abp_is_playing
    assert getattr(abp_window, "abp_errors") == []

    abp_other = abpMainWindow(abp_services)
    qtbot.addWidget(abp_other)
    abp_other.abp_open_project(abp_window.abp_project_id or 0)
    assert abp_other.abp_scenario is not None
    assert abp_other.abp_scenario.abp_total_occupants == 35
    assert abp_other.abp_scenario.abp_seed == 77
    abp_restored = abp_other.abp_simulation_page.abp_current_run
    assert abp_restored is not None
    assert abp_restored.abp_result.abp_total_time_s == abp_run.abp_result.abp_total_time_s


def abp_test_cancel_simulation(abp_window: abpMainWindow, qtbot: QtBot) -> None:
    abp_window.abp_go_to_step(abp_STEP_ROOMS)
    abp_window.abp_rooms_page.abp_detect_rooms()
    abp_window.abp_rooms_page.abp_set_occupants("Ambiente 1", "adulto", 200)
    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    abp_page = abp_window.abp_simulation_page
    abp_page.abp_start_simulation()
    assert abp_page.abp_job is not None
    with qtbot.waitSignal(abp_page.abp_job.abp_cancelled, timeout=60_000):
        abp_page.abp_cancel_simulation()
    assert abp_page.abp_run_button.isEnabled()
    assert "cancelada" in abp_page.abp_status_label.text()


def abp_test_simulation_errors_are_reported(abp_window: abpMainWindow, qtbot: QtBot) -> None:
    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    abp_page = abp_window.abp_simulation_page
    with qtbot.waitSignal(abp_page.abp_error, timeout=30_000) as abp_blocker:
        abp_page.abp_start_simulation()
    assert "ambientes" in abp_blocker.args[0]


def abp_test_refresh_plan_and_outdated_results(
    abp_window: abpMainWindow, abp_services: abpAppServices, qtbot: QtBot
) -> None:
    abp_window.abp_go_to_step(abp_STEP_ROOMS)
    abp_window.abp_rooms_page.abp_detect_rooms()
    abp_window.abp_rooms_page.abp_set_occupants("Ambiente 1", "adulto", 6)
    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    abp_page = abp_window.abp_simulation_page
    with qtbot.waitSignal(abp_page.abp_run_finished, timeout=120_000):
        abp_page.abp_start_simulation()
    assert not abp_page.abp_is_outdated
    abp_plan = abp_window.abp_plan
    abp_window.abp__on_plan_edited(dataclasses.replace(abp_plan, abp_walls=abp_plan.abp_walls[:-1]))
    abp_page.abp_refresh_button.click()
    assert abp_window.abp_message_banner.abp_kind == "success"
    assert not abp_window.abp_is_dirty
    assert abp_page.abp_is_outdated
    assert abp_page.abp_outdated_banner.abp_action_button.isVisible() or not abp_page.isVisible()
    with qtbot.waitSignal(abp_page.abp_run_finished, timeout=120_000):
        abp_page.abp_outdated_banner.abp_action_button.click()
    assert not abp_page.abp_is_outdated
    abp_page.abp_seed_spin.setValue(abp_page.abp_seed_spin.value() + 1)
    assert abp_page.abp_is_outdated
    abp_reloaded = abp_services.abp_simulations.abp_last_run(abp_window.abp_project_id or 0)
    assert abp_reloaded is not None
    assert abp_reloaded.abp_fingerprint
