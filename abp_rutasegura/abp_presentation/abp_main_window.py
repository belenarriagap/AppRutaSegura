from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPoint, QSize, QStandardPaths, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import abp_rutasegura
from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_plan_import import abp_rotate_point, abpVectorPlan
from abp_rutasegura.abp_application.abp_progress import (
    abp_wizard_progress,
    abpStepState,
    abpWizardProgress,
)
from abp_rutasegura.abp_application.abp_project_archive import abp_default_export_name
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSign
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_presentation.abp_calibration_dialog import abpCalibrationDialog
from abp_rutasegura.abp_presentation.abp_icons import abp_step_icon
from abp_rutasegura.abp_presentation.abp_norms_page import abpNormsPage
from abp_rutasegura.abp_presentation.abp_project_dialogs import (
    abpNewProjectDialog,
    abpOpenProjectDialog,
    abpProjectDetailsDialog,
)
from abp_rutasegura.abp_presentation.abp_report_page import abpReportPage
from abp_rutasegura.abp_presentation.abp_rooms_page import abpRoomsPage
from abp_rutasegura.abp_presentation.abp_rules_dialog import abpRulesDialog
from abp_rutasegura.abp_presentation.abp_simulation_page import abpSimulationPage
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted, abpBanner
from abp_rutasegura.abp_presentation.abp_wizard_pages import (
    abpEditorPage,
    abpLoadPlanPage,
    abpScalePage,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpUiTexts

abpImage = npt.NDArray[np.uint8]

(
    abp_STEP_LOAD,
    abp_STEP_SCALE,
    abp_STEP_EDIT,
    abp_STEP_ROOMS,
    abp_STEP_NORMS,
    abp_STEP_SIMULATE,
    abp_STEP_REPORT,
) = range(7)
abp_MAX_FLOORS = 4
abp_ACTIVE_STEPS = (
    abp_STEP_LOAD,
    abp_STEP_SCALE,
    abp_STEP_EDIT,
    abp_STEP_ROOMS,
    abp_STEP_NORMS,
    abp_STEP_SIMULATE,
    abp_STEP_REPORT,
)


class abpMainWindow(QMainWindow):
    def __init__(
        self,
        abp_services: abpAppServices,
        abp_texts: abpUiTexts = abp_TEXTS,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__services = abp_services
        self.abp__texts = abp_texts
        self.abp_project_id: int | None = None
        self.abp__plan = abpFloorPlan()
        self.abp__image: abpImage | None = None
        self.abp__vectors: dict[int, abpVectorPlan | None] = {}
        self.abp__image_dirty = False
        self.abp__dirty = False
        self.abp__scenario: abpScenario | None = None
        self.abp__scenario_dirty = False
        self.abp__project_use = abpUseType.abp_EDUCATION
        self.abp__other_floors: dict[int, tuple[abpFloorPlan, abpImage | None]] = {}
        self.abp__project_name = ""

        self.setWindowTitle(abp_texts.abp_window_title)
        self.resize(1200, 780)
        self.abp__build_pages()
        self.abp__build_menu()
        self.abp__build_central()
        self.statusBar().showMessage(abp_texts.abp_status_ready)
        self.abp__update_steps()
        self.abp_refresh_guide()

    def abp__build_menu(self) -> None:
        abp_t, abp_p = self.abp__texts, self.abp__texts.abp_project
        abp_file_menu = self.menuBar().addMenu(abp_t.abp_menu_file)
        self.abp_new_action = QAction(abp_p.abp_menu_new, self)
        self.abp_new_action.setShortcut(QKeySequence.StandardKey.New)
        self.abp_new_action.triggered.connect(self.abp_ask_new_project)
        self.abp_open_action = QAction(abp_p.abp_menu_open, self)
        self.abp_open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.abp_open_action.triggered.connect(self.abp_ask_open_project)
        self.abp_save_action = QAction(abp_p.abp_menu_save, self)
        self.abp_save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.abp_save_action.triggered.connect(self.abp_save)
        abp_quit_action = QAction(abp_t.abp_action_quit, self)
        abp_quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        abp_quit_action.triggered.connect(self.close)
        self.abp_details_action = QAction(abp_p.abp_menu_details, self)
        self.abp_details_action.triggered.connect(self.abp_edit_project_details)
        self.abp_import_action = QAction(abp_p.abp_menu_import, self)
        self.abp_import_action.triggered.connect(self.abp_ask_import_project)
        self.abp_export_action = QAction(abp_p.abp_menu_export, self)
        self.abp_export_action.triggered.connect(
            lambda: self.abp_ask_export_project(self.abp_project_id)
        )
        self.abp_duplicate_action = QAction(abp_p.abp_menu_duplicate, self)
        self.abp_duplicate_action.triggered.connect(
            lambda: self.abp_duplicate_project(self.abp_project_id)
        )
        self.abp_delete_project_action = QAction(abp_p.abp_menu_delete, self)
        self.abp_delete_project_action.triggered.connect(
            lambda: self.abp_ask_delete_project(self.abp_project_id)
        )
        for abp_action in (
            self.abp_new_action,
            self.abp_open_action,
            self.abp_save_action,
            self.abp_details_action,
        ):
            abp_file_menu.addAction(abp_action)
        abp_file_menu.addSeparator()
        for abp_action in (
            self.abp_import_action,
            self.abp_export_action,
            self.abp_duplicate_action,
            self.abp_delete_project_action,
        ):
            abp_file_menu.addAction(abp_action)
        abp_file_menu.addSeparator()
        abp_file_menu.addAction(abp_quit_action)

        abp_edit_menu = self.menuBar().addMenu(abp_t.abp_menu_edit)
        abp_editor = self.abp_editor_page.abp_editor
        abp_edit_menu.addAction(abp_editor.abp_undo_action)
        abp_edit_menu.addAction(abp_editor.abp_redo_action)
        abp_edit_menu.addSeparator()
        abp_edit_menu.addAction(abp_editor.abp_confirm_action)
        abp_edit_menu.addAction(abp_editor.abp_confirm_all_action)
        abp_edit_menu.addAction(abp_editor.abp_delete_action)

        abp_tools_menu = self.menuBar().addMenu(abp_t.abp_calibration.abp_menu_tools)
        self.abp_calibrate_action = QAction(abp_t.abp_calibration.abp_menu_calibrate, self)
        self.abp_calibrate_action.triggered.connect(self.abp_open_calibration)
        abp_tools_menu.addAction(self.abp_calibrate_action)
        self.abp_rules_action = QAction(abp_t.abp_norms.abp_rules_menu, self)
        self.abp_rules_action.triggered.connect(self.abp_open_rules)
        abp_tools_menu.addAction(self.abp_rules_action)

        abp_help_menu = self.menuBar().addMenu(abp_t.abp_menu_help)
        abp_about_action = QAction(abp_t.abp_action_about, self)
        abp_about_action.triggered.connect(self.abp__show_about)
        abp_help_menu.addAction(abp_about_action)

    def abp__build_pages(self) -> None:
        abp_plans = self.abp__services.abp_plans
        self.abp_load_page = abpLoadPlanPage(abp_plans, self.abp__texts.abp_wizard)
        self.abp_scale_page = abpScalePage(abp_plans, self.abp__texts.abp_wizard)
        self.abp_editor_page = abpEditorPage(
            abp_plans, self.abp__texts.abp_wizard, self.abp__texts.abp_editor
        )
        self.abp_load_page.abp_image_loaded.connect(self.abp__on_image_loaded)
        self.abp_scale_page.abp_scale_changed.connect(self.abp__on_scale_changed)
        self.abp_editor_page.abp_editor.abp_plan_changed.connect(self.abp__on_plan_edited)
        self.abp_editor_page.abp_sign_proposer = self.abp__propose_signs
        self.abp_editor_page.abp_floors_provider = lambda: [
            abp_plan for abp_plan, _ in self.abp_all_floors()
        ]
        self.abp_rooms_page = abpRoomsPage(
            abp_plans,
            self.abp__texts.abp_rooms,
            self.abp__texts.abp_project,
            abp_norms=self.abp__services.abp_norms,
        )
        self.abp_rooms_page.abp_plan_changed.connect(self.abp__on_plan_edited)
        self.abp_rooms_page.abp_scenario_changed.connect(self.abp__on_scenario_changed)
        self.abp_simulation_page = abpSimulationPage(
            self.abp__services.abp_simulations,
            self.abp__texts.abp_simulation,
            self.abp__texts.abp_scenarios,
        )
        self.abp_simulation_page.abp_scenario_changed.connect(self.abp__on_scenario_changed)
        self.abp_simulation_page.abp_run_shown.connect(lambda abp__run: self.abp_refresh_guide())
        self.abp_simulation_page.abp_refresh_requested.connect(self.abp_refresh_simulation_plan)
        self.abp_norms_page = abpNormsPage(self.abp__services.abp_norms, self.abp__texts.abp_norms)
        self.abp_norms_page.abp_plan_changed.connect(self.abp__on_plan_edited)
        self.abp_norms_page.abp_verify_requested.connect(self.abp_open_rules)
        self.abp_report_page = abpReportPage(
            self.abp__services.abp_reports,
            self.abp__texts.abp_report,
            self.abp__services.abp_sheets,
        )
        self.abp_report_page.abp_exits_chosen.connect(self.abp__on_exits_chosen)
        self.abp_editor_page.abp_rotate_requested.connect(self.abp_rotate_plan)
        for abp_page in (
            self.abp_load_page,
            self.abp_scale_page,
            self.abp_editor_page,
            self.abp_rooms_page,
            self.abp_norms_page,
            self.abp_simulation_page,
            self.abp_report_page,
        ):
            abp_page.abp_error.connect(self.abp_show_error)

    def abp__build_central(self) -> None:
        abp_t = self.abp__texts
        self.abp_steps_list = QListWidget()
        self.abp_steps_list.setObjectName("wizardSteps")
        self.abp_steps_list.setIconSize(QSize(22, 22))
        for abp_step in abp_t.abp_wizard_steps:
            self.abp_steps_list.addItem(QListWidgetItem(abp_step))
        self.abp_steps_list.currentRowChanged.connect(self.abp__on_step_selected)
        abp_title = QLabel(abp_t.abp_app_name)
        abp_title.setObjectName("sidebarTitle")
        abp_subtitle = QLabel(abp_t.abp_guide.abp_app_subtitle)
        abp_subtitle.setObjectName("sidebarSubtitle")
        abp_sidebar = QWidget()
        abp_sidebar.setObjectName("sidebar")
        abp_sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        abp_sidebar.setFixedWidth(232)
        abp_side = QVBoxLayout(abp_sidebar)
        abp_side.setContentsMargins(14, 18, 12, 12)
        abp_side.addWidget(abp_title)
        abp_side.addWidget(abp_subtitle)
        abp_side.addSpacing(16)
        abp_side.addWidget(self.abp_steps_list, stretch=1)

        self.abp_stack = QStackedWidget()
        self.abp_welcome_page = self.abp__build_welcome()
        self.abp_pending_page = QLabel(abp_t.abp_wizard.abp_step_not_ready)
        self.abp_pending_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for abp_page in (
            self.abp_welcome_page,
            self.abp_load_page,
            self.abp_scale_page,
            self.abp_editor_page,
            self.abp_rooms_page,
            self.abp_norms_page,
            self.abp_simulation_page,
            self.abp_report_page,
            self.abp_pending_page,
        ):
            self.abp_stack.addWidget(abp_page)

        abp_ft = abp_t.abp_floors
        self.abp_floor_combo = QComboBox()
        self.abp_floor_combo.currentIndexChanged.connect(self.abp__on_floor_selected)
        self.abp_add_floor_button = QPushButton(abp_ft.abp_add)
        self.abp_add_floor_button.clicked.connect(self.abp_add_floor)
        self.abp_delete_floor_button = QPushButton(abp_ft.abp_delete)
        self.abp_delete_floor_button.clicked.connect(self.abp_ask_delete_floor)
        self.abp_floor_bar = QWidget()
        self.abp_floor_bar.setObjectName("floorBar")
        self.abp_floor_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        abp_floor_bar = QHBoxLayout(self.abp_floor_bar)
        abp_floor_bar.setContentsMargins(10, 6, 10, 6)
        abp_floor_bar.addWidget(QLabel(abp_ft.abp_label))
        abp_floor_bar.addWidget(self.abp_floor_combo)
        abp_floor_bar.addWidget(self.abp_add_floor_button)
        abp_floor_bar.addWidget(self.abp_delete_floor_button)
        abp_floor_bar.addStretch(1)
        self.abp_details_button = QPushButton(abp_t.abp_project.abp_details_button)
        self.abp_details_button.clicked.connect(self.abp_edit_project_details)
        abp_floor_bar.addWidget(self.abp_details_button)

        self.abp_message_banner = abpBanner(abp_closable=True)
        self.abp_guide_banner = abpBanner(abp_closable=False)

        abp_g = abp_t.abp_guide
        self.abp_prev_button = QPushButton(abp_g.abp_previous)
        self.abp_prev_button.clicked.connect(
            lambda: self.abp_go_to_step(self.abp_current_step() - 1)
        )
        self.abp_next_button = abp_set_primary(QPushButton(abp_g.abp_next))
        self.abp_next_button.clicked.connect(
            lambda: self.abp_go_to_step(self.abp_current_step() + 1)
        )
        self.abp_nav_label = QLabel()
        self.abp_nav_label.setObjectName("navStep")
        self.abp_nav_bar = QWidget()
        self.abp_nav_bar.setObjectName("navBar")
        self.abp_nav_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        abp_nav = QHBoxLayout(self.abp_nav_bar)
        abp_nav.setContentsMargins(10, 6, 10, 6)
        abp_nav.addWidget(self.abp_prev_button)
        abp_nav.addStretch(1)
        abp_nav.addWidget(self.abp_nav_label)
        abp_nav.addStretch(1)
        abp_nav.addWidget(self.abp_next_button)

        abp_right = QVBoxLayout()
        abp_right.setContentsMargins(14, 12, 14, 12)
        abp_right.setSpacing(8)
        abp_right.addWidget(self.abp_floor_bar)
        abp_right.addWidget(self.abp_message_banner)
        abp_right.addWidget(self.abp_guide_banner)
        abp_right.addWidget(self.abp_stack, stretch=1)
        abp_right.addWidget(self.abp_nav_bar)

        abp_layout = QHBoxLayout()
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.setSpacing(0)
        abp_layout.addWidget(abp_sidebar)
        abp_layout.addLayout(abp_right, stretch=1)
        abp_central = QWidget()
        abp_central.setLayout(abp_layout)
        self.setCentralWidget(abp_central)

    def abp__build_welcome(self) -> QWidget:
        abp_t, abp_p = self.abp__texts, self.abp__texts.abp_project
        abp_title = QLabel(abp_t.abp_welcome_title)
        abp_title.setObjectName("welcomeTitle")
        abp_body = abp_muted(abp_t.abp_welcome_body)
        abp_new_button = abp_set_primary(QPushButton(abp_p.abp_welcome_new))
        abp_new_button.clicked.connect(self.abp_ask_new_project)
        abp_open_button = QPushButton(abp_p.abp_welcome_open)
        abp_open_button.clicked.connect(self.abp_ask_open_project)
        abp_import_button = QPushButton(abp_p.abp_welcome_import)
        abp_import_button.clicked.connect(self.abp_ask_import_project)
        abp_buttons = QHBoxLayout()
        abp_buttons.addWidget(abp_new_button)
        abp_buttons.addWidget(abp_open_button)
        abp_buttons.addWidget(abp_import_button)
        abp_buttons.addStretch(1)

        self.abp_recent_list = QListWidget()
        self.abp_recent_list.setObjectName("recentProjects")
        self.abp_recent_list.setMinimumHeight(160)
        self.abp_recent_list.itemActivated.connect(self.abp__on_recent_activated)
        self.abp_recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.abp_recent_list.customContextMenuRequested.connect(self.abp__on_recent_menu)
        self.abp_recent_empty = abp_muted(abp_p.abp_recent_empty)
        abp_recent_title = QLabel(abp_p.abp_recent_title)
        abp_recent_title.setObjectName("sectionTitle")

        abp_card = QFrame()
        abp_card.setObjectName("welcomeCard")
        abp_card.setMaximumWidth(720)
        abp_inner = QVBoxLayout(abp_card)
        abp_inner.setContentsMargins(32, 28, 32, 28)
        abp_inner.setSpacing(12)
        abp_inner.addWidget(abp_title)
        abp_inner.addWidget(abp_body)
        abp_inner.addSpacing(6)
        abp_inner.addLayout(abp_buttons)
        abp_inner.addSpacing(14)
        abp_inner.addWidget(abp_recent_title)
        abp_inner.addWidget(self.abp_recent_empty)
        abp_inner.addWidget(self.abp_recent_list)
        abp_inner.addWidget(abp_muted(abp_p.abp_recent_hint))

        abp_row = QHBoxLayout()
        abp_row.addStretch(1)
        abp_row.addWidget(abp_card, stretch=4)
        abp_row.addStretch(1)
        abp_layout = QVBoxLayout()
        abp_layout.addStretch(1)
        abp_layout.addLayout(abp_row)
        abp_layout.addStretch(2)
        abp_page = QWidget()
        abp_page.setLayout(abp_layout)
        return abp_page

    def abp_refresh_recent_projects(self) -> None:
        abp_p = self.abp__texts.abp_project
        abp_labels = dict(abp_p.abp_use_labels)
        self.abp_recent_list.clear()
        abp_projects = self.abp__services.abp_projects.abp_list_projects()
        for abp_project_id, abp_project in abp_projects:
            abp_date = (
                abp_project.abp_created_at.strftime("%d/%m/%Y")
                if abp_project.abp_created_at
                else "—"
            )
            abp_text = abp_p.abp_recent_item.format(
                name=abp_project.abp_name,
                use=abp_labels.get(abp_project.abp_use.value, abp_project.abp_use.value),
                date=abp_date,
            )
            abp_item = QListWidgetItem(abp_text)
            abp_item.setData(Qt.ItemDataRole.UserRole, abp_project_id)
            self.abp_recent_list.addItem(abp_item)
        self.abp_recent_list.setVisible(bool(abp_projects))
        self.abp_recent_empty.setVisible(not abp_projects)

    def abp_recent_menu(self, abp_project_id: int) -> QMenu:
        abp_p = self.abp__texts.abp_project
        abp_menu = QMenu(self)
        abp_menu.addAction(abp_p.abp_item_open).triggered.connect(
            lambda: self.abp_open_project(abp_project_id)
        )
        abp_menu.addAction(abp_p.abp_menu_duplicate.replace("&", "")).triggered.connect(
            lambda: self.abp_duplicate_project(abp_project_id)
        )
        abp_menu.addAction(abp_p.abp_menu_export.replace("&", "")).triggered.connect(
            lambda: self.abp_ask_export_project(abp_project_id)
        )
        abp_menu.addSeparator()
        abp_menu.addAction(abp_p.abp_menu_delete.replace("&", "")).triggered.connect(
            lambda: self.abp_ask_delete_project(abp_project_id)
        )
        return abp_menu

    def abp__on_recent_menu(self, abp_pos: QPoint) -> None:
        abp_item = self.abp_recent_list.itemAt(abp_pos)
        if abp_item is None:
            return
        abp_project_id = abp_item.data(Qt.ItemDataRole.UserRole)
        if abp_project_id is not None:
            self.abp_recent_menu(int(abp_project_id)).exec(
                self.abp_recent_list.mapToGlobal(abp_pos)
            )

    def abp_ask_import_project(self) -> None:
        abp_p = self.abp__texts.abp_project
        abp_filename, _ = QFileDialog.getOpenFileName(
            self, abp_p.abp_import_title, "", abp_p.abp_archive_filter
        )
        if abp_filename:
            self.abp_import_project(Path(abp_filename))

    def abp_import_project(self, abp_path: Path) -> int | None:
        if not self.abp__save_if_dirty():
            return None
        try:
            abp_project_id = self.abp__services.abp_archive.abp_import_project(abp_path)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return None
        self.abp_open_project(abp_project_id)
        self.abp_show_message(
            self.abp__texts.abp_project.abp_imported.format(name=self.abp__project_name), "success"
        )
        return abp_project_id

    def abp_ask_export_project(self, abp_project_id: int | None) -> None:
        if abp_project_id is None:
            return
        abp_p = self.abp__texts.abp_project
        try:
            abp_project = self.abp__services.abp_projects.abp_get_project(abp_project_id)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return
        abp_folder = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        abp_suggested = str(Path(abp_folder) / abp_default_export_name(abp_project))
        abp_filename, _ = QFileDialog.getSaveFileName(
            self, abp_p.abp_export_title, abp_suggested, abp_p.abp_archive_filter
        )
        if abp_filename:
            self.abp_export_project(abp_project_id, Path(abp_filename))

    def abp_export_project(self, abp_project_id: int, abp_path: Path) -> Path | None:
        if abp_project_id == self.abp_project_id and not self.abp_save():
            return None
        try:
            abp_saved = self.abp__services.abp_archive.abp_export_project(abp_project_id, abp_path)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return None
        self.abp_show_message(
            self.abp__texts.abp_project.abp_exported.format(path=abp_saved), "success"
        )
        return abp_saved

    def abp_duplicate_project(self, abp_project_id: int | None) -> int | None:
        if abp_project_id is None:
            return None
        if abp_project_id == self.abp_project_id and not self.abp_save():
            return None
        try:
            abp_copy_id = self.abp__services.abp_archive.abp_duplicate_project(abp_project_id)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return None
        self.abp_open_project(abp_copy_id)
        self.abp_show_message(
            self.abp__texts.abp_project.abp_duplicated.format(name=self.abp__project_name),
            "success",
        )
        return abp_copy_id

    def abp_ask_delete_project(self, abp_project_id: int | None) -> None:
        if abp_project_id is None:
            return
        abp_p = self.abp__texts.abp_project
        try:
            abp_name = self.abp__services.abp_projects.abp_get_project(abp_project_id).abp_name
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return
        abp_answer = QMessageBox.question(
            self,
            abp_p.abp_menu_delete.replace("&", ""),
            abp_p.abp_confirm_delete.format(name=abp_name),
        )
        if abp_answer == QMessageBox.StandardButton.Yes:
            self.abp_delete_project(abp_project_id)

    def abp_delete_project(self, abp_project_id: int) -> None:
        abp_name = self.abp__services.abp_projects.abp_get_project(abp_project_id).abp_name
        if abp_project_id == self.abp_project_id:
            self.abp__dirty = self.abp__scenario_dirty = self.abp__image_dirty = False
            self.abp_project_id = None
            self.abp__project_name = ""
            self.abp__plan, self.abp__image, self.abp__other_floors = abpFloorPlan(), None, {}
            self.abp__vectors = {}
            self.abp__scenario = None
            self.abp_simulation_page.abp_set_run(None)
            self.setWindowTitle(self.abp__texts.abp_window_title)
        self.abp__services.abp_archive.abp_delete_project(abp_project_id)
        self.abp__update_steps()
        self.abp_refresh_guide()
        self.abp_show_message(self.abp__texts.abp_project.abp_deleted.format(name=abp_name), "info")

    def abp__on_recent_activated(self, abp_item: QListWidgetItem) -> None:
        abp_project_id = abp_item.data(Qt.ItemDataRole.UserRole)
        if abp_project_id is not None:
            self.abp_open_project(int(abp_project_id))

    def abp_ask_new_project(self) -> None:
        abp_dialog = abpNewProjectDialog(self.abp__texts.abp_project, self)
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            abp_details = abp_dialog.abp_project()
            abp_project_id = self.abp_create_project(
                abp_details.abp_name,
                abp_details.abp_use,
                abp_details.abp_address,
                abp_details=abp_details,
            )
            if abp_project_id is not None and isinstance(abp_dialog.abp_logo_change, tuple):
                self.abp__services.abp_projects.abp_set_logo(
                    abp_project_id, *abp_dialog.abp_logo_change
                )

    def abp_edit_project_details(self) -> None:
        if self.abp_project_id is None:
            return
        try:
            abp_project = self.abp__services.abp_projects.abp_get_project(self.abp_project_id)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return
        abp_dialog = abpProjectDetailsDialog(abp_project, self.abp__texts.abp_project, self)
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            self.abp_apply_project_details(abp_dialog.abp_project(), abp_dialog.abp_logo_change)

    def abp_apply_project_details(
        self, abp_project: abpProject, abp_logo_change: tuple[bytes, str] | bytes | None = None
    ) -> bool:
        if self.abp_project_id is None:
            return False
        try:
            abp_saved = self.abp__services.abp_projects.abp_update_project(
                self.abp_project_id, abp_project
            )
            if isinstance(abp_logo_change, tuple):
                self.abp__services.abp_projects.abp_set_logo(self.abp_project_id, *abp_logo_change)
            elif abp_logo_change == b"":
                self.abp__services.abp_projects.abp_set_logo(self.abp_project_id, None)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return False
        self.abp__project_name = abp_saved.abp_name
        self.abp__project_use = abp_saved.abp_use
        self.setWindowTitle(f"{abp_saved.abp_name} — {self.abp__texts.abp_window_title}")
        self.abp_show_message(self.abp__texts.abp_project.abp_details_saved, "success")
        return True

    def abp_rules_dialog(self) -> abpRulesDialog:
        abp_verifier = ""
        if self.abp_project_id is not None:
            abp_verifier = self.abp__services.abp_projects.abp_get_project(
                self.abp_project_id
            ).abp_responsible
        abp_dialog = abpRulesDialog(
            self.abp__services.abp_norms,
            self.abp__texts.abp_norms,
            abp_verifier=abp_verifier,
            abp_parent=self,
        )
        abp_dialog.abp_rules_changed.connect(self.abp__on_rules_changed)
        return abp_dialog

    def abp_open_rules(self) -> None:
        self.abp_rules_dialog().exec()

    def abp_refresh_simulation_plan(self) -> None:
        if self.abp_project_id is None or self.abp__scenario is None or not self.abp_save():
            return
        self.abp_simulation_page.abp_set_content(
            self.abp_project_id, self.abp_all_floors(), self.abp__scenario
        )
        self.abp_show_message(self.abp__texts.abp_simulation.abp_refreshed, "success")

    def abp__on_rules_changed(self) -> None:
        if self.abp_current_step() == abp_STEP_NORMS:
            self.abp_go_to_step(abp_STEP_NORMS)

    def abp_ask_open_project(self) -> None:
        abp_dialog = abpOpenProjectDialog(
            self.abp__services.abp_projects.abp_list_projects(), self.abp__texts.abp_project, self
        )
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            abp_project_id = abp_dialog.abp_selected_id()
            if abp_project_id is not None:
                self.abp_open_project(abp_project_id)

    def abp_create_project(
        self,
        abp_name: str,
        abp_use: abpUseType,
        abp_address: str = "",
        *,
        abp_details: abpProject | None = None,
    ) -> int | None:
        if not self.abp__save_if_dirty():
            return None
        try:
            abp_project_id = self.abp__services.abp_projects.abp_create_project(
                abp_name, abp_use, abp_address, abp_details=abp_details
            )
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return None
        self.abp_open_project(abp_project_id)
        return abp_project_id

    def abp_open_project(self, abp_project_id: int) -> None:
        if not self.abp__save_if_dirty():
            return
        try:
            abp_project = self.abp__services.abp_projects.abp_get_project(abp_project_id)
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return
        abp_floors = self.abp__services.abp_projects.abp_load_floors(abp_project_id) or [
            abpFloorPlan()
        ]
        abp_images = [
            self.abp__services.abp_projects.abp_load_floor_image(abp_f) for abp_f in abp_floors
        ]
        abp_plan, abp_image = abp_floors[0], abp_images[0]
        self.abp__vectors = {
            abp_f.abp_level: self.abp__services.abp_projects.abp_load_floor_vector(abp_f)
            for abp_f in abp_floors
        }
        self.abp__other_floors = {
            abp_f.abp_level: (abp_f, abp_img)
            for abp_f, abp_img in zip(abp_floors[1:], abp_images[1:], strict=True)
        }
        self.abp_project_id = abp_project_id
        self.abp__project_use = abp_project.abp_use
        self.abp__project_name = abp_project.abp_name
        self.abp__plan, self.abp__image = abp_plan, abp_image
        self.abp__image_dirty = self.abp__dirty = self.abp__scenario_dirty = False
        self.abp__scenario = self.abp__services.abp_simulations.abp_load_scenario(abp_project_id)
        self.abp_simulation_page.abp_set_run(
            self.abp__services.abp_simulations.abp_last_run(abp_project_id)
        )
        self.abp_load_page.abp_set_image(abp_image, self.abp__vector)
        self.abp_scale_page.abp_set_content(
            abp_image, abp_plan.abp_scale_m_per_px, self.abp__vector
        )
        self.abp_editor_page.abp_set_content(abp_plan, abp_image, self.abp__vector)
        self.setWindowTitle(f"{abp_project.abp_name} — {self.abp__texts.abp_window_title}")
        self.statusBar().showMessage(
            self.abp__texts.abp_project.abp_opened.format(name=abp_project.abp_name)
        )
        self.abp__refresh_floor_bar()
        self.abp__update_steps()
        abp_has_elements = bool(abp_plan.abp_walls or abp_plan.abp_doors or abp_plan.abp_exits)
        self.abp_go_to_step(abp_STEP_EDIT if abp_has_elements else abp_STEP_LOAD)

    def abp_save(self) -> bool:
        if self.abp_project_id is None:
            return True
        try:
            self.abp__plan = self.abp__services.abp_projects.abp_save_floor(
                self.abp_project_id,
                self.abp__plan,
                self.abp__image if self.abp__image_dirty else None,
                self.abp__vector,
            )
            self.abp__image_dirty = self.abp__dirty = False
            if self.abp__scenario is not None and self.abp__scenario_dirty:
                self.abp__services.abp_simulations.abp_save_scenario(
                    self.abp_project_id, self.abp__scenario
                )
                self.abp__scenario_dirty = False
        except abpUserFacingError as abp_exc:
            self.abp_show_error(abp_exc.abp_message)
            return False
        self.statusBar().showMessage(self.abp__texts.abp_project.abp_saved, 4000)
        return True

    def abp__save_if_dirty(self) -> bool:
        return self.abp_save() if self.abp_is_dirty else True

    @property
    def abp_plan(self) -> abpFloorPlan:
        return self.abp__plan

    @property
    def abp_level(self) -> int:
        return self.abp__plan.abp_level

    def abp_all_floors(self) -> list[tuple[abpFloorPlan, abpImage | None]]:
        abp_floors = {
            **self.abp__other_floors,
            self.abp__plan.abp_level: (self.abp__plan, self.abp__image),
        }
        return [abp_floors[abp_level] for abp_level in sorted(abp_floors)]

    def abp_switch_floor(self, abp_level: int) -> bool:
        if abp_level == self.abp__plan.abp_level or abp_level not in self.abp__other_floors:
            return abp_level == self.abp__plan.abp_level
        if not self.abp_save():
            return False
        self.abp__other_floors[self.abp__plan.abp_level] = (self.abp__plan, self.abp__image)
        self.abp__load_current(*self.abp__other_floors.pop(abp_level))
        abp_step = self.abp_current_step()
        self.abp_go_to_step(abp_step if abp_step in abp_ACTIVE_STEPS else abp_STEP_LOAD)
        return True

    def abp_add_floor(self) -> bool:
        abp_ft = self.abp__texts.abp_floors
        abp_levels = [abp_plan.abp_level for abp_plan, _ in self.abp_all_floors()]
        if len(abp_levels) >= abp_MAX_FLOORS:
            self.abp_show_error(abp_ft.abp_max_floors)
            return False
        if not self.abp_save():
            return False
        self.abp__other_floors[self.abp__plan.abp_level] = (self.abp__plan, self.abp__image)
        abp_new_level = max(abp_levels) + 1
        self.abp__load_current(abpFloorPlan(abp_level=abp_new_level), None)
        self.abp__dirty = True
        self.abp_save()
        self.abp_go_to_step(abp_STEP_LOAD)
        self.abp_show_message(
            abp_ft.abp_added.format(name=abp_ft.abp_name.format(number=abp_new_level + 1)), "info"
        )
        return True

    def abp_ask_delete_floor(self) -> None:
        abp_ft = self.abp__texts.abp_floors
        abp_name = abp_ft.abp_name.format(number=self.abp__plan.abp_level + 1)
        abp_answer = QMessageBox.question(
            self, abp_ft.abp_delete, abp_ft.abp_confirm_delete.format(name=abp_name)
        )
        if abp_answer == QMessageBox.StandardButton.Yes:
            self.abp_delete_current_floor()

    def abp_delete_current_floor(self) -> bool:
        abp_levels = [abp_plan.abp_level for abp_plan, _ in self.abp_all_floors()]
        abp_level = self.abp__plan.abp_level
        if (
            self.abp_project_id is None
            or abp_level == min(abp_levels)
            or abp_level != max(abp_levels)
        ):
            self.abp_show_error(self.abp__texts.abp_floors.abp_cannot_delete)
            return False
        if self.abp__scenario is not None:
            self.abp__scenario = dataclasses.replace(
                self.abp__scenario,
                abp_occupancies=tuple(
                    abp_o
                    for abp_o in self.abp__scenario.abp_occupancies
                    if abp_o.abp_level != abp_level
                ),
            )
            self.abp__scenario_dirty = True
        self.abp__move_routes(abp_level, None)
        self.abp__services.abp_projects.abp_delete_floor(self.abp_project_id, abp_level)
        self.abp__dirty = self.abp__image_dirty = False
        abp_below = max(self.abp__other_floors)
        self.abp__load_current(*self.abp__other_floors.pop(abp_below))
        self.abp_save()
        self.abp_go_to_step(
            abp_STEP_LOAD
            if self.abp_current_step() not in abp_ACTIVE_STEPS
            else self.abp_current_step()
        )
        return True

    def abp__load_current(self, abp_plan: abpFloorPlan, abp_image: abpImage | None) -> None:
        self.abp__plan, self.abp__image = abp_plan, abp_image
        self.abp__dirty = self.abp__image_dirty = False
        self.abp_load_page.abp_set_image(abp_image, self.abp__vector)
        self.abp_scale_page.abp_set_content(
            abp_image, abp_plan.abp_scale_m_per_px, self.abp__vector
        )
        self.abp_editor_page.abp_set_content(abp_plan, abp_image, self.abp__vector)
        self.abp__refresh_floor_bar()

    def abp__refresh_floor_bar(self) -> None:
        abp_ft = self.abp__texts.abp_floors
        abp_levels = [abp_plan.abp_level for abp_plan, _ in self.abp_all_floors()]
        self.abp_floor_combo.blockSignals(True)
        self.abp_floor_combo.clear()
        for abp_level in abp_levels:
            self.abp_floor_combo.addItem(abp_ft.abp_name.format(number=abp_level + 1), abp_level)
        self.abp_floor_combo.setCurrentIndex(
            self.abp_floor_combo.findData(self.abp__plan.abp_level)
        )
        self.abp_floor_combo.blockSignals(False)
        self.abp_add_floor_button.setEnabled(len(abp_levels) < abp_MAX_FLOORS)
        self.abp_delete_floor_button.setEnabled(
            self.abp__plan.abp_level == max(abp_levels)
            and self.abp__plan.abp_level != min(abp_levels)
        )

    def abp__on_floor_selected(self, abp_index: int) -> None:
        abp_level = self.abp_floor_combo.itemData(abp_index)
        if abp_level is not None and not self.abp_switch_floor(int(abp_level)):
            self.abp__refresh_floor_bar()

    @property
    def abp_scenario(self) -> abpScenario | None:
        return self.abp__scenario

    @property
    def abp_is_dirty(self) -> bool:
        return self.abp__dirty or self.abp__scenario_dirty

    def abp_go_to_step(self, abp_step: int) -> None:
        if self.abp_project_id is None:
            self.abp_stack.setCurrentWidget(self.abp_welcome_page)
            return
        abp_step = max(0, min(abp_step, len(abp_ACTIVE_STEPS) - 1))
        if abp_step != self.abp_current_step():
            self.abp_message_banner.abp_dismiss()
        self.abp__save_if_dirty()
        self.abp_steps_list.blockSignals(True)
        self.abp_steps_list.setCurrentRow(abp_step)
        self.abp_steps_list.blockSignals(False)
        if abp_step == abp_STEP_LOAD:
            self.abp_stack.setCurrentWidget(self.abp_load_page)
        elif abp_step == abp_STEP_SCALE:
            self.abp_scale_page.abp_set_content(
                self.abp__image, self.abp__plan.abp_scale_m_per_px, self.abp__vector
            )
            self.abp_stack.setCurrentWidget(self.abp_scale_page)
        elif abp_step == abp_STEP_EDIT:
            if self.abp_editor_page.abp_editor.abp_plan() != self.abp__plan:
                self.abp_editor_page.abp_set_content(
                    self.abp__plan, self.abp__image, self.abp__vector
                )
            self.abp_stack.setCurrentWidget(self.abp_editor_page)
            if self.abp_editor_page.abp_needs_detection():
                self.abp_editor_page.abp_detect()
        elif abp_step == abp_STEP_ROOMS and self.abp__scenario is not None:
            self.abp_rooms_page.abp_set_content(
                self.abp__plan,
                self.abp__image,
                self.abp__scenario,
                self.abp__services.abp_simulations.abp_profiles(),
                self.abp__project_use,
                abp_labels=self.abp__services.abp_plans.abp_room_labels(self.abp__vector),
            )
            self.abp_stack.setCurrentWidget(self.abp_rooms_page)
        elif abp_step == abp_STEP_NORMS:
            self.abp_norms_page.abp_set_content(self.abp__plan, self.abp__scenario)
            self.abp_stack.setCurrentWidget(self.abp_norms_page)
        elif abp_step == abp_STEP_REPORT:
            self.abp_report_page.abp_set_content(
                self.abp_project_id,
                self.abp__project_name,
                self.abp_simulation_page.abp_current_run is not None,
                [abp_plan for abp_plan, _ in self.abp_all_floors()],
                self.abp__services.abp_projects.abp_get_project(
                    self.abp_project_id
                ).abp_responsible,
            )
            self.abp_stack.setCurrentWidget(self.abp_report_page)
        elif abp_step == abp_STEP_SIMULATE and self.abp__scenario is not None:
            self.abp_simulation_page.abp_set_content(
                self.abp_project_id, self.abp_all_floors(), self.abp__scenario
            )
            self.abp_stack.setCurrentWidget(self.abp_simulation_page)
        else:
            self.abp_stack.setCurrentWidget(self.abp_pending_page)
        self.abp_refresh_guide()

    def abp_current_step(self) -> int:
        return self.abp_steps_list.currentRow()

    def abp__on_step_selected(self, abp_row: int) -> None:
        if abp_row >= 0:
            self.abp_go_to_step(abp_row)

    def abp__update_steps(self) -> None:
        for abp_row in range(self.abp_steps_list.count()):
            abp_item = self.abp_steps_list.item(abp_row)
            abp_enabled = self.abp_project_id is not None and abp_row in abp_ACTIVE_STEPS
            abp_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            abp_item.setFlags(abp_flags if abp_enabled else Qt.ItemFlag.NoItemFlags)
            if abp_row not in abp_ACTIVE_STEPS:
                abp_item.setToolTip(self.abp__texts.abp_wizard.abp_step_not_ready)
        self.abp_save_action.setEnabled(self.abp_project_id is not None)
        for abp_action in (
            self.abp_export_action,
            self.abp_duplicate_action,
            self.abp_delete_project_action,
            self.abp_details_action,
        ):
            abp_action.setEnabled(self.abp_project_id is not None)
        self.abp_calibrate_action.setEnabled(self.abp_project_id is not None)
        self.abp_floor_bar.setVisible(self.abp_project_id is not None)
        self.abp_nav_bar.setVisible(self.abp_project_id is not None)
        if self.abp_project_id is None:
            self.abp_refresh_recent_projects()
            self.abp_stack.setCurrentWidget(self.abp_welcome_page)

    def abp_progress(self) -> abpWizardProgress:
        abp_run = self.abp_simulation_page.abp_current_run
        abp_levels = [abp_plan.abp_level for abp_plan, _ in self.abp_all_floors()]
        return abp_wizard_progress(
            self.abp__plan,
            abp_has_image=self.abp__image is not None,
            abp_scenario=self.abp__scenario,
            abp_result=abp_run.abp_result if abp_run is not None else None,
            abp_is_lowest_floor=self.abp__plan.abp_level == min(abp_levels),
        )

    def abp_refresh_guide(self) -> None:
        abp_g, abp_names = self.abp__texts.abp_guide, self.abp__texts.abp_wizard_steps
        abp_has_project = self.abp_project_id is not None
        abp_progress = self.abp_progress()
        for abp_row in range(self.abp_steps_list.count()):
            abp_state = (
                abp_progress.abp_steps[abp_row].abp_state
                if abp_has_project
                else abpStepState.abp_TODO
            )
            self.abp_steps_list.item(abp_row).setIcon(
                abp_step_icon(abp_state, abp_row + 1, abp_enabled=abp_has_project)
            )
        abp_step = self.abp_current_step()
        if not abp_has_project or abp_step not in abp_ACTIVE_STEPS:
            self.abp_guide_banner.abp_dismiss()
            return
        self.abp_prev_button.setEnabled(abp_step > 0)
        self.abp_next_button.setEnabled(abp_step < len(abp_ACTIVE_STEPS) - 1)
        self.abp_nav_label.setText(
            abp_g.abp_step_of.format(
                number=abp_step + 1, total=len(abp_ACTIVE_STEPS), name=abp_names[abp_step]
            )
        )
        abp_blocker = abp_progress.abp_blocker(abp_step)
        abp_own = abp_progress.abp_steps[abp_step]
        if abp_blocker is not None:
            abp_target = abp_blocker.abp_step
            self.abp_guide_banner.abp_show_message(
                abp_g.abp_before_step.format(
                    number=abp_target + 1, issue=abp_g.abp_issue_text(abp_blocker.abp_issue.value)
                ),
                "warning",
                abp_action_text=abp_g.abp_go_to.format(number=abp_target + 1),
                abp_action=lambda: self.abp_go_to_step(abp_target),
            )
        elif abp_own.abp_issue is not None:
            abp_warning = abp_own.abp_state is abpStepState.abp_WARNING
            abp_template = abp_g.abp_review if abp_warning else abp_g.abp_missing
            self.abp_guide_banner.abp_show_message(
                abp_template.format(issue=abp_g.abp_issue_text(abp_own.abp_issue.value)),
                "warning" if abp_warning else "info",
            )
        elif abp_step == abp_STEP_NORMS and self.abp__norm_observations():
            self.abp_guide_banner.abp_show_message(
                abp_g.abp_norms_observations.format(count=self.abp__norm_observations()), "warning"
            )
        elif abp_own.abp_state is abpStepState.abp_DONE:
            abp_last = abp_step == len(abp_ACTIVE_STEPS) - 1
            abp_text = (
                abp_g.abp_step_done_last
                if abp_last
                else abp_g.abp_step_done.format(next=abp_names[abp_step + 1])
            )
            self.abp_guide_banner.abp_show_message(abp_text, "success")
        else:
            self.abp_guide_banner.abp_dismiss()

    def abp__norm_observations(self) -> int:
        abp_evaluation = self.abp_norms_page.abp_evaluation
        return len(abp_evaluation.abp_observations) if abp_evaluation is not None else 0

    def abp__propose_signs(self, abp_plan: abpFloorPlan) -> tuple[abpSign, ...]:
        abp_floors = [
            abp_f for abp_f, _ in self.abp_all_floors() if abp_f.abp_level != abp_plan.abp_level
        ] + [abp_plan]
        return self.abp__services.abp_sheets.abp_propose_signs(
            abp_floors, abp_plan.abp_level, self.abp__scenario, self.abp__vector
        )

    @property
    def abp__vector(self) -> abpVectorPlan | None:
        return self.abp__vectors.get(self.abp__plan.abp_level)

    def abp__on_image_loaded(self, abp_image: abpImage) -> None:
        self.abp__image = abp_image
        self.abp__image_dirty = True
        abp_vector = self.abp_load_page.abp_vector
        abp_signs, abp_zones = self.abp_load_page.abp_drawn_signs
        self.abp__plan = abpFloorPlan(
            abp_level=self.abp__plan.abp_level,
            abp_scale_m_per_px=self.abp__services.abp_plans.abp_sheet_scale(abp_vector),
            abp_signs=abp_signs,
            abp_safe_zones=abp_zones,
        )
        if abp_signs:
            self.abp_show_message(
                self.abp__texts.abp_pdf.abp_signs_found.format(count=len(abp_signs)), "info"
            )
        self.abp__dirty = True
        abp_level = self.abp__plan.abp_level
        self.abp__vectors[abp_level] = abp_vector
        if self.abp__scenario is not None and any(
            abp_o.abp_level == abp_level for abp_o in self.abp__scenario.abp_occupancies
        ):
            abp_kept = tuple(
                abp_o
                for abp_o in self.abp__scenario.abp_occupancies
                if abp_o.abp_level != abp_level
            )
            self.abp__scenario = dataclasses.replace(self.abp__scenario, abp_occupancies=abp_kept)
            self.abp__scenario_dirty = True
        self.abp__move_routes(abp_level, None)
        self.abp_editor_page.abp_set_content(self.abp__plan, abp_image, abp_vector)
        self.abp_refresh_guide()

    def abp__on_scale_changed(self, abp_scale: float) -> None:
        self.abp__plan = dataclasses.replace(self.abp__plan, abp_scale_m_per_px=abp_scale)
        self.abp__dirty = True
        self.abp_refresh_guide()

    def abp__on_plan_edited(self, abp_plan: abpFloorPlan) -> None:
        if abp_plan != self.abp__plan:
            self.abp__plan = abp_plan
            self.abp__dirty = True
            self.abp_refresh_guide()

    def abp__on_exits_chosen(self, abp_choices: dict[str, str]) -> None:
        abp_floors = {abp_plan.abp_level: abp_plan for abp_plan, _ in self.abp_all_floors()}
        abp_lowest = abp_floors[min(abp_floors)]
        abp_rooms = tuple(
            dataclasses.replace(
                abp_r, abp_exit_name=abp_choices.get(abp_r.abp_name, abp_r.abp_exit_name)
            )
            for abp_r in abp_lowest.abp_rooms
        )
        abp_changed = dataclasses.replace(abp_lowest, abp_rooms=abp_rooms)
        if abp_lowest.abp_level == self.abp__plan.abp_level:
            self.abp__plan = abp_changed
            self.abp__dirty = True
            self.abp_save()
        elif self.abp_project_id is not None:
            abp_saved = self.abp__services.abp_projects.abp_save_floor(
                self.abp_project_id, abp_changed
            )
            self.abp__other_floors[abp_lowest.abp_level] = (
                abp_saved,
                self.abp__other_floors[abp_lowest.abp_level][1],
            )

    def abp_rotate_plan(self, abp_turns: int) -> None:
        if self.abp__image is None:
            return
        self.abp__plan = self.abp_editor_page.abp_editor.abp_plan()
        abp_h, abp_w = self.abp__image.shape[:2]
        abp_plans = self.abp__services.abp_plans
        self.abp__plan = abp_plans.abp_rotate_plan(self.abp__plan, (abp_w, abp_h), abp_turns)
        self.abp__move_routes(
            self.abp__plan.abp_level, lambda abp_p: abp_rotate_point(abp_p, abp_w, abp_h, abp_turns)
        )
        self.abp__image = abp_plans.abp_rotate_image(self.abp__image, abp_turns)
        abp_vector = self.abp__vector
        if abp_vector is not None:
            self.abp__vectors[self.abp__plan.abp_level] = abp_vector.abp_rotated(abp_turns)
        self.abp_load_page.abp_set_image(self.abp__image, self.abp__vector)
        self.abp__dirty = self.abp__image_dirty = True
        self.abp_scale_page.abp_set_content(
            self.abp__image, self.abp__plan.abp_scale_m_per_px, self.abp__vector
        )
        self.abp_editor_page.abp_set_content(self.abp__plan, self.abp__image, self.abp__vector)
        self.abp_save()
        self.abp_refresh_guide()

    def abp__move_routes(
        self, abp_level: int, abp_move: Callable[[abpPoint], abpPoint] | None
    ) -> None:
        if self.abp_project_id is None or self.abp__scenario is None:
            return
        abp_moved = self.abp__services.abp_simulations.abp_move_routes(
            self.abp_project_id, self.abp__scenario, abp_level, abp_move
        )
        if abp_moved != self.abp__scenario:
            self.abp__scenario = abp_moved
            self.abp__scenario_dirty = True

    def abp__on_scenario_changed(self, abp_scenario: abpScenario) -> None:
        if abp_scenario != self.abp__scenario:
            self.abp__scenario = abp_scenario
            self.abp__scenario_dirty = True
            self.abp_refresh_guide()

    def abp_calibration_dialog(self) -> abpCalibrationDialog | None:
        if self.abp_project_id is None or self.abp__scenario is None or not self.abp_save():
            self.abp_show_error(self.abp__texts.abp_calibration.abp_no_project)
            return None
        abp_dialog = abpCalibrationDialog(
            self.abp__services.abp_calibration,
            self.abp_project_id,
            [abp_plan for abp_plan, _ in self.abp_all_floors()],
            self.abp__scenario,
            abp_texts=self.abp__texts.abp_calibration,
            abp_parent=self,
        )
        abp_dialog.abp_applied.connect(
            lambda: self.abp_show_message(self.abp__texts.abp_calibration.abp_applied, "success")
        )
        return abp_dialog

    def abp_open_calibration(self) -> None:
        abp_dialog = self.abp_calibration_dialog()
        if abp_dialog is not None:
            abp_dialog.exec()

    def abp_show_error(self, abp_message: str) -> None:
        self.abp_message_banner.abp_show_message(abp_message, "error")

    def abp_show_message(self, abp_message: str, abp_kind: str = "info") -> None:
        abp_timeout = 8000 if abp_kind == "success" else 0
        self.abp_message_banner.abp_show_message(abp_message, abp_kind, abp_timeout_ms=abp_timeout)

    def closeEvent(self, abp_event: QCloseEvent) -> None:
        self.abp__save_if_dirty()
        super().closeEvent(abp_event)

    def abp__show_about(self) -> None:
        QMessageBox.about(
            self,
            self.abp__texts.abp_about_title,
            self.abp__texts.abp_about_body.format(version=abp_rutasegura.__version__),
        )
