from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_sheet_service import (
    abp_SCALES,
    abp_SHEET_PAPERS,
    abpSheetOptions,
)
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpSheetTexts


class abpEvacuationSheetDialog(QDialog):
    def __init__(
        self,
        *,
        abp_previous: abpSheetOptions | None = None,
        abp_specialist: str = "",
        abp_has_meeting_zone: bool = True,
        abp_rooms: Sequence[tuple[str, str]] = (),
        abp_exits: Sequence[str] = (),
        abp_texts: abpSheetTexts = abp_TEXTS.abp_sheet,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        abp_start = abp_previous or abpSheetOptions(
            abp_title=abp_texts.abp_default_title,
            abp_specialist=abp_specialist,
            abp_note=abp_texts.abp_default_note,
        )
        self.setWindowTitle(abp_texts.abp_title)
        self.setMinimumWidth(820)

        self.abp_paper_combo = QComboBox()
        self.abp_paper_combo.addItems(list(abp_SHEET_PAPERS))
        self.abp_paper_combo.setCurrentText(abp_start.abp_paper)
        self.abp_scale_combo = QComboBox()
        self.abp_scale_combo.addItem(abp_texts.abp_scale_auto, 0)
        for abp_denominator in abp_SCALES:
            self.abp_scale_combo.addItem(f"1/{abp_denominator}", abp_denominator)
        self.abp_scale_combo.setCurrentIndex(
            max(0, self.abp_scale_combo.findData(abp_start.abp_scale or 0))
        )
        self.abp_orientation_combo = abp__combo(
            (
                (abp_texts.abp_orientation_auto, "auto"),
                (abp_texts.abp_orientation_landscape, "horizontal"),
                (abp_texts.abp_orientation_portrait, "vertical"),
            ),
            abp_start.abp_orientation,
        )
        self.abp_tables_combo = abp__combo(
            (
                (abp_texts.abp_tables_auto, "auto"),
                (abp_texts.abp_tables_side, "costado"),
                (abp_texts.abp_tables_bottom, "abajo"),
            ),
            abp_start.abp_tables,
        )
        self.abp_identify_combo = abp__combo(
            ((abp_texts.abp_identify_room, "ambiente"), (abp_texts.abp_identify_exit, "salida")),
            abp_start.abp_identify,
        )
        self.abp_underlay_combo = QComboBox()
        self.abp_underlay_combo.addItem(abp_texts.abp_underlay_original, "original")
        self.abp_underlay_combo.addItem(abp_texts.abp_underlay_clean, "limpio")
        self.abp_underlay_combo.setCurrentIndex(
            self.abp_underlay_combo.findData(abp_start.abp_underlay)
        )
        self.abp_furniture_check = QCheckBox(abp_texts.abp_furniture)
        self.abp_furniture_check.setChecked(abp_start.abp_follow_furniture)
        self.abp_signs_check = QCheckBox(abp_texts.abp_signs)
        self.abp_signs_check.setChecked(abp_start.abp_propose_signs)
        abp_sheet_box = QGroupBox(abp_texts.abp_section_sheet)
        abp_form = QFormLayout(abp_sheet_box)
        abp_form.addRow(abp_texts.abp_paper, self.abp_paper_combo)
        abp_form.addRow(abp_texts.abp_orientation, self.abp_orientation_combo)
        abp_form.addRow(abp_texts.abp_scale, self.abp_scale_combo)
        abp_form.addRow(abp_texts.abp_tables, self.abp_tables_combo)
        abp_form.addRow(abp_texts.abp_identify, self.abp_identify_combo)
        abp_form.addRow(abp_texts.abp_underlay, self.abp_underlay_combo)
        abp_form.addRow(self.abp_furniture_check)
        abp_form.addRow(self.abp_signs_check)

        self.abp_title_edit = QLineEdit(abp_start.abp_title)
        self.abp_code_edit = QLineEdit(abp_start.abp_code)
        self.abp_specialist_edit = QLineEdit(abp_start.abp_specialist)
        self.abp_drafter_edit = QLineEdit(abp_start.abp_drafter)
        self.abp_sector_edit = QLineEdit(abp_start.abp_sector)
        self.abp_north_spin = QDoubleSpinBox()
        self.abp_north_spin.setRange(0.0, 359.0)
        self.abp_north_spin.setDecimals(0)
        self.abp_north_spin.setSuffix("°")
        self.abp_north_spin.setWrapping(True)
        self.abp_north_spin.setValue(abp_start.abp_north_deg)
        abp_block_box = QGroupBox(abp_texts.abp_section_block)
        abp_form = QFormLayout(abp_block_box)
        abp_form.addRow(abp_texts.abp_plan_title, self.abp_title_edit)
        abp_form.addRow(abp_texts.abp_specialist, self.abp_specialist_edit)
        abp_form.addRow(abp_texts.abp_drafter, self.abp_drafter_edit)
        abp_form.addRow(abp_texts.abp_sector, self.abp_sector_edit)
        abp_form.addRow(abp_texts.abp_code, self.abp_code_edit)
        abp_form.addRow(abp_texts.abp_north, self.abp_north_spin)

        self.abp_people_combo = QComboBox()
        self.abp_people_combo.addItem(abp_texts.abp_people_capacity, "aforo")
        self.abp_people_combo.addItem(abp_texts.abp_people_occupants, "ocupantes")
        self.abp_people_combo.setCurrentIndex(
            self.abp_people_combo.findData(abp_start.abp_people_source)
        )
        self.abp_flow_spin = abp__spin(abp_start.abp_flow, 0.1, 5.0)
        self.abp_speed_spin = abp__spin(abp_start.abp_speed, 0.1, 3.0)
        abp_times_box = QGroupBox(abp_texts.abp_section_times)
        abp_form = QFormLayout(abp_times_box)
        abp_form.addRow(abp_texts.abp_people, self.abp_people_combo)
        abp_form.addRow(abp_texts.abp_flow, self.abp_flow_spin)
        abp_form.addRow(abp_texts.abp_speed, self.abp_speed_spin)
        abp_form.addRow(abp_muted(abp_texts.abp_formula))

        self.abp_note_edit = QPlainTextEdit(abp_start.abp_note)
        self.abp_note_edit.setMaximumHeight(70)
        abp_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_exits_box = self.abp__exits_box(abp_rooms, abp_exits)
        abp_columns = QHBoxLayout()
        abp_left, abp_right = QVBoxLayout(), QVBoxLayout()
        for abp_box in (abp_sheet_box, abp_times_box):
            abp_left.addWidget(abp_box)
        abp_left.addStretch(1)
        abp_right.addWidget(abp_block_box)
        if abp_exits_box is not None:
            abp_right.addWidget(abp_exits_box, stretch=1)
        else:
            abp_right.addStretch(1)
        abp_columns.addLayout(abp_left, stretch=1)
        abp_columns.addLayout(abp_right, stretch=1)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_muted(abp_texts.abp_help))
        if not abp_has_meeting_zone:
            abp_layout.addWidget(abp_muted(abp_texts.abp_meeting_tip))
        abp_layout.addLayout(abp_columns)
        abp_note_form = QFormLayout()
        abp_note_form.addRow(abp_texts.abp_note, self.abp_note_edit)
        abp_layout.addLayout(abp_note_form)
        abp_layout.addWidget(abp_buttons)

    def abp__exits_box(
        self, abp_rooms: Sequence[tuple[str, str]], abp_exits: Sequence[str]
    ) -> QGroupBox | None:
        self.abp_exits_table = QTableWidget(0, 2)
        self.abp__exit_combos: dict[str, QComboBox] = {}
        if len(abp_exits) < 2 or not abp_rooms:
            return None
        abp_texts = self.abp__texts
        self.abp_exits_table.setHorizontalHeaderLabels(
            [abp_texts.abp_exits_room, abp_texts.abp_exits_exit]
        )
        self.abp_exits_table.verticalHeader().setVisible(False)
        self.abp_exits_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.abp_exits_table.setRowCount(len(abp_rooms))
        abp_choices = [
            (abp_texts.abp_exit_auto, ""),
            *((abp_name, abp_name) for abp_name in abp_exits),
        ]
        for abp_row, (abp_room, abp_current) in enumerate(abp_rooms):
            self.abp_exits_table.setItem(abp_row, 0, QTableWidgetItem(abp_room))
            abp_combo = abp__combo(abp_choices, abp_current if abp_current in abp_exits else "")
            self.abp__exit_combos[abp_room] = abp_combo
            self.abp_exits_table.setCellWidget(abp_row, 1, abp_combo)
        abp_header = self.abp_exits_table.horizontalHeader()
        abp_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        abp_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.abp_exits_table.setMinimumHeight(170)
        abp_box = QGroupBox(abp_texts.abp_section_exits)
        abp_layout = QVBoxLayout(abp_box)
        abp_layout.addWidget(abp_muted(abp_texts.abp_exits_help))
        abp_layout.addWidget(self.abp_exits_table)
        return abp_box

    def abp_set_exit(self, abp_room: str, abp_exit_name: str) -> None:
        abp_combo = self.abp__exit_combos[abp_room]
        abp_combo.setCurrentIndex(max(0, abp_combo.findData(abp_exit_name)))

    def abp_exit_choices(self) -> dict[str, str]:
        return {
            abp_room: str(abp_c.currentData()) for abp_room, abp_c in self.abp__exit_combos.items()
        }

    def abp_options(self) -> abpSheetOptions:
        return abpSheetOptions(
            abp_paper=self.abp_paper_combo.currentText(),
            abp_scale=int(self.abp_scale_combo.currentData()) or None,
            abp_title=self.abp_title_edit.text().strip() or self.abp__texts.abp_default_title,
            abp_code=self.abp_code_edit.text().strip() or "ES",
            abp_specialist=self.abp_specialist_edit.text().strip(),
            abp_drafter=self.abp_drafter_edit.text().strip(),
            abp_sector=self.abp_sector_edit.text().strip(),
            abp_north_deg=self.abp_north_spin.value(),
            abp_flow=self.abp_flow_spin.value(),
            abp_speed=self.abp_speed_spin.value(),
            abp_people_source=str(self.abp_people_combo.currentData()),
            abp_underlay=str(self.abp_underlay_combo.currentData()),
            abp_follow_furniture=self.abp_furniture_check.isChecked(),
            abp_propose_signs=self.abp_signs_check.isChecked(),
            abp_orientation=str(self.abp_orientation_combo.currentData()),
            abp_tables=str(self.abp_tables_combo.currentData()),
            abp_identify=str(self.abp_identify_combo.currentData()),
            abp_note=self.abp_note_edit.toPlainText().strip(),
            abp_made_on=date.today(),
        )


def abp__combo(abp_choices: Sequence[tuple[str, str]], abp_current: str) -> QComboBox:
    abp_combo = QComboBox()
    for abp_label, abp_value in abp_choices:
        abp_combo.addItem(abp_label, abp_value)
    abp_combo.setCurrentIndex(max(0, abp_combo.findData(abp_current)))
    return abp_combo


def abp__spin(abp_value: float, abp_low: float, abp_high: float) -> QDoubleSpinBox:
    abp_spin = QDoubleSpinBox()
    abp_spin.setRange(abp_low, abp_high)
    abp_spin.setDecimals(2)
    abp_spin.setSingleStep(0.1)
    abp_spin.setValue(abp_value)
    return abp_spin
