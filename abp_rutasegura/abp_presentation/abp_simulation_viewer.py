from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpRoomRoute, abpSimulationResult, abpTrajectories
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import abpPlanScene
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView
from abp_rutasegura.abp_presentation.abp_qt_support import abp_to_pixmap
from abp_rutasegura.abp_presentation.abp_route_editing import abpRouteLayer
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpFloorTexts, abpSimulationTexts

abp_PROFILE_COLORS = ("#2471a3", "#e67e22", "#8e44ad", "#16a085", "#c0392b", "#7f8c8d")
abp_SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)
abp_TICK_MS = 33
abp_SLIDER_STEPS = 1000


abp_ROUTE_COLOR = "#2e7d32"
abp_MANUAL_COLOR = "#1565c0"


def abp_add_arrow_polyline(
    abp_path: QPainterPath, abp_points: Sequence[QPointF], abp_head: float
) -> None:
    abp_path.moveTo(abp_points[0])
    for abp_p in abp_points[1:]:
        abp_path.lineTo(abp_p)
    for abp_k, (abp_a, abp_b) in enumerate(itertools.pairwise(abp_points)):
        abp_last = abp_k == len(abp_points) - 2
        abp_length = math.hypot(abp_b.x() - abp_a.x(), abp_b.y() - abp_a.y())
        if abp_length < 1e-6 or (not abp_last and abp_length < 8 * abp_head):
            continue
        abp_tip = (
            abp_b if abp_last else QPointF((abp_a.x() + abp_b.x()) / 2, (abp_a.y() + abp_b.y()) / 2)
        )
        abp_angle = math.atan2(abp_b.y() - abp_a.y(), abp_b.x() - abp_a.x())
        for abp_side in (-1, 1):
            abp_wing = abp_angle + math.pi + abp_side * math.radians(28)
            abp_path.moveTo(abp_tip)
            abp_path.lineTo(
                abp_tip.x() + abp_head * math.cos(abp_wing),
                abp_tip.y() + abp_head * math.sin(abp_wing),
            )


def abp_format_time(abp_seconds: float) -> str:
    abp_seconds = max(0.0, abp_seconds)
    abp_minutes, abp_secs = divmod(round(abp_seconds), 60)
    return f"{abp_minutes}:{abp_secs:02d}"


def abp_heatmap_rgba(abp_density: npt.NDArray[np.float64]) -> npt.NDArray[np.uint8]:
    abp_peak = float(abp_density.max()) if abp_density.size else 0.0
    abp_rgba = np.zeros((*abp_density.shape, 4), dtype=np.uint8)
    if abp_peak <= 0:
        return abp_rgba
    abp_v = np.clip(abp_density / abp_peak, 0.0, 1.0)
    abp_shown = abp_v > 0.02
    abp_rgba[..., 0] = np.where(abp_shown, 255 - 40 * abp_v, 0).astype(np.uint8)
    abp_rgba[..., 1] = np.where(abp_shown, 235 * (1 - abp_v), 0).astype(np.uint8)
    abp_rgba[..., 2] = np.where(abp_shown, 60 * (1 - abp_v), 0).astype(np.uint8)
    abp_rgba[..., 3] = np.where(abp_shown, 70 + 150 * np.sqrt(abp_v), 0).astype(np.uint8)
    return abp_rgba


class abpAgentsItem(QGraphicsItem):
    def __init__(self) -> None:
        super().__init__()
        self.abp__bounds = QRectF()
        self.abp__xy = np.zeros((0, 2))
        self.abp__radius = np.zeros(0)
        self.abp__groups: list[tuple[QColor, npt.NDArray[np.int64]]] = []
        self.abp__visible = np.zeros(0, dtype=bool)
        self.setZValue(100)

    def abp_configure(
        self,
        abp_bounds: QRectF,
        abp_radius_px: npt.NDArray[np.float64],
        abp_profile_index: npt.NDArray[np.int32],
    ) -> None:
        self.prepareGeometryChange()
        self.abp__bounds = QRectF(abp_bounds)
        self.abp__radius = abp_radius_px
        self.abp__groups = [
            (
                QColor(abp_PROFILE_COLORS[abp_k % len(abp_PROFILE_COLORS)]),
                np.flatnonzero(abp_profile_index == abp_k),
            )
            for abp_k in np.unique(abp_profile_index)
        ]
        self.abp__xy = np.zeros((len(abp_radius_px), 2))
        self.abp__visible = np.zeros(len(abp_radius_px), dtype=bool)

    def abp_set_frame(
        self, abp_xy_px: npt.NDArray[np.float64], abp_visible: npt.NDArray[np.bool_]
    ) -> None:
        self.abp__xy = abp_xy_px
        self.abp__visible = abp_visible
        self.update()

    @property
    def abp_visible_count(self) -> int:
        return int(self.abp__visible.sum())

    def boundingRect(self) -> QRectF:
        return self.abp__bounds

    def paint(
        self,
        abp_painter: QPainter,
        abp_option: QStyleOptionGraphicsItem,
        abp_widget: QWidget | None = None,
    ) -> None:
        abp_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        abp_painter.setPen(Qt.PenStyle.NoPen)
        for abp_color, abp_indices in self.abp__groups:
            abp_painter.setBrush(QBrush(abp_color))
            abp_shown = abp_indices[self.abp__visible[abp_indices]]
            for abp_x, abp_y, abp_r in zip(
                self.abp__xy[abp_shown, 0],
                self.abp__xy[abp_shown, 1],
                self.abp__radius[abp_shown],
                strict=True,
            ):
                abp_painter.drawEllipse(
                    QPointF(float(abp_x), float(abp_y)), float(abp_r), float(abp_r)
                )


class abpSimulationViewer(QWidget):
    abp_time_changed = Signal(float)
    abp_floor_shown = Signal(int)

    def __init__(
        self,
        abp_texts: abpSimulationTexts = abp_TEXTS.abp_simulation,
        abp_parent: QWidget | None = None,
        abp_floor_texts: abpFloorTexts = abp_TEXTS.abp_floors,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.abp__floor_texts = abp_floor_texts
        self.abp__trajectories: abpTrajectories | None = None
        self.abp__result: abpSimulationResult | None = None
        self.abp__floors: dict[int, tuple[abpFloorPlan, npt.NDArray[np.uint8] | None]] = {}
        self.abp__level = 0
        self.abp__scale = 1.0
        self.abp__fallback_scale = 1.0
        self.abp__time = 0.0
        self.abp__speed = 1.0
        self.abp__end = 0.0
        self.abp__total = 0

        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_agents = abpAgentsItem()
        self.abp_scene.addItem(self.abp_agents)
        self.abp_heatmap = QGraphicsPixmapItem()
        self.abp_heatmap.setZValue(50)
        self.abp_heatmap.setVisible(False)
        self.abp_scene.addItem(self.abp_heatmap)

        self.abp_timer = QTimer(self)
        self.abp_timer.setInterval(abp_TICK_MS)
        self.abp_timer.timeout.connect(self.abp__tick)

        self.abp_play_button = QPushButton(abp_texts.abp_play)
        self.abp_play_button.clicked.connect(self.abp_toggle_play)
        self.abp_speed_combo = QComboBox()
        for abp_speed in abp_SPEEDS:
            self.abp_speed_combo.addItem(f"{abp_speed:g}×", abp_speed)
        self.abp_speed_combo.setCurrentIndex(abp_SPEEDS.index(1.0))
        self.abp_speed_combo.currentIndexChanged.connect(
            lambda abp_i: self.abp_set_speed(float(self.abp_speed_combo.itemData(abp_i)))
        )
        self.abp_slider = QSlider(Qt.Orientation.Horizontal)
        self.abp_slider.setRange(0, abp_SLIDER_STEPS)
        self.abp_slider.sliderMoved.connect(self.abp__on_slider)
        self.abp_time_label = QLabel(abp_texts.abp_time.format(now="0:00", end="0:00"))
        self.abp_evacuated_label = QLabel()
        self.abp_heatmap_check = QCheckBox(abp_texts.abp_heatmap)
        self.abp_heatmap_check.toggled.connect(self.abp_heatmap.setVisible)
        self.abp__routes: tuple[abpRoomRoute, ...] = ()
        self.abp_routes_item = QGraphicsPathItem()
        self.abp_routes_item.setZValue(55)
        self.abp_routes_item.setVisible(False)
        abp_route_pen = QPen(QColor(abp_ROUTE_COLOR), 3)
        abp_route_pen.setCosmetic(True)
        abp_route_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        abp_route_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.abp_routes_item.setPen(abp_route_pen)
        self.abp_scene.addItem(self.abp_routes_item)
        self.abp_manual_item = QGraphicsPathItem()
        self.abp_manual_item.setZValue(56)
        self.abp_manual_item.setVisible(False)
        abp_manual_pen = QPen(abp_route_pen)
        abp_manual_pen.setColor(QColor(abp_MANUAL_COLOR))
        self.abp_manual_item.setPen(abp_manual_pen)
        self.abp_scene.addItem(self.abp_manual_item)
        self.abp_route_layer = abpRouteLayer(self.abp_view)
        self.abp_routes_check = QCheckBox(abp_texts.abp_routes)
        self.abp_routes_check.setToolTip(abp_texts.abp_routes_tip)
        self.abp_routes_check.toggled.connect(self.abp_routes_item.setVisible)
        self.abp_routes_check.toggled.connect(self.abp_manual_item.setVisible)
        self.abp_floor_label = QLabel(abp_floor_texts.abp_label)
        self.abp_floor_combo = QComboBox()
        self.abp_floor_combo.currentIndexChanged.connect(self.abp__on_floor_selected)

        abp_controls = QHBoxLayout()
        abp_controls.addWidget(self.abp_floor_label)
        abp_controls.addWidget(self.abp_floor_combo)
        abp_controls.addWidget(self.abp_play_button)
        abp_controls.addWidget(QLabel(abp_texts.abp_speed))
        abp_controls.addWidget(self.abp_speed_combo)
        abp_controls.addWidget(self.abp_slider, stretch=1)
        abp_controls.addWidget(self.abp_time_label)
        abp_controls.addWidget(self.abp_heatmap_check)
        abp_controls.addWidget(self.abp_routes_check)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(self.abp_view, stretch=1)
        abp_layout.addLayout(abp_controls)
        abp_layout.addWidget(self.abp_evacuated_label)
        self.abp__set_enabled(False)

    def abp_set_plan(self, abp_plan: abpFloorPlan, abp_image: npt.NDArray[np.uint8] | None) -> None:
        self.abp_set_floors([(abp_plan, abp_image)])

    def abp_set_floors(
        self, abp_floors: list[tuple[abpFloorPlan, npt.NDArray[np.uint8] | None]]
    ) -> None:
        self.abp__floors = {
            abp_plan.abp_level: (abp_plan, abp_image) for abp_plan, abp_image in abp_floors
        }
        abp_levels = sorted(self.abp__floors)
        self.abp_floor_combo.blockSignals(True)
        self.abp_floor_combo.clear()
        for abp_level in abp_levels:
            self.abp_floor_combo.addItem(
                self.abp__floor_texts.abp_name.format(number=abp_level + 1), abp_level
            )
        self.abp_floor_combo.blockSignals(False)
        abp_multi = len(abp_levels) > 1
        self.abp_floor_label.setVisible(abp_multi)
        self.abp_floor_combo.setVisible(abp_multi)
        self.abp_show_floor(abp_levels[0] if abp_levels else 0)

    @property
    def abp_level(self) -> int:
        return self.abp__level

    def abp_show_floor(self, abp_level: int) -> None:
        self.abp__level = abp_level
        abp_index = self.abp_floor_combo.findData(abp_level)
        if abp_index >= 0 and self.abp_floor_combo.currentIndex() != abp_index:
            self.abp_floor_combo.blockSignals(True)
            self.abp_floor_combo.setCurrentIndex(abp_index)
            self.abp_floor_combo.blockSignals(False)
        abp_plan, abp_image = self.abp__floors.get(
            abp_level, (abpFloorPlan(abp_level=abp_level), None)
        )
        self.abp__scale = abp_plan.abp_scale_m_per_px or self.abp__fallback_scale
        self.abp_scene.abp_set_image(abp_image)
        self.abp_scene.abp_render_plan(abp_plan)
        for abp_item in self.abp_scene.abp_all_element_items():
            abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.abp__configure_run()
        self.abp__draw_routes()
        self.abp_view.abp_fit_all()
        self.abp_floor_shown.emit(abp_level)

    def abp_set_routes(self, abp_routes: Sequence[abpRoomRoute]) -> None:
        self.abp__routes = tuple(abp_routes)
        self.abp__draw_routes()

    @property
    def abp_route_count(self) -> int:
        return sum(
            1
            for abp_r in self.abp__routes
            if abp_r.abp_level == self.abp__level and len(abp_r.abp_path_m) >= 2
        )

    def abp__draw_routes(self) -> None:
        abp_scale = self.abp__scale or 1.0
        abp_path, abp_manual = QPainterPath(), QPainterPath()
        for abp_route in self.abp__routes:
            if abp_route.abp_level != self.abp__level or len(abp_route.abp_path_m) < 2:
                continue
            abp_points = [
                QPointF(abp_p.abp_x / abp_scale, abp_p.abp_y / abp_scale)
                for abp_p in abp_route.abp_path_m
            ]
            abp_add_arrow_polyline(
                abp_manual if abp_route.abp_manual else abp_path,
                abp_points,
                abp_head=0.45 / abp_scale,
            )
        self.abp_routes_item.setPath(abp_path)
        self.abp_manual_item.setPath(abp_manual)

    def abp__on_floor_selected(self, abp_index: int) -> None:
        abp_level = self.abp_floor_combo.itemData(abp_index)
        if abp_level is not None:
            self.abp_show_floor(int(abp_level))

    def abp_set_run(
        self,
        abp_trajectories: abpTrajectories | None,
        abp_result: abpSimulationResult | None,
        abp_scale: float,
    ) -> None:
        self.abp_pause()
        self.abp__trajectories = abp_trajectories
        self.abp__result = abp_result
        self.abp__fallback_scale = abp_scale
        abp_plan = self.abp__floors.get(self.abp__level, (abpFloorPlan(), None))[0]
        self.abp__scale = abp_plan.abp_scale_m_per_px or abp_scale
        self.abp__configure_run()

    def abp__configure_run(self) -> None:
        abp_trajectories, abp_result, abp_scale = (
            self.abp__trajectories,
            self.abp__result,
            self.abp__scale,
        )
        if abp_trajectories is None or abp_result is None or abp_trajectories.abp_frame_count == 0:
            self.abp_agents.abp_configure(QRectF(), np.zeros(0), np.zeros(0, np.int32))
            self.abp_heatmap.setPixmap(abp_to_pixmap(np.zeros((1, 1, 4), np.uint8)))
            self.abp__end = 0.0
            self.abp__total = 0
            self.abp__set_enabled(False)
            self.abp_evacuated_label.setText("")
            return
        self.abp__end = float(abp_trajectories.abp_times_s[-1])
        self.abp__total = abp_trajectories.abp_agent_count
        abp_bounds = self.abp_scene.sceneRect().united(self.abp_scene.itemsBoundingRect())
        self.abp_agents.abp_configure(
            abp_bounds.adjusted(-50, -50, 50, 50),
            abp_trajectories.abp_radius_m.astype(np.float64) / abp_scale,
            abp_trajectories.abp_profile_index,
        )
        abp_maps = {abp_m.abp_level: abp_m for abp_m in abp_result.abp_maps()}
        abp_floor_map = (
            abp_maps.get(self.abp__level) if abp_result.abp_floor_maps else abp_result.abp_maps()[0]
        )
        if abp_floor_map is None:
            self.abp_heatmap.setPixmap(abp_to_pixmap(np.zeros((1, 1, 4), np.uint8)))
        else:
            self.abp_heatmap.setPixmap(
                abp_to_pixmap(abp_heatmap_rgba(abp_floor_map.abp_density_map))
            )
            self.abp_heatmap.setScale(abp_floor_map.abp_cell_size_m / abp_scale)
            self.abp_heatmap.setPos(
                abp_floor_map.abp_grid_origin_m[0] / abp_scale,
                abp_floor_map.abp_grid_origin_m[1] / abp_scale,
            )
        self.abp__set_enabled(True)
        self.abp_set_time(min(self.abp__time, self.abp__end))

    @property
    def abp_current_time(self) -> float:
        return self.abp__time

    @property
    def abp_end_time(self) -> float:
        return self.abp__end

    @property
    def abp_speed(self) -> float:
        return self.abp__speed

    @property
    def abp_is_playing(self) -> bool:
        return self.abp_timer.isActive()

    def abp_play(self) -> None:
        if self.abp__trajectories is None:
            return
        if self.abp__time >= self.abp__end:
            self.abp_set_time(0.0)
        self.abp_timer.start()
        self.abp_play_button.setText(self.abp__texts.abp_pause)

    def abp_pause(self) -> None:
        self.abp_timer.stop()
        self.abp_play_button.setText(self.abp__texts.abp_play)

    def abp_toggle_play(self) -> None:
        if self.abp_is_playing:
            self.abp_pause()
        else:
            self.abp_play()

    def abp_set_speed(self, abp_factor: float) -> None:
        self.abp__speed = min(max(abp_factor, abp_SPEEDS[0]), abp_SPEEDS[-1])

    def abp_set_time(self, abp_seconds: float) -> None:
        abp_traj = self.abp__trajectories
        if abp_traj is None:
            return
        self.abp__time = min(max(abp_seconds, 0.0), self.abp__end)
        abp_times = abp_traj.abp_times_s
        abp_idx = int(
            np.clip(
                np.searchsorted(abp_times, self.abp__time, side="right") - 1, 0, len(abp_times) - 1
            )
        )
        abp_nxt = min(abp_idx + 1, len(abp_times) - 1)
        abp_span = abp_times[abp_nxt] - abp_times[abp_idx]
        abp_alpha = 0.0 if abp_span <= 0 else (self.abp__time - abp_times[abp_idx]) / abp_span
        abp_pos = (
            abp_traj.abp_positions[abp_idx] * (1 - abp_alpha)
            + abp_traj.abp_positions[abp_nxt] * abp_alpha
        )
        abp_present = abp_traj.abp_status[abp_idx] != abpAgentStatus.abp_EVACUATED
        abp_visible = abp_present
        if abp_traj.abp_level is not None:
            abp_here = abp_traj.abp_levels_at(abp_idx)
            abp_visible = abp_present & (abp_here == self.abp__level)
            abp_jumped = abp_here != abp_traj.abp_levels_at(abp_nxt)
            abp_pos[abp_jumped] = abp_traj.abp_positions[abp_idx][abp_jumped]
        self.abp_agents.abp_set_frame(abp_pos.astype(np.float64) / self.abp__scale, abp_visible)
        abp_evacuated = self.abp__total - int(abp_present.sum())
        abp_text = self.abp__texts.abp_evacuated.format(done=abp_evacuated, total=self.abp__total)
        if abp_traj.abp_level is not None:
            abp_now_levels = abp_traj.abp_levels_at(abp_idx)
            abp_on_floor = int((abp_present & (abp_now_levels == self.abp__level)).sum())
            abp_in_stairs = int((abp_present & (abp_now_levels < 0)).sum())
            abp_text += " · " + self.abp__texts.abp_viewer_floor.format(
                here=abp_on_floor, stairs=abp_in_stairs
            )
        self.abp_evacuated_label.setText(abp_text)
        self.abp_time_label.setText(
            self.abp__texts.abp_time.format(
                now=abp_format_time(self.abp__time), end=abp_format_time(self.abp__end)
            )
        )
        if not self.abp_slider.isSliderDown():
            self.abp_slider.blockSignals(True)
            self.abp_slider.setValue(
                round(abp_SLIDER_STEPS * self.abp__time / self.abp__end) if self.abp__end else 0
            )
            self.abp_slider.blockSignals(False)
        self.abp_time_changed.emit(self.abp__time)

    def abp_advance(self, abp_real_seconds: float) -> None:
        self.abp_set_time(self.abp__time + abp_real_seconds * self.abp__speed)
        if self.abp__time >= self.abp__end:
            self.abp_pause()

    def abp__tick(self) -> None:
        self.abp_advance(abp_TICK_MS / 1000.0)

    def abp__on_slider(self, abp_value: int) -> None:
        self.abp_set_time(self.abp__end * abp_value / abp_SLIDER_STEPS)

    def abp__set_enabled(self, abp_enabled: bool) -> None:
        for abp_widget in (
            self.abp_play_button,
            self.abp_speed_combo,
            self.abp_slider,
            self.abp_heatmap_check,
        ):
            abp_widget.setEnabled(abp_enabled)
