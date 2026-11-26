from __future__ import annotations

import math
from collections.abc import Callable
from enum import Enum, auto

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

abpSnapper = Callable[[QPointF, QPointF | None], tuple[QPointF, str] | None]
abpNodeFinder = Callable[[QPointF], tuple[QPointF, list[QPointF]] | None]
abp_SNAP_COLORS = {"nodo": "#e8710a", "cruce": "#c2185b", "sobre_muro": "#0e7490"}
abp_PREVIEW_COLOR = "#d35400"


class abpTool(Enum):
    abp_SELECT = auto()
    abp_WALL = auto()
    abp_DOOR = auto()
    abp_EXIT = auto()
    abp_STAIR = auto()
    abp_OBSTACLE = auto()
    abp_SAFE_ZONE = auto()
    abp_SIGN = auto()
    abp_IDENTIFY = auto()
    abp_MEASURE = auto()
    abp_POINTS = auto()
    abp_POLYGON = auto()
    abp_NONE = auto()


abp_SEGMENT_TOOLS = frozenset(
    {abpTool.abp_WALL, abpTool.abp_DOOR, abpTool.abp_EXIT, abpTool.abp_MEASURE}
)
abp_AREA_TOOLS = frozenset({abpTool.abp_STAIR, abpTool.abp_OBSTACLE, abpTool.abp_SAFE_ZONE})
abp_MIN_ZOOM, abp_MAX_ZOOM = 0.02, 40.0


def abp_snap_to_angle(abp_start: QPointF, abp_end: QPointF, abp_step_deg: float = 45.0) -> QPointF:
    abp_dx, abp_dy = abp_end.x() - abp_start.x(), abp_end.y() - abp_start.y()
    abp_length = math.hypot(abp_dx, abp_dy)
    if abp_length == 0:
        return QPointF(abp_end)
    abp_angle = round(math.degrees(math.atan2(abp_dy, abp_dx)) / abp_step_deg) * abp_step_deg
    abp_rad = math.radians(abp_angle)
    return QPointF(
        abp_start.x() + abp_length * math.cos(abp_rad),
        abp_start.y() + abp_length * math.sin(abp_rad),
    )


class abpPlanView(QGraphicsView):
    abp_segment_drawn = Signal(object, QPointF, QPointF)
    abp_area_drawn = Signal(object, QRectF)
    abp_point_picked = Signal(QPointF)
    abp_polygon_drawn = Signal(list)
    abp_delete_requested = Signal()
    abp_context_menu_requested = Signal(QPoint, QPointF)
    abp_double_clicked = Signal(QPointF)
    abp_node_moved = Signal(QPointF, QPointF)

    def __init__(self, abp_scene: QGraphicsScene, abp_parent: QWidget | None = None) -> None:
        super().__init__(abp_scene, abp_parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#f4f4f4"))
        self.abp__tool = abpTool.abp_NONE
        self.abp__start: QPointF | None = None
        self.abp__preview: QGraphicsLineItem | QGraphicsRectItem | None = None
        self.abp__pan_from: QPoint | None = None
        self.abp__vertices: list[QPointF] = []
        self.abp__fit_pending = False
        self.abp__polygon_preview: QGraphicsPathItem | None = None
        self.abp_snapper: abpSnapper | None = None
        self.abp_node_finder: abpNodeFinder | None = None
        self.abp_length_formatter: Callable[[float], str] | None = None
        self.abp_ortho = False
        self.abp__snap_marker: QGraphicsRectItem | None = None
        self.abp__length_label: QGraphicsSimpleTextItem | None = None
        self.abp__drag_node: QPointF | None = None
        self.abp__drag_anchors: list[QPointF] = []
        self.abp__drag_target: QPointF | None = None
        self.abp__drag_preview: QGraphicsPathItem | None = None
        self.abp_set_tool(abpTool.abp_NONE)

    @property
    def abp_tool(self) -> abpTool:
        return self.abp__tool

    def abp_set_tool(self, abp_tool: abpTool) -> None:
        self.abp__cancel_drawing()
        self.abp__tool = abp_tool
        if abp_tool is abpTool.abp_SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            abp_cursor = (
                Qt.CursorShape.ArrowCursor
                if abp_tool is abpTool.abp_NONE
                else Qt.CursorShape.CrossCursor
            )
            self.viewport().setCursor(abp_cursor)

    def abp_zoom_factor(self) -> float:
        return float(self.transform().m11())

    def abp_zoom_by(self, abp_factor: float) -> None:
        abp_current = self.abp_zoom_factor()
        abp_target = min(abp_MAX_ZOOM, max(abp_MIN_ZOOM, abp_current * abp_factor))
        if abp_current > 0:
            self.scale(abp_target / abp_current, abp_target / abp_current)

    def abp_zoom_to(self, abp_center: QPointF, abp_reach: float) -> None:
        abp_box = QRectF(
            abp_center.x() - abp_reach, abp_center.y() - abp_reach, 2 * abp_reach, 2 * abp_reach
        )
        self.fitInView(abp_box, Qt.AspectRatioMode.KeepAspectRatio)

    def abp_fit_all(self) -> None:
        abp_rect = getattr(self.scene(), "abp_content_rect", None) or self.sceneRect()
        if abp_rect.isEmpty():
            return
        if not self.isVisible():
            self.abp__fit_pending = True
            return
        self.abp__fit_pending = False
        self.fitInView(abp_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, abp_event: QShowEvent) -> None:
        super().showEvent(abp_event)
        if self.abp__fit_pending:
            self.abp_fit_all()

    def resizeEvent(self, abp_event: QResizeEvent) -> None:
        super().resizeEvent(abp_event)
        if self.abp__fit_pending:
            self.abp_fit_all()

    def wheelEvent(self, abp_event: QWheelEvent) -> None:
        abp_steps = abp_event.angleDelta().y() / 120.0
        if abp_steps:
            self.abp_zoom_by(1.25**abp_steps)
        abp_event.accept()

    def mousePressEvent(self, abp_event: QMouseEvent) -> None:
        if abp_event.button() == Qt.MouseButton.MiddleButton:
            self.abp__pan_from = abp_event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            abp_event.accept()
            return
        if (
            self.abp__tool is abpTool.abp_POLYGON
            and abp_event.button() == Qt.MouseButton.RightButton
        ):
            self.abp_finish_polygon()
            abp_event.accept()
            return
        if abp_event.button() == Qt.MouseButton.LeftButton:
            abp_pos = self.mapToScene(abp_event.position().toPoint())
            if self.abp__tool is abpTool.abp_SELECT and self.abp_node_finder is not None:
                abp_found = self.abp_node_finder(abp_pos)
                if abp_found is not None:
                    self.abp__begin_node_drag(*abp_found)
                    abp_event.accept()
                    return
            if self.abp__tool is abpTool.abp_POLYGON:
                self.abp_add_polygon_vertex(abp_pos)
                abp_event.accept()
                return
            if self.abp__tool in (abpTool.abp_POINTS, abpTool.abp_SIGN, abpTool.abp_IDENTIFY):
                self.abp_point_picked.emit(abp_pos)
                abp_event.accept()
                return
            if self.abp__tool in abp_SEGMENT_TOOLS or self.abp__tool in abp_AREA_TOOLS:
                if self.abp__tool in abp_SEGMENT_TOOLS:
                    abp_pos = self.abp__snapped(abp_pos)
                self.abp__start = abp_pos
                abp_pen = QPen(QColor("#d35400"), 2, Qt.PenStyle.DashLine)
                abp_pen.setCosmetic(True)
                if self.abp__tool in abp_SEGMENT_TOOLS:
                    self.abp__preview = QGraphicsLineItem(QLineF(abp_pos, abp_pos))
                else:
                    self.abp__preview = QGraphicsRectItem(QRectF(abp_pos, abp_pos))
                self.abp__preview.setPen(abp_pen)
                self.abp__preview.setZValue(1000)
                self.scene().addItem(self.abp__preview)
                abp_event.accept()
                return
        super().mousePressEvent(abp_event)

    def mouseMoveEvent(self, abp_event: QMouseEvent) -> None:
        if self.abp__pan_from is not None:
            abp_delta = abp_event.position().toPoint() - self.abp__pan_from
            self.abp__pan_from = abp_event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - abp_delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - abp_delta.y())
            abp_event.accept()
            return
        if self.abp__drag_node is not None:
            self.abp__update_node_drag(self.mapToScene(abp_event.position().toPoint()))
            abp_event.accept()
            return
        if self.abp__tool is abpTool.abp_POLYGON and self.abp__vertices:
            self.abp__update_polygon_preview(self.mapToScene(abp_event.position().toPoint()))
            abp_event.accept()
            return
        if self.abp__start is not None and self.abp__preview is not None:
            abp_end = self.abp__end_point(abp_event)
            if isinstance(self.abp__preview, QGraphicsLineItem):
                self.abp__preview.setLine(QLineF(self.abp__start, abp_end))
                self.abp__show_length(self.abp__start, abp_end)
            else:
                self.abp__preview.setRect(QRectF(self.abp__start, abp_end).normalized())
            abp_event.accept()
            return
        if self.abp__tool in abp_SEGMENT_TOOLS:
            self.abp__snapped(self.mapToScene(abp_event.position().toPoint()))
        super().mouseMoveEvent(abp_event)

    def mouseReleaseEvent(self, abp_event: QMouseEvent) -> None:
        if abp_event.button() == Qt.MouseButton.MiddleButton and self.abp__pan_from is not None:
            self.abp__pan_from = None
            self.abp_set_tool(self.abp__tool)
            abp_event.accept()
            return
        if abp_event.button() == Qt.MouseButton.LeftButton and self.abp__drag_node is not None:
            abp_node, abp_target = self.abp__drag_node, self.abp__drag_target
            self.abp__end_node_drag()
            if abp_target is not None and QLineF(abp_node, abp_target).length() > 0.5:
                self.abp_node_moved.emit(abp_node, abp_target)
            abp_event.accept()
            return
        if abp_event.button() == Qt.MouseButton.LeftButton and self.abp__start is not None:
            abp_start, abp_end = self.abp__start, self.abp__end_point(abp_event)
            abp_tool = self.abp__tool
            self.abp__cancel_drawing()
            if abp_tool in abp_SEGMENT_TOOLS and QLineF(abp_start, abp_end).length() >= 3:
                self.abp_segment_drawn.emit(abp_tool, abp_start, abp_end)
            elif abp_tool in abp_AREA_TOOLS:
                abp_rect = QRectF(abp_start, abp_end).normalized()
                if abp_rect.width() >= 3 and abp_rect.height() >= 3:
                    self.abp_area_drawn.emit(abp_tool, abp_rect)
            abp_event.accept()
            return
        super().mouseReleaseEvent(abp_event)

    def mouseDoubleClickEvent(self, abp_event: QMouseEvent) -> None:
        if self.abp__tool is abpTool.abp_POLYGON:
            self.abp_finish_polygon()
            abp_event.accept()
            return
        if self.abp__tool is abpTool.abp_SELECT and abp_event.button() == Qt.MouseButton.LeftButton:
            self.abp_double_clicked.emit(self.mapToScene(abp_event.position().toPoint()))
            abp_event.accept()
            return
        super().mouseDoubleClickEvent(abp_event)

    def contextMenuEvent(self, abp_event: QContextMenuEvent) -> None:
        if self.abp__tool is abpTool.abp_POLYGON or self.abp__start is not None:
            abp_event.accept()
            return
        self.abp_context_menu_requested.emit(
            abp_event.globalPos(), self.mapToScene(abp_event.pos())
        )
        abp_event.accept()

    def abp_scene_tolerance(self, abp_pixels: float = 6.0) -> float:
        abp_zoom = self.abp_zoom_factor()
        return abp_pixels / abp_zoom if abp_zoom > 0 else abp_pixels

    def keyPressEvent(self, abp_event: QKeyEvent) -> None:
        if self.abp__tool is abpTool.abp_POLYGON and abp_event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self.abp_finish_polygon()
            abp_event.accept()
            return
        if abp_event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.abp_delete_requested.emit()
            abp_event.accept()
            return
        if abp_event.key() == Qt.Key.Key_Escape:
            self.abp__end_node_drag()
            self.abp__cancel_drawing()
            abp_event.accept()
            return
        super().keyPressEvent(abp_event)

    def abp__end_point(self, abp_event: QMouseEvent) -> QPointF:
        abp_end = self.mapToScene(abp_event.position().toPoint())
        if self.abp__start is None or self.abp__tool not in abp_SEGMENT_TOOLS:
            return abp_end
        abp_shift = bool(abp_event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self.abp_ortho or abp_shift:
            abp_end = abp_snap_to_angle(self.abp__start, abp_end, 90.0 if self.abp_ortho else 45.0)
        return self.abp__snapped(abp_end)

    def abp__snapped(self, abp_point: QPointF, abp_exclude: QPointF | None = None) -> QPointF:
        abp_target = (
            self.abp_snapper(abp_point, abp_exclude) if self.abp_snapper is not None else None
        )
        if abp_target is None:
            self.abp__hide_marker()
            return abp_point
        abp_snapped, abp_kind = abp_target
        self.abp__show_marker(abp_snapped, abp_kind)
        return abp_snapped

    def abp__show_marker(self, abp_point: QPointF, abp_kind: str) -> None:
        if self.abp__snap_marker is None or self.abp__snap_marker.scene() is None:
            self.abp__snap_marker = QGraphicsRectItem(-5, -5, 10, 10)
            self.abp__snap_marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            self.abp__snap_marker.setZValue(1100)
            self.scene().addItem(self.abp__snap_marker)
        abp_pen = QPen(QColor(abp_SNAP_COLORS.get(abp_kind, abp_PREVIEW_COLOR)), 2)
        abp_pen.setCosmetic(True)
        self.abp__snap_marker.setPen(abp_pen)
        self.abp__snap_marker.setPos(abp_point)
        self.abp__snap_marker.setVisible(True)

    def abp__hide_marker(self) -> None:
        if self.abp__snap_marker is not None and self.abp__snap_marker.scene() is not None:
            self.abp__snap_marker.setVisible(False)

    @property
    def abp_snap_marker_visible(self) -> bool:
        abp_marker = self.abp__snap_marker
        return abp_marker is not None and abp_marker.scene() is not None and abp_marker.isVisible()

    def abp__show_length(self, abp_start: QPointF, abp_end: QPointF) -> None:
        if self.abp_length_formatter is None:
            return
        if self.abp__length_label is None or self.abp__length_label.scene() is None:
            self.abp__length_label = QGraphicsSimpleTextItem()
            self.abp__length_label.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            self.abp__length_label.setBrush(QColor(abp_PREVIEW_COLOR))
            self.abp__length_label.setZValue(1100)
            self.scene().addItem(self.abp__length_label)
        self.abp__length_label.setText(
            self.abp_length_formatter(QLineF(abp_start, abp_end).length())
        )
        self.abp__length_label.setPos(abp_end + QPointF(8 / max(self.abp_zoom_factor(), 1e-6), 0))
        self.abp__length_label.setVisible(True)

    @property
    def abp_length_text(self) -> str:
        abp_label = self.abp__length_label
        if abp_label is None or abp_label.scene() is None or not abp_label.isVisible():
            return ""
        return abp_label.text()

    def abp__begin_node_drag(self, abp_node: QPointF, abp_anchors: list[QPointF]) -> None:
        self.abp__drag_node = QPointF(abp_node)
        self.abp__drag_anchors = list(abp_anchors)
        self.abp__drag_target = QPointF(abp_node)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        abp_pen = QPen(QColor(abp_PREVIEW_COLOR), 2, Qt.PenStyle.DashLine)
        abp_pen.setCosmetic(True)
        self.abp__drag_preview = QGraphicsPathItem()
        self.abp__drag_preview.setPen(abp_pen)
        self.abp__drag_preview.setZValue(1000)
        self.scene().addItem(self.abp__drag_preview)

    def abp__update_node_drag(self, abp_point: QPointF) -> None:
        if self.abp__drag_node is None or self.abp__drag_preview is None:
            return
        abp_target = self.abp__snapped(abp_point, abp_exclude=self.abp__drag_node)
        self.abp__drag_target = abp_target
        abp_path = QPainterPath()
        for abp_anchor in self.abp__drag_anchors:
            abp_path.moveTo(abp_anchor)
            abp_path.lineTo(abp_target)
        self.abp__drag_preview.setPath(abp_path)
        if self.abp__drag_anchors:
            self.abp__show_length(self.abp__drag_anchors[0], abp_target)

    def abp_drag_node(self, abp_node: QPointF, abp_to: QPointF) -> None:
        abp_found = self.abp_node_finder(abp_node) if self.abp_node_finder is not None else None
        if abp_found is None:
            return
        self.abp__begin_node_drag(*abp_found)
        self.abp__update_node_drag(abp_to)
        abp_start, abp_target = self.abp__drag_node, self.abp__drag_target
        self.abp__end_node_drag()
        if (
            abp_start is not None
            and abp_target is not None
            and QLineF(abp_start, abp_target).length() > 0.5
        ):
            self.abp_node_moved.emit(abp_start, abp_target)

    def abp__end_node_drag(self) -> None:
        if self.abp__drag_preview is not None and self.abp__drag_preview.scene() is not None:
            self.scene().removeItem(self.abp__drag_preview)
        self.abp__drag_preview = None
        abp_was_dragging = self.abp__drag_node is not None
        self.abp__drag_node = None
        self.abp__drag_anchors = []
        self.abp__drag_target = None
        self.abp__hide_marker()
        if self.abp__length_label is not None and self.abp__length_label.scene() is not None:
            self.abp__length_label.setVisible(False)
        if abp_was_dragging:
            self.abp_set_tool(self.abp__tool)

    def abp_add_polygon_vertex(self, abp_point: QPointF) -> None:
        if self.abp__vertices and QLineF(self.abp__vertices[-1], abp_point).length() < 2:
            return
        self.abp__vertices.append(QPointF(abp_point))
        self.abp__update_polygon_preview(abp_point)

    def abp_finish_polygon(self) -> None:
        abp_vertices = list(self.abp__vertices)
        self.abp__cancel_drawing()
        if len(abp_vertices) >= 3:
            self.abp_polygon_drawn.emit(abp_vertices)

    def abp__update_polygon_preview(self, abp_cursor: QPointF) -> None:
        abp_path = QPainterPath(self.abp__vertices[0])
        for abp_vertex in self.abp__vertices[1:]:
            abp_path.lineTo(abp_vertex)
        abp_path.lineTo(abp_cursor)
        if self.abp__polygon_preview is None:
            abp_pen = QPen(QColor("#d35400"), 2, Qt.PenStyle.DashLine)
            abp_pen.setCosmetic(True)
            self.abp__polygon_preview = QGraphicsPathItem()
            self.abp__polygon_preview.setPen(abp_pen)
            self.abp__polygon_preview.setZValue(1000)
            self.scene().addItem(self.abp__polygon_preview)
        self.abp__polygon_preview.setPath(abp_path)

    def abp__cancel_drawing(self) -> None:
        if self.abp__preview is not None and self.abp__preview.scene() is not None:
            self.scene().removeItem(self.abp__preview)
        if self.abp__polygon_preview is not None and self.abp__polygon_preview.scene() is not None:
            self.scene().removeItem(self.abp__polygon_preview)
        self.abp__preview = None
        self.abp__polygon_preview = None
        self.abp__vertices = []
        self.abp__start = None
        self.abp__hide_marker()
        if self.abp__length_label is not None and self.abp__length_label.scene() is not None:
            self.abp__length_label.setVisible(False)
