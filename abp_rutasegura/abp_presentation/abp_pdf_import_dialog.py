from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_plan_import import (
    abp_rotate_point,
    abpLoadedPlan,
    abpPdfPage,
    abpPlanImportService,
    abpRect,
)
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpSign
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import abpPlanScene
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView, abpTool
from abp_rutasegura.abp_presentation.abp_qt_support import abp_run_in_background, abp_to_pixmap
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted, abp_section_title
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpPdfTexts

abp_THUMB = 150
abp_HANDLE = 12


def abp__kinds(abp_signs: Sequence[abpSign]) -> str:
    abp_counts = Counter(abp_SIGNS[abp_s.abp_kind].abp_label for abp_s in abp_signs)
    return ", ".join(f"{abp_n} {abp_label}" for abp_label, abp_n in abp_counts.most_common(6))


def abp__scale_text(abp_loaded: abpLoadedPlan, abp_info: abpPdfPage) -> str:
    abp_vector = abp_loaded.abp_vector
    abp_value = (
        abp_vector.abp_scale_denominator
        if abp_vector is not None
        else abp_info.abp_scale_denominator
    )
    return f"{abp_value:.4g}" if abp_value is not None else "?"


def abp__turned_rect(
    abp_rect: abpRect | None, abp_w: float, abp_h: float, abp_turns: int
) -> abpRect | None:
    if abp_rect is None:
        return None
    abp_a = abp_rotate_point(abpPoint(abp_rect[0], abp_rect[1]), abp_w, abp_h, abp_turns)
    abp_b = abp_rotate_point(abpPoint(abp_rect[2], abp_rect[3]), abp_w, abp_h, abp_turns)
    return (
        min(abp_a.abp_x, abp_b.abp_x),
        min(abp_a.abp_y, abp_b.abp_y),
        max(abp_a.abp_x, abp_b.abp_x),
        max(abp_a.abp_y, abp_b.abp_y),
    )


class abp__Handle(QGraphicsRectItem):
    def __init__(self, abp_frame: abpCropFrame, abp_index: int) -> None:
        super().__init__(-abp_HANDLE / 2, -abp_HANDLE / 2, abp_HANDLE, abp_HANDLE, abp_frame)
        self.abp__frame = abp_frame
        self.abp__index = abp_index
        self.setBrush(QBrush(QColor("#202020")))
        self.setPen(QPen(QColor("white"), 1.5))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, abp_event: QGraphicsSceneMouseEvent) -> None:
        abp_event.accept()

    def mouseMoveEvent(self, abp_event: QGraphicsSceneMouseEvent) -> None:
        self.abp__frame.abp_move_corner(self.abp__index, abp_event.scenePos())


class abpCropFrame(QGraphicsPathItem):
    def __init__(self, abp_bounds: QRectF) -> None:
        super().__init__()
        self.abp__bounds = abp_bounds
        self.abp__rect = QRectF(abp_bounds)
        self.setBrush(QBrush(QColor(20, 40, 50, 110)))
        abp_pen = QPen(QColor("#202020"), 2)
        abp_pen.setCosmetic(True)
        self.setPen(abp_pen)
        self.setZValue(300)
        self.abp__handles = [abp__Handle(self, abp_i) for abp_i in range(4)]
        self.abp_set_rect(abp_bounds)

    @property
    def abp_rect(self) -> QRectF:
        return QRectF(self.abp__rect)

    def abp_set_rect(self, abp_rect: QRectF) -> None:
        self.abp__rect = abp_rect.normalized().intersected(self.abp__bounds)
        abp_path = QPainterPath()
        abp_path.addRect(self.abp__bounds)
        abp_path.addRect(self.abp__rect)
        self.setPath(abp_path)
        abp_r = self.abp__rect
        abp_corners = (abp_r.topLeft(), abp_r.topRight(), abp_r.bottomRight(), abp_r.bottomLeft())
        for abp_handle, abp_corner in zip(self.abp__handles, abp_corners, strict=True):
            abp_handle.setPos(abp_corner)

    def abp_move_corner(self, abp_index: int, abp_point: QPointF) -> None:
        abp_r = QRectF(self.abp__rect)
        if abp_index in (0, 3):
            abp_r.setLeft(min(abp_point.x(), abp_r.right() - 60))
        else:
            abp_r.setRight(max(abp_point.x(), abp_r.left() + 60))
        if abp_index in (0, 1):
            abp_r.setTop(min(abp_point.y(), abp_r.bottom() - 60))
        else:
            abp_r.setBottom(max(abp_point.y(), abp_r.top() + 60))
        self.abp_set_rect(abp_r)


class abpPdfImportDialog(QDialog):
    abp_preview_ready = Signal()

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_path: Path,
        *,
        abp_page: int = 0,
        abp_texts: abpPdfTexts = abp_TEXTS.abp_pdf,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__path = abp_path
        self.abp__texts = abp_texts
        self.abp__loaded: abpLoadedPlan | None = None
        self.abp__frame: abpCropFrame | None = None
        self.abp__request = 0
        self.abp__suggested: abpRect | None = None
        self.abp_pages: tuple[abpPdfPage, ...] = abp_plans.abp_pdf_pages(abp_path)
        self.setWindowTitle(abp_texts.abp_title.format(name=abp_path.name))
        self.resize(1180, 760)

        self.abp_page_list = QListWidget()
        self.abp_page_list.setIconSize(QSize(abp_THUMB, abp_THUMB))
        self.abp_page_list.setSpacing(4)
        self.abp_page_list.setWordWrap(True)
        self.abp_page_list.setMinimumWidth(250)
        for abp_info in self.abp_pages:
            abp_item = QListWidgetItem(self.abp__page_text(abp_info))
            abp_item.setIcon(
                QIcon(
                    abp_to_pixmap(
                        abp_plans.abp_pdf_thumbnail(abp_path, abp_info.abp_number, abp_THUMB)
                    )
                )
            )
            self.abp_page_list.addItem(abp_item)

        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_view.abp_set_tool(abpTool.abp_NONE)
        self.abp_info_label = QLabel()
        self.abp_info_label.setWordWrap(True)
        self.abp_clean_check = QCheckBox(abp_texts.abp_clean)
        self.abp_clean_check.setToolTip(abp_texts.abp_clean_tip)
        self.abp_crop_check = QCheckBox(abp_texts.abp_crop)
        self.abp_crop_check.setToolTip(abp_texts.abp_crop_tip)
        self.abp_crop_check.setChecked(True)
        self.abp_crop_button = QPushButton(abp_texts.abp_crop_auto)
        self.abp__turns = 0
        self.abp_rotate_left_button = QPushButton(abp_texts.abp_rotate_left)
        self.abp_rotate_right_button = QPushButton(abp_texts.abp_rotate_right)
        for abp_button, abp_turns in (
            (self.abp_rotate_left_button, 3),
            (self.abp_rotate_right_button, 1),
        ):
            abp_button.setToolTip(abp_texts.abp_rotate_tip)
            abp_button.clicked.connect(
                lambda abp__checked=False, abp_n=abp_turns: self.abp_rotate(abp_n)
            )
        self.abp_layers = QListWidget()
        self.abp_layers.setToolTip(abp_texts.abp_layers_tip)

        abp_side = QWidget()
        abp_side_layout = QVBoxLayout(abp_side)
        abp_side_layout.setContentsMargins(0, 0, 0, 0)
        abp_side_layout.addWidget(self.abp_info_label)
        abp_side_layout.addWidget(self.abp_clean_check)
        abp_row = QHBoxLayout()
        abp_row.addWidget(self.abp_crop_check)
        abp_row.addWidget(self.abp_crop_button)
        abp_side_layout.addLayout(abp_row)
        abp_turn_row = QHBoxLayout()
        abp_turn_row.addWidget(self.abp_rotate_left_button)
        abp_turn_row.addWidget(self.abp_rotate_right_button)
        abp_side_layout.addLayout(abp_turn_row)
        abp_side_layout.addWidget(abp_section_title(abp_texts.abp_layers))
        abp_side_layout.addWidget(abp_muted(abp_texts.abp_layers_help))
        abp_side_layout.addWidget(self.abp_layers, stretch=1)

        abp_splitter = QSplitter()
        abp_splitter.addWidget(self.abp_page_list)
        abp_splitter.addWidget(self.abp_view)
        abp_splitter.addWidget(abp_side)
        abp_splitter.setStretchFactor(1, 1)
        abp_splitter.setSizes([260, 620, 280])
        abp_buttons = QDialogButtonBox()
        self.abp_ok_button = abp_set_primary(QPushButton(abp_texts.abp_accept))
        abp_buttons.addButton(self.abp_ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        abp_buttons.addButton(QDialogButtonBox.StandardButton.Cancel).setText(abp_texts.abp_cancel)
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_muted(abp_texts.abp_help))
        abp_layout.addWidget(abp_splitter, stretch=1)
        abp_layout.addWidget(abp_buttons)

        self.abp_page_list.currentRowChanged.connect(self.abp__on_page)
        self.abp_clean_check.toggled.connect(lambda _: self.abp__reload())
        self.abp_layers.itemChanged.connect(lambda _: self.abp__reload())
        self.abp_crop_check.toggled.connect(self.abp__on_crop_toggled)
        self.abp_crop_button.clicked.connect(self.abp_reset_crop)
        self.abp_page_list.setCurrentRow(min(abp_page, len(self.abp_pages) - 1))

    @property
    def abp_page(self) -> abpPdfPage:
        return self.abp_pages[max(self.abp_page_list.currentRow(), 0)]

    @property
    def abp_loaded(self) -> abpLoadedPlan | None:
        return self.abp__loaded

    def abp_hidden_layers(self) -> tuple[str, ...]:
        abp_items = (self.abp_layers.item(abp_i) for abp_i in range(self.abp_layers.count()))
        return tuple(
            str(abp_i.data(Qt.ItemDataRole.UserRole))
            for abp_i in abp_items
            if abp_i is not None and abp_i.checkState() != Qt.CheckState.Checked
        )

    def abp_crop_rect(self) -> abpRect | None:
        if self.abp__frame is None or not self.abp_crop_check.isChecked():
            return None
        abp_r = self.abp__frame.abp_rect
        return (abp_r.left(), abp_r.top(), abp_r.right(), abp_r.bottom())

    def abp_set_crop(self, abp_rect: abpRect) -> None:
        if self.abp__frame is not None:
            self.abp__frame.abp_set_rect(QRectF(QPointF(*abp_rect[:2]), QPointF(*abp_rect[2:])))

    def abp_result_plan(self) -> abpLoadedPlan | None:
        abp_rect = self.abp_crop_rect()
        if self.abp__loaded is None or abp_rect is None:
            return self.abp__loaded
        return self.abp__plans.abp_crop(self.abp__loaded, abp_rect)

    def abp_rotate(self, abp_turns: int) -> None:
        if self.abp__loaded is None:
            return
        abp_rect = self.abp_crop_rect()
        abp_h, abp_w = self.abp__loaded.abp_image.shape[:2]
        self.abp__turns = (self.abp__turns + abp_turns) % 4
        self.abp__loaded = self.abp__plans.abp_rotate(self.abp__loaded, abp_turns)
        self.abp__suggested = abp__turned_rect(self.abp__suggested, abp_w, abp_h, abp_turns)
        self.abp__show_loaded(abp_new_page=False)
        if abp_rect is not None:
            abp_turned = abp__turned_rect(abp_rect, abp_w, abp_h, abp_turns)
            if abp_turned is not None:
                self.abp_set_crop(abp_turned)
        self.abp_view.abp_fit_all()

    def abp__page_text(self, abp_info: abpPdfPage) -> str:
        abp_t = self.abp__texts
        abp_lines = [abp_t.abp_page.format(number=abp_info.abp_number + 1)]
        if abp_info.abp_title:
            abp_lines.append(
                abp_info.abp_title.capitalize()
                if abp_info.abp_title.isupper()
                else abp_info.abp_title
            )
        abp_details = []
        if abp_info.abp_level is not None:
            abp_details.append(abp_t.abp_level.format(number=abp_info.abp_level + 1))
        if abp_info.abp_scale_denominator is not None:
            abp_details.append(abp_t.abp_scale.format(n=f"{abp_info.abp_scale_denominator:.4g}"))
        if not abp_info.abp_is_vector:
            abp_details.append(abp_t.abp_scanned)
        if abp_details:
            abp_lines.append(" · ".join(abp_details))
        return "\n".join(abp_lines)

    def abp__on_page(self, abp__row: int) -> None:
        abp_info = self.abp_page
        self.abp_layers.blockSignals(True)
        self.abp_layers.clear()
        abp_suggested = set(self.abp__plans.abp_suggested_hidden_layers(abp_info))
        for abp_name in abp_info.abp_layers:
            abp_item = QListWidgetItem(abp_name or self.abp__texts.abp_no_layer)
            abp_item.setData(Qt.ItemDataRole.UserRole, abp_name)
            abp_item.setFlags(abp_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            abp_hidden = abp_name in abp_suggested
            abp_item.setCheckState(Qt.CheckState.Unchecked if abp_hidden else Qt.CheckState.Checked)
            self.abp_layers.addItem(abp_item)
        self.abp_layers.blockSignals(False)
        self.abp_clean_check.blockSignals(True)
        self.abp_clean_check.setChecked(abp_info.abp_is_vector and bool(abp_info.abp_kind))
        self.abp_clean_check.blockSignals(False)
        self.abp__suggested = None
        self.abp__turns = 0
        self.abp__reload(abp_new_page=True)

    def abp__reload(self, *, abp_new_page: bool = False) -> None:
        self.abp__request += 1
        abp_request, abp_number = self.abp__request, self.abp_page.abp_number
        abp_hidden, abp_clean = self.abp_hidden_layers(), self.abp_clean_check.isChecked()
        abp_path, abp_plans = self.abp__path, self.abp__plans
        abp_new_page = abp_new_page or self.abp__loaded is None
        abp_turns = self.abp__turns
        self.abp_ok_button.setEnabled(False)
        self.abp_info_label.setText(self.abp__texts.abp_loading)

        def abp_work() -> tuple[int, bool, abpLoadedPlan, abpRect | None]:
            abp_loaded = abp_plans.abp_load_pdf_page(
                abp_path, abp_number, abp_hidden_layers=abp_hidden, abp_remove_colors=abp_clean
            )
            abp_loaded = abp_plans.abp_rotate(abp_loaded, abp_turns)
            return (
                abp_request,
                abp_new_page,
                abp_loaded,
                abp_plans.abp_suggest_crop(abp_loaded) if abp_new_page else None,
            )

        abp_run_in_background(abp_work, self.abp__on_loaded, self.abp__on_failed)

    def abp__on_loaded(self, abp_result: tuple[int, bool, abpLoadedPlan, abpRect | None]) -> None:
        abp_request, abp_new_page, abp_loaded, abp_suggested = abp_result
        if abp_request != self.abp__request:
            return
        self.abp__loaded = abp_loaded
        if abp_new_page:
            self.abp__suggested = abp_suggested
        self.abp__show_loaded(abp_new_page=abp_new_page)
        abp_straight = self.abp__plans.abp_suggested_turns(abp_loaded) if abp_new_page else 0
        if abp_straight:
            self.abp_rotate(abp_straight)
        self.abp_preview_ready.emit()

    def abp__show_loaded(self, *, abp_new_page: bool) -> None:
        abp_loaded = self.abp__loaded
        if abp_loaded is None:
            return
        abp_previous = self.abp__frame.abp_rect if self.abp__frame is not None else None
        if self.abp__frame is not None:
            self.abp_scene.removeItem(self.abp__frame)
        self.abp_scene.abp_set_image(abp_loaded.abp_image)
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]
        self.abp__frame = abpCropFrame(QRectF(0, 0, abp_w, abp_h))
        self.abp_scene.addItem(self.abp__frame)
        if abp_new_page:
            self.abp_reset_crop()
        elif abp_previous is not None:
            self.abp__frame.abp_set_rect(abp_previous)
        self.abp__frame.setVisible(self.abp_crop_check.isChecked())
        self.abp_ok_button.setEnabled(True)
        self.abp__show_info()
        if abp_new_page:
            self.abp_view.abp_fit_all()

    def abp__on_failed(self, abp_message: str) -> None:
        self.abp_info_label.setText(abp_message)
        self.abp_preview_ready.emit()

    def abp__on_crop_toggled(self, abp_checked: bool) -> None:
        self.abp_crop_button.setEnabled(abp_checked)
        if self.abp__frame is not None:
            self.abp__frame.setVisible(abp_checked)

    def abp_reset_crop(self) -> None:
        if self.abp__frame is None or self.abp__loaded is None:
            return
        abp_h, abp_w = self.abp__loaded.abp_image.shape[:2]
        self.abp_set_crop(self.abp__suggested or (0.0, 0.0, float(abp_w), float(abp_h)))

    def abp__show_info(self) -> None:
        abp_t, abp_info = self.abp__texts, self.abp_page
        abp_lines = [f"<b>{abp_t.abp_page.format(number=abp_info.abp_number + 1)}</b>"]
        abp_lines.append(
            abp_t.abp_info_vector if abp_info.abp_is_vector else abp_t.abp_info_scanned
        )
        abp_loaded = self.abp__loaded
        if abp_loaded is not None and abp_loaded.abp_scale_m_per_px is not None:
            abp_lines.append(abp_t.abp_info_scale.format(n=abp__scale_text(abp_loaded, abp_info)))
            if abp_loaded.abp_written_scale is not None:
                abp_real = abp__scale_text(abp_loaded, abp_info)
                abp_lines.append(
                    abp_t.abp_scale_fixed.format(
                        written=f"{abp_loaded.abp_written_scale:g}", real=abp_real
                    )
                )
        else:
            abp_lines.append(abp_t.abp_info_no_scale)
        abp_labels = (
            self.abp__plans.abp_room_labels(abp_loaded.abp_vector) if abp_loaded is not None else ()
        )
        if abp_labels:
            abp_names = ", ".join(abp_q.abp_name for abp_q in abp_labels[:6])
            abp_lines.append(abp_t.abp_info_rooms.format(count=len(abp_labels), names=abp_names))
        if abp_loaded is not None and abp_loaded.abp_signs:
            abp_lines.append(
                abp_t.abp_info_signs.format(
                    count=len(abp_loaded.abp_signs), kinds=abp__kinds(abp_loaded.abp_signs)
                )
            )
        if abp_info.abp_kind:
            abp_lines.append(abp_t.abp_info_kind)
        self.abp_info_label.setText("<br>".join(abp_lines))

    def accept(self) -> None:
        try:
            self.abp_result_plan()
        except abpUserFacingError as abp_exc:
            self.abp_info_label.setText(abp_exc.abp_message)
            return
        super().accept()
