from __future__ import annotations

import dataclasses
import functools
from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_stairs_service import (
    abp_entry_side,
    abp_names_below,
    abp_SIDES,
    abp_stair_roles,
    abp_with_entry_side,
)
from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpStair
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted, abp_set_cell
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpEditorTexts, abpStairsTexts

abp_NAME, abp_USE, abp_SIDE, abp_BELOW, abp_ROLE = range(5)


class abpStairsDialog(QDialog):
    abp_analyze_requested = Signal()

    def __init__(
        self,
        abp_editor: abpPlanEditor,
        abp_floors: Sequence[abpFloorPlan] = (),
        *,
        abp_can_analyze: bool = False,
        abp_texts: abpStairsTexts = abp_TEXTS.abp_stairs,
        abp_editor_texts: abpEditorTexts = abp_TEXTS.abp_editor,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__editor = abp_editor
        self.abp__floors = list(abp_floors)
        self.abp__texts = abp_texts
        self.abp__uses = abp_editor_texts.abp_stair_uses
        self.setWindowTitle(abp_texts.abp_title)
        self.resize(900, 380)
        self.abp_table = QTableWidget(0, 5)
        self.abp_table.setHorizontalHeaderLabels(list(abp_texts.abp_columns))
        self.abp_table.verticalHeader().setVisible(False)
        self.abp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.abp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        abp_header = self.abp_table.horizontalHeader()
        abp_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        abp_header.setSectionResizeMode(abp_ROLE, QHeaderView.ResizeMode.Stretch)
        self.abp_table.currentCellChanged.connect(lambda abp_row, *_: self.abp__locate(abp_row))
        self.abp_table.itemChanged.connect(self.abp__on_renamed)
        self.abp_empty_label = QLabel(abp_texts.abp_empty)
        self.abp_empty_label.setWordWrap(True)
        self.abp_analyze_button = QPushButton(abp_texts.abp_analyze)
        self.abp_analyze_button.setToolTip(
            abp_texts.abp_analyze_tip if abp_can_analyze else abp_texts.abp_analyze_no_lines
        )
        self.abp_analyze_button.setEnabled(abp_can_analyze)
        self.abp_analyze_button.clicked.connect(self.abp_analyze_requested)
        self.abp_confirm_button = QPushButton(abp_texts.abp_confirm)
        self.abp_confirm_button.clicked.connect(self.abp_confirm_all)
        self.abp_close_button = abp_set_primary(QPushButton(abp_texts.abp_close))
        self.abp_close_button.clicked.connect(self.accept)
        abp_buttons = QHBoxLayout()
        abp_buttons.addWidget(self.abp_analyze_button)
        abp_buttons.addWidget(self.abp_confirm_button)
        abp_buttons.addStretch(1)
        abp_buttons.addWidget(self.abp_close_button)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_muted(abp_texts.abp_help))
        abp_layout.addWidget(self.abp_empty_label)
        abp_layout.addWidget(self.abp_table, stretch=1)
        abp_layout.addLayout(abp_buttons)
        abp_editor.abp_plan_changed.connect(self.abp__on_plan)
        self.abp__filling = False
        self.abp_refresh()

    @property
    def abp_plan(self) -> abpFloorPlan:
        return self.abp__editor.abp_plan()

    @property
    def abp_upper_floor(self) -> bool:
        abp_levels = [abp_f.abp_level for abp_f in self.abp__floors] + [self.abp_plan.abp_level]
        return self.abp_plan.abp_level > min(abp_levels)

    def abp_refresh(self) -> None:
        abp_plan = self.abp_plan
        abp_below = abp_names_below(self.abp__floors, abp_plan.abp_level)
        abp_roles = abp_stair_roles(abp_plan, abp_upper_floor=self.abp_upper_floor)
        self.abp__filling = True
        abp_row = self.abp_table.currentRow()
        self.abp_table.setRowCount(len(abp_plan.abp_stairs))
        for abp_index, abp_stair in enumerate(abp_plan.abp_stairs):
            abp_name = QTableWidgetItem(abp_stair.abp_name)
            self.abp_table.setItem(abp_index, abp_NAME, abp_name)
            abp_set_cell(
                self.abp_table,
                abp_index,
                abp_USE,
                self.abp__combo(
                    self.abp__uses,
                    abp_stair.abp_use.value,
                    functools.partial(self.abp_set_use, abp_index),
                ),
            )
            abp_sides = (
                ("", self.abp__texts.abp_side_auto),
                *zip(abp_SIDES, self.abp__texts.abp_sides, strict=True),
            )
            abp_set_cell(
                self.abp_table,
                abp_index,
                abp_SIDE,
                self.abp__combo(
                    abp_sides,
                    abp_entry_side(abp_stair),
                    functools.partial(self.abp_set_side, abp_index),
                ),
            )
            abp_options = [
                ("", self.abp__texts.abp_below_same),
                *((abp_n, abp_n) for abp_n in abp_below),
            ]
            if abp_stair.abp_leads_to and abp_stair.abp_leads_to not in abp_below:
                abp_options.append((abp_stair.abp_leads_to, abp_stair.abp_leads_to))
            abp_combo = self.abp__combo(
                abp_options,
                abp_stair.abp_leads_to,
                functools.partial(self.abp_set_below, abp_index),
            )
            abp_combo.setEnabled(bool(abp_below))
            abp_set_cell(self.abp_table, abp_index, abp_BELOW, abp_combo)
            abp_role = QTableWidgetItem(dict(self.abp__texts.abp_roles)[abp_roles[abp_index]])
            abp_role.setFlags(abp_role.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.abp_table.setItem(abp_index, abp_ROLE, abp_role)
        self.abp_table.setColumnHidden(abp_BELOW, not self.abp_upper_floor)
        if 0 <= abp_row < len(abp_plan.abp_stairs):
            self.abp_table.setCurrentCell(abp_row, abp_NAME)
        self.abp__filling = False
        self.abp_table.setVisible(bool(abp_plan.abp_stairs))
        self.abp_empty_label.setVisible(not abp_plan.abp_stairs)
        self.abp_confirm_button.setEnabled(
            any(not abp_s.abp_confirmed for abp_s in abp_plan.abp_stairs)
        )

    @staticmethod
    def abp__combo(
        abp_options: Sequence[tuple[str, str]], abp_value: str, abp_changed: functools.partial[None]
    ) -> QComboBox:
        abp_combo = QComboBox()
        for abp_data, abp_label in abp_options:
            abp_combo.addItem(abp_label, abp_data)
        abp_combo.setCurrentIndex(max(0, abp_combo.findData(abp_value)))
        abp_combo.activated.connect(
            lambda abp_i, abp_c=abp_combo: abp_changed(str(abp_c.itemData(abp_i)))
        )
        return abp_combo

    def abp_set_use(self, abp_index: int, abp_use: str) -> None:
        abp_stair = self.abp_plan.abp_stairs[abp_index]
        self.abp__replace(
            abp_index,
            dataclasses.replace(abp_stair, abp_use=abpStairUse(abp_use), abp_confirmed=True),
            self.abp__texts.abp_cmd,
        )

    def abp_set_side(self, abp_index: int, abp_side: str) -> None:
        self.abp__replace(
            abp_index,
            abp_with_entry_side(self.abp_plan.abp_stairs[abp_index], abp_side),
            self.abp__texts.abp_cmd,
        )

    def abp_set_below(self, abp_index: int, abp_name: str) -> None:
        abp_stair = dataclasses.replace(self.abp_plan.abp_stairs[abp_index], abp_leads_to=abp_name)
        self.abp__replace(abp_index, abp_stair, self.abp__texts.abp_cmd)

    def abp_confirm_all(self) -> None:
        abp_stairs = tuple(
            dataclasses.replace(abp_s, abp_confirmed=True) for abp_s in self.abp_plan.abp_stairs
        )
        self.abp__editor.abp_apply(
            dataclasses.replace(self.abp_plan, abp_stairs=abp_stairs), self.abp__texts.abp_confirm
        )

    def abp__on_renamed(self, abp_item: QTableWidgetItem) -> None:
        if self.abp__filling or abp_item.column() != abp_NAME:
            return
        abp_stair = self.abp_plan.abp_stairs[abp_item.row()]
        abp_name = abp_item.text().strip()
        abp_taken = any(
            abp_s.abp_name == abp_name
            for abp_i, abp_s in enumerate(self.abp_plan.abp_stairs)
            if abp_i != abp_item.row()
        )
        if not abp_name or abp_taken or abp_name == abp_stair.abp_name:
            self.abp_refresh()
            return
        self.abp__replace(
            abp_item.row(),
            dataclasses.replace(abp_stair, abp_name=abp_name),
            self.abp__texts.abp_cmd,
        )

    def abp__replace(self, abp_index: int, abp_stair: abpStair, abp_text: str) -> None:
        abp_stairs = list(self.abp_plan.abp_stairs)
        if abp_stairs[abp_index] == abp_stair:
            return
        abp_stairs[abp_index] = abp_stair
        self.abp__editor.abp_apply(
            dataclasses.replace(self.abp_plan, abp_stairs=tuple(abp_stairs)), abp_text
        )

    def abp__on_plan(self, abp__plan: object) -> None:
        if self.isVisible() or self.abp_table.rowCount():
            self.abp_refresh()

    def abp__locate(self, abp_row: int) -> None:
        if self.abp__filling or not 0 <= abp_row < len(self.abp_plan.abp_stairs):
            return
        self.abp__editor.abp_show_area(self.abp_plan.abp_stairs[abp_row].abp_area)
