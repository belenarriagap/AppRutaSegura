from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService
from abp_rutasegura.abp_presentation.abp_qt_support import abp_run_in_background
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpPdfTexts


class abpCadImportDialog(QDialog):
    abp_sheets_ready = Signal()
    abp_converted = Signal()

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_path: Path,
        abp_texts: abpPdfTexts = abp_TEXTS.abp_pdf,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__path = abp_path
        self.abp__texts = abp_texts
        self.abp_pdf_path: Path | None = None
        self.abp_error_message = ""
        self.setWindowTitle(abp_texts.abp_cad_title)
        self.setMinimumWidth(460)
        self.abp_status_label = QLabel(abp_texts.abp_cad_reading)
        self.abp_status_label.setWordWrap(True)
        self.abp_progress = QProgressBar()
        self.abp_progress.setRange(0, 0)
        self.abp_sheet_list = QListWidget()
        self.abp_sheet_list.setVisible(False)
        self.abp_all_button = QPushButton(abp_texts.abp_cad_all)
        self.abp_all_button.setVisible(False)
        self.abp_all_button.clicked.connect(self.abp_check_all)
        self.abp_ok_button = abp_set_primary(QPushButton(abp_texts.abp_accept))
        self.abp_ok_button.setEnabled(False)
        abp_buttons = QDialogButtonBox()
        abp_buttons.addButton(self.abp_ok_button, QDialogButtonBox.ButtonRole.ActionRole)
        abp_buttons.addButton(QDialogButtonBox.StandardButton.Cancel).setText(abp_texts.abp_cancel)
        self.abp_ok_button.clicked.connect(self.abp_convert)
        abp_buttons.rejected.connect(self.reject)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(self.abp_status_label)
        abp_layout.addWidget(self.abp_progress)
        abp_layout.addWidget(self.abp_sheet_list)
        abp_layout.addWidget(self.abp_all_button)
        abp_layout.addWidget(abp_muted(abp_texts.abp_cad_wait))
        abp_layout.addWidget(abp_buttons)
        abp_run_in_background(
            lambda: abp_plans.abp_cad_sheets(abp_path), self.abp__on_sheets, self.abp__on_failed
        )

    def abp_check_all(self) -> None:
        for abp_i in range(self.abp_sheet_list.count()):
            self.abp_sheet_list.item(abp_i).setCheckState(Qt.CheckState.Checked)

    def abp_chosen(self) -> tuple[str, ...]:
        abp_items = (
            self.abp_sheet_list.item(abp_i) for abp_i in range(self.abp_sheet_list.count())
        )
        return tuple(
            abp_i.text() for abp_i in abp_items if abp_i.checkState() == Qt.CheckState.Checked
        )

    def abp_convert(self) -> None:
        abp_names = self.abp_chosen()
        if not abp_names:
            self.abp_status_label.setText(self.abp__texts.abp_cad_help)
            return
        self.abp_ok_button.setEnabled(False)
        self.abp_sheet_list.setEnabled(False)
        self.abp_progress.setVisible(True)
        self.abp_status_label.setText(self.abp__texts.abp_cad_reading)
        abp_plans, abp_path = self.abp__plans, self.abp__path
        abp_run_in_background(
            lambda: abp_plans.abp_cad_to_pdf(abp_path, abp_names),
            self.abp__on_converted,
            self.abp__on_failed,
        )

    def abp__on_sheets(self, abp_names: tuple[str, ...]) -> None:
        for abp_index, abp_name in enumerate(abp_names):
            abp_item = QListWidgetItem(abp_name)
            abp_item.setFlags(abp_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            abp_first = abp_index == 0
            abp_item.setCheckState(Qt.CheckState.Checked if abp_first else Qt.CheckState.Unchecked)
            self.abp_sheet_list.addItem(abp_item)
        self.abp_sheets_ready.emit()
        if len(abp_names) == 1:
            self.abp_convert()
            return
        self.abp_progress.setVisible(False)
        self.abp_sheet_list.setVisible(True)
        self.abp_all_button.setVisible(True)
        self.abp_ok_button.setEnabled(True)
        self.abp_status_label.setText(self.abp__texts.abp_cad_help)

    def abp__on_converted(self, abp_path: Path) -> None:
        self.abp_pdf_path = abp_path
        self.abp_converted.emit()
        self.accept()

    def abp__on_failed(self, abp_message: str) -> None:
        self.abp_error_message = abp_message
        self.abp_progress.setVisible(False)
        self.abp_status_label.setText(abp_message)
        self.abp_converted.emit()
