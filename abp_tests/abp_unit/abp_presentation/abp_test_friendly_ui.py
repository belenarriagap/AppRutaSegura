from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QPushButton
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_progress import abpStepState
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpSafeZone
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_icons import (
    abp_element_icon,
    abp_select_icon,
    abp_step_icon,
)
from abp_rutasegura.abp_presentation.abp_main_window import (
    abp_STEP_EDIT,
    abp_STEP_LOAD,
    abp_STEP_SCALE,
    abpMainWindow,
)
from abp_rutasegura.abp_presentation.abp_theme import (
    abp_apply_theme,
    abp_PRIMARY,
    abp_set_primary,
    abp_STYLESHEET,
)
from abp_rutasegura.abp_presentation.abp_widgets import abpBanner, abpMetricCard
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect


def abp__seg(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


class abpTestThemeAndWidgets:
    def abp_test_theme_applies(self, qtbot: QtBot) -> None:
        abp_app = QApplication.instance()
        assert isinstance(abp_app, QApplication)
        abp_sheet, abp_font, abp_palette, abp_style = (
            abp_app.styleSheet(),
            abp_app.font(),
            abp_app.palette(),
            abp_app.style().name(),
        )
        try:
            abp_apply_theme(abp_app)
            assert abp_app.styleSheet() == abp_STYLESHEET
            assert (
                abp_app.palette().color(abp_app.palette().ColorRole.Highlight).name() == abp_PRIMARY
            )
        finally:
            abp_app.setStyleSheet(abp_sheet)
            abp_app.setFont(abp_font)
            abp_app.setPalette(abp_palette)
            abp_app.setStyle(abp_style)
        abp_button = abp_set_primary(QPushButton("Simular"))
        qtbot.addWidget(abp_button)
        assert abp_button.property("primary") is True

    def abp_test_icons_are_drawn(self, qtbot: QtBot) -> None:
        for abp_kind in (None, *abpElementType):
            assert not abp_element_icon(abp_kind).isNull()
        assert not abp_select_icon().isNull()
        for abp_state in abpStepState:
            assert not abp_step_icon(abp_state, 3).isNull()

    def abp_test_banner(self, qtbot: QtBot) -> None:
        abp_banner = abpBanner()
        qtbot.addWidget(abp_banner)
        assert abp_banner.isHidden()
        abp_clicks: list[int] = []
        abp_banner.abp_show_message(
            "Falta la escala",
            "warning",
            abp_action_text="Ir",
            abp_action=lambda: abp_clicks.append(1),
        )
        assert not abp_banner.isHidden()
        assert abp_banner.abp_kind == "warning"
        assert abp_banner.abp_text == "Falta la escala"
        abp_banner.abp_action_button.click()
        assert abp_clicks == [1]
        with qtbot.waitSignal(abp_banner.abp_closed):
            abp_banner.abp_close_button.click()
        assert abp_banner.isHidden()
        with pytest.raises(ValueError, match="desconocido"):
            abp_banner.abp_show_message("x", "rosado")

    def abp_test_banner_hides_itself(self, qtbot: QtBot) -> None:
        abp_banner = abpBanner()
        qtbot.addWidget(abp_banner)
        abp_banner.abp_show_message("Guardado", "success", abp_timeout_ms=10)
        qtbot.waitUntil(abp_banner.isHidden, timeout=2000)

    def abp_test_metric_card(self, qtbot: QtBot) -> None:
        abp_card = abpMetricCard("Tiempo total")
        qtbot.addWidget(abp_card)
        abp_card.abp_set_value("1 min 30 s", "Salieron todos", "success")
        assert abp_card.abp_value_label.text() == "1 min 30 s"
        assert abp_card.abp_kind == "success"
        assert not abp_card.abp_note_label.isHidden()


class abpTestEditorExtras:
    @pytest.fixture
    def abp_editor(self, qtbot: QtBot) -> abpPlanEditor:
        abp_widget = abpPlanEditor()
        qtbot.addWidget(abp_widget)
        abp_widget.resize(900, 600)
        abp_widget.abp_set_plan(abpFloorPlan(), np.full((400, 600, 3), 255, np.uint8))
        return abp_widget

    def abp_test_tools_have_icons_shortcuts_and_tips(self, abp_editor: abpPlanEditor) -> None:
        for abp_action in abp_editor.abp_tool_actions.values():
            assert not abp_action.icon().isNull()
            assert not abp_action.shortcut().isEmpty()
            assert "Atajo:" in abp_action.toolTip()

    def abp_test_rename_with_undo_and_validation(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_EXIT, abp__seg(0, 0, 50, 0))
        abp_editor.abp_add_segment(abpElementType.abp_EXIT, abp__seg(0, 100, 50, 100))
        abp_errors: list[str] = []
        abp_editor.abp_error.connect(abp_errors.append)
        assert abp_editor.abp_rename((abpElementType.abp_EXIT, 0), "Puerta principal")
        assert abp_editor.abp_plan().abp_exits[0].abp_name == "Puerta principal"
        assert not abp_editor.abp_rename((abpElementType.abp_EXIT, 1), "Puerta principal")
        assert not abp_editor.abp_rename((abpElementType.abp_EXIT, 1), "   ")
        assert len(abp_errors) == 2
        assert not abp_editor.abp_rename((abpElementType.abp_WALL, 0), "Muro")
        abp_editor.abp_undo_stack.undo()
        assert abp_editor.abp_plan().abp_exits[0].abp_name == "Salida 1"
        abp_editor.abp_add_area(abpElementType.abp_SAFE_ZONE, abp_rect(1, 1, 2, 2))
        assert abp_editor.abp_rename((abpElementType.abp_SAFE_ZONE, 0), "Patio")
        assert abp_editor.abp_plan().abp_safe_zones[0] == abpSafeZone(abp_rect(1, 1, 2, 2), "Patio")

    def abp_test_context_menu_actions(self, abp_editor: abpPlanEditor) -> None:
        abp_proposed = abpFloorPlan(
            abp_exits=(abpExit(abp__seg(0, 0, 50, 0), "Salida 1", abp_confirmed=False),)
        )
        abp_editor.abp_set_plan(abp_proposed, None)
        abp_menu = abp_editor.abp_context_menu((abpElementType.abp_EXIT, 0))
        abp_labels = [abp_a.text() for abp_a in abp_menu.actions() if not abp_a.isSeparator()]
        abp_t = abp_TEXTS.abp_editor
        assert abp_labels[0] == abp_t.abp_menu_confirm
        assert "Convertir en puerta" in abp_labels
        assert abp_labels[-2:] == [abp_t.abp_menu_rename, abp_t.abp_menu_delete]
        abp_menu.actions()[0].trigger()
        assert abp_editor.abp_plan().abp_exits[0].abp_confirmed
        abp_menu = abp_editor.abp_context_menu((abpElementType.abp_EXIT, 0))
        assert abp_t.abp_menu_confirm not in [abp_a.text() for abp_a in abp_menu.actions()]
        next(
            abp_a for abp_a in abp_menu.actions() if abp_a.text() == abp_t.abp_menu_delete
        ).trigger()
        assert abp_editor.abp_plan().abp_exits == ()

    def abp_test_double_click_confirms_a_proposed_exit(
        self, abp_editor: abpPlanEditor, qtbot: QtBot
    ) -> None:
        abp_editor.show()
        qtbot.waitExposed(abp_editor)
        abp_proposed = abpFloorPlan(
            abp_exits=(abpExit(abp__seg(100, 100, 300, 100), "Salida 1", abp_confirmed=False),)
        )
        abp_editor.abp_set_plan(abp_proposed, np.full((400, 600, 3), 255, np.uint8))
        abp_editor.abp_view.abp_fit_all()
        abp_on_exit, abp_empty = QPointF(200, 101), QPointF(50, 300)
        assert abp_editor.abp_scene.abp_ref_at(
            abp_on_exit, abp_editor.abp_view.abp_scene_tolerance()
        ) == (abpElementType.abp_EXIT, 0)
        abp_editor.abp_view.abp_double_clicked.emit(abp_on_exit)
        assert abp_editor.abp_plan().abp_exits[0].abp_confirmed
        abp_before = abp_editor.abp_plan()
        abp_editor.abp_view.abp_double_clicked.emit(abp_empty)
        assert abp_editor.abp_plan() == abp_before


class abpTestGuide:
    def abp_test_welcome_lists_projects(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        assert abp_window.abp_recent_list.isHidden()
        assert not abp_window.abp_recent_empty.isHidden()
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Colegio Los Pinos", abpUseType.abp_EDUCATION
        )
        abp_window.abp_refresh_recent_projects()
        assert abp_window.abp_recent_list.count() == 1
        abp_item = abp_window.abp_recent_list.item(0)
        assert "Colegio Los Pinos" in abp_item.text()
        abp_window.abp__on_recent_activated(abp_item)
        assert abp_window.abp_project_id == abp_project_id

    def abp_test_guide_tells_what_is_missing(
        self, qtbot: QtBot, abp_services: abpAppServices
    ) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_window.abp_create_project("Tienda", abpUseType.abp_COMMERCE)
        abp_g = abp_TEXTS.abp_guide
        assert abp_window.abp_current_step() == abp_STEP_LOAD
        assert not abp_window.abp_guide_banner.isHidden()
        assert abp_g.abp_issue_text("sin_imagen") in abp_window.abp_guide_banner.abp_text
        assert not abp_window.abp_prev_button.isEnabled()
        abp_window.abp_go_to_step(abp_STEP_EDIT)
        assert abp_window.abp_guide_banner.abp_kind == "warning"
        assert "paso 1" in abp_window.abp_guide_banner.abp_text
        abp_window.abp_guide_banner.abp_action_button.click()
        assert abp_window.abp_current_step() == abp_STEP_LOAD
        abp_window.abp_next_button.click()
        assert abp_window.abp_current_step() == abp_STEP_SCALE
        assert abp_TEXTS.abp_wizard_steps[abp_STEP_SCALE] in abp_window.abp_nav_label.text()
        abp_window.abp_prev_button.click()
        assert abp_window.abp_current_step() == abp_STEP_LOAD

    def abp_test_errors_show_in_a_banner(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        abp_window.abp_create_project("Oficina", abpUseType.abp_OFFICE)
        abp_window.abp_show_error("No se pudo leer el archivo.")
        assert abp_window.abp_message_banner.abp_kind == "error"
        assert abp_window.abp_message_banner.abp_text == "No se pudo leer el archivo."
        abp_window.abp_go_to_step(abp_STEP_SCALE)
        assert abp_window.abp_message_banner.isHidden()
