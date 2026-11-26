from __future__ import annotations

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpUseType
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import (
    abp_next_stair_name,
    abpPlanEditor,
)
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_ROOMS,
    abp_STEP_SIMULATE,
    abpMainWindow,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_two_floor_building


@pytest.fixture
def abp_window(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> abpMainWindow:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio de dos pisos", abpUseType.abp_EDUCATION
    )
    abp_ground, abp_upper = abp_two_floor_building()
    abp_image = np.full((320, 520, 3), 250, np.uint8)
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_ground, abp_image)
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_upper, abp_image)
    abp_win = abpMainWindow(abp_services)
    qtbot.addWidget(abp_win)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_win, "abp_show_error", abp_errors.append)
    abp_win.abp_errors = abp_errors
    abp_win.abp_open_project(abp_project_id)
    return abp_win


def abp__errors(abp_window: abpMainWindow) -> list[str]:
    return list(getattr(abp_window, "abp_errors"))


def abp_test_floor_bar_and_switching(abp_window: abpMainWindow) -> None:
    assert not abp_window.abp_floor_bar.isHidden()
    assert [
        abp_window.abp_floor_combo.itemText(abp_i)
        for abp_i in range(abp_window.abp_floor_combo.count())
    ] == [
        "Piso 1",
        "Piso 2",
    ]
    assert abp_window.abp_level == 0
    assert not abp_window.abp_delete_floor_button.isEnabled()
    assert abp_window.abp_switch_floor(1)
    assert abp_window.abp_level == 1
    assert abp_window.abp_plan.abp_rooms[0].abp_name == "Aula 201"
    assert abp_window.abp_editor_page.abp_editor.abp_plan().abp_level == 1
    assert abp_window.abp_delete_floor_button.isEnabled()
    abp_window.abp_floor_combo.setCurrentIndex(0)
    assert abp_window.abp_level == 0


def abp_test_occupants_per_floor_and_simulation(abp_window: abpMainWindow, qtbot: QtBot) -> None:
    abp_window.abp_go_to_step(abp_STEP_ROOMS)
    abp_window.abp_rooms_page.abp_set_occupants("Hall", "adulto", 5)
    abp_window.abp_switch_floor(1)
    assert abp_window.abp_current_step() == abp_STEP_ROOMS
    abp_window.abp_rooms_page.abp_set_occupants("Aula 201", "niño", 20)
    abp_scenario = abp_window.abp_scenario
    assert abp_scenario is not None
    assert {(abp_o.abp_room_name, abp_o.abp_level) for abp_o in abp_scenario.abp_occupancies} == {
        ("Hall", 0),
        ("Aula 201", 1),
    }

    abp_window.abp_go_to_step(abp_STEP_SIMULATE)
    abp_page = abp_window.abp_simulation_page
    assert [abp_p.abp_level for abp_p in abp_page.abp_plans] == [0, 1]
    with qtbot.waitSignal(abp_page.abp_run_finished, timeout=120_000):
        abp_page.abp_start_simulation()
    abp_run = abp_page.abp_current_run
    assert abp_run is not None
    assert abp_run.abp_result.abp_agents_total == 25
    assert [abp_m.abp_level for abp_m in abp_run.abp_result.abp_floor_maps] == [0, 1]
    abp_viewer = abp_page.abp_viewer
    assert not abp_viewer.abp_floor_combo.isHidden()
    abp_viewer.abp_pause()
    abp_viewer.abp_set_time(0.0)
    abp_viewer.abp_show_floor(1)
    assert abp_viewer.abp_agents.abp_visible_count == 20
    abp_viewer.abp_show_floor(0)
    assert abp_viewer.abp_agents.abp_visible_count == 5
    assert abp__errors(abp_window) == []


def abp_test_add_and_delete_floors(abp_window: abpMainWindow) -> None:
    assert abp_window.abp_add_floor()
    assert abp_window.abp_level == 2
    assert abp_window.abp_floor_combo.count() == 3
    abp_window.abp_go_to_step(abp_STEP_ROOMS)
    assert abp_window.abp_delete_current_floor()
    assert abp_window.abp_level == 1
    assert abp_window.abp_floor_combo.count() == 2
    abp_window.abp_switch_floor(0)
    assert not abp_window.abp_delete_current_floor()
    assert any("más alto" in abp_e for abp_e in abp__errors(abp_window))
    assert abp_window.abp_add_floor()
    assert abp_window.abp_add_floor()
    assert abp_window.abp_floor_combo.count() == 4
    assert not abp_window.abp_add_floor()
    assert any("hasta 4 pisos" in abp_e for abp_e in abp__errors(abp_window))
    assert not abp_window.abp_add_floor_button.isEnabled()


def abp_test_stairs_are_named_in_order(qtbot: QtBot) -> None:
    abp_editor = abpPlanEditor()
    qtbot.addWidget(abp_editor)
    abp_editor.abp_add_area(abpElementType.abp_STAIR, abp_rect(0, 0, 1, 2))
    abp_editor.abp_add_area(abpElementType.abp_STAIR, abp_rect(5, 0, 1, 2))
    assert [abp_s.abp_name for abp_s in abp_editor.abp_plan().abp_stairs] == [
        "Escalera A",
        "Escalera B",
    ]
    assert abp_next_stair_name(abp_editor.abp_plan(), "Escalera {letter}") == "Escalera C"
