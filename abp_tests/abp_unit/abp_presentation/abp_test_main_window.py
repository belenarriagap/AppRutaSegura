from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_presentation.abp_main_window import abpMainWindow
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS


def abp__window(qtbot: QtBot, abp_services: abpAppServices) -> abpMainWindow:
    abp_window = abpMainWindow(abp_services)
    qtbot.addWidget(abp_window)
    return abp_window


def abp_test_main_window_opens(qtbot: QtBot, abp_services: abpAppServices) -> None:
    abp_window = abp__window(qtbot, abp_services)
    abp_window.show()
    qtbot.waitExposed(abp_window)
    assert abp_window.isVisible()
    assert abp_window.windowTitle() == abp_TEXTS.abp_window_title
    abp_steps = abp_window.findChild(QListWidget, "wizardSteps")
    assert abp_steps is not None
    assert [abp_steps.item(abp_i).text() for abp_i in range(abp_steps.count())] == list(
        abp_TEXTS.abp_wizard_steps
    )
    assert abp_window.abp_stack.currentWidget() is abp_window.abp_welcome_page


def abp_test_menus_are_in_spanish(qtbot: QtBot, abp_services: abpAppServices) -> None:
    abp_window = abp__window(qtbot, abp_services)
    abp_titles = [abp_action.text() for abp_action in abp_window.menuBar().actions()]
    assert abp_titles == [
        abp_TEXTS.abp_menu_file,
        abp_TEXTS.abp_menu_edit,
        abp_TEXTS.abp_calibration.abp_menu_tools,
        abp_TEXTS.abp_menu_help,
    ]


def abp_test_steps_enable_after_creating_project(
    qtbot: QtBot, abp_services: abpAppServices
) -> None:
    abp_window = abp__window(qtbot, abp_services)

    def abp_enabled(abp_row: int) -> bool:
        return bool(abp_window.abp_steps_list.item(abp_row).flags() & Qt.ItemFlag.ItemIsEnabled)

    assert not any(abp_enabled(abp_r) for abp_r in range(7))
    assert not abp_window.abp_save_action.isEnabled()
    abp_project_id = abp_window.abp_create_project("Colegio Prueba", abpUseType.abp_EDUCATION)
    assert abp_project_id is not None
    assert [abp_enabled(abp_r) for abp_r in range(7)] == [True] * 7
    assert abp_window.abp_stack.currentWidget() is abp_window.abp_load_page
    assert "Colegio Prueba" in abp_window.windowTitle()


def abp_test_invalid_project_name_shows_error(
    qtbot: QtBot, abp_services: abpAppServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    abp_window = abp__window(qtbot, abp_services)
    abp_errors: list[str] = []
    monkeypatch.setattr(abp_window, "abp_show_error", abp_errors.append)
    assert abp_window.abp_create_project("   ", abpUseType.abp_OFFICE) is None
    assert abp_errors == ["El proyecto necesita un nombre."]
