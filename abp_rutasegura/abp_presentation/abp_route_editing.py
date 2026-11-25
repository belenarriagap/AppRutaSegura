from __future__ import annotations

import functools
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_simulation_service import abpRouteSource
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView, abpTool
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted, abp_section_title, abp_set_cell
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpRouteTexts

abpRouteKey = tuple[int, bool, str]
abp_SELECTED_COLOR = "#e8710a"
abp_GRAB_PX = 11.0


@dataclass(frozen=True, slots=True)
class abpEditableRoute:
    abp_key: abpRouteKey
    abp_path: tuple[QPointF, ...]
    abp_waypoints: tuple[QPointF, ...] = ()


def abp__distance(abp_a: QPointF, abp_b: QPointF) -> float:
    return math.hypot(abp_a.x() - abp_b.x(), abp_a.y() - abp_b.y())


def abp_along(abp_path: Sequence[QPointF], abp_point: QPointF) -> tuple[float, float, QPointF]:
    abp_best = (math.inf, 0.0, QPointF(abp_point))
    abp_walked = 0.0
    for abp_a, abp_b in itertools.pairwise(abp_path):
        abp_length = abp__distance(abp_a, abp_b)
        abp_dx, abp_dy = abp_b.x() - abp_a.x(), abp_b.y() - abp_a.y()
        abp_t = 0.0
        if abp_length > 1e-9:
            abp_t = (
                (abp_point.x() - abp_a.x()) * abp_dx + (abp_point.y() - abp_a.y()) * abp_dy
            ) / abp_length**2
            abp_t = min(max(abp_t, 0.0), 1.0)
        abp_near = QPointF(abp_a.x() + abp_t * abp_dx, abp_a.y() + abp_t * abp_dy)
        abp_away = abp__distance(abp_near, abp_point)
        if abp_away < abp_best[0]:
            abp_best = (abp_away, abp_walked + abp_t * abp_length, abp_near)
        abp_walked += abp_length
    return abp_best


class abpRouteLayer(QObject):
    abp_selected = Signal(object)
    abp_edited = Signal(object, object)
    abp_end_dropped = Signal(object, QPointF)
    abp_reset_requested = Signal(object)
    abp_place_picked = Signal(QPointF)

    def __init__(
        self, abp_view: abpPlanView, abp_texts: abpRouteTexts = abp_TEXTS.abp_routes
    ) -> None:
        super().__init__(abp_view)
        self.abp__view = abp_view
        self.abp__texts = abp_texts
        self.abp__routes: dict[abpRouteKey, abpEditableRoute] = {}
        self.abp__key: abpRouteKey | None = None
        self.abp__grab: tuple[str, int] | None = None
        self.abp__items: list[QGraphicsItem] = []
        self.abp_active = False
        abp_view.abp_node_moved.connect(self.abp__on_moved)
        abp_view.abp_context_menu_requested.connect(self.abp__on_menu)
        abp_view.abp_double_clicked.connect(self.abp__on_double_click)

    @property
    def abp_key(self) -> abpRouteKey | None:
        return self.abp__key

    @property
    def abp_current(self) -> abpEditableRoute | None:
        return self.abp__routes.get(self.abp__key) if self.abp__key is not None else None

    def abp_set_active(self, abp_active: bool) -> None:
        self.abp_active = abp_active
        self.abp__view.abp_node_finder = self.abp_find if abp_active else None
        self.abp__view.abp_set_tool(abpTool.abp_SELECT if abp_active else abpTool.abp_NONE)
        if not abp_active:
            self.abp__key = None
        self.abp__draw()

    def abp_set_routes(self, abp_routes: Sequence[abpEditableRoute]) -> None:
        self.abp__routes = {
            abp_r.abp_key: abp_r for abp_r in abp_routes if len(abp_r.abp_path) >= 2
        }
        self.abp__draw()

    def abp_select(self, abp_key: abpRouteKey | None) -> None:
        if abp_key != self.abp__key:
            self.abp__key = abp_key
            self.abp__draw()
            if abp_key is not None:
                self.abp_selected.emit(abp_key)

    def abp_find(self, abp_pos: QPointF) -> tuple[QPointF, list[QPointF]] | None:
        abp_tol = self.abp__view.abp_scene_tolerance(abp_GRAB_PX)
        self.abp__grab = None
        abp_route = self.abp_current
        if abp_route is not None:
            abp_fixed = [abp_route.abp_path[0], *abp_route.abp_waypoints, abp_route.abp_path[-1]]
            for abp_i, abp_w in enumerate(abp_route.abp_waypoints):
                if abp__distance(abp_w, abp_pos) <= abp_tol:
                    self.abp__grab = ("move", abp_i)
                    return abp_w, [abp_fixed[abp_i], abp_fixed[abp_i + 2]]
            if abp__distance(abp_route.abp_path[-1], abp_pos) <= abp_tol:
                self.abp__grab = ("end", 0)
                return abp_route.abp_path[-1], [abp_fixed[-2]]
        abp_found = self.abp__route_at(abp_pos, abp_tol)
        if abp_found is None:
            return None
        self.abp_select(abp_found.abp_key)
        abp__away, abp_where, abp_near = abp_along(abp_found.abp_path, abp_pos)
        abp_index = sum(
            abp_along(abp_found.abp_path, abp_w)[1] < abp_where for abp_w in abp_found.abp_waypoints
        )
        self.abp__grab = ("insert", abp_index)
        abp_fixed = [abp_found.abp_path[0], *abp_found.abp_waypoints, abp_found.abp_path[-1]]
        return abp_near, [abp_fixed[abp_index], abp_fixed[abp_index + 1]]

    def abp__route_at(self, abp_pos: QPointF, abp_tol: float) -> abpEditableRoute | None:
        abp_near = [
            (
                abp_r.abp_key != self.abp__key,
                abp_along(abp_r.abp_path, abp_pos)[0],
                abp_r.abp_key,
                abp_r,
            )
            for abp_r in self.abp__routes.values()
            if abp_along(abp_r.abp_path, abp_pos)[0] <= abp_tol
        ]
        return min(abp_near, key=lambda abp_x: abp_x[:3])[3] if abp_near else None

    def abp__on_moved(self, abp__start: QPointF, abp_target: QPointF) -> None:
        abp_route, abp_grab = self.abp_current, self.abp__grab
        self.abp__grab = None
        if not self.abp_active or abp_route is None or abp_grab is None:
            return
        abp_kind, abp_index = abp_grab
        abp_points = list(abp_route.abp_waypoints)
        if abp_kind == "end":
            self.abp_end_dropped.emit(abp_route.abp_key, abp_target)
            return
        if abp_kind == "move":
            abp_points[abp_index] = abp_target
        else:
            abp_points.insert(abp_index, abp_target)
        self.abp_edited.emit(abp_route.abp_key, abp_points)

    def abp_remove_point(self, abp_index: int) -> None:
        abp_route = self.abp_current
        if abp_route is not None and 0 <= abp_index < len(abp_route.abp_waypoints):
            abp_points = list(abp_route.abp_waypoints)
            abp_points.pop(abp_index)
            self.abp_edited.emit(abp_route.abp_key, abp_points)

    def abp_menu_at(self, abp_pos: QPointF) -> QMenu | None:
        abp_tol = self.abp__view.abp_scene_tolerance(abp_GRAB_PX)
        abp_menu = QMenu(self.abp__view)
        abp_route = self.abp_current
        if abp_route is not None:
            for abp_i, abp_w in enumerate(abp_route.abp_waypoints):
                if abp__distance(abp_w, abp_pos) <= abp_tol:
                    abp_action = abp_menu.addAction(self.abp__texts.abp_remove_point)
                    abp_action.triggered.connect(
                        functools.partial(self.abp__call, self.abp_remove_point, abp_i)
                    )
                    break
        abp_found = self.abp__route_at(abp_pos, abp_tol)
        if abp_menu.isEmpty() and abp_found is None:
            return None
        abp_key = abp_found.abp_key if abp_found is not None else self.abp__key
        abp_reset = abp_menu.addAction(self.abp__texts.abp_reset)
        abp_reset.triggered.connect(lambda _=False: self.abp_reset_requested.emit(abp_key))
        return abp_menu

    @staticmethod
    def abp__call(
        abp_function: Callable[[int], None], abp_index: int, abp__checked: bool = False
    ) -> None:
        abp_function(abp_index)

    def abp__on_menu(self, abp_where: QPoint, abp_pos: QPointF) -> None:
        if not self.abp_active:
            return
        abp_menu = self.abp_menu_at(abp_pos)
        if abp_menu is not None:
            abp_menu.exec(abp_where)

    def abp__on_double_click(self, abp_pos: QPointF) -> None:
        if self.abp_active:
            self.abp_place_picked.emit(abp_pos)

    def abp__draw(self) -> None:
        abp_scene = self.abp__view.scene()
        for abp_item in self.abp__items:
            if abp_item.scene() is not None:
                abp_scene.removeItem(abp_item)
        self.abp__items = []
        abp_route = self.abp_current
        if not self.abp_active or abp_route is None:
            return
        abp_path = QPainterPath(abp_route.abp_path[0])
        for abp_p in abp_route.abp_path[1:]:
            abp_path.lineTo(abp_p)
        abp_line = QGraphicsPathItem(abp_path)
        abp_pen = QPen(QColor(abp_SELECTED_COLOR), 5)
        abp_pen.setCosmetic(True)
        abp_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        abp_line.setPen(abp_pen)
        abp_line.setZValue(60)
        self.abp__add(abp_line)
        for abp_w in abp_route.abp_waypoints:
            abp_dot = QGraphicsEllipseItem(-7, -7, 14, 14)
            self.abp__add_handle(abp_dot, abp_w, "#ffffff", self.abp__texts.abp_point_tip)
        abp_end = QGraphicsRectItem(-7, -7, 14, 14)
        self.abp__add_handle(
            abp_end, abp_route.abp_path[-1], abp_SELECTED_COLOR, self.abp__texts.abp_end_tip
        )

    def abp__add_handle(
        self,
        abp_item: QGraphicsEllipseItem | QGraphicsRectItem,
        abp_pos: QPointF,
        abp_fill: str,
        abp_tip: str,
    ) -> None:
        abp_pen = QPen(QColor(abp_SELECTED_COLOR), 3)
        abp_item.setPen(abp_pen)
        abp_item.setBrush(QBrush(QColor(abp_fill)))
        abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        abp_item.setPos(abp_pos)
        abp_item.setZValue(61)
        abp_item.setToolTip(abp_tip)
        self.abp__add(abp_item)

    def abp__add(self, abp_item: QGraphicsItem) -> None:
        self.abp__view.scene().addItem(abp_item)
        self.abp__items.append(abp_item)


class abpRoutePanel(QWidget):
    abp_selected = Signal(object)
    abp_exit_chosen = Signal(object, str)
    abp_reset_requested = Signal(object)
    abp_reset_all_requested = Signal()
    abp_undo_requested = Signal()
    abp_finished = Signal()

    def __init__(
        self, abp_texts: abpRouteTexts = abp_TEXTS.abp_routes, abp_parent: QWidget | None = None
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.abp__sources: list[abpRouteSource] = []
        self.abp__manual: set[abpRouteKey] = set()
        self.abp__filling = False
        self.abp_table = QTableWidget(0, 3)
        self.abp_table.setHorizontalHeaderLabels(list(abp_texts.abp_columns))
        self.abp_table.verticalHeader().setVisible(False)
        self.abp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.abp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.abp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        abp_header = self.abp_table.horizontalHeader()
        abp_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        abp_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.abp_table.currentCellChanged.connect(lambda abp_row, *_: self.abp__on_row(abp_row))
        self.abp_message_label = abp_muted()
        self.abp_undo_button = QPushButton(abp_texts.abp_undo)
        self.abp_undo_button.clicked.connect(self.abp_undo_requested)
        self.abp_reset_button = QPushButton(abp_texts.abp_reset)
        self.abp_reset_button.clicked.connect(self.abp__on_reset)
        self.abp_reset_all_button = QPushButton(abp_texts.abp_reset_all)
        self.abp_reset_all_button.clicked.connect(self.abp_reset_all_requested)
        self.abp_done_button = abp_set_primary(QPushButton(abp_texts.abp_done))
        self.abp_done_button.clicked.connect(self.abp_finished)
        abp_first = QHBoxLayout()
        abp_first.addWidget(self.abp_undo_button)
        abp_first.addWidget(self.abp_reset_button)
        abp_second = QHBoxLayout()
        abp_second.addWidget(self.abp_reset_all_button)
        abp_second.addWidget(self.abp_done_button)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(6, 0, 0, 0)
        abp_layout.addWidget(abp_section_title(abp_texts.abp_title))
        abp_layout.addWidget(abp_muted(abp_texts.abp_help))
        abp_layout.addWidget(self.abp_table, stretch=1)
        abp_layout.addWidget(self.abp_message_label)
        abp_layout.addLayout(abp_first)
        abp_layout.addLayout(abp_second)

    @property
    def abp_key(self) -> abpRouteKey | None:
        abp_row = self.abp_table.currentRow()
        return self.abp__sources[abp_row].abp_key if 0 <= abp_row < len(self.abp__sources) else None

    def abp_set_sources(
        self,
        abp_sources: Sequence[abpRouteSource],
        abp_routes: Sequence[abpManualRoute],
        abp_targets: dict[abpRouteKey, str],
        *,
        abp_can_undo: bool,
    ) -> None:
        abp_manual = {abp_r.abp_key: abp_r for abp_r in abp_routes}
        self.abp__manual = set(abp_manual)
        abp_key = self.abp_key
        self.abp__sources = list(abp_sources)
        self.abp__filling = True
        self.abp_table.setRowCount(len(self.abp__sources))
        for abp_row, abp_source in enumerate(self.abp__sources):
            abp_route = abp_manual.get(abp_source.abp_key)
            abp_label = abp_source.abp_name
            if abp_source.abp_from_stair:
                abp_label = self.abp__texts.abp_from_stair.format(name=abp_source.abp_name)
            elif abp_source.abp_people:
                abp_label = self.abp__texts.abp_room.format(
                    name=abp_source.abp_name, people=abp_source.abp_people
                )
            self.abp_table.setItem(abp_row, 0, QTableWidgetItem(abp_label))
            abp_combo = QComboBox()
            abp_target = abp_targets.get(abp_source.abp_key, "")
            abp_automatic = self.abp__texts.abp_automatic
            if abp_target and not (abp_route is not None and abp_route.abp_exit_name):
                abp_automatic = self.abp__texts.abp_automatic_to.format(name=abp_target)
            abp_combo.addItem(abp_automatic, "")
            for abp_goal in abp_source.abp_goals:
                abp_combo.addItem(abp_goal, abp_goal)
            if (
                abp_route is not None
                and abp_route.abp_exit_name
                and abp_route.abp_exit_name not in abp_source.abp_goals
            ):
                abp_combo.addItem(
                    self.abp__texts.abp_closed.format(name=abp_route.abp_exit_name),
                    abp_route.abp_exit_name,
                )
            abp_combo.setCurrentIndex(
                max(0, abp_combo.findData(abp_route.abp_exit_name if abp_route else ""))
            )
            abp_combo.activated.connect(
                lambda abp_i, abp_c=abp_combo, abp_k=abp_source.abp_key: self.abp_exit_chosen.emit(
                    abp_k, str(abp_c.itemData(abp_i))
                )
            )
            abp_set_cell(self.abp_table, abp_row, 1, abp_combo)
            abp_state = (
                self.abp__texts.abp_state_manual
                if abp_route is not None
                else self.abp__texts.abp_state_auto
            )
            self.abp_table.setItem(abp_row, 2, QTableWidgetItem(abp_state))
        self.abp__filling = False
        self.abp_undo_button.setEnabled(abp_can_undo)
        self.abp_reset_all_button.setEnabled(bool(abp_routes))
        self.abp_select(abp_key)

    def abp_select(self, abp_key: abpRouteKey | None) -> None:
        abp_row = next(
            (abp_i for abp_i, abp_s in enumerate(self.abp__sources) if abp_s.abp_key == abp_key), -1
        )
        self.abp__filling = True
        if abp_row >= 0:
            self.abp_table.setCurrentCell(abp_row, 0)
        else:
            self.abp_table.clearSelection()
            self.abp_table.setCurrentCell(-1, -1)
        self.abp__filling = False
        self.abp_reset_button.setEnabled(abp_key in self.abp__manual)

    def abp__on_row(self, abp__row: int) -> None:
        if not self.abp__filling and self.abp_key is not None:
            self.abp_reset_button.setEnabled(self.abp_key in self.abp__manual)
            self.abp_selected.emit(self.abp_key)

    def abp__on_reset(self) -> None:
        if self.abp_key is not None:
            self.abp_reset_requested.emit(self.abp_key)
