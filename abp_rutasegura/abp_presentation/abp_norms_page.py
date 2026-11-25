from __future__ import annotations

import dataclasses
import functools

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_norms import abpNormEvaluation
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_presentation.abp_room_types import abp_room_type_combo
from abp_rutasegura.abp_presentation.abp_widgets import (
    abp_page_help,
    abp_page_title,
    abp_section_title,
    abpBanner,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpNormsTexts

(
    abp_COL_NAME,
    abp_COL_CATEGORY,
    abp_COL_AREA,
    abp_COL_CAPACITY,
    abp_COL_OCCUPANTS,
    abp_COL_TRAVEL,
    abp_COL_STATUS,
) = range(7)
abp_EXCEEDED_COLOR = QColor("#fadbd8")


class abpNormsPage(QWidget):
    abp_verify_requested = Signal()

    abp_plan_changed = Signal(object)
    abp_error = Signal(str)

    def __init__(
        self,
        abp_norms: abpNormsService,
        abp_texts: abpNormsTexts = abp_TEXTS.abp_norms,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__norms = abp_norms
        self.abp__texts = abp_texts
        self.abp__plan = abpFloorPlan()
        self.abp__scenario: abpScenario | None = None
        self.abp_evaluation: abpNormEvaluation | None = None

        abp_title = abp_page_title(abp_texts.abp_title)
        abp_help_label = abp_page_help(abp_texts.abp_help)
        self.abp_warning_banner = abpBanner(abp_closable=False)
        self.abp_table = QTableWidget()
        self.abp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.abp_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.abp_table.setAlternatingRowColors(True)
        self.abp_total_label = abp_section_title("")
        self.abp_observations = QListWidget()
        self.abp_observations.setWordWrap(True)
        self.abp_observations.setSpacing(3)
        abp_observations_title = abp_section_title(abp_texts.abp_observations_title)

        abp_top = QWidget()
        abp_top_layout = QVBoxLayout(abp_top)
        abp_top_layout.setContentsMargins(0, 0, 0, 0)
        abp_top_layout.addWidget(self.abp_table)
        abp_top_layout.addWidget(self.abp_total_label)
        abp_bottom = QWidget()
        abp_bottom_layout = QVBoxLayout(abp_bottom)
        abp_bottom_layout.setContentsMargins(0, 0, 0, 0)
        abp_bottom_layout.addWidget(abp_observations_title)
        abp_bottom_layout.addWidget(self.abp_observations)
        abp_splitter = QSplitter(Qt.Orientation.Vertical)
        abp_splitter.addWidget(abp_top)
        abp_splitter.addWidget(abp_bottom)

        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_title)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addWidget(self.abp_warning_banner)
        abp_layout.addWidget(abp_splitter, stretch=1)

    @property
    def abp_plan(self) -> abpFloorPlan:
        return self.abp__plan

    def abp_set_content(self, abp_plan: abpFloorPlan, abp_scenario: abpScenario | None) -> None:
        self.abp__plan = abp_plan
        self.abp__scenario = abp_scenario
        self.abp__refresh()

    def abp_set_category(self, abp_row: int, abp_category: str) -> None:
        if 0 <= abp_row < len(self.abp__plan.abp_rooms):
            self.abp_set_room_type(abp_row, self.abp__plan.abp_rooms[abp_row].abp_use, abp_category)

    def abp_set_room_type(self, abp_row: int, abp_use: abpUseType, abp_category: str) -> None:
        abp_rooms = list(self.abp__plan.abp_rooms)
        if not 0 <= abp_row < len(abp_rooms) or (
            abp_rooms[abp_row].abp_use,
            abp_rooms[abp_row].abp_category,
        ) == (abp_use, abp_category):
            return
        abp_rooms[abp_row] = dataclasses.replace(
            abp_rooms[abp_row], abp_use=abp_use, abp_category=abp_category
        )
        self.abp__plan = dataclasses.replace(self.abp__plan, abp_rooms=tuple(abp_rooms))
        self.abp_plan_changed.emit(self.abp__plan)
        self.abp__refresh()

    def abp__refresh(self) -> None:
        abp_t = self.abp__texts
        self.abp_table.clear()
        self.abp_observations.clear()
        self.abp_evaluation = None
        try:
            abp_evaluation = self.abp__norms.abp_evaluate(self.abp__plan, self.abp__scenario)
        except abpUserFacingError as abp_exc:
            self.abp_table.setRowCount(0)
            self.abp_total_label.setText("")
            self.abp_warning_banner.abp_show_message(abp_exc.abp_message, "warning")
            return
        self.abp_evaluation = abp_evaluation
        abp_headers = [
            abp_t.abp_column_name,
            abp_t.abp_column_category,
            abp_t.abp_column_area,
            abp_t.abp_column_capacity,
            abp_t.abp_column_occupants,
            abp_t.abp_column_travel,
            abp_t.abp_column_status,
        ]
        self.abp_table.setColumnCount(len(abp_headers))
        self.abp_table.setHorizontalHeaderLabels(abp_headers)
        self.abp_table.setRowCount(len(abp_evaluation.abp_capacities))
        abp_travel = {
            abp_r.abp_room_name: abp_r.abp_max_distance_m for abp_r in abp_evaluation.abp_routes
        }
        for abp_row, (abp_room, abp_cap) in enumerate(
            zip(self.abp__plan.abp_rooms, abp_evaluation.abp_capacities, strict=True)
        ):
            abp_combo = abp_room_type_combo(
                self.abp__norms,
                abp_room,
                abp_room.abp_use,
                functools.partial(self.abp_set_room_type, abp_row),
            )
            self.abp_table.setCellWidget(abp_row, abp_COL_CATEGORY, abp_combo)
            if abp_cap.abp_capacity is None:
                abp_status = abp_t.abp_status_no_capacity
            else:
                abp_status = (
                    abp_t.abp_status_exceeded if abp_cap.abp_exceeded else abp_t.abp_status_ok
                )
            abp_values = {
                abp_COL_NAME: abp_cap.abp_room_name,
                abp_COL_AREA: f"{abp_cap.abp_area_m2:.1f}",
                abp_COL_CAPACITY: "—"
                if abp_cap.abp_capacity is None
                else str(abp_cap.abp_capacity),
                abp_COL_OCCUPANTS: str(abp_cap.abp_occupants),
                abp_COL_TRAVEL: f"{abp_travel[abp_cap.abp_room_name]:.1f}"
                if abp_cap.abp_room_name in abp_travel
                else "—",
                abp_COL_STATUS: abp_status,
            }
            for abp_col, abp_text in abp_values.items():
                abp_item = QTableWidgetItem(abp_text)
                if abp_cap.abp_exceeded:
                    abp_item.setBackground(abp_EXCEEDED_COLOR)
                self.abp_table.setItem(abp_row, abp_col, abp_item)
        self.abp_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.abp_total_label.setText(
            abp_t.abp_total.format(
                capacity=abp_evaluation.abp_total_capacity,
                occupants=abp_evaluation.abp_total_occupants,
            )
        )
        abp_unverified = len(abp_evaluation.abp_unverified_rules)
        if abp_unverified:
            self.abp_warning_banner.abp_show_message(
                abp_t.abp_unverified_warning.format(count=abp_unverified),
                "warning",
                abp_action_text=abp_t.abp_verify_rules,
                abp_action=self.abp_verify_requested.emit,
            )
        else:
            self.abp_warning_banner.abp_dismiss()
        if not abp_evaluation.abp_observations:
            self.abp_observations.addItem(abp_t.abp_no_observations)
        for abp_i, abp_obs in enumerate(abp_evaluation.abp_observations, start=1):
            abp_citation = f"{abp_obs.abp_norm}, {abp_obs.abp_article}" + (
                "" if abp_obs.abp_verified else abp_t.abp_unverified_tag
            )
            abp_entry = QListWidgetItem(
                f"{abp_i}. "
                + abp_t.abp_observation.format(
                    description=abp_obs.abp_description, citation=abp_citation
                )
            )
            abp_entry.setToolTip(abp_obs.abp_recommendation)
            self.abp_observations.addItem(abp_entry)
