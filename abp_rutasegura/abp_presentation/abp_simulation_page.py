from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_simulation_service import (
    abp_BASE_SCENARIO,
    abpSimulationRun,
    abpSimulationService,
)
from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpRoomRoute
from abp_rutasegura.abp_domain.abp_scenario import abp_MAX_RUNS, abpManualRoute, abpScenario
from abp_rutasegura.abp_presentation.abp_qt_support import abpBackgroundJob
from abp_rutasegura.abp_presentation.abp_route_editing import (
    abpEditableRoute,
    abpRouteKey,
    abpRoutePanel,
)
from abp_rutasegura.abp_presentation.abp_scenario_dialogs import (
    abpComparisonDialog,
    abpScenarioChoice,
    abpScenarioDialog,
)
from abp_rutasegura.abp_presentation.abp_simulation_viewer import (
    abp_format_time,
    abpSimulationViewer,
)
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary, abp_WARNING
from abp_rutasegura.abp_presentation.abp_widgets import (
    abp_muted,
    abp_page_help,
    abp_page_title,
    abp_section_title,
    abpBanner,
    abpMetricCard,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpScenarioTexts, abpSimulationTexts

abpImage = npt.NDArray[np.uint8]
abp_DROP_M = 2.5


class abpSimulationPage(QWidget):
    abp_error = Signal(str)
    abp_run_finished = Signal(object)
    abp_run_shown = Signal(object)
    abp_refresh_requested = Signal()
    abp_scenario_changed = Signal(object)

    def __init__(
        self,
        abp_simulations: abpSimulationService,
        abp_texts: abpSimulationTexts = abp_TEXTS.abp_simulation,
        abp_scenario_texts: abpScenarioTexts = abp_TEXTS.abp_scenarios,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__simulations = abp_simulations
        self.abp__texts = abp_texts
        self.abp__stexts = abp_scenario_texts
        self.abp__project_id: int | None = None
        self.abp__floors: list[tuple[abpFloorPlan, abpImage | None]] = []
        self.abp__scenario = abpScenario(abp_BASE_SCENARIO, 0)
        self.abp__variants: list[abpScenario] = []
        self.abp__current = abp_BASE_SCENARIO
        self.abp__run: abpSimulationRun | None = None
        self.abp_job: abpBackgroundJob | None = None

        abp_st = abp_scenario_texts
        self.abp_scenario_combo = QComboBox()
        self.abp_scenario_combo.currentTextChanged.connect(self.abp__on_scenario_selected)
        self.abp_new_button = QPushButton(abp_st.abp_new)
        self.abp_new_button.clicked.connect(self.abp_ask_new_variant)
        self.abp_edit_button = QPushButton(abp_st.abp_edit)
        self.abp_edit_button.clicked.connect(self.abp_ask_edit_variant)
        self.abp_delete_button = QPushButton(abp_st.abp_delete)
        self.abp_delete_button.clicked.connect(self.abp_ask_delete_variant)
        self.abp_compare_button = QPushButton(abp_st.abp_compare)
        self.abp_compare_button.clicked.connect(self.abp_open_comparison)

        self.abp_seed_spin = QSpinBox()
        self.abp_seed_spin.setRange(0, 2_000_000_000)
        self.abp_seed_spin.valueChanged.connect(self.abp__on_seed)
        self.abp_runs_spin = QSpinBox()
        self.abp_runs_spin.setRange(1, abp_MAX_RUNS)
        self.abp_runs_spin.setToolTip(abp_texts.abp_runs_tip)
        self.abp_runs_spin.valueChanged.connect(self.abp__on_runs)
        self.abp_settings_label = abp_muted()
        self.abp_run_button = abp_set_primary(QPushButton(abp_texts.abp_run))
        self.abp_refresh_button = QPushButton(abp_texts.abp_refresh)
        self.abp_refresh_button.setToolTip(abp_texts.abp_refresh_tip)
        self.abp_refresh_button.clicked.connect(self.abp_refresh_requested)
        self.abp_outdated_banner = abpBanner(abp_closable=False)
        self.abp_run_button.clicked.connect(self.abp_start_simulation)
        self.abp_routes_button = QPushButton(abp_TEXTS.abp_routes.abp_button)
        self.abp_routes_button.setToolTip(abp_TEXTS.abp_routes.abp_tip)
        self.abp_routes_button.setCheckable(True)
        self.abp_routes_button.toggled.connect(self.abp_set_route_editing)
        self.abp_cancel_button = QPushButton(abp_texts.abp_cancel)
        self.abp_cancel_button.clicked.connect(self.abp_cancel_simulation)
        self.abp_cancel_button.setEnabled(False)
        self.abp_progress = QProgressBar()
        self.abp_progress.setRange(0, 100)
        self.abp_progress.setVisible(False)
        self.abp_status_label = QLabel()
        self.abp_pending_label = QLabel()
        self.abp_pending_label.setWordWrap(True)
        self.abp_pending_label.setStyleSheet(f"color: {abp_WARNING};")

        self.abp_viewer = abpSimulationViewer(abp_texts)
        self.abp_total_card = abpMetricCard(abp_texts.abp_card_total)
        self.abp_ninety_card = abpMetricCard(abp_texts.abp_card_ninety)
        self.abp_evacuated_card = abpMetricCard(abp_texts.abp_card_evacuated)
        abp_cards = QGridLayout()
        abp_cards.setSpacing(8)
        abp_cards.addWidget(self.abp_total_card, 0, 0, 1, 2)
        abp_cards.addWidget(self.abp_ninety_card, 1, 0)
        abp_cards.addWidget(self.abp_evacuated_card, 1, 1)
        self.abp_summary_label = QLabel(abp_texts.abp_no_run)
        self.abp_summary_label.setWordWrap(True)
        self.abp_bottleneck_list = QListWidget()
        self.abp_bottleneck_list.setWordWrap(True)
        self.abp_bottleneck_list.setSpacing(2)
        abp_provisional = abp_muted(abp_texts.abp_provisional)

        abp_panel = QWidget()
        abp_panel_layout = QVBoxLayout(abp_panel)
        abp_panel_layout.setContentsMargins(6, 0, 0, 0)
        abp_panel_layout.addWidget(abp_section_title(abp_texts.abp_results_title))
        abp_panel_layout.addLayout(abp_cards)
        abp_panel_layout.addWidget(self.abp_summary_label)
        abp_panel_layout.addWidget(abp_section_title(abp_texts.abp_bottlenecks_title))
        abp_panel_layout.addWidget(self.abp_bottleneck_list, stretch=1)
        abp_panel_layout.addWidget(abp_provisional)
        self.abp_route_panel = abpRoutePanel()
        self.abp_route_panel.abp_selected.connect(self.abp_viewer.abp_route_layer.abp_select)
        self.abp_route_panel.abp_exit_chosen.connect(self.abp_set_route_exit)
        self.abp_route_panel.abp_reset_requested.connect(self.abp_reset_route)
        self.abp_route_panel.abp_reset_all_requested.connect(self.abp_reset_all_routes)
        self.abp_route_panel.abp_undo_requested.connect(self.abp_undo_route)
        self.abp_route_panel.abp_finished.connect(lambda: self.abp_routes_button.setChecked(False))
        abp_layer = self.abp_viewer.abp_route_layer
        abp_layer.abp_selected.connect(self.abp_route_panel.abp_select)
        abp_layer.abp_edited.connect(self.abp_set_route_points)
        abp_layer.abp_end_dropped.connect(self.abp_drop_route_end)
        abp_layer.abp_reset_requested.connect(self.abp_reset_route)
        abp_layer.abp_place_picked.connect(self.abp_pick_room)
        self.abp_viewer.abp_floor_shown.connect(lambda abp__level: self.abp__fill_routes())
        self.abp__shown_routes: tuple[abpRoomRoute, ...] = ()
        self.abp__route_history: list[abpScenario] = []
        self.abp_side_stack = QStackedWidget()
        self.abp_side_stack.addWidget(abp_panel)
        self.abp_side_stack.addWidget(self.abp_route_panel)
        abp_splitter = QSplitter()
        abp_splitter.addWidget(self.abp_viewer)
        abp_splitter.addWidget(self.abp_side_stack)
        abp_splitter.setSizes([760, 380])

        abp_scenario_row = QHBoxLayout()
        abp_scenario_row.addWidget(QLabel(abp_st.abp_label))
        abp_scenario_row.addWidget(self.abp_scenario_combo, stretch=1)
        for abp_button in (
            self.abp_new_button,
            self.abp_edit_button,
            self.abp_delete_button,
            self.abp_compare_button,
        ):
            abp_scenario_row.addWidget(abp_button)
        abp_row = QHBoxLayout()
        abp_row.addWidget(QLabel(abp_texts.abp_seed))
        abp_row.addWidget(self.abp_seed_spin)
        abp_row.addWidget(QLabel(abp_texts.abp_runs))
        abp_row.addWidget(self.abp_runs_spin)
        abp_row.addWidget(self.abp_run_button)
        abp_row.addWidget(self.abp_refresh_button)
        abp_row.addWidget(self.abp_routes_button)
        abp_row.addWidget(self.abp_cancel_button)
        abp_row.addWidget(self.abp_progress, stretch=1)
        abp_row.addWidget(self.abp_status_label)
        abp_row.addStretch(1)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_page_title(abp_texts.abp_title))
        abp_layout.addWidget(abp_page_help(abp_texts.abp_help))
        abp_layout.addLayout(abp_scenario_row)
        abp_layout.addLayout(abp_row)
        abp_layout.addWidget(self.abp_pending_label)
        abp_layout.addWidget(self.abp_outdated_banner)
        abp_layout.addWidget(self.abp_settings_label)
        abp_layout.addWidget(abp_splitter, stretch=1)

    @property
    def abp_current_run(self) -> abpSimulationRun | None:
        return self.abp__run

    @property
    def abp_current_scenario(self) -> abpScenario:
        if self.abp__current == abp_BASE_SCENARIO:
            return self.abp__scenario
        return next(
            (abp_v for abp_v in self.abp__variants if abp_v.abp_name == self.abp__current),
            self.abp__scenario,
        )

    @property
    def abp_scenario_names(self) -> list[str]:
        return [
            self.abp_scenario_combo.itemText(abp_i)
            for abp_i in range(self.abp_scenario_combo.count())
        ]

    def abp_set_content(
        self,
        abp_project_id: int,
        abp_floors: list[tuple[abpFloorPlan, abpImage | None]],
        abp_scenario: abpScenario,
    ) -> None:
        if self.abp__project_id != abp_project_id:
            self.abp__current = abp_BASE_SCENARIO
        self.abp__project_id = abp_project_id
        self.abp__floors = sorted(abp_floors, key=lambda abp_f: abp_f[0].abp_level)
        self.abp__scenario = abp_scenario
        self.abp_outdated_banner.abp_dismiss()
        abp_pending = sum(
            1
            for abp_plan in self.abp_plans
            for abp_e in abp_plan.abp_exits
            if not abp_e.abp_confirmed
        )
        abp_lines = (
            [self.abp__texts.abp_pending_exits.format(count=abp_pending)] if abp_pending else []
        )
        abp_lowest = self.abp_plans[0].abp_stairs if self.abp__floors else ()
        abp_automatic = sum(
            1
            for abp_s in abp_lowest
            if abp_s.abp_confirmed and abp_s.abp_use is abpStairUse.abp_AUTO
        )
        if abp_automatic:
            abp_lines.append(self.abp__texts.abp_automatic_stairs.format(count=abp_automatic))
        self.abp_pending_label.setText("\n".join(abp_lines))
        self.abp_pending_label.setVisible(bool(abp_lines))
        self.abp__route_history.clear()
        self.abp_viewer.abp_set_floors(self.abp__floors)
        self.abp__reload_variants()
        self.abp__refresh_routes()

    @property
    def abp_plans(self) -> list[abpFloorPlan]:
        return [abp_plan for abp_plan, _ in self.abp__floors]

    def abp__reload_variants(self) -> None:
        if self.abp__project_id is None:
            return
        self.abp__variants = self.abp__simulations.abp_list_scenarios(self.abp__project_id)[1:]
        abp_names = [abp_BASE_SCENARIO, *(abp_v.abp_name for abp_v in self.abp__variants)]
        if self.abp__current not in abp_names:
            self.abp__current = abp_BASE_SCENARIO
        self.abp_scenario_combo.blockSignals(True)
        self.abp_scenario_combo.clear()
        self.abp_scenario_combo.addItems(abp_names)
        self.abp_scenario_combo.setCurrentText(self.abp__current)
        self.abp_scenario_combo.blockSignals(False)
        self.abp__select(self.abp__current)

    def abp__on_scenario_selected(self, abp_name: str) -> None:
        if abp_name and abp_name != self.abp__current:
            self.abp__select(abp_name)

    def abp__select(self, abp_name: str) -> None:
        if abp_name != self.abp__current:
            self.abp__route_history.clear()
        self.abp__current = abp_name
        abp_is_base = abp_name == abp_BASE_SCENARIO
        self.abp_edit_button.setEnabled(not abp_is_base)
        self.abp_delete_button.setEnabled(not abp_is_base)
        abp_current = self.abp_current_scenario
        for abp_spin, abp_value in (
            (self.abp_seed_spin, abp_current.abp_seed),
            (self.abp_runs_spin, abp_current.abp_runs),
        ):
            abp_spin.blockSignals(True)
            abp_spin.setValue(abp_value)
            abp_spin.blockSignals(False)
        abp_factors = (abp_current.abp_reaction_factor, abp_current.abp_speed_factor)
        self.abp_settings_label.setText(
            ""
            if abp_factors == (1.0, 1.0)
            else self.abp__texts.abp_scenario_settings.format(
                reaction=abp_factors[0], speed=abp_factors[1]
            )
        )
        self.abp_settings_label.setVisible(abp_factors != (1.0, 1.0))
        if self.abp__project_id is not None:
            self.abp_set_run(self.abp__simulations.abp_last_run(self.abp__project_id, abp_name))
        self.abp__refresh_routes()

    def abp__refresh_routes(self) -> None:
        if not self.abp__floors:
            return
        try:
            abp_routes = self.abp__simulations.abp_routes(self.abp_plans, self.abp_current_scenario)
        except abpUserFacingError:
            abp_routes = ()
        self.abp__shown_routes = abp_routes
        self.abp_viewer.abp_set_routes(abp_routes)
        self.abp__fill_routes()

    @property
    def abp_editing_routes(self) -> bool:
        return self.abp_viewer.abp_route_layer.abp_active

    def abp_set_route_editing(self, abp_editing: bool) -> None:
        if self.abp_routes_button.isChecked() != abp_editing:
            self.abp_routes_button.setChecked(abp_editing)
            return
        self.abp_viewer.abp_pause()
        if abp_editing:
            self.abp_viewer.abp_routes_check.setChecked(True)
        self.abp_viewer.abp_routes_check.setEnabled(not abp_editing)
        self.abp_viewer.abp_route_layer.abp_set_active(abp_editing)
        self.abp_side_stack.setCurrentIndex(1 if abp_editing else 0)
        self.abp__fill_routes()

    def abp__fill_routes(self) -> None:
        if not self.abp_editing_routes or not self.abp__floors:
            return
        abp_level = self.abp_viewer.abp_level
        abp_scenario = self.abp_current_scenario
        abp_scale = self.abp__plan_at(abp_level).abp_scale_m_per_px or 1.0
        abp_shown = {
            (abp_r.abp_level, abp_r.abp_from_stair, abp_r.abp_room_name): abp_r
            for abp_r in self.abp__shown_routes
        }
        abp_sources = [
            abp_s
            for abp_s in self.abp__simulations.abp_route_sources(self.abp_plans, abp_scenario)
            if abp_s.abp_level == abp_level
        ]
        abp_sources.sort(key=lambda abp_s: -abp_s.abp_people)
        self.abp_route_panel.abp_set_sources(
            abp_sources,
            [abp_r for abp_r in abp_scenario.abp_routes if abp_r.abp_level == abp_level],
            {abp_key: abp_r.abp_target_name for abp_key, abp_r in abp_shown.items()},
            abp_can_undo=bool(self.abp__route_history),
        )
        abp_manual = {abp_r.abp_key: abp_r for abp_r in abp_scenario.abp_routes}
        self.abp_viewer.abp_route_layer.abp_set_routes(
            [
                abpEditableRoute(
                    abp_key,
                    tuple(
                        QPointF(abp_p.abp_x / abp_scale, abp_p.abp_y / abp_scale)
                        for abp_p in abp_r.abp_path_m
                    ),
                    tuple(
                        QPointF(abp_p.abp_x, abp_p.abp_y)
                        for abp_p in abp_manual[abp_key].abp_waypoints
                    )
                    if abp_key in abp_manual
                    else (),
                )
                for abp_key, abp_r in abp_shown.items()
                if abp_r.abp_level == abp_level
            ]
        )

    def abp__plan_at(self, abp_level: int) -> abpFloorPlan:
        return next(
            (abp_p for abp_p in self.abp_plans if abp_p.abp_level == abp_level),
            abpFloorPlan(abp_level=abp_level),
        )

    def abp__route(self, abp_key: abpRouteKey) -> abpManualRoute:
        abp_level, abp_from_stair, abp_source = abp_key
        abp_found = self.abp_current_scenario.abp_route_of(
            abp_level, abp_source, abp_from_stair=abp_from_stair
        )
        return abp_found or abpManualRoute(abp_source, abp_level, abp_from_stair=abp_from_stair)

    def abp_set_route_exit(self, abp_key: abpRouteKey, abp_exit_name: str) -> None:
        self.abp_viewer.abp_route_layer.abp_select(abp_key)
        self.abp__change_route(
            dataclasses.replace(self.abp__route(abp_key), abp_exit_name=abp_exit_name)
        )

    def abp_set_route_points(self, abp_key: abpRouteKey, abp_points: Sequence[QPointF]) -> None:
        abp_route = self.abp__route(abp_key)
        abp_goal = abp_route.abp_exit_name
        if not abp_goal and abp_points:
            abp_goal = next(
                (
                    abp_r.abp_target_name
                    for abp_r in self.abp__shown_routes
                    if (abp_r.abp_level, abp_r.abp_from_stair, abp_r.abp_room_name) == abp_key
                ),
                "",
            )
        self.abp__change_route(
            dataclasses.replace(
                abp_route,
                abp_exit_name=abp_goal,
                abp_waypoints=tuple(
                    abpPoint(round(abp_p.x(), 1), round(abp_p.y(), 1)) for abp_p in abp_points
                ),
            )
        )

    def abp_drop_route_end(self, abp_key: abpRouteKey, abp_where: QPointF) -> None:
        abp_plan = self.abp__plan_at(abp_key[0])
        abp_source = next(
            (
                abp_s
                for abp_s in self.abp__simulations.abp_route_sources(
                    self.abp_plans, self.abp_current_scenario
                )
                if abp_s.abp_key == abp_key
            ),
            None,
        )
        abp_places = [
            (abp_e.abp_name, abp_e.abp_segment.abp_midpoint) for abp_e in abp_plan.abp_exits
        ]
        abp_places += [
            (abp_z.abp_name, abp_z.abp_area.abp_centroid) for abp_z in abp_plan.abp_safe_zones
        ]
        abp_places += [
            (abp_s.abp_name, abp_s.abp_area.abp_centroid) for abp_s in abp_plan.abp_stairs
        ]
        abp_point = abpPoint(abp_where.x(), abp_where.y())
        abp_near = [
            (abp_p.abp_distance_to(abp_point), abp_name)
            for abp_name, abp_p in abp_places
            if abp_source is not None and abp_name in abp_source.abp_goals
        ]
        abp_reach = abp_DROP_M / (abp_plan.abp_scale_m_per_px or 1.0)
        if not abp_near or min(abp_near)[0] > abp_reach:
            self.abp_route_panel.abp_message_label.setText(abp_TEXTS.abp_routes.abp_no_exit_there)
            return
        self.abp_set_route_exit(abp_key, min(abp_near)[1])

    def abp_reset_route(self, abp_key: abpRouteKey) -> None:
        abp_level, abp_from_stair, abp_source = abp_key
        self.abp__change_route(abpManualRoute(abp_source, abp_level, abp_from_stair=abp_from_stair))

    def abp_reset_all_routes(self) -> None:
        if self.abp_current_scenario.abp_routes:
            self.abp__apply_routes(dataclasses.replace(self.abp_current_scenario, abp_routes=()))

    def abp_undo_route(self) -> None:
        if self.abp__route_history:
            abp_before = self.abp__route_history.pop()
            self.abp__store_routes(
                dataclasses.replace(self.abp_current_scenario, abp_routes=abp_before.abp_routes)
            )

    def abp_pick_room(self, abp_where: QPointF) -> None:
        abp_polygon_point = QPointF(abp_where)
        for abp_room in self.abp__plan_at(self.abp_viewer.abp_level).abp_rooms:
            abp_area = QPolygonF(
                [QPointF(abp_v.abp_x, abp_v.abp_y) for abp_v in abp_room.abp_area.abp_vertices]
            )
            if abp_area.containsPoint(abp_polygon_point, Qt.FillRule.OddEvenFill):
                self.abp_viewer.abp_route_layer.abp_select(
                    (self.abp_viewer.abp_level, False, abp_room.abp_name)
                )
                return

    def abp__change_route(self, abp_route: abpManualRoute) -> None:
        abp_scenario = self.abp_current_scenario
        abp_changed = abp_scenario.abp_with_route(abp_route)
        if abp_changed == abp_scenario:
            return
        abp_lowest = min(abp_p.abp_level for abp_p in self.abp_plans)
        try:
            self.abp__simulations.abp_check_route(
                self.abp__plan_at(abp_route.abp_level),
                abp_changed,
                abp_route,
                abp_upper_floor=abp_route.abp_level != abp_lowest,
            )
        except abpUserFacingError as abp_exc:
            self.abp_route_panel.abp_message_label.setText(abp_exc.abp_message)
            self.abp__fill_routes()
            return
        self.abp__apply_routes(abp_changed)

    def abp__apply_routes(self, abp_changed: abpScenario) -> None:
        self.abp__route_history.append(self.abp_current_scenario)
        self.abp__store_routes(abp_changed)

    def abp__store_routes(self, abp_changed: abpScenario) -> None:
        self.abp__update_current(abp_changed)
        self.abp_route_panel.abp_message_label.setText(abp_TEXTS.abp_routes.abp_pending)
        self.abp__refresh_routes()
        self.abp__check_outdated()

    def abp_select_scenario(self, abp_name: str) -> None:
        self.abp_scenario_combo.setCurrentText(abp_name)

    def abp__exit_names(self) -> list[str]:
        abp_exits = [
            abp_e.abp_name
            for abp_plan in self.abp_plans
            for abp_e in abp_plan.abp_exits
            if abp_e.abp_confirmed
        ]
        abp_zones = [
            abp_z.abp_name
            for abp_plan in self.abp_plans
            for abp_z in abp_plan.abp_safe_zones
            if abp_z.abp_name
        ]
        return abp_exits + abp_zones

    def abp_create_variant(self, abp_choice: abpScenarioChoice) -> bool:
        return self.abp__save_variant(abp_choice, None)

    def abp_update_current_variant(self, abp_choice: abpScenarioChoice) -> bool:
        if self.abp__current == abp_BASE_SCENARIO:
            return False
        return self.abp__save_variant(abp_choice, self.abp__current)

    def abp__save_variant(self, abp_choice: abpScenarioChoice, abp_previous: str | None) -> bool:
        if self.abp__project_id is None:
            return False
        try:
            abp_variant = self.abp__simulations.abp_save_variant(
                self.abp__project_id,
                abp_choice.abp_name,
                self.abp__scenario,
                abp_choice.abp_percent,
                abp_choice.abp_blocked,
                abp_previous_name=abp_previous,
                abp_description=abp_choice.abp_description,
                abp_reaction_factor=abp_choice.abp_reaction_factor,
                abp_speed_factor=abp_choice.abp_speed_factor,
                abp_runs=abp_choice.abp_runs,
            )
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return False
        self.abp__current = abp_variant.abp_name
        self.abp__reload_variants()
        return True

    def abp_delete_current_variant(self) -> None:
        if self.abp__project_id is None or self.abp__current == abp_BASE_SCENARIO:
            return
        self.abp__simulations.abp_delete_scenario(self.abp__project_id, self.abp__current)
        self.abp__current = abp_BASE_SCENARIO
        self.abp__reload_variants()

    def abp_ask_new_variant(self) -> None:
        abp_dialog = abpScenarioDialog(
            self.abp__exit_names(),
            self.abp__scenario.abp_total_occupants,
            abp_texts=self.abp__stexts,
            abp_parent=self,
        )
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            self.abp_create_variant(abp_dialog.abp_choice())

    def abp_ask_edit_variant(self) -> None:
        abp_variant = self.abp_current_scenario
        if abp_variant.abp_name == abp_BASE_SCENARIO:
            return
        abp_base_total = self.abp__scenario.abp_total_occupants
        abp_percent = (
            round(100 * abp_variant.abp_total_occupants / abp_base_total) if abp_base_total else 100
        )
        abp_dialog = abpScenarioDialog(
            self.abp__exit_names(),
            abp_base_total,
            abp_name=abp_variant.abp_name,
            abp_percent=max(10, abp_percent),
            abp_blocked=abp_variant.abp_blocked_exits,
            abp_editing=True,
            abp_description=abp_variant.abp_description,
            abp_reaction_factor=abp_variant.abp_reaction_factor,
            abp_speed_factor=abp_variant.abp_speed_factor,
            abp_runs=abp_variant.abp_runs,
            abp_texts=self.abp__stexts,
            abp_parent=self,
        )
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            self.abp_update_current_variant(abp_dialog.abp_choice())

    def abp_ask_delete_variant(self) -> None:
        if self.abp__current == abp_BASE_SCENARIO:
            return
        abp_answer = QMessageBox.question(
            self,
            self.abp__stexts.abp_delete,
            self.abp__stexts.abp_confirm_delete.format(name=self.abp__current),
        )
        if abp_answer == QMessageBox.StandardButton.Yes:
            self.abp_delete_current_variant()

    def abp_comparison_dialog(self) -> abpComparisonDialog | None:
        if self.abp__project_id is None:
            return None
        abp_project_id = self.abp__project_id
        return abpComparisonDialog(
            [self.abp__scenario, *self.abp__variants],
            lambda abp_name: self.abp__simulations.abp_last_run(abp_project_id, abp_name),
            self.abp__floors,
            abp_texts=self.abp__stexts,
            abp_sim_texts=self.abp__texts,
            abp_parent=self,
        )

    def abp_open_comparison(self) -> None:
        abp_dialog = self.abp_comparison_dialog()
        if abp_dialog is not None:
            abp_dialog.exec()

    def abp_set_run(self, abp_run: abpSimulationRun | None) -> None:
        self.abp__run = abp_run
        self.abp__show_run(abp_run)
        self.abp__check_outdated()
        self.abp_run_shown.emit(abp_run)

    @property
    def abp_is_outdated(self) -> bool:
        return not self.abp_outdated_banner.isHidden()

    def abp__check_outdated(self) -> None:
        abp_run = self.abp__run
        if abp_run is None or not self.abp__floors:
            self.abp_outdated_banner.abp_dismiss()
            return
        try:
            abp_outdated = self.abp__simulations.abp_is_outdated(
                abp_run, self.abp_plans, self.abp_current_scenario
            )
        except abpUserFacingError:
            abp_outdated = False
        if abp_outdated:
            self.abp_outdated_banner.abp_show_message(
                self.abp__texts.abp_outdated,
                "warning",
                abp_action_text=self.abp__texts.abp_resimulate,
                abp_action=self.abp_start_simulation,
            )
        else:
            self.abp_outdated_banner.abp_dismiss()

    def abp_start_simulation(self) -> None:
        if self.abp__project_id is None or (self.abp_job is not None and self.abp_job.abp_running):
            return
        abp_project_id, abp_plan, abp_scenario = (
            self.abp__project_id,
            self.abp_plans,
            self.abp_current_scenario,
        )
        abp_simulations = self.abp__simulations

        def abp_work(
            abp_report: Callable[[float], None], abp_should_cancel: Callable[[], bool]
        ) -> object:
            return abp_simulations.abp_run(
                abp_project_id,
                abp_plan,
                abp_scenario,
                abp_progress=abp_report,
                abp_should_cancel=abp_should_cancel,
            )

        self.abp_job = abpBackgroundJob(abp_work, self)
        self.abp_job.abp_progress.connect(self.abp__on_progress)
        self.abp_job.abp_done.connect(self.abp__on_done)
        self.abp_job.abp_failed.connect(self.abp__on_failed)
        self.abp_job.abp_cancelled.connect(self.abp__on_cancelled)
        self.abp__set_running(True)
        self.abp_job.abp_start()

    def abp_cancel_simulation(self) -> None:
        if self.abp_job is not None:
            self.abp_job.abp_cancel()

    def abp__on_progress(self, abp_fraction: float) -> None:
        abp_percent = 100 * abp_fraction
        self.abp_progress.setValue(round(abp_percent))
        abp_runs = self.abp_current_scenario.abp_runs
        abp_text = (
            self.abp__texts.abp_running_runs.format(runs=abp_runs, percent=abp_percent)
            if abp_runs > 1
            else self.abp__texts.abp_running.format(percent=abp_percent)
        )
        self.abp_status_label.setText(abp_text)

    def abp__on_done(self, abp_run: object) -> None:
        self.abp__set_running(False)
        self.abp_status_label.setText("")
        if isinstance(abp_run, abpSimulationRun):
            self.abp_set_run(abp_run)
            self.abp_viewer.abp_play()
            self.abp_run_finished.emit(abp_run)

    def abp__on_failed(self, abp_message: str) -> None:
        self.abp__set_running(False)
        self.abp_status_label.setText("")
        self.abp_error.emit(abp_message)

    def abp__on_cancelled(self) -> None:
        self.abp__set_running(False)
        self.abp_status_label.setText(self.abp__texts.abp_cancelled)

    def abp__set_running(self, abp_running: bool) -> None:
        self.abp_run_button.setEnabled(not abp_running)
        self.abp_refresh_button.setEnabled(not abp_running)
        if abp_running:
            self.abp_routes_button.setChecked(False)
        self.abp_routes_button.setEnabled(not abp_running)
        self.abp_seed_spin.setEnabled(not abp_running)
        self.abp_runs_spin.setEnabled(not abp_running)
        self.abp_scenario_combo.setEnabled(not abp_running)
        for abp_button in (self.abp_new_button, self.abp_compare_button):
            abp_button.setEnabled(not abp_running)
        abp_is_base = self.abp__current == abp_BASE_SCENARIO
        self.abp_edit_button.setEnabled(not abp_running and not abp_is_base)
        self.abp_delete_button.setEnabled(not abp_running and not abp_is_base)
        self.abp_cancel_button.setEnabled(abp_running)
        self.abp_progress.setVisible(abp_running)
        self.abp_progress.setValue(0)

    def abp__on_seed(self, abp_value: int) -> None:
        self.abp__update_current(dataclasses.replace(self.abp_current_scenario, abp_seed=abp_value))
        self.abp__check_outdated()

    def abp__on_runs(self, abp_value: int) -> None:
        self.abp__update_current(dataclasses.replace(self.abp_current_scenario, abp_runs=abp_value))
        self.abp__check_outdated()

    def abp__update_current(self, abp_variant: abpScenario) -> None:
        if self.abp__current == abp_BASE_SCENARIO:
            self.abp__scenario = abp_variant
            self.abp_scenario_changed.emit(self.abp__scenario)
            return
        self.abp__variants = [
            abp_variant if abp_v.abp_name == abp_variant.abp_name else abp_v
            for abp_v in self.abp__variants
        ]
        if self.abp__project_id is not None:
            try:
                self.abp__simulations.abp_save_scenario(self.abp__project_id, abp_variant)
            except abpUserFacingError as abp_exc:
                self.abp_error.emit(abp_exc.abp_message)

    def abp__show_run(self, abp_run: abpSimulationRun | None) -> None:
        self.abp_bottleneck_list.clear()
        abp_t = self.abp__texts
        if abp_run is None:
            self.abp_viewer.abp_set_run(None, None, 1.0)
            self.abp_summary_label.setText(abp_t.abp_no_run)
            for abp_card in (self.abp_total_card, self.abp_ninety_card, self.abp_evacuated_card):
                abp_card.abp_set_value("—")
            return
        abp_result = abp_run.abp_result
        self.abp_viewer.abp_set_run(
            abp_run.abp_trajectories, abp_result, abp_run.abp_scale_m_per_px
        )
        abp_left = abp_result.abp_agents_total - abp_result.abp_agents_evacuated
        abp_congestion = len(abp_run.abp_observations)
        if not abp_result.abp_completed:
            abp_kind, abp_note = "error", abp_t.abp_note_left.format(left=abp_left)
        elif abp_congestion:
            abp_kind, abp_note = "warning", abp_t.abp_note_congestion.format(count=abp_congestion)
        else:
            abp_kind, abp_note = "success", abp_t.abp_note_no_congestion
        abp_stats = abp_run.abp_statistics
        if abp_stats is not None and not abp_stats.abp_all_completed:
            abp_kind = "error"
        if abp_stats is not None:
            abp_note = abp_t.abp_note_p95.format(
                runs=abp_stats.abp_runs, p95=abp_format_time(abp_stats.abp_total_p95_s)
            )
            self.abp_total_card.abp_set_value(
                abp_format_time(abp_stats.abp_total_mean_s), abp_note, abp_kind
            )
        else:
            self.abp_total_card.abp_set_value(
                abp_format_time(abp_result.abp_total_time_s), abp_note, abp_kind
            )
        abp_ninety = abp_result.abp_time_to_evacuate(0.9)
        self.abp_ninety_card.abp_set_value(
            "—" if abp_ninety is None else abp_format_time(abp_ninety),
            abp_t.abp_note_ninety,
            "info",
        )
        self.abp_evacuated_card.abp_set_value(
            abp_t.abp_card_evacuated_value.format(
                done=abp_result.abp_agents_evacuated, total=abp_result.abp_agents_total
            ),
            abp_t.abp_note_all_out
            if abp_result.abp_completed
            else abp_t.abp_note_left.format(left=abp_left),
            "success" if abp_result.abp_completed else "error",
        )
        abp_lines = [
            abp_t.abp_total_time.format(time=abp_format_time(abp_result.abp_total_time_s)),
            abp_t.abp_per_exit_title + ":",
        ]
        abp_lines += [
            "  • " + abp_t.abp_per_exit.format(name=abp_n, time=abp_format_time(abp_s))
            for abp_n, abp_s in abp_result.abp_time_per_exit_s
        ]
        if not abp_result.abp_completed:
            abp_lines.append(
                abp_t.abp_incomplete.format(
                    time=abp_format_time(abp_result.abp_total_time_s), left=abp_left
                )
            )
        abp_floors = abp_run.abp_floor_clearance
        if abp_floors:
            abp_lines += ["", abp_t.abp_floors_title + ":"]
            abp_lowest = min(abp_f.abp_level for abp_f in abp_floors)
            for abp_floor in sorted(abp_floors, key=lambda abp_f: -abp_f.abp_level):
                abp_number = abp_floor.abp_level + 1
                if abp_floor.abp_cleared_s is None:
                    abp_text = abp_t.abp_floor_not_cleared.format(
                        number=abp_number, people=abp_floor.abp_people
                    )
                elif abp_floor.abp_level == abp_lowest:
                    abp_text = abp_t.abp_floor_lower.format(
                        number=abp_number,
                        people=abp_floor.abp_people,
                        time=abp_format_time(abp_floor.abp_cleared_s),
                    )
                else:
                    abp_text = abp_t.abp_floor_upper.format(
                        number=abp_number,
                        people=abp_floor.abp_people,
                        descended=abp_floor.abp_descended,
                        time=abp_format_time(abp_floor.abp_cleared_s),
                    )
                abp_lines.append("  • " + abp_text)
        if abp_stats is not None:
            abp_lines.append("")
            abp_lines.append(abp_t.abp_stats_title.format(runs=abp_stats.abp_runs) + ":")
            abp_lines.append(
                abp_t.abp_stats_line.format(
                    mean=abp_format_time(abp_stats.abp_total_mean_s),
                    std=abp_format_time(abp_stats.abp_total_std_s),
                    best=abp_format_time(abp_stats.abp_total_min_s),
                    worst=abp_format_time(abp_stats.abp_total_max_s),
                    p95=abp_format_time(abp_stats.abp_total_p95_s),
                    seed=abp_stats.abp_representative_seed,
                )
            )
            abp_failed = abp_stats.abp_completed.count(False)
            if abp_failed:
                abp_lines.append(
                    abp_t.abp_stats_incomplete.format(count=abp_failed, runs=abp_stats.abp_runs)
                )
        self.abp_summary_label.setText("\n".join(abp_lines))
        if not abp_run.abp_observations:
            self.abp_bottleneck_list.addItem(abp_t.abp_no_bottlenecks)
        for abp_rank, abp_observation in enumerate(abp_run.abp_observations, start=1):
            abp_item = QListWidgetItem(f"{abp_rank}. {abp_observation.abp_description}")
            abp_item.setToolTip(abp_observation.abp_recommendation)
            self.abp_bottleneck_list.addItem(abp_item)
