from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QSpinBox
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpTool
from abp_rutasegura.abp_presentation.abp_rooms_page import abp_FIRST_PROFILE_COL, abpRoomsPage
from abp_rutasegura.abp_presentation.abp_simulation_viewer import (
    abp_format_time,
    abp_heatmap_rgba,
    abp_SPEEDS,
    abpSimulationViewer,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_SCALE, abp_two_rooms
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation

abp_PROFILES = [
    abpPersonProfile("adulto", 1.3, 5, 2, 0.25),
    abpPersonProfile("niño", 1.0, 3, 1, 0.2),
]


@pytest.fixture
def abp_page(qtbot: QtBot) -> abpRoomsPage:
    abp_widget = abpRoomsPage(abpPlanImportService())
    qtbot.addWidget(abp_widget)
    abp_plan = dataclasses.replace(abp_two_rooms(), abp_rooms=())
    abp_widget.abp_set_content(
        abp_plan, None, abpScenario("Base", 1), abp_PROFILES, abpUseType.abp_EDUCATION
    )
    return abp_widget


class abpTestRoomsPage:
    def abp_test_detect_and_assign_occupants(self, abp_page: abpRoomsPage, qtbot: QtBot) -> None:
        with qtbot.waitSignal(abp_page.abp_plan_changed):
            abp_page.abp_detect_rooms()
        assert [abp_r.abp_name for abp_r in abp_page.abp_plan.abp_rooms] == [
            "Ambiente 1",
            "Ambiente 2",
        ]
        assert abp_page.abp_table.rowCount() == 2
        abp_area_item = abp_page.abp_table.item(0, 2)
        assert abp_area_item is not None
        assert float(abp_area_item.text()) == pytest.approx(36.0, rel=0.1)
        abp_spin = abp_page.abp_table.cellWidget(0, abp_FIRST_PROFILE_COL + 1)
        assert isinstance(abp_spin, QSpinBox)
        with qtbot.waitSignal(abp_page.abp_scenario_changed):
            abp_spin.setValue(25)
        assert abp_page.abp_scenario.abp_occupancies == (abpOccupancy("Ambiente 1", "niño", 25),)
        assert "25" in abp_page.abp_total_label.text()
        abp_page.abp_detect_rooms()
        assert len(abp_page.abp_plan.abp_rooms) == 2

    def abp_test_rename_updates_occupancies(self, abp_page: abpRoomsPage) -> None:
        abp_page.abp_detect_rooms()
        abp_page.abp_set_occupants("Ambiente 1", "adulto", 3)
        abp_name_item = abp_page.abp_table.item(0, 0)
        assert abp_name_item is not None
        abp_name_item.setText("Aula 1A")
        assert abp_page.abp_plan.abp_rooms[0].abp_name == "Aula 1A"
        assert abp_page.abp_scenario.abp_occupancies == (abpOccupancy("Aula 1A", "adulto", 3),)

    def abp_test_duplicate_name_is_rejected(self, abp_page: abpRoomsPage, qtbot: QtBot) -> None:
        abp_page.abp_detect_rooms()
        with qtbot.waitSignal(abp_page.abp_error) as abp_blocker:
            abp_page.abp_rename_room(1, "Ambiente 1")
        assert "Ya existe" in abp_blocker.args[0]
        assert abp_page.abp_plan.abp_rooms[1].abp_name == "Ambiente 2"

    def abp_test_delete_room_removes_its_occupants(self, abp_page: abpRoomsPage) -> None:
        abp_page.abp_detect_rooms()
        abp_page.abp_set_occupants("Ambiente 1", "adulto", 3)
        abp_page.abp_set_occupants("Ambiente 2", "niño", 4)
        abp_page.abp_table.selectRow(0)
        abp_page.abp_delete_selected_room()
        assert [abp_r.abp_name for abp_r in abp_page.abp_plan.abp_rooms] == ["Ambiente 2"]
        assert abp_page.abp_scenario.abp_occupancies == (abpOccupancy("Ambiente 2", "niño", 4),)

    def abp_test_draw_room_with_polygon_tool(self, abp_page: abpRoomsPage) -> None:
        abp_page.abp_draw_button.setChecked(True)
        assert abp_page.abp_view.abp_tool is abpTool.abp_POLYGON
        for abp_x, abp_y in ((0, 0), (100, 0), (100, 100)):
            abp_page.abp_view.abp_add_polygon_vertex(QPointF(abp_x, abp_y))
        abp_page.abp_view.abp_add_polygon_vertex(QPointF(100, 100.5))
        abp_page.abp_view.abp_finish_polygon()
        assert len(abp_page.abp_plan.abp_rooms) == 1
        assert len(abp_page.abp_plan.abp_rooms[0].abp_area.abp_vertices) == 3
        assert abp_page.abp_plan.abp_rooms[0].abp_use is abpUseType.abp_EDUCATION
        abp_page.abp_view.abp_add_polygon_vertex(QPointF(0, 0))
        abp_page.abp_view.abp_finish_polygon()
        assert len(abp_page.abp_plan.abp_rooms) == 1

    def abp_test_change_use(self, abp_page: abpRoomsPage) -> None:
        abp_page.abp_detect_rooms()
        abp_page.abp_set_room_use(0, abpUseType.abp_OFFICE)
        assert abp_page.abp_plan.abp_rooms[0].abp_use is abpUseType.abp_OFFICE


class abpTestViewer:
    @pytest.fixture
    def abp_viewer(self, qtbot: QtBot) -> abpSimulationViewer:
        abp_out = abp_make_simulation(
            abp_two_rooms(), [abpOccupancy("Aula 1", "adulto", 15)]
        ).abp_run()
        abp_widget = abpSimulationViewer()
        qtbot.addWidget(abp_widget)
        abp_widget.abp_set_plan(abp_two_rooms(), np.full((300, 600, 3), 255, np.uint8))
        abp_widget.abp_set_run(abp_out.abp_trajectories, abp_out.abp_result, abp_SCALE)
        return abp_widget

    def abp_test_timeline_and_interpolation(self, abp_viewer: abpSimulationViewer) -> None:
        assert abp_viewer.abp_end_time > 0
        assert abp_viewer.abp_agents.abp_visible_count == 15
        abp_viewer.abp_set_time(abp_viewer.abp_end_time)
        assert abp_viewer.abp_agents.abp_visible_count == 0
        assert abp_viewer.abp_slider.value() == 1000
        abp_viewer.abp_set_time(-5)
        assert abp_viewer.abp_current_time == 0
        assert "0 de 15" in abp_viewer.abp_evacuated_label.text()

    def abp_test_play_pause_and_speed(self, abp_viewer: abpSimulationViewer) -> None:
        abp_viewer.abp_play()
        assert abp_viewer.abp_is_playing
        abp_viewer.abp_set_speed(100)
        assert abp_viewer.abp_speed == abp_SPEEDS[-1]
        abp_viewer.abp_set_speed(0.1)
        assert abp_viewer.abp_speed == abp_SPEEDS[0]
        abp_viewer.abp_set_speed(4.0)
        abp_viewer.abp_advance(1.0)
        assert abp_viewer.abp_current_time == pytest.approx(4.0)
        abp_viewer.abp_advance(10_000)
        assert not abp_viewer.abp_is_playing
        assert abp_viewer.abp_current_time == abp_viewer.abp_end_time
        abp_viewer.abp_play()
        assert abp_viewer.abp_current_time == 0.0
        abp_viewer.abp_toggle_play()
        assert not abp_viewer.abp_is_playing

    def abp_test_heatmap_toggle(self, abp_viewer: abpSimulationViewer) -> None:
        assert not abp_viewer.abp_heatmap.isVisible()
        abp_viewer.abp_heatmap_check.setChecked(True)
        assert abp_viewer.abp_heatmap.isVisible()

    def abp_test_clear(self, abp_viewer: abpSimulationViewer) -> None:
        abp_viewer.abp_set_run(None, None, 1.0)
        assert not abp_viewer.abp_play_button.isEnabled()
        assert abp_viewer.abp_end_time == 0.0


def abp_test_heatmap_colors_and_time_format() -> None:
    abp_density = np.array([[0.0, 1.0], [5.0, 10.0]])
    abp_rgba = abp_heatmap_rgba(abp_density)
    assert abp_rgba.shape == (2, 2, 4)
    assert abp_rgba[0, 0, 3] == 0
    assert abp_rgba[1, 1, 3] > abp_rgba[0, 1, 3]
    assert abp_heatmap_rgba(np.zeros((2, 2)))[..., 3].max() == 0
    assert abp_format_time(155.4) == "2:35"
    assert abp_format_time(-3) == "0:00"
