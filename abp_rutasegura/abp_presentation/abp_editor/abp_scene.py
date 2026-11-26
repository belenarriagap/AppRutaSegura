from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QObject, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from abp_rutasegura.abp_application.abp_stairs_service import abp_entry_arrow
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSign
from abp_rutasegura.abp_presentation.abp_qt_support import abp_to_pixmap
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS, abpSignArt
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS

abp_KIND_KEY = 0
abp_INDEX_KEY = 1
abp_LOW_CONFIDENCE = 0.7

abp_WALL_COLOR = QColor("#1f3a93")
abp_LOW_CONF_COLOR = QColor("#e67e22")
abp_DOOR_COLOR = QColor("#27ae60")
abp_EXIT_COLOR = QColor("#c0392b")
abp_STAIR_COLOR = QColor("#8e44ad")
abp_OBSTACLE_COLOR = QColor("#7f8c8d")
abp_SAFE_ZONE_COLOR = QColor("#2ecc71")

abpElementRef = tuple[abpElementType, int]


def abp__pen(abp_color: QColor, abp_width: float, abp_dashed: bool = False) -> QPen:
    abp_pen = QPen(abp_color, abp_width)
    abp_pen.setCosmetic(True)
    abp_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    if abp_dashed:
        abp_pen.setStyle(Qt.PenStyle.DashLine)
    return abp_pen


def abp__qpolygon(abp_polygon: abpPolygon) -> QPolygonF:
    return QPolygonF([QPointF(abp_p.abp_x, abp_p.abp_y) for abp_p in abp_polygon.abp_vertices])


abp_SIGN_SIZE_M = 0.6


def abp_sign_size_px(abp_plan: abpFloorPlan) -> float:
    return abp_SIGN_SIZE_M / abp_plan.abp_scale_m_per_px if abp_plan.abp_scale_m_per_px else 30.0


def abp_paint_sign(abp_painter: QPainter, abp_art: abpSignArt, abp_text: str = "") -> None:
    abp_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for abp_shape in abp_art.abp_shapes:
        abp_color = QColor(abp_shape.abp_color)
        abp_points = [QPointF(abp_x, abp_y) for abp_x, abp_y in abp_shape.abp_points]
        abp_painter.setPen(Qt.PenStyle.NoPen)
        abp_painter.setBrush(QBrush(abp_color))
        if abp_shape.abp_kind == "poly":
            abp_painter.drawPolygon(QPolygonF(abp_points))
        elif abp_shape.abp_kind == "circle":
            abp_painter.drawEllipse(abp_points[0], abp_shape.abp_size, abp_shape.abp_size)
        elif abp_shape.abp_kind == "line":
            abp_pen = QPen(abp_color, abp_shape.abp_size)
            abp_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            abp_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            abp_painter.setPen(abp_pen)
            abp_painter.setBrush(Qt.BrushStyle.NoBrush)
            abp_painter.drawPolyline(QPolygonF(abp_points))
        else:
            abp__paint_text(
                abp_painter,
                abp_points[0],
                abp_shape.abp_text.format(text=abp_text),
                abp_shape.abp_size,
                abp_color,
            )


def abp__paint_text(
    abp_painter: QPainter, abp_center: QPointF, abp_text: str, abp_size: float, abp_color: QColor
) -> None:
    abp_font = QFont()
    abp_font.setBold(True)
    abp_font.setPixelSize(100)
    abp_metrics = QFontMetricsF(abp_font)
    abp_painter.save()
    abp_painter.translate(abp_center)
    abp_factor = abp_size / abp_metrics.capHeight()
    abp_painter.scale(abp_factor, abp_factor)
    abp_painter.setFont(abp_font)
    abp_painter.setPen(QPen(abp_color))
    abp_width = abp_metrics.horizontalAdvance(abp_text)
    abp_painter.drawText(QPointF(-abp_width / 2, abp_metrics.capHeight() / 2), abp_text)
    abp_painter.restore()


class abpSignItem(QGraphicsItem):
    def __init__(self, abp_sign: abpSign, abp_size: float) -> None:
        super().__init__()
        self.abp__art = abp_SIGNS[abp_sign.abp_kind]
        self.abp__text = abp_sign.abp_text
        self.abp__size = abp_size
        self.setPos(abp_sign.abp_position.abp_x, abp_sign.abp_position.abp_y)
        if self.abp__art.abp_rotates:
            self.setRotation(abp_sign.abp_rotation_deg)
        abp_generic = abp_sign.abp_text and abp_sign.abp_kind is not abpSignKind.abp_CAPACITY
        self.setToolTip(
            f"{self.abp__art.abp_label}: {abp_sign.abp_text}"
            if abp_generic
            else self.abp__art.abp_label
        )

    def boundingRect(self) -> QRectF:
        abp_s = self.abp__size
        return QRectF(-0.88 * abp_s, -0.66 * abp_s, 1.76 * abp_s, 1.32 * abp_s)

    def paint(
        self,
        abp_painter: QPainter,
        abp_option: QStyleOptionGraphicsItem,
        abp_widget: QWidget | None = None,
    ) -> None:
        abp_painter.save()
        abp_painter.scale(self.abp__size, self.abp__size)
        abp_paint_sign(abp_painter, self.abp__art, self.abp__text)
        abp_painter.restore()
        if self.isSelected():
            abp_pen = QPen(QColor("#e8710a"), 2, Qt.PenStyle.DashLine)
            abp_pen.setCosmetic(True)
            abp_painter.setPen(abp_pen)
            abp_painter.setBrush(Qt.BrushStyle.NoBrush)
            abp_painter.drawRect(self.boundingRect())


class abpPlanScene(QGraphicsScene):
    def __init__(self, abp_parent: QObject | None = None) -> None:
        super().__init__(abp_parent)
        self.abp__background: QGraphicsPixmapItem | None = None
        self.abp__items: dict[abpElementType, list[QGraphicsItem]] = {
            abp_k: [] for abp_k in abpElementType
        }
        self.abp__labels: list[QGraphicsItem] = []
        self.abp__stair_labels: list[QGraphicsItem] = []
        self.abp__visible: dict[abpElementType | None, bool] = {
            abp_k: True for abp_k in abpElementType
        }
        self.abp__visible[None] = True
        self.abp__node_items: list[QGraphicsItem] = []
        self.abp__nodes_visible = True
        self.abp__highlight: QGraphicsItem | None = None

    def abp_set_image(self, abp_image: npt.NDArray[np.uint8] | None) -> None:
        if self.abp__background is not None:
            self.removeItem(self.abp__background)
            self.abp__background = None
        if abp_image is not None:
            self.abp__background = self.addPixmap(abp_to_pixmap(abp_image))
            self.abp__background.setZValue(-100)
            self.abp__background.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.abp__background.setVisible(self.abp__visible[None])
            abp_rect = self.abp__background.boundingRect()
            abp_dx, abp_dy = 0.35 * abp_rect.width(), 0.35 * abp_rect.height()
            self.setSceneRect(abp_rect.adjusted(-abp_dx, -abp_dy, abp_dx, abp_dy))

    @property
    def abp_content_rect(self) -> QRectF:
        abp_rect = (
            self.abp__background.boundingRect() if self.abp__background is not None else QRectF()
        )
        for abp_item in self.abp_all_element_items():
            abp_rect = abp_rect.united(abp_item.sceneBoundingRect())
        return abp_rect if not abp_rect.isEmpty() else self.sceneRect()

    @property
    def abp_has_image(self) -> bool:
        return self.abp__background is not None

    def abp_render_plan(self, abp_plan: abpFloorPlan) -> None:
        abp_selected = {self.abp_ref(abp_item) for abp_item in self.selectedItems()}
        for abp_items in self.abp__items.values():
            for abp_item in abp_items:
                self.removeItem(abp_item)
            abp_items.clear()
        for abp_label in self.abp__labels + self.abp__stair_labels:
            self.removeItem(abp_label)
        self.abp__labels.clear()
        self.abp__stair_labels.clear()

        for abp_i, abp_wall in enumerate(abp_plan.abp_walls):
            abp_low = abp_wall.abp_confidence < abp_LOW_CONFIDENCE
            abp_pen = abp__pen(
                abp_LOW_CONF_COLOR if abp_low else abp_WALL_COLOR, 4, abp_dashed=abp_low
            )
            self.abp__add_line(
                abpElementType.abp_WALL, abp_i, abp_wall.abp_segment, abp_pen, abp_z=1
            )
        for abp_i, abp_door in enumerate(abp_plan.abp_doors):
            abp_low = abp_door.abp_confidence < abp_LOW_CONFIDENCE
            abp_pen = abp__pen(
                abp_LOW_CONF_COLOR if abp_low else abp_DOOR_COLOR, 6, abp_dashed=abp_low
            )
            self.abp__add_line(
                abpElementType.abp_DOOR, abp_i, abp_door.abp_segment, abp_pen, abp_z=2
            )
        for abp_i, abp_exit_ in enumerate(abp_plan.abp_exits):
            abp_pen = abp__pen(abp_EXIT_COLOR, 7, abp_dashed=not abp_exit_.abp_confirmed)
            self.abp__add_line(
                abpElementType.abp_EXIT, abp_i, abp_exit_.abp_segment, abp_pen, abp_z=3
            )
            abp_suffix = "" if abp_exit_.abp_confirmed else abp_TEXTS.abp_editor.abp_proposed_suffix
            abp_label = QGraphicsSimpleTextItem(abp_exit_.abp_name + abp_suffix)
            abp_label.setBrush(QBrush(abp_EXIT_COLOR))
            abp_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            abp_mid = abp_exit_.abp_segment.abp_midpoint
            abp_label.setPos(abp_mid.abp_x + 6, abp_mid.abp_y + 6)
            abp_label.setZValue(4)
            abp_label.setVisible(self.abp__visible[abpElementType.abp_EXIT])
            self.addItem(abp_label)
            self.abp__labels.append(abp_label)
        for abp_i, abp_stair in enumerate(abp_plan.abp_stairs):
            abp_brush = QBrush(abp_STAIR_COLOR, Qt.BrushStyle.BDiagPattern)
            abp_pen = abp__pen(abp_STAIR_COLOR, 2, abp_dashed=not abp_stair.abp_confirmed)
            self.abp__add_polygon(
                abpElementType.abp_STAIR, abp_i, abp_stair.abp_area, abp_pen, abp_brush
            )
            abp_mark = dict(abp_TEXTS.abp_editor.abp_stair_marks).get(abp_stair.abp_use.value, "")
            abp_arrow = abp_entry_arrow(abp_stair)
            if abp_arrow is not None:
                self.abp__add_entry(*abp_arrow)
            if abp_stair.abp_name or abp_mark:
                abp_label = QGraphicsSimpleTextItem(f"{abp_stair.abp_name}\n{abp_mark}".strip())
                abp_label.setBrush(QBrush(abp_STAIR_COLOR))
                abp_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                abp_center = abp_stair.abp_area.abp_centroid
                abp_label.setPos(abp_center.abp_x, abp_center.abp_y)
                abp_label.setZValue(4)
                abp_label.setVisible(self.abp__visible[abpElementType.abp_STAIR])
                self.addItem(abp_label)
                self.abp__stair_labels.append(abp_label)
        for abp_i, abp_obstacle in enumerate(abp_plan.abp_obstacles):
            abp_base = abp_OBSTACLE_COLOR if abp_obstacle.abp_confirmed else abp_LOW_CONF_COLOR
            abp_color = QColor(abp_base)
            abp_color.setAlpha(140 if abp_obstacle.abp_confirmed else 60)
            abp_pen = abp__pen(abp_base, 2, abp_dashed=not abp_obstacle.abp_confirmed)
            self.abp__add_polygon(
                abpElementType.abp_OBSTACLE,
                abp_i,
                abp_obstacle.abp_area,
                abp_pen,
                QBrush(abp_color),
            )
            if abp_obstacle.abp_name:
                self.abp__items[abpElementType.abp_OBSTACLE][-1].setToolTip(abp_obstacle.abp_name)
        for abp_i, abp_zone in enumerate(abp_plan.abp_safe_zones):
            abp_color = QColor(abp_SAFE_ZONE_COLOR)
            abp_color.setAlpha(70)
            self.abp__add_polygon(
                abpElementType.abp_SAFE_ZONE,
                abp_i,
                abp_zone.abp_area,
                abp__pen(abp_SAFE_ZONE_COLOR, 2),
                QBrush(abp_color),
            )
        for abp_i, abp_sign in enumerate(abp_plan.abp_signs):
            self.abp__tag(
                abpSignItem(abp_sign, abp_sign_size_px(abp_plan)),
                abpElementType.abp_SIGN,
                abp_i,
                abp_z=5,
            )
        for abp_item in self.abp_all_element_items():
            if self.abp_ref(abp_item) in abp_selected:
                abp_item.setSelected(True)

    def abp__add_entry(self, abp_start: abpPoint, abp_end: abpPoint) -> None:
        abp_path = QPainterPath(QPointF(abp_start.abp_x, abp_start.abp_y))
        abp_path.lineTo(abp_end.abp_x, abp_end.abp_y)
        abp_angle = math.atan2(abp_start.abp_y - abp_end.abp_y, abp_start.abp_x - abp_end.abp_x)
        abp_head = 0.35 * math.hypot(
            abp_end.abp_x - abp_start.abp_x, abp_end.abp_y - abp_start.abp_y
        )
        for abp_turn in (-0.5, 0.5):
            abp_path.moveTo(abp_end.abp_x, abp_end.abp_y)
            abp_path.lineTo(
                abp_end.abp_x + abp_head * math.cos(abp_angle + abp_turn),
                abp_end.abp_y + abp_head * math.sin(abp_angle + abp_turn),
            )
        abp_item = QGraphicsPathItem(abp_path)
        abp_item.setPen(abp__pen(abp_STAIR_COLOR, 3))
        abp_item.setZValue(4)
        abp_item.setVisible(self.abp__visible[abpElementType.abp_STAIR])
        self.addItem(abp_item)
        self.abp__stair_labels.append(abp_item)

    def abp_show_highlight(self, abp_points: list[QPointF]) -> None:
        if self.abp__highlight is not None:
            self.removeItem(self.abp__highlight)
            self.abp__highlight = None
        if not abp_points:
            return
        abp_pen = QPen(QColor("#e8710a"), 4)
        abp_pen.setCosmetic(True)
        abp_item: QGraphicsItem
        if len(abp_points) == 1:
            abp_radius = 26.0
            abp_circle = QGraphicsEllipseItem(
                -abp_radius, -abp_radius, 2 * abp_radius, 2 * abp_radius
            )
            abp_circle.setPos(abp_points[0])
            abp_circle.setPen(abp_pen)
            abp_circle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            abp_item = abp_circle
        else:
            abp_outline = QGraphicsPolygonItem(QPolygonF(abp_points))
            abp_outline.setPen(abp_pen)
            abp_outline.setBrush(QBrush(QColor(232, 113, 10, 60)))
            abp_item = abp_outline
        abp_item.setZValue(90)
        self.addItem(abp_item)
        self.abp__highlight = abp_item

    def abp_render_nodes(self, abp_points: list[tuple[float, float]]) -> None:
        for abp_item in self.abp__node_items:
            self.removeItem(abp_item)
        self.abp__node_items.clear()
        abp_pen = QPen(abp_WALL_COLOR, 1.5)
        abp_pen.setCosmetic(True)
        for abp_x, abp_y in abp_points:
            abp_item = self.addRect(QRectF(-3.5, -3.5, 7, 7), abp_pen, QBrush(QColor("#ffffff")))
            abp_item.setPos(abp_x, abp_y)
            abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            abp_item.setZValue(60)
            abp_item.setVisible(self.abp__nodes_visible)
            self.abp__node_items.append(abp_item)

    def abp_set_nodes_visible(self, abp_visible: bool) -> None:
        self.abp__nodes_visible = abp_visible
        for abp_item in self.abp__node_items:
            abp_item.setVisible(abp_visible)

    @property
    def abp_visible_node_count(self) -> int:
        return sum(1 for abp_item in self.abp__node_items if abp_item.isVisible())

    def abp__tag(
        self, abp_item: QGraphicsItem, abp_kind: abpElementType, abp_index: int, abp_z: float
    ) -> None:
        abp_item.setData(abp_KIND_KEY, abp_kind.value)
        abp_item.setData(abp_INDEX_KEY, abp_index)
        abp_item.setZValue(abp_z)
        abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        abp_item.setVisible(self.abp__visible[abp_kind])
        self.addItem(abp_item)
        self.abp__items[abp_kind].append(abp_item)

    def abp__add_line(
        self,
        abp_kind: abpElementType,
        abp_index: int,
        abp_seg: abpSegment,
        abp_pen: QPen,
        abp_z: float,
    ) -> None:
        abp_item = QGraphicsLineItem(
            abp_seg.abp_start.abp_x,
            abp_seg.abp_start.abp_y,
            abp_seg.abp_end.abp_x,
            abp_seg.abp_end.abp_y,
        )
        abp_item.setPen(abp_pen)
        self.abp__tag(abp_item, abp_kind, abp_index, abp_z)

    def abp__add_polygon(
        self,
        abp_kind: abpElementType,
        abp_index: int,
        abp_polygon: abpPolygon,
        abp_pen: QPen,
        abp_brush: QBrush,
    ) -> None:
        abp_item = QGraphicsPolygonItem(abp__qpolygon(abp_polygon))
        abp_item.setPen(abp_pen)
        abp_item.setBrush(abp_brush)
        self.abp__tag(abp_item, abp_kind, abp_index, abp_z=0)

    @staticmethod
    def abp_ref(abp_item: QGraphicsItem) -> abpElementRef | None:
        abp_kind = abp_item.data(abp_KIND_KEY)
        abp_index = abp_item.data(abp_INDEX_KEY)
        if abp_kind is None or abp_index is None:
            return None
        return abpElementType(abp_kind), int(abp_index)

    def abp_items_of(self, abp_kind: abpElementType) -> list[QGraphicsItem]:
        return list(self.abp__items[abp_kind])

    def abp_all_element_items(self) -> list[QGraphicsItem]:
        return [abp_item for abp_items in self.abp__items.values() for abp_item in abp_items]

    def abp_ref_at(self, abp_point: QPointF, abp_tolerance: float = 3.0) -> abpElementRef | None:
        abp_area = QRectF(
            abp_point.x() - abp_tolerance,
            abp_point.y() - abp_tolerance,
            2 * abp_tolerance,
            2 * abp_tolerance,
        )
        for abp_item in self.items(
            abp_area, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder
        ):
            abp_ref = self.abp_ref(abp_item)
            if abp_ref is not None and abp_item.isVisible():
                return abp_ref
        return None

    def abp_select_only(self, abp_ref: abpElementRef) -> None:
        self.clearSelection()
        for abp_item in self.abp_all_element_items():
            if self.abp_ref(abp_item) == abp_ref:
                abp_item.setSelected(True)

    def abp_selected_refs(self) -> list[abpElementRef]:
        abp_refs = (self.abp_ref(abp_item) for abp_item in self.selectedItems())
        return [abp_r for abp_r in abp_refs if abp_r is not None]

    def abp_set_layer_visible(self, abp_kind: abpElementType | None, abp_visible: bool) -> None:
        self.abp__visible[abp_kind] = abp_visible
        if abp_kind is None:
            if self.abp__background is not None:
                self.abp__background.setVisible(abp_visible)
            return
        for abp_item in self.abp__items[abp_kind]:
            abp_item.setVisible(abp_visible)
            if not abp_visible:
                abp_item.setSelected(False)
        if abp_kind is abpElementType.abp_EXIT:
            for abp_label in self.abp__labels:
                abp_label.setVisible(abp_visible)
        if abp_kind is abpElementType.abp_STAIR:
            for abp_label in self.abp__stair_labels:
                abp_label.setVisible(abp_visible)

    def abp_is_layer_visible(self, abp_kind: abpElementType | None) -> bool:
        return self.abp__visible[abp_kind]
