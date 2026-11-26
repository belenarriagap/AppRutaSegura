from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_report_service import abpMapOptions, abpReportService
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetOptions, abpSheetService
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_presentation.abp_evacuation_map_dialog import abpEvacuationMapDialog
from abp_rutasegura.abp_presentation.abp_evacuation_sheet_dialog import abpEvacuationSheetDialog
from abp_rutasegura.abp_presentation.abp_qt_support import abpBackgroundJob
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import (
    abp_muted,
    abp_page_help,
    abp_page_title,
    abp_section_title,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpReportTexts


class abpReportPage(QWidget):
    abp_error = Signal(str)
    abp_exits_chosen = Signal(object)
    abp_report_ready = Signal(object)

    def __init__(
        self,
        abp_reports: abpReportService,
        abp_texts: abpReportTexts = abp_TEXTS.abp_report,
        abp_sheets: abpSheetService | None = None,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__reports = abp_reports
        self.abp__sheets = abp_sheets
        self.abp__sheet_options: abpSheetOptions | None = None
        self.abp_last_sheet_path: Path | None = None
        self.abp__texts = abp_texts
        self.abp__project_id: int | None = None
        self.abp__project_name = ""
        self.abp_last_path: Path | None = None
        self.abp_last_map_path: Path | None = None
        self.abp__floors: list[abpFloorPlan] = []
        self.abp__responsible = ""
        self.abp_job: abpBackgroundJob | None = None

        abp_title = abp_page_title(abp_texts.abp_title)
        abp_help_label = abp_page_help(abp_texts.abp_help)
        self.abp_status_label = QLabel()
        self.abp_status_label.setWordWrap(True)
        self.abp_result_label = QLabel()
        self.abp_result_label.setWordWrap(True)
        self.abp_result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.abp_generate_button = abp_set_primary(QPushButton(abp_texts.abp_generate))
        self.abp_generate_button.clicked.connect(self.abp_ask_and_generate)
        self.abp_map_button = QPushButton(abp_texts.abp_map_generate)
        self.abp_map_button.clicked.connect(self.abp_ask_and_generate_map)
        self.abp_map_result_label = QLabel()
        self.abp_map_result_label.setWordWrap(True)
        self.abp_map_result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.abp_open_button = QPushButton(abp_texts.abp_open)
        self.abp_open_button.clicked.connect(self.abp_open_report)
        self.abp_open_button.setEnabled(False)
        abp_buttons = QHBoxLayout()
        abp_buttons.addWidget(self.abp_generate_button)
        abp_buttons.addWidget(self.abp_open_button)
        abp_buttons.addStretch(1)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_title)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addWidget(self.abp_status_label)
        abp_layout.addLayout(abp_buttons)
        abp_layout.addWidget(self.abp_result_label)
        abp_layout.addSpacing(18)
        abp_layout.addWidget(abp_section_title(abp_texts.abp_map_title))
        abp_layout.addWidget(abp_muted(abp_texts.abp_map_help))
        abp_map_row = QHBoxLayout()
        abp_map_row.addWidget(self.abp_map_button)
        abp_map_row.addStretch(1)
        abp_layout.addLayout(abp_map_row)
        abp_layout.addWidget(self.abp_map_result_label)
        abp_layout.addWidget(abp_section_title(abp_TEXTS.abp_sheet.abp_title))
        abp_layout.addWidget(abp_muted(abp_TEXTS.abp_sheet.abp_help))
        self.abp_sheet_button = QPushButton(abp_TEXTS.abp_sheet.abp_generate)
        self.abp_sheet_button.clicked.connect(self.abp_ask_and_generate_sheet)
        self.abp_sheet_result_label = QLabel()
        self.abp_sheet_result_label.setWordWrap(True)
        self.abp_sheet_result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        abp_sheet_row = QHBoxLayout()
        abp_sheet_row.addWidget(self.abp_sheet_button)
        abp_sheet_row.addStretch(1)
        abp_layout.addLayout(abp_sheet_row)
        abp_layout.addWidget(self.abp_sheet_result_label)
        abp_layout.addStretch(1)

    def abp_set_content(
        self,
        abp_project_id: int,
        abp_project_name: str,
        abp_has_run: bool,
        abp_floors: Sequence[abpFloorPlan] = (),
        abp_responsible: str = "",
    ) -> None:
        self.abp__project_id = abp_project_id
        self.abp__project_name = abp_project_name
        self.abp__floors = list(abp_floors)
        self.abp__responsible = abp_responsible
        self.abp_status_label.setText(
            self.abp__texts.abp_ready if abp_has_run else self.abp__texts.abp_no_run
        )

    def abp_ask_and_generate(self) -> None:
        abp_folder = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        abp_safe_name = "".join(
            abp_c for abp_c in self.abp__project_name if abp_c not in '\\/:*?"<>|'
        ).strip()
        abp_suggested = str(
            Path(abp_folder)
            / self.abp__texts.abp_default_name.format(name=abp_safe_name or "local")
        )
        abp_filename, _ = QFileDialog.getSaveFileName(
            self, self.abp__texts.abp_save_title, abp_suggested, self.abp__texts.abp_save_filter
        )
        if abp_filename:
            self.abp_generate_to(Path(abp_filename))

    def abp_generate_to(self, abp_path: Path) -> None:
        if self.abp__project_id is None or (self.abp_job is not None and self.abp_job.abp_running):
            return
        abp_project_id, abp_reports = self.abp__project_id, self.abp__reports

        def abp_work(
            abp__report: Callable[[float], None], abp__cancel: Callable[[], bool]
        ) -> object:
            return abp_reports.abp_generate(abp_project_id, abp_path)

        self.abp_job = abpBackgroundJob(abp_work, self)
        self.abp_job.abp_done.connect(self.abp__on_done)
        self.abp_job.abp_failed.connect(self.abp__on_failed)
        self.abp_generate_button.setEnabled(False)
        self.abp_result_label.setText(self.abp__texts.abp_generating)
        self.abp_job.abp_start()

    def abp_ask_and_generate_map(self) -> None:
        abp_dialog = abpEvacuationMapDialog(
            self.abp__floors,
            abp_responsible=self.abp__responsible,
            abp_texts=self.abp__texts,
            abp_parent=self,
        )
        if abp_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        abp_folder = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        abp_safe_name = "".join(
            abp_c for abp_c in self.abp__project_name if abp_c not in '\\/:*?"<>|'
        ).strip()
        abp_suggested = str(
            Path(abp_folder)
            / self.abp__texts.abp_map_default_name.format(name=abp_safe_name or "local")
        )
        abp_filename, _ = QFileDialog.getSaveFileName(
            self,
            self.abp__texts.abp_map_dialog_title,
            abp_suggested,
            self.abp__texts.abp_save_filter,
        )
        if abp_filename:
            self.abp_generate_map_to(Path(abp_filename), abp_dialog.abp_options())

    def abp_generate_map_to(self, abp_path: Path, abp_options: abpMapOptions) -> Path | None:
        if self.abp__project_id is None:
            return None
        self.setCursor(Qt.CursorShape.BusyCursor)
        try:
            abp_saved = self.abp__reports.abp_generate_map(
                self.abp__project_id, abp_path, abp_options
            )
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return None
        finally:
            self.unsetCursor()
        self.abp_last_map_path = abp_saved
        self.abp_map_result_label.setText(self.abp__texts.abp_map_saved.format(path=abp_saved))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(abp_saved)))
        return abp_saved

    def abp_ask_and_generate_sheet(self) -> None:
        abp_lowest = min(self.abp__floors, key=lambda abp_f: abp_f.abp_level, default=None)
        abp_dialog = abpEvacuationSheetDialog(
            abp_previous=self.abp__sheet_options,
            abp_specialist=self.abp__responsible,
            abp_has_meeting_zone=any(abp_f.abp_safe_zones for abp_f in self.abp__floors),
            abp_rooms=self.abp__exit_rooms(),
            abp_exits=[abp_e.abp_name for abp_e in abp_lowest.abp_exits if abp_e.abp_confirmed]
            if abp_lowest is not None
            else [],
            abp_parent=self,
        )
        if abp_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.abp__sheet_options = abp_dialog.abp_options()
        abp_choices = abp_dialog.abp_exit_choices()
        if any(
            abp_choices.get(abp_name, abp_now) != abp_now
            for abp_name, abp_now in self.abp__exit_rooms()
        ):
            self.abp_exits_chosen.emit(abp_choices)
        abp_folder = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        abp_safe_name = "".join(
            abp_c for abp_c in self.abp__project_name if abp_c not in '\\/:*?"<>|'
        ).strip()
        abp_name = abp_TEXTS.abp_sheet.abp_default_name.format(name=abp_safe_name or "local")
        abp_filename, _ = QFileDialog.getSaveFileName(
            self,
            abp_TEXTS.abp_sheet.abp_title,
            str(Path(abp_folder) / abp_name),
            self.abp__texts.abp_save_filter,
        )
        if abp_filename:
            self.abp_generate_sheet_to(Path(abp_filename), self.abp__sheet_options)

    def abp__exit_rooms(self) -> list[tuple[str, str]]:
        abp_lowest = min(self.abp__floors, key=lambda abp_f: abp_f.abp_level, default=None)
        return (
            [(abp_r.abp_name, abp_r.abp_exit_name) for abp_r in abp_lowest.abp_rooms]
            if abp_lowest is not None
            else []
        )

    def abp_generate_sheet_to(self, abp_path: Path, abp_options: abpSheetOptions) -> Path | None:
        if self.abp__project_id is None or self.abp__sheets is None:
            return None
        self.setCursor(Qt.CursorShape.BusyCursor)
        try:
            abp_saved = self.abp__sheets.abp_generate(self.abp__project_id, abp_path, abp_options)
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return None
        finally:
            self.unsetCursor()
        self.abp_last_sheet_path = abp_saved
        self.abp_sheet_result_label.setText(abp_TEXTS.abp_sheet.abp_saved.format(path=abp_saved))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(abp_saved)))
        return abp_saved

    def abp_open_report(self) -> None:
        if self.abp_last_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.abp_last_path)))

    def abp__on_done(self, abp_path: object) -> None:
        self.abp_generate_button.setEnabled(True)
        if isinstance(abp_path, Path):
            self.abp_last_path = abp_path
            self.abp_open_button.setEnabled(True)
            self.abp_result_label.setText(self.abp__texts.abp_saved.format(path=abp_path))
            self.abp_report_ready.emit(abp_path)

    def abp__on_failed(self, abp_message: str) -> None:
        self.abp_generate_button.setEnabled(True)
        self.abp_result_label.setText("")
        self.abp_error.emit(abp_message)
