from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_report_service import abp_PAPER_NAMES, abpMapOptions
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpReportTexts

abp_PHONE_ROWS = 5


class abpEvacuationMapDialog(QDialog):
    def __init__(
        self,
        abp_floors: Sequence[abpFloorPlan],
        *,
        abp_responsible: str = "",
        abp_texts: abpReportTexts = abp_TEXTS.abp_report,
        abp_floor_name: str = abp_TEXTS.abp_floors.abp_name,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.setWindowTitle(abp_texts.abp_map_dialog_title)
        self.setMinimumWidth(560)
        self.abp_paper_combo = QComboBox()
        self.abp_paper_combo.addItems(list(abp_PAPER_NAMES))
        abp_form = QFormLayout()
        abp_form.addRow(abp_texts.abp_map_paper, self.abp_paper_combo)
        self.abp_here_combos: dict[int, QComboBox] = {}
        for abp_plan in sorted(abp_floors, key=lambda abp_f: abp_f.abp_level):
            abp_combo = QComboBox()
            abp_combo.addItem(abp_texts.abp_map_here_none, "")
            for abp_room in abp_plan.abp_rooms:
                abp_combo.addItem(abp_room.abp_name, abp_room.abp_name)
            abp_label = abp_texts.abp_map_here.format(
                floor=abp_floor_name.format(number=abp_plan.abp_level + 1).lower()
            )
            abp_form.addRow(abp_label, abp_combo)
            self.abp_here_combos[abp_plan.abp_level] = abp_combo
        self.abp_responsible_edit = QLineEdit(abp_responsible)
        self.abp_meeting_edit = QLineEdit()
        self.abp_meeting_edit.setPlaceholderText(abp_texts.abp_map_meeting_placeholder)
        abp_form.addRow(abp_texts.abp_map_responsible, self.abp_responsible_edit)
        abp_form.addRow(abp_texts.abp_map_meeting_point, self.abp_meeting_edit)

        self.abp_phones_table = QTableWidget(abp_PHONE_ROWS, 2)
        self.abp_phones_table.setHorizontalHeaderLabels(
            [abp_texts.abp_map_phone_service, abp_texts.abp_map_phone_number]
        )
        self.abp_phones_table.verticalHeader().setVisible(False)
        self.abp_phones_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.abp_phones_table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.abp_phones_table.setMaximumHeight(170)
        for abp_row, (abp_service, abp_number) in enumerate(
            abp_texts.abp_map_default_phones[:abp_PHONE_ROWS]
        ):
            self.abp_phones_table.setItem(abp_row, 0, QTableWidgetItem(abp_service))
            self.abp_phones_table.setItem(abp_row, 1, QTableWidgetItem(abp_number))
        self.abp_instructions_edit = QPlainTextEdit(
            "\n".join(abp_texts.abp_map_default_instructions)
        )
        self.abp_instructions_edit.setMinimumHeight(130)

        abp_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_layout = QVBoxLayout(self)
        abp_help_label = QLabel(abp_texts.abp_map_help)
        abp_help_label.setObjectName("muted")
        abp_help_label.setWordWrap(True)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addLayout(abp_form)
        abp_layout.addWidget(QLabel(abp_texts.abp_map_phones))
        abp_layout.addWidget(self.abp_phones_table)
        abp_layout.addWidget(QLabel(abp_texts.abp_map_instructions))
        abp_layout.addWidget(self.abp_instructions_edit)
        abp_layout.addWidget(abp_buttons)

    def abp_options(self) -> abpMapOptions:
        abp_phones: list[tuple[str, str]] = []
        for abp_row in range(self.abp_phones_table.rowCount()):
            abp_cells = [self.abp_phones_table.item(abp_row, abp_col) for abp_col in (0, 1)]
            abp_service, abp_number = (
                abp_c.text().strip() if abp_c is not None else "" for abp_c in abp_cells
            )
            if abp_service and abp_number:
                abp_phones.append((abp_service, abp_number))
        abp_instructions = tuple(
            abp_line.strip() for abp_line in self.abp_instructions_edit.toPlainText().splitlines()
        )
        abp_here = tuple(
            (abp_level, str(abp_combo.currentData()))
            for abp_level, abp_combo in self.abp_here_combos.items()
            if abp_combo.currentData()
        )
        return abpMapOptions(
            abp_paper=self.abp_paper_combo.currentText(),
            abp_you_are_here=abp_here,
            abp_responsible=self.abp_responsible_edit.text().strip(),
            abp_phones=tuple(abp_phones),
            abp_meeting_point=self.abp_meeting_edit.text().strip(),
            abp_instructions=tuple(abp_line for abp_line in abp_instructions if abp_line),
            abp_disclaimer=self.abp__texts.abp_map_disclaimer,
        )
