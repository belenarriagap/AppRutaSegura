from __future__ import annotations

import dataclasses
import functools
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_plan_import import (
    abp_label_inside,
    abpPlanImportService,
    abpRoomLabel,
)
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpRoom
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import abpPlanScene
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView, abpTool
from abp_rutasegura.abp_presentation.abp_room_types import abp_room_type_combo
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import (
    abp_page_help,
    abp_page_title,
    abp_section_title,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpProjectTexts, abpRoomsTexts

abpImage = npt.NDArray[np.uint8]
abp_ROOM_COLOR = QColor("#2980b9")
abp_SELECTED_COLOR = QColor("#e67e22")
abp_COL_NAME, abp_COL_USE, abp_COL_AREA, abp_FIRST_PROFILE_COL = 0, 1, 2, 3


class abpRoomsPage(QWidget):
    abp_plan_changed = Signal(object)
    abp_scenario_changed = Signal(object)
    abp_error = Signal(str)

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_texts: abpRoomsTexts = abp_TEXTS.abp_rooms,
        abp_project_texts: abpProjectTexts = abp_TEXTS.abp_project,
        abp_parent: QWidget | None = None,
        abp_norms: abpNormsService | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__norms = abp_norms or abpNormsService()
        self.abp__texts = abp_texts
        self.abp__use_labels = dict(abp_project_texts.abp_use_labels)
        self.abp__plan = abpFloorPlan()
        self.abp__scenario = abpScenario("", 0)
        self.abp__profiles: list[abpPersonProfile] = []
        self.abp__default_use = abpUseType.abp_EDUCATION
        self.abp__room_items: list[QGraphicsPolygonItem] = []
        self.abp__label_items: list[QGraphicsItem] = []
        self.abp__updating = False

        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_view.abp_polygon_drawn.connect(self.abp__on_polygon)
        self.abp_detect_button = abp_set_primary(QPushButton(abp_texts.abp_detect))
        self.abp_detect_button.clicked.connect(self.abp_detect_rooms)
        self.abp_draw_button = QPushButton(abp_texts.abp_draw)
        self.abp_draw_button.setCheckable(True)
        self.abp_draw_button.toggled.connect(
            lambda abp_on: self.abp_view.abp_set_tool(
                abpTool.abp_POLYGON if abp_on else abpTool.abp_NONE
            )
        )
        self.abp_plan_occupants_button = QPushButton(abp_TEXTS.abp_pdf.abp_plan_occupants)
        self.abp_plan_occupants_button.setToolTip(abp_TEXTS.abp_pdf.abp_plan_occupants_tip)
        self.abp_plan_occupants_button.clicked.connect(self.abp_use_plan_occupants)
        self.abp__labels: tuple[abpRoomLabel, ...] = ()
        self.abp_delete_button = QPushButton(abp_texts.abp_delete)
        self.abp_delete_button.clicked.connect(self.abp_delete_selected_room)
        self.abp_status_label = QLabel()
        self.abp_status_label.setWordWrap(True)
        self.abp_total_label = abp_section_title("")
        self.abp_table = QTableWidget()
        self.abp_table.setAlternatingRowColors(True)
        self.abp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.abp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.abp_table.itemChanged.connect(self.abp__on_item_changed)
        self.abp_table.itemSelectionChanged.connect(self.abp__highlight_selection)

        abp_buttons = QHBoxLayout()
        for abp_button in (
            self.abp_detect_button,
            self.abp_draw_button,
            self.abp_delete_button,
            self.abp_plan_occupants_button,
        ):
            abp_buttons.addWidget(abp_button)
        abp_buttons.addStretch(1)
        abp_right = QWidget()
        abp_right_layout = QVBoxLayout(abp_right)
        abp_right_layout.setContentsMargins(0, 0, 0, 0)
        abp_right_layout.addWidget(self.abp_table, stretch=1)
        abp_right_layout.addWidget(self.abp_total_label)
        abp_splitter = QSplitter()
        abp_splitter.addWidget(self.abp_view)
        abp_splitter.addWidget(abp_right)
        abp_splitter.setSizes([600, 500])

        abp_title = abp_page_title(abp_texts.abp_title)
        abp_help_label = abp_page_help(abp_texts.abp_help)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_title)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addLayout(abp_buttons)
        abp_layout.addWidget(self.abp_status_label)
        abp_layout.addWidget(abp_splitter, stretch=1)

    @property
    def abp_plan(self) -> abpFloorPlan:
        return self.abp__plan

    @property
    def abp_scenario(self) -> abpScenario:
        return self.abp__scenario

    def abp_set_content(
        self,
        abp_plan: abpFloorPlan,
        abp_image: abpImage | None,
        abp_scenario: abpScenario,
        abp_profiles: Sequence[abpPersonProfile],
        abp_default_use: abpUseType,
        *,
        abp_labels: Sequence[abpRoomLabel] = (),
    ) -> None:
        self.abp__labels = tuple(abp_labels)
        self.abp_plan_occupants_button.setVisible(
            any(abp_q.abp_capacity for abp_q in self.abp__labels)
        )
        self.abp__plan = abp_plan
        self.abp__scenario = abp_scenario
        self.abp__profiles = list(abp_profiles)
        self.abp__default_use = abp_default_use
        self.abp_scene.abp_set_image(abp_image)
        self.abp_scene.abp_render_plan(abp_plan)
        for abp_kind_items in (self.abp_scene.abp_all_element_items(),):
            for abp_item in abp_kind_items:
                abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.abp__refresh()
        self.abp_view.abp_fit_all()
        self.abp_status_label.setText(
            "" if abp_plan.abp_is_scaled else self.abp__texts.abp_no_scale
        )

    def abp_detect_rooms(self) -> None:
        try:
            abp_new_plan = self.abp__plans.abp_detect_rooms(
                self.abp__plan,
                self.abp__default_use,
                self.abp__texts.abp_name_template,
                abp_labels=self.abp__labels,
            )
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return
        abp_added = len(abp_new_plan.abp_rooms) - len(self.abp__plan.abp_rooms)
        self.abp_status_label.setText(
            self.abp__texts.abp_detected.format(count=abp_added)
            if abp_added
            else self.abp__texts.abp_nothing_detected
        )
        if abp_added:
            self.abp__set_plan(abp_new_plan)

    def abp_use_plan_occupants(self) -> None:
        abp_total = 0
        for abp_room in self.abp__plan.abp_rooms:
            abp_label = abp_label_inside(abp_room.abp_area, self.abp__labels)
            if abp_label is not None and abp_label.abp_capacity and self.abp__profiles:
                self.abp_set_occupants(
                    abp_room.abp_name, self.abp__profiles[0].abp_name, abp_label.abp_capacity
                )
                abp_total += abp_label.abp_capacity
        abp_texts = abp_TEXTS.abp_pdf
        self.abp_status_label.setText(
            abp_texts.abp_plan_occupants_done.format(count=abp_total)
            if abp_total
            else abp_texts.abp_plan_occupants_none
        )

    def abp_add_room(self, abp_polygon: abpPolygon, abp_name: str | None = None) -> None:
        abp_used = {abp_r.abp_name for abp_r in self.abp__plan.abp_rooms}
        if abp_name is None:
            abp_number = 1
            while self.abp__texts.abp_name_template.format(number=abp_number) in abp_used:
                abp_number += 1
            abp_name = self.abp__texts.abp_name_template.format(number=abp_number)
        abp_room = abpRoom(abp_name, self.abp__default_use, abp_polygon)
        self.abp__set_plan(
            dataclasses.replace(self.abp__plan, abp_rooms=(*self.abp__plan.abp_rooms, abp_room))
        )

    def abp_delete_room(self, abp_index: int) -> None:
        if not 0 <= abp_index < len(self.abp__plan.abp_rooms):
            return
        abp_removed = self.abp__plan.abp_rooms[abp_index]
        abp_rooms = tuple(
            abp_r for abp_i, abp_r in enumerate(self.abp__plan.abp_rooms) if abp_i != abp_index
        )
        abp_occupancies = tuple(
            abp_o
            for abp_o in self.abp__scenario.abp_occupancies
            if not (
                abp_o.abp_room_name == abp_removed.abp_name
                and abp_o.abp_level == self.abp__plan.abp_level
            )
        )
        self.abp__set_scenario(
            dataclasses.replace(self.abp__scenario, abp_occupancies=abp_occupancies)
        )
        self.abp__set_plan(dataclasses.replace(self.abp__plan, abp_rooms=abp_rooms))

    def abp_delete_selected_room(self) -> None:
        self.abp_delete_room(self.abp_table.currentRow())

    def abp_set_occupants(self, abp_room_name: str, abp_profile_name: str, abp_count: int) -> None:
        abp_level = self.abp__plan.abp_level
        abp_others = [
            abp_o
            for abp_o in self.abp__scenario.abp_occupancies
            if not (
                abp_o.abp_room_name == abp_room_name
                and abp_o.abp_profile_name == abp_profile_name
                and abp_o.abp_level == abp_level
            )
        ]
        if abp_count > 0:
            abp_others.append(abpOccupancy(abp_room_name, abp_profile_name, abp_count, abp_level))
        abp_order = {abp_r.abp_name: abp_i for abp_i, abp_r in enumerate(self.abp__plan.abp_rooms)}
        abp_profile_order = {
            abp_p.abp_name: abp_i for abp_i, abp_p in enumerate(self.abp__profiles)
        }
        abp_others.sort(
            key=lambda abp_o: (
                abp_order.get(abp_o.abp_room_name, 999),
                abp_profile_order.get(abp_o.abp_profile_name, 999),
            )
        )
        self.abp__set_scenario(
            dataclasses.replace(self.abp__scenario, abp_occupancies=tuple(abp_others))
        )
        self.abp__sync_spin(abp_room_name, abp_profile_name, abp_count)
        self.abp__update_total()

    def abp__sync_spin(self, abp_room_name: str, abp_profile_name: str, abp_count: int) -> None:
        abp_rows = [
            abp_i
            for abp_i, abp_r in enumerate(self.abp__plan.abp_rooms)
            if abp_r.abp_name == abp_room_name
        ]
        abp_cols = [
            abp_k
            for abp_k, abp_p in enumerate(self.abp__profiles)
            if abp_p.abp_name == abp_profile_name
        ]
        if not abp_rows or not abp_cols:
            return
        abp_spin = self.abp_table.cellWidget(abp_rows[0], abp_FIRST_PROFILE_COL + abp_cols[0])
        if isinstance(abp_spin, QSpinBox) and abp_spin.value() != abp_count:
            abp_spin.blockSignals(True)
            abp_spin.setValue(abp_count)
            abp_spin.blockSignals(False)

    def abp_rename_room(self, abp_index: int, abp_new_name: str) -> None:
        abp_new_name = abp_new_name.strip()
        abp_old = self.abp__plan.abp_rooms[abp_index]
        if not abp_new_name or abp_new_name == abp_old.abp_name:
            self.abp__refresh()
            return
        if any(abp_r.abp_name == abp_new_name for abp_r in self.abp__plan.abp_rooms):
            self.abp_error.emit(f"Ya existe un ambiente llamado «{abp_new_name}».")
            self.abp__refresh()
            return
        abp_rooms = list(self.abp__plan.abp_rooms)
        abp_rooms[abp_index] = dataclasses.replace(abp_old, abp_name=abp_new_name)
        self.abp__set_scenario(
            self.abp__scenario.abp_renamed_room(
                self.abp__plan.abp_level, abp_old.abp_name, abp_new_name
            )
        )
        self.abp__set_plan(dataclasses.replace(self.abp__plan, abp_rooms=tuple(abp_rooms)))

    def abp_set_room_use(self, abp_index: int, abp_use: abpUseType) -> None:
        self.abp_set_room_type(abp_index, abp_use, "")

    def abp_set_room_type(self, abp_index: int, abp_use: abpUseType, abp_category: str) -> None:
        abp_rooms = list(self.abp__plan.abp_rooms)
        if not 0 <= abp_index < len(abp_rooms):
            return
        if (abp_rooms[abp_index].abp_use, abp_rooms[abp_index].abp_category) == (
            abp_use,
            abp_category,
        ):
            return
        abp_rooms[abp_index] = dataclasses.replace(
            abp_rooms[abp_index], abp_use=abp_use, abp_category=abp_category
        )
        self.abp__set_plan(
            dataclasses.replace(self.abp__plan, abp_rooms=tuple(abp_rooms)), abp_refresh=False
        )

    def abp__set_plan(self, abp_plan: abpFloorPlan, *, abp_refresh: bool = True) -> None:
        self.abp__plan = abp_plan
        if abp_refresh:
            self.abp__refresh()
        self.abp_plan_changed.emit(abp_plan)

    def abp__set_scenario(self, abp_scenario: abpScenario) -> None:
        self.abp__scenario = abp_scenario
        self.abp_scenario_changed.emit(abp_scenario)

    def abp__on_polygon(self, abp_points: list[QPointF]) -> None:
        self.abp_add_room(abpPolygon(tuple(abpPoint(abp_p.x(), abp_p.y()) for abp_p in abp_points)))

    def abp__count(self, abp_room: str, abp_profile: str) -> int:
        for abp_o in self.abp__scenario.abp_occupancies:
            if (
                abp_o.abp_room_name == abp_room
                and abp_o.abp_profile_name == abp_profile
                and abp_o.abp_level == self.abp__plan.abp_level
            ):
                return abp_o.abp_count
        return 0

    def abp__refresh(self) -> None:
        self.abp__draw_rooms()
        self.abp__updating = True
        abp_t = self.abp__texts
        abp_headers = [
            abp_t.abp_column_name,
            abp_t.abp_column_use,
            abp_t.abp_column_area,
            *(abp_p.abp_name for abp_p in self.abp__profiles),
        ]
        self.abp_table.clear()
        self.abp_table.setColumnCount(len(abp_headers))
        self.abp_table.setHorizontalHeaderLabels(abp_headers)
        self.abp_table.setRowCount(len(self.abp__plan.abp_rooms))
        for abp_row, abp_room in enumerate(self.abp__plan.abp_rooms):
            self.abp_table.setItem(abp_row, abp_COL_NAME, QTableWidgetItem(abp_room.abp_name))
            abp_combo = abp_room_type_combo(
                self.abp__norms,
                abp_room,
                self.abp__default_use,
                functools.partial(self.abp_set_room_type, abp_row),
            )
            self.abp_table.setCellWidget(abp_row, abp_COL_USE, abp_combo)
            abp_area = (
                f"{self.abp__plan.abp_area_m2(abp_room.abp_area):.1f}"
                if self.abp__plan.abp_is_scaled
                else "—"
            )
            abp_area_item = QTableWidgetItem(abp_area)
            abp_area_item.setFlags(abp_area_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.abp_table.setItem(abp_row, abp_COL_AREA, abp_area_item)
            for abp_k, abp_profile in enumerate(self.abp__profiles):
                abp_spin = QSpinBox()
                abp_spin.setRange(0, 5000)
                abp_spin.setValue(self.abp__count(abp_room.abp_name, abp_profile.abp_name))
                abp_spin.valueChanged.connect(
                    lambda abp_value, abp_rn=abp_room.abp_name, abp_pn=abp_profile.abp_name: (
                        self.abp_set_occupants(abp_rn, abp_pn, abp_value)
                    )
                )
                self.abp_table.setCellWidget(abp_row, abp_FIRST_PROFILE_COL + abp_k, abp_spin)
        abp_header = self.abp_table.horizontalHeader()
        abp_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        abp_header.setMinimumSectionSize(70)
        self.abp__updating = False
        self.abp_delete_button.setEnabled(bool(self.abp__plan.abp_rooms))
        self.abp__update_total()

    def abp__update_total(self) -> None:
        self.abp_total_label.setText(
            self.abp__texts.abp_total.format(count=self.abp__scenario.abp_total_occupants)
        )

    def abp__on_item_changed(self, abp_item: QTableWidgetItem) -> None:
        if self.abp__updating or abp_item.column() != abp_COL_NAME:
            return
        self.abp_rename_room(abp_item.row(), abp_item.text())

    def abp__draw_rooms(self) -> None:
        for abp_item in self.abp__room_items + self.abp__label_items:
            self.abp_scene.removeItem(abp_item)
        self.abp__room_items.clear()
        self.abp__label_items.clear()
        for abp_room in self.abp__plan.abp_rooms:
            abp_fill = QColor(abp_ROOM_COLOR)
            abp_fill.setAlpha(45)
            abp_pen = QPen(abp_ROOM_COLOR, 2)
            abp_pen.setCosmetic(True)
            abp_item = QGraphicsPolygonItem(
                QPolygonF(
                    [QPointF(abp_p.abp_x, abp_p.abp_y) for abp_p in abp_room.abp_area.abp_vertices]
                )
            )
            abp_item.setPen(abp_pen)
            abp_item.setBrush(QBrush(abp_fill))
            abp_item.setZValue(5)
            self.abp_scene.addItem(abp_item)
            self.abp__room_items.append(abp_item)
            abp_label = QGraphicsSimpleTextItem(abp_room.abp_name)
            abp_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            abp_center = abp_room.abp_area.abp_centroid
            abp_label.setPos(abp_center.abp_x, abp_center.abp_y)
            abp_label.setZValue(6)
            self.abp_scene.addItem(abp_label)
            self.abp__label_items.append(abp_label)
        self.abp__highlight_selection()

    def abp__highlight_selection(self) -> None:
        abp_selected = self.abp_table.currentRow()
        for abp_i, abp_item in enumerate(self.abp__room_items):
            abp_color = abp_SELECTED_COLOR if abp_i == abp_selected else abp_ROOM_COLOR
            abp_pen = QPen(abp_color, 3 if abp_i == abp_selected else 2)
            abp_pen.setCosmetic(True)
            abp_item.setPen(abp_pen)
