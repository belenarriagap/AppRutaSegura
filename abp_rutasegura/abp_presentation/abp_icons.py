from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from abp_rutasegura.abp_application.abp_progress import abpStepState
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind
from abp_rutasegura.abp_presentation import abp_theme
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import (
    abp_DOOR_COLOR,
    abp_EXIT_COLOR,
    abp_OBSTACLE_COLOR,
    abp_paint_sign,
    abp_SAFE_ZONE_COLOR,
    abp_STAIR_COLOR,
    abp_WALL_COLOR,
)
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS

abp__SCALE = 3
abpPainter = Callable[[QPainter, float], None]


def abp__icon(abp_paint: abpPainter, abp_size: int = 20) -> QIcon:
    abp_pixmap = QPixmap(abp_size * abp__SCALE, abp_size * abp__SCALE)
    abp_pixmap.fill(Qt.GlobalColor.transparent)
    abp_pixmap.setDevicePixelRatio(abp__SCALE)
    abp_painter = QPainter(abp_pixmap)
    abp_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    abp_paint(abp_painter, float(abp_size))
    abp_painter.end()
    return QIcon(abp_pixmap)


def abp__pen(abp_color: QColor | str, abp_width: float) -> QPen:
    abp_pen = QPen(QColor(abp_color), abp_width)
    abp_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    abp_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return abp_pen


def abp__wall(abp_p: QPainter, abp_s: float) -> None:
    abp_p.setPen(abp__pen(abp_WALL_COLOR, abp_s * 0.2))
    abp_p.drawLine(QPointF(abp_s * 0.15, abp_s * 0.5), QPointF(abp_s * 0.85, abp_s * 0.5))


def abp__door(abp_p: QPainter, abp_s: float) -> None:
    abp_p.setPen(abp__pen(abp_WALL_COLOR, abp_s * 0.14))
    abp_p.drawLine(QPointF(abp_s * 0.08, abp_s * 0.8), QPointF(abp_s * 0.25, abp_s * 0.8))
    abp_p.drawLine(QPointF(abp_s * 0.75, abp_s * 0.8), QPointF(abp_s * 0.92, abp_s * 0.8))
    abp_p.setPen(abp__pen(abp_DOOR_COLOR, abp_s * 0.12))
    abp_p.drawLine(QPointF(abp_s * 0.25, abp_s * 0.8), QPointF(abp_s * 0.25, abp_s * 0.28))
    abp_arc = QPen(abp_DOOR_COLOR, abp_s * 0.06, Qt.PenStyle.DashLine)
    abp_p.setPen(abp_arc)
    abp_p.drawArc(QRectF(abp_s * -0.27, abp_s * 0.28, abp_s * 1.04, abp_s * 1.04), 0, 90 * 16)


def abp__exit(abp_p: QPainter, abp_s: float) -> None:
    abp_p.setPen(abp__pen(abp_EXIT_COLOR, abp_s * 0.16))
    abp_p.drawLine(QPointF(abp_s * 0.82, abp_s * 0.12), QPointF(abp_s * 0.82, abp_s * 0.88))
    abp_p.setPen(abp__pen(abp_EXIT_COLOR, abp_s * 0.12))
    abp_p.drawLine(QPointF(abp_s * 0.12, abp_s * 0.5), QPointF(abp_s * 0.62, abp_s * 0.5))
    abp_p.drawLine(QPointF(abp_s * 0.44, abp_s * 0.3), QPointF(abp_s * 0.64, abp_s * 0.5))
    abp_p.drawLine(QPointF(abp_s * 0.44, abp_s * 0.7), QPointF(abp_s * 0.64, abp_s * 0.5))


def abp__stair(abp_p: QPainter, abp_s: float) -> None:
    abp_path = QPainterPath(QPointF(abp_s * 0.1, abp_s * 0.85))
    for abp_i in range(3):
        abp_x0 = abp_s * (0.1 + 0.26 * abp_i)
        abp_y0 = abp_s * (0.85 - 0.25 * abp_i)
        abp_path.lineTo(abp_x0, abp_y0 - abp_s * 0.25)
        abp_path.lineTo(abp_x0 + abp_s * 0.26, abp_y0 - abp_s * 0.25)
    abp_p.setPen(abp__pen(abp_STAIR_COLOR, abp_s * 0.11))
    abp_p.drawPath(abp_path)


def abp__area(abp_color: QColor, abp_alpha: int) -> abpPainter:
    def abp_paint(abp_p: QPainter, abp_s: float) -> None:
        abp_fill = QColor(abp_color)
        abp_fill.setAlpha(abp_alpha)
        abp_p.setPen(abp__pen(abp_color, abp_s * 0.08))
        abp_p.setBrush(QBrush(abp_fill))
        abp_p.drawRoundedRect(
            QRectF(abp_s * 0.15, abp_s * 0.2, abp_s * 0.7, abp_s * 0.6), abp_s * 0.08, abp_s * 0.08
        )

    return abp_paint


def abp__background(abp_p: QPainter, abp_s: float) -> None:
    abp_p.setPen(abp__pen("#7a8696", abp_s * 0.07))
    abp_p.setBrush(QBrush(QColor("#eef2f7")))
    abp_p.drawRoundedRect(
        QRectF(abp_s * 0.1, abp_s * 0.18, abp_s * 0.8, abp_s * 0.64), abp_s * 0.06, abp_s * 0.06
    )
    abp_p.setPen(abp__pen("#7a8696", abp_s * 0.07))
    abp_p.drawLine(QPointF(abp_s * 0.1, abp_s * 0.5), QPointF(abp_s * 0.55, abp_s * 0.5))
    abp_p.drawLine(QPointF(abp_s * 0.55, abp_s * 0.18), QPointF(abp_s * 0.55, abp_s * 0.82))


def abp__sign(abp_kind: abpSignKind) -> abpPainter:
    def abp_paint(abp_p: QPainter, abp_s: float) -> None:
        abp_art = abp_SIGNS[abp_kind]
        abp_xs = [
            abs(abp_x) for abp_shape in abp_art.abp_shapes for abp_x, _ in abp_shape.abp_points
        ]
        abp_ys = [
            abs(abp_y) for abp_shape in abp_art.abp_shapes for _, abp_y in abp_shape.abp_points
        ]
        abp_p.save()
        abp_p.translate(abp_s / 2, abp_s / 2)
        abp_k = 0.46 * abp_s / max(*abp_xs, *abp_ys, 0.5)
        abp_p.scale(abp_k, abp_k)
        abp_paint_sign(abp_p, abp_art, "N")
        abp_p.restore()

    return abp_paint


def abp_sign_icon(abp_kind: str, abp_size: int = 22) -> QIcon:
    return abp__icon(abp__sign(abpSignKind(abp_kind)), abp_size)


def abp__select(abp_p: QPainter, abp_s: float) -> None:
    abp_path = QPainterPath(QPointF(abp_s * 0.25, abp_s * 0.1))
    abp_path.lineTo(abp_s * 0.25, abp_s * 0.82)
    abp_path.lineTo(abp_s * 0.43, abp_s * 0.64)
    abp_path.lineTo(abp_s * 0.57, abp_s * 0.92)
    abp_path.lineTo(abp_s * 0.68, abp_s * 0.86)
    abp_path.lineTo(abp_s * 0.55, abp_s * 0.59)
    abp_path.lineTo(abp_s * 0.8, abp_s * 0.58)
    abp_path.closeSubpath()
    abp_p.setPen(abp__pen(abp_theme.abp_TEXT, abp_s * 0.06))
    abp_p.setBrush(QBrush(QColor("#ffffff")))
    abp_p.drawPath(abp_path)


abp__ELEMENT_PAINTERS: dict[abpElementType | None, abpPainter] = {
    None: abp__background,
    abpElementType.abp_WALL: abp__wall,
    abpElementType.abp_DOOR: abp__door,
    abpElementType.abp_EXIT: abp__exit,
    abpElementType.abp_STAIR: abp__stair,
    abpElementType.abp_OBSTACLE: abp__area(abp_OBSTACLE_COLOR, 160),
    abpElementType.abp_SAFE_ZONE: abp__area(abp_SAFE_ZONE_COLOR, 90),
    abpElementType.abp_SIGN: abp__sign(abpSignKind.abp_DIRECTION),
}


def abp_element_icon(abp_kind: abpElementType | None, abp_size: int = 20) -> QIcon:
    return abp__icon(abp__ELEMENT_PAINTERS[abp_kind], abp_size)


def abp__identify(abp_p: QPainter, abp_s: float) -> None:
    abp_p.setPen(abp__pen(abp_theme.abp_PRIMARY, abp_s * 0.09))
    abp_p.setBrush(Qt.BrushStyle.NoBrush)
    abp_p.drawEllipse(QPointF(abp_s * 0.42, abp_s * 0.42), abp_s * 0.28, abp_s * 0.28)
    abp_p.drawLine(QPointF(abp_s * 0.63, abp_s * 0.63), QPointF(abp_s * 0.88, abp_s * 0.88))
    abp_p.setBrush(QBrush(QColor(abp_theme.abp_PRIMARY)))
    abp_p.drawEllipse(QPointF(abp_s * 0.42, abp_s * 0.42), abp_s * 0.06, abp_s * 0.06)


def abp_identify_icon(abp_size: int = 20) -> QIcon:
    return abp__icon(abp__identify, abp_size)


def abp_select_icon(abp_size: int = 20) -> QIcon:
    return abp__icon(abp__select, abp_size)


def abp_step_icon(
    abp_state: abpStepState, abp_number: int, abp_enabled: bool = True, abp_size: int = 22
) -> QIcon:
    def abp_paint(abp_p: QPainter, abp_s: float) -> None:
        abp_rect = QRectF(abp_s * 0.06, abp_s * 0.06, abp_s * 0.88, abp_s * 0.88)
        abp_font = QFont()
        abp_font.setBold(True)
        abp_font.setPixelSize(round(abp_s * 0.55))
        abp_p.setFont(abp_font)
        abp_rect = QRectF(abp_s * 0.12, abp_s * 0.12, abp_s * 0.76, abp_s * 0.76)
        if abp_state is abpStepState.abp_DONE and abp_enabled:
            abp_p.setPen(Qt.PenStyle.NoPen)
            abp_p.setBrush(QBrush(QColor(abp_theme.abp_TEXT)))
            abp_p.drawRect(abp_rect)
            abp_p.setPen(QColor("#ffffff"))
            abp_p.drawText(abp_rect, Qt.AlignmentFlag.AlignCenter, str(abp_number))
        elif abp_state is abpStepState.abp_WARNING and abp_enabled:
            abp_p.setPen(abp__pen(abp_theme.abp_TEXT, abp_s * 0.1))
            abp_p.setBrush(QBrush(QColor("#ffffff")))
            abp_p.drawRect(abp_rect)
            abp_p.setPen(QColor(abp_theme.abp_TEXT))
            abp_p.drawText(abp_rect, Qt.AlignmentFlag.AlignCenter, "!")
        else:
            abp_color = QColor(
                abp_theme.abp_SIDEBAR_MUTED if abp_enabled else abp_theme.abp_SIDEBAR_DISABLED
            )
            abp_p.setPen(abp__pen(abp_color, abp_s * 0.06))
            abp_p.setBrush(Qt.BrushStyle.NoBrush)
            abp_p.drawRect(abp_rect)
            abp_p.setPen(abp_color)
            abp_p.drawText(abp_rect, Qt.AlignmentFlag.AlignCenter, str(abp_number))

    return abp__icon(abp_paint, abp_size)
