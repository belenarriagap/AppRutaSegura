from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_plan_import import abpPlanElement
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpElementsTexts

abp_INDEX = Qt.ItemDataRole.UserRole


class abpElementsDialog(QDialog):
    abp_picked = Signal(object)

    def __init__(
        self,
        abp_elements: Sequence[abpPlanElement],
        abp_texts: abpElementsTexts = abp_TEXTS.abp_elements,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__elements = list(abp_elements)
        self.abp__texts = abp_texts
        self.setWindowTitle(abp_texts.abp_title)
        self.resize(520, 640)
        self.abp_search_edit = QLineEdit()
        self.abp_search_edit.setPlaceholderText(abp_texts.abp_search)
        self.abp_search_edit.setClearButtonEnabled(True)
        self.abp_search_edit.textChanged.connect(self.abp__filter)
        self.abp_tree = QTreeWidget()
        self.abp_tree.setHeaderLabels([abp_texts.abp_column_element, abp_texts.abp_column_detail])
        self.abp_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.abp_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.abp_tree.currentItemChanged.connect(self.abp__on_current)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_muted(abp_texts.abp_help))
        abp_layout.addWidget(self.abp_search_edit)
        abp_layout.addWidget(self.abp_tree, stretch=1)
        self.abp__fill()

    def abp_label_of(self, abp_element: abpPlanElement) -> str:
        abp_art = abp_SIGNS.get(abp_element.abp_label) if abp_element.abp_kind == "senal" else None
        return abp_art.abp_label if abp_art is not None else abp_element.abp_label

    def abp_counts(self) -> dict[str, int]:
        abp_out: dict[str, int] = {}
        for abp_element in self.abp__elements:
            abp_out[abp_element.abp_kind] = abp_out.get(abp_element.abp_kind, 0) + 1
        return abp_out

    def abp__fill(self) -> None:
        abp_names = dict(self.abp__texts.abp_kinds)
        abp_counts = self.abp_counts()
        for abp_kind, abp__title in self.abp__texts.abp_kinds:
            if abp_kind not in abp_counts:
                continue
            abp_group = QTreeWidgetItem([f"{abp_names[abp_kind]} ({abp_counts[abp_kind]})", ""])
            abp_font = abp_group.font(0)
            abp_font.setBold(True)
            abp_group.setFont(0, abp_font)
            for abp_index, abp_element in enumerate(self.abp__elements):
                if abp_element.abp_kind != abp_kind:
                    continue
                abp_item = QTreeWidgetItem([self.abp_label_of(abp_element), abp_element.abp_detail])
                abp_item.setData(0, abp_INDEX, abp_index)
                abp_group.addChild(abp_item)
            self.abp_tree.addTopLevelItem(abp_group)
            abp_group.setExpanded(abp_counts[abp_kind] <= 12 and abp_kind != "muro")

    def abp__filter(self, abp_text: str) -> None:
        abp_needle = abp_text.strip().lower()
        for abp_g in range(self.abp_tree.topLevelItemCount()):
            abp_group = self.abp_tree.topLevelItem(abp_g)
            if abp_group is None:
                continue
            abp_visible = 0
            for abp_i in range(abp_group.childCount()):
                abp_child = abp_group.child(abp_i)
                if abp_child is None:
                    continue
                abp_match = (
                    abp_needle
                    in f"{abp_group.text(0)} {abp_child.text(0)} {abp_child.text(1)}".lower()
                )
                abp_child.setHidden(not abp_match)
                abp_visible += int(abp_match)
            abp_group.setHidden(abp_visible == 0)
            if abp_needle:
                abp_group.setExpanded(True)

    def abp__on_current(
        self, abp_current: QTreeWidgetItem | None, abp__previous: QTreeWidgetItem | None
    ) -> None:
        abp_index = abp_current.data(0, abp_INDEX) if abp_current is not None else None
        if abp_index is not None:
            self.abp_picked.emit(self.abp__elements[int(abp_index)])
