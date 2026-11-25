from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpProjectTexts


class abpProjectDetailsDialog(QDialog):
    def __init__(
        self,
        abp_project: abpProject | None = None,
        abp_texts: abpProjectTexts = abp_TEXTS.abp_project,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.abp__original = abp_project
        self.abp_logo_change: tuple[bytes, str] | bytes | None = None
        self.setWindowTitle(
            abp_texts.abp_new_title if abp_project is None else abp_texts.abp_details_title
        )
        self.setMinimumWidth(560)
        abp_p = abp_project or abpProject(abp_name="-", abp_use=abpUseType.abp_EDUCATION)

        def abp_line(abp_value: str, abp_placeholder: str = "") -> QLineEdit:
            abp_edit = QLineEdit(abp_value)
            abp_edit.setPlaceholderText(abp_placeholder)
            return abp_edit

        self.abp_name_edit = abp_line("" if abp_project is None else abp_p.abp_name)
        self.abp_use_combo = QComboBox()
        for abp_value, abp_label in abp_texts.abp_use_labels:
            self.abp_use_combo.addItem(abp_label, abp_value)
        self.abp_use_combo.setCurrentIndex(max(0, self.abp_use_combo.findData(abp_p.abp_use.value)))
        self.abp_address_edit = abp_line(abp_p.abp_address)
        self.abp_district_edit = abp_line(abp_p.abp_district)
        self.abp_province_edit = abp_line(abp_p.abp_province)
        self.abp_department_edit = abp_line(abp_p.abp_department)
        self.abp_responsible_edit = abp_line(
            abp_p.abp_responsible, abp_texts.abp_responsible_placeholder
        )
        self.abp_role_edit = abp_line(abp_p.abp_responsible_role)
        self.abp_phone_edit = abp_line(abp_p.abp_phone)
        self.abp_email_edit = abp_line(abp_p.abp_email)
        self.abp_schedule_edit = abp_line(abp_p.abp_schedule, abp_texts.abp_schedule_placeholder)
        self.abp_notes_edit = QPlainTextEdit(abp_p.abp_notes)
        self.abp_notes_edit.setMaximumHeight(70)
        self.abp_logo_label = QLabel()
        self.abp_logo_label.setFixedSize(150, 60)
        self.abp_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.abp_logo_label.setStyleSheet("border: 1px dashed #b0bac0; border-radius: 4px;")
        self.abp__show_logo(abp_p.abp_logo_path if abp_project is not None else None)
        abp_choose = QPushButton(abp_texts.abp_logo_choose)
        abp_choose.clicked.connect(self.abp_choose_logo)
        abp_remove = QPushButton(abp_texts.abp_logo_remove)
        abp_remove.clicked.connect(self.abp_remove_logo)
        abp_logo_row = QHBoxLayout()
        abp_logo_row.addWidget(self.abp_logo_label)
        abp_logo_row.addWidget(abp_choose)
        abp_logo_row.addWidget(abp_remove)
        abp_logo_row.addStretch(1)
        self.abp_error_label = QLabel()
        self.abp_error_label.setStyleSheet("color: #c62828;")
        self.abp_error_label.setWordWrap(True)

        def abp_section(abp_title: str) -> QLabel:
            abp_label = QLabel(abp_title)
            abp_label.setObjectName("sectionTitle")
            return abp_label

        abp_help_label = QLabel(abp_texts.abp_details_help)
        abp_help_label.setObjectName("muted")
        abp_help_label.setWordWrap(True)
        abp_general = QFormLayout()
        abp_general.addRow(abp_texts.abp_name, self.abp_name_edit)
        abp_general.addRow(abp_texts.abp_use, self.abp_use_combo)
        abp_location = QFormLayout()
        abp_location.addRow(abp_texts.abp_address, self.abp_address_edit)
        abp_location.addRow(abp_texts.abp_district, self.abp_district_edit)
        abp_location.addRow(abp_texts.abp_province, self.abp_province_edit)
        abp_location.addRow(abp_texts.abp_department, self.abp_department_edit)
        abp_contact = QFormLayout()
        abp_contact.addRow(abp_texts.abp_responsible, self.abp_responsible_edit)
        abp_contact.addRow(abp_texts.abp_responsible_role, self.abp_role_edit)
        abp_contact.addRow(abp_texts.abp_phone, self.abp_phone_edit)
        abp_contact.addRow(abp_texts.abp_email, self.abp_email_edit)
        abp_other = QFormLayout()
        abp_other.addRow(abp_texts.abp_schedule, self.abp_schedule_edit)
        abp_other.addRow(abp_texts.abp_notes, self.abp_notes_edit)
        abp_other.addRow(abp_texts.abp_logo, abp_logo_row)
        abp_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_help_label)
        for abp_title, abp_form in (
            (abp_texts.abp_section_general, abp_general),
            (abp_texts.abp_section_location, abp_location),
            (abp_texts.abp_section_contact, abp_contact),
            (abp_texts.abp_section_other, abp_other),
        ):
            abp_layout.addWidget(abp_section(abp_title))
            abp_layout.addLayout(abp_form)
        abp_layout.addWidget(self.abp_error_label)
        abp_layout.addWidget(abp_buttons)

    def abp__show_logo(self, abp_path: str | None) -> None:
        abp_pixmap = QPixmap(abp_path) if abp_path else QPixmap()
        if abp_pixmap.isNull():
            self.abp_logo_label.setPixmap(QPixmap())
            self.abp_logo_label.setText(self.abp__texts.abp_logo_none)
            return
        self.abp_logo_label.setPixmap(
            abp_pixmap.scaled(
                self.abp_logo_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def abp_choose_logo(self) -> None:
        abp_filename, _ = QFileDialog.getOpenFileName(
            self, self.abp__texts.abp_logo, "", self.abp__texts.abp_logo_filter
        )
        if abp_filename:
            self.abp_set_logo_file(Path(abp_filename))

    def abp_set_logo_file(self, abp_path: Path) -> bool:
        if QPixmap(str(abp_path)).isNull():
            self.abp_error_label.setText(self.abp__texts.abp_logo_invalid)
            return False
        self.abp_logo_change = (abp_path.read_bytes(), abp_path.suffix)
        self.abp__show_logo(str(abp_path))
        self.abp_error_label.setText("")
        return True

    def abp_remove_logo(self) -> None:
        self.abp_logo_change = b""
        self.abp__show_logo(None)

    def accept(self) -> None:
        try:
            self.abp_project()
        except ValueError as abp_exc:
            abp_message = str(abp_exc)
            if not self.abp_name_edit.text().strip():
                abp_message = self.abp__texts.abp_name_required
                self.abp_name_edit.setFocus()
            self.abp_error_label.setText(abp_message)
            return
        super().accept()

    def abp_project(self) -> abpProject:
        abp_base = self.abp__original or abpProject(abp_name="-", abp_use=abpUseType.abp_EDUCATION)
        return dataclasses.replace(
            abp_base,
            abp_name=self.abp_name_edit.text().strip(),
            abp_use=abpUseType(self.abp_use_combo.currentData()),
            abp_address=self.abp_address_edit.text().strip(),
            abp_district=self.abp_district_edit.text().strip(),
            abp_province=self.abp_province_edit.text().strip(),
            abp_department=self.abp_department_edit.text().strip(),
            abp_responsible=self.abp_responsible_edit.text().strip(),
            abp_responsible_role=self.abp_role_edit.text().strip(),
            abp_phone=self.abp_phone_edit.text().strip(),
            abp_email=self.abp_email_edit.text().strip(),
            abp_schedule=self.abp_schedule_edit.text().strip(),
            abp_notes=self.abp_notes_edit.toPlainText().strip(),
        )

    def abp_values(self) -> tuple[str, abpUseType, str]:
        abp_project = self.abp_project()
        return abp_project.abp_name, abp_project.abp_use, abp_project.abp_address


class abpNewProjectDialog(abpProjectDetailsDialog):
    def __init__(
        self, abp_texts: abpProjectTexts = abp_TEXTS.abp_project, abp_parent: QWidget | None = None
    ) -> None:
        super().__init__(None, abp_texts, abp_parent)


class abpOpenProjectDialog(QDialog):
    def __init__(
        self,
        abp_projects: list[tuple[int, abpProject]],
        abp_texts: abpProjectTexts = abp_TEXTS.abp_project,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.setWindowTitle(abp_texts.abp_open_title)
        self.resize(480, 360)
        abp_labels = dict(abp_texts.abp_use_labels)
        self.abp_list_widget = QListWidget()
        for abp_project_id, abp_project in abp_projects:
            abp_date = (
                abp_project.abp_created_at.strftime("%d/%m/%Y")
                if abp_project.abp_created_at
                else ""
            )
            abp_item = QListWidgetItem(
                f"{abp_project.abp_name} — {abp_labels.get(abp_project.abp_use.value, '')} {abp_date}"
            )
            abp_item.setData(Qt.ItemDataRole.UserRole, abp_project_id)
            self.abp_list_widget.addItem(abp_item)
        if abp_projects:
            self.abp_list_widget.setCurrentRow(0)
        self.abp_list_widget.itemDoubleClicked.connect(lambda abp__item: self.accept())
        abp_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(abp_projects))
        abp_layout = QVBoxLayout(self)
        if not abp_projects:
            abp_layout.addWidget(QLabel(abp_texts.abp_no_projects))
        abp_layout.addWidget(self.abp_list_widget)
        abp_layout.addWidget(abp_buttons)

    def abp_selected_id(self) -> int | None:
        abp_item = self.abp_list_widget.currentItem()
        return None if abp_item is None else int(abp_item.data(Qt.ItemDataRole.UserRole))
