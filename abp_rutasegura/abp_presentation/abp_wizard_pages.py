from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QLineF, QMimeData, QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDragEnterEvent, QDropEvent, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_plan_import import (
    abpLoadedPlan,
    abpPlanImportService,
    abpVectorPlan,
)
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSafeZone, abpSign
from abp_rutasegura.abp_presentation.abp_cad_import_dialog import abpCadImportDialog
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import abpPlanScene
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView, abpTool
from abp_rutasegura.abp_presentation.abp_elements_dialog import abpElementsDialog
from abp_rutasegura.abp_presentation.abp_pdf_import_dialog import abpPdfImportDialog
from abp_rutasegura.abp_presentation.abp_qt_support import abp_run_in_background
from abp_rutasegura.abp_presentation.abp_stairs_dialog import abpStairsDialog
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary, abp_SUCCESS, abp_WARNING
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted, abp_page_help, abp_page_title
from abp_rutasegura.abp_resources.abp_texts import (
    abp_TEXTS,
    abpEditorTexts,
    abpPdfTexts,
    abpWizardTexts,
)

abpImage = npt.NDArray[np.uint8]


def abp__marker(abp_point: QPointF, abp_color: str) -> QGraphicsEllipseItem:
    abp_item = QGraphicsEllipseItem(-6, -6, 12, 12)
    abp_item.setPos(abp_point)
    abp_item.setBrush(QBrush(QColor(abp_color)))
    abp_pen = QPen(QColor("white"), 2)
    abp_pen.setCosmetic(True)
    abp_item.setPen(abp_pen)
    abp_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    abp_item.setZValue(500)
    return abp_item


class abpLoadPlanPage(QWidget):
    abp_image_loaded = Signal(object)
    abp_error = Signal(str)

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_texts: abpWizardTexts = abp_TEXTS.abp_wizard,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__texts = abp_texts
        self.abp__path: Path | None = None
        self.abp__image: abpImage | None = None
        self.abp__original: abpImage | None = None
        self.abp__loaded: abpLoadedPlan | None = None
        self.abp__vector: abpVectorPlan | None = None
        self.abp__corners: list[QPointF] = []
        self.abp__markers: list[QGraphicsEllipseItem] = []

        self.abp_choose_button = abp_set_primary(QPushButton(abp_texts.abp_choose_file))
        self.abp_choose_button.clicked.connect(self.abp_choose_file)
        self.abp_file_label = abp_muted(abp_texts.abp_no_file)
        self.abp_page_label = QLabel(abp_texts.abp_page_label)
        self.abp_page_spin = QSpinBox()
        self.abp_page_spin.setMinimum(1)
        self.abp_page_spin.valueChanged.connect(self.abp__on_page_changed)
        self.abp_options_button = QPushButton(abp_TEXTS.abp_pdf.abp_options)
        self.abp_options_button.clicked.connect(self.abp__show_pdf_options)
        self.abp_straighten_button = QPushButton(abp_texts.abp_straighten)
        self.abp_straighten_button.setCheckable(True)
        self.abp_straighten_button.toggled.connect(self.abp__on_straighten_toggled)
        self.abp_undo_straighten_button = QPushButton(abp_texts.abp_straighten_undo)
        self.abp_undo_straighten_button.clicked.connect(self.abp_undo_straighten)
        self.abp_status_label = QLabel()
        self.abp_status_label.setWordWrap(True)

        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_view.abp_point_picked.connect(self.abp_add_corner)
        self.setAcceptDrops(True)
        self.abp_view.setAcceptDrops(False)

        abp_row = QHBoxLayout()
        abp_row.addWidget(self.abp_choose_button)
        abp_row.addWidget(self.abp_file_label)
        abp_row.addStretch(1)
        abp_right: tuple[QWidget, ...] = (
            self.abp_page_label,
            self.abp_page_spin,
            self.abp_options_button,
            self.abp_straighten_button,
            self.abp_undo_straighten_button,
        )
        for abp_widget in abp_right:
            abp_row.addWidget(abp_widget)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_page_title(abp_texts.abp_load_title))
        abp_layout.addWidget(abp_page_help(abp_texts.abp_load_help))
        abp_layout.addLayout(abp_row)
        abp_layout.addWidget(self.abp_status_label)
        abp_layout.addWidget(self.abp_view, stretch=1)
        self.abp__refresh()

    @property
    def abp_image(self) -> abpImage | None:
        return self.abp__image

    @property
    def abp_vector(self) -> abpVectorPlan | None:
        return self.abp__vector

    @property
    def abp_drawn_signs(self) -> tuple[tuple[abpSign, ...], tuple[abpSafeZone, ...]]:
        if self.abp__loaded is None or self.abp__loaded.abp_image is not self.abp__image:
            return (), ()
        return self.abp__loaded.abp_signs, self.abp__loaded.abp_zones

    def abp_set_image(
        self, abp_image: abpImage | None, abp_vector: abpVectorPlan | None = None
    ) -> None:
        self.abp__path = None
        self.abp__original = None
        self.abp__vector = abp_vector
        self.abp__image = abp_image
        self.abp_scene.abp_set_image(abp_image)
        self.abp_file_label.setText("" if abp_image is not None else self.abp__texts.abp_no_file)
        self.abp__refresh()
        self.abp_view.abp_fit_all()

    def dragEnterEvent(self, abp_event: QDragEnterEvent) -> None:
        if self.abp__dropped(abp_event.mimeData()) is not None:
            abp_event.acceptProposedAction()

    def dropEvent(self, abp_event: QDropEvent) -> None:
        abp_path = self.abp__dropped(abp_event.mimeData())
        if abp_path is not None:
            abp_event.acceptProposedAction()
            self.abp_open_any(abp_path)

    def abp__dropped(self, abp_data: QMimeData) -> Path | None:
        for abp_url in abp_data.urls():
            abp_path = Path(abp_url.toLocalFile())
            if abp_path.suffix.lower() in self.abp__plans.abp_supported_suffixes():
                return abp_path
        return None

    def abp_open_any(self, abp_path: Path) -> None:
        if self.abp__plans.abp_is_cad(abp_path):
            self.abp_open_cad(abp_path)
        elif self.abp__plans.abp_is_pdf(abp_path):
            self.abp_open_pdf(abp_path)
        else:
            self.abp_open_file(abp_path)

    def abp_choose_file(self) -> None:
        abp_patterns = " ".join(f"*{abp_s}" for abp_s in self.abp__plans.abp_supported_suffixes())
        abp_filename, _ = QFileDialog.getOpenFileName(
            self,
            self.abp__texts.abp_file_dialog_title,
            "",
            self.abp__texts.abp_file_filter.format(patterns=abp_patterns),
        )
        if not abp_filename:
            return
        self.abp_open_any(Path(abp_filename))

    def abp_open_cad(self, abp_path: Path) -> None:
        abp_dialog = abpCadImportDialog(self.abp__plans, abp_path, abp_parent=self)
        if abp_dialog.exec() == QDialog.DialogCode.Accepted and abp_dialog.abp_pdf_path is not None:
            self.abp_open_pdf(abp_dialog.abp_pdf_path)

    def abp_open_pdf(self, abp_path: Path, abp_page: int = 0) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            abp_dialog = abpPdfImportDialog(
                self.abp__plans, abp_path, abp_page=abp_page, abp_parent=self
            )
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return
        finally:
            QApplication.restoreOverrideCursor()
        if abp_dialog.exec() == QDialog.DialogCode.Accepted:
            abp_loaded = abp_dialog.abp_result_plan()
            if abp_loaded is not None:
                self.abp_use_plan(
                    abp_path, abp_dialog.abp_page.abp_number, len(abp_dialog.abp_pages), abp_loaded
                )

    def abp__show_pdf_options(self) -> None:
        if self.abp__path is not None:
            self.abp_open_pdf(self.abp__path, self.abp_page_spin.value() - 1)

    def abp_open_file(self, abp_path: Path, abp_page: int = 0) -> None:
        try:
            abp_pages = self.abp__plans.abp_page_count(abp_path)
            if self.abp__plans.abp_is_pdf(abp_path):
                abp_loaded = self.abp__plans.abp_load_pdf_page(abp_path, abp_page)
            else:
                abp_loaded = abpLoadedPlan(self.abp__plans.abp_load(abp_path, abp_page))
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return
        self.abp_use_plan(abp_path, abp_page, abp_pages, abp_loaded)

    def abp_use_plan(
        self, abp_path: Path, abp_page: int, abp_pages: int, abp_loaded: abpLoadedPlan
    ) -> None:
        abp_image = abp_loaded.abp_image
        self.abp__path = abp_path
        self.abp_page_spin.blockSignals(True)
        self.abp_page_spin.setMaximum(abp_pages)
        self.abp_page_spin.setValue(abp_page + 1)
        self.abp_page_spin.blockSignals(False)
        self.abp_file_label.setText(abp_path.name)
        self.abp__original = abp_image
        self.abp__loaded = abp_loaded
        self.abp__vector = abp_loaded.abp_vector
        self.abp__set_new_image(abp_image)

    def abp__on_page_changed(self, abp_value: int) -> None:
        if self.abp__path is not None:
            self.abp_open_file(self.abp__path, abp_value - 1)

    def abp__set_new_image(self, abp_image: abpImage) -> None:
        self.abp__image = abp_image
        self.abp_scene.abp_set_image(abp_image)
        self.abp_straighten_button.setChecked(False)
        self.abp__clear_corners()
        self.abp__refresh()
        self.abp_view.abp_fit_all()
        self.abp_image_loaded.emit(abp_image)

    def abp__on_straighten_toggled(self, abp_checked: bool) -> None:
        self.abp__clear_corners()
        self.abp_view.abp_set_tool(abpTool.abp_POINTS if abp_checked else abpTool.abp_NONE)
        self.abp__refresh()

    def abp_add_corner(self, abp_point: QPointF) -> None:
        if not self.abp_straighten_button.isChecked() or self.abp__image is None:
            return
        self.abp__corners.append(abp_point)
        abp_marker = abp__marker(abp_point, "#e74c3c")
        self.abp_scene.addItem(abp_marker)
        self.abp__markers.append(abp_marker)
        if len(self.abp__corners) == 4:
            abp_corners = [abpPoint(abp_p.x(), abp_p.y()) for abp_p in self.abp__corners]
            try:
                abp_straight = self.abp__plans.abp_straighten(self.abp__image, abp_corners)
            except abpUserFacingError as abp_exc:
                self.abp__clear_corners()
                self.abp_error.emit(abp_exc.abp_message)
                return
            if self.abp__original is None:
                self.abp__original = self.abp__image
            self.abp__vector = None
            self.abp__set_new_image(abp_straight)
            return
        self.abp__refresh()

    def abp_undo_straighten(self) -> None:
        if self.abp__original is not None and self.abp__original is not self.abp__image:
            if self.abp__loaded is not None and self.abp__loaded.abp_image is self.abp__original:
                self.abp__vector = self.abp__loaded.abp_vector
            self.abp__set_new_image(self.abp__original)

    def abp__clear_corners(self) -> None:
        for abp_marker in self.abp__markers:
            self.abp_scene.removeItem(abp_marker)
        self.abp__markers.clear()
        self.abp__corners.clear()

    def abp__refresh(self) -> None:
        abp_has_image = self.abp__image is not None
        abp_multi_page = self.abp_page_spin.maximum() > 1 and self.abp__path is not None
        self.abp_page_label.setVisible(abp_multi_page)
        self.abp_page_spin.setVisible(abp_multi_page)
        self.abp_options_button.setVisible(
            self.abp__path is not None and self.abp__plans.abp_is_pdf(self.abp__path)
        )
        self.abp_straighten_button.setEnabled(abp_has_image)
        self.abp_undo_straighten_button.setVisible(
            self.abp__original is not None and self.abp__original is not self.abp__image
        )
        self.abp_status_label.setVisible(self.abp_straighten_button.isChecked())
        if self.abp_straighten_button.isChecked():
            self.abp_status_label.setText(
                self.abp__texts.abp_straighten_help.format(count=len(self.abp__corners))
            )
        else:
            self.abp_status_label.setText("")


class abpScalePage(QWidget):
    abp_scale_changed = Signal(float)
    abp_error = Signal(str)

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_texts: abpWizardTexts = abp_TEXTS.abp_wizard,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__texts = abp_texts
        self.abp__reference: tuple[abpPoint, abpPoint] | None = None
        self.abp__line: QGraphicsLineItem | None = None
        self.abp__scale: float | None = None
        self.abp__sheet_scale: float | None = None
        self.abp__pdf_texts: abpPdfTexts = abp_TEXTS.abp_pdf

        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_view.abp_set_tool(abpTool.abp_MEASURE)
        self.abp_view.abp_segment_drawn.connect(
            lambda abp__tool, abp_a, abp_b: self.abp_set_reference(
                abpPoint(abp_a.x(), abp_a.y()), abpPoint(abp_b.x(), abp_b.y())
            )
        )
        self.abp_meters_spin = QDoubleSpinBox()
        self.abp_meters_spin.setRange(0.01, 1000.0)
        self.abp_meters_spin.setDecimals(2)
        self.abp_meters_spin.setSingleStep(0.1)
        self.abp_meters_spin.setValue(1.0)
        self.abp_meters_spin.setSuffix(" m")
        self.abp_apply_button = abp_set_primary(QPushButton(abp_texts.abp_scale_apply))
        self.abp_apply_button.clicked.connect(self.abp_apply_scale)
        self.abp_result_label = QLabel()
        self.abp_result_label.setWordWrap(True)

        abp_row = QHBoxLayout()
        abp_row.addWidget(QLabel(abp_texts.abp_scale_meters))
        abp_row.addWidget(self.abp_meters_spin)
        abp_row.addWidget(self.abp_apply_button)
        abp_row.addSpacing(12)
        abp_row.addWidget(self.abp_result_label, stretch=1)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_page_title(abp_texts.abp_scale_title))
        abp_layout.addWidget(abp_page_help(abp_texts.abp_scale_help))
        abp_layout.addLayout(abp_row)
        abp_layout.addWidget(self.abp_view, stretch=1)
        self.abp__show_scale()

    @property
    def abp_scale(self) -> float | None:
        return self.abp__scale

    def abp_set_content(
        self,
        abp_image: abpImage | None,
        abp_scale: float | None,
        abp_vector: abpVectorPlan | None = None,
    ) -> None:
        self.abp_scene.abp_set_image(abp_image)
        self.abp__clear_reference()
        self.abp__scale = abp_scale
        abp_printed = self.abp__plans.abp_sheet_scale(abp_vector)
        abp_same = (
            abp_printed is not None
            and abp_scale is not None
            and abs(abp_printed - abp_scale) < 1e-9
        )
        self.abp__sheet_scale = (
            round(abp_printed / 0.0254 * abp_vector.abp_dpi, 1)
            if abp_vector is not None and abp_printed and abp_same
            else None
        )
        self.abp__show_scale()
        self.abp_view.abp_fit_all()

    def abp_set_reference(self, abp_p1: abpPoint, abp_p2: abpPoint) -> None:
        self.abp__clear_reference()
        self.abp__reference = (abp_p1, abp_p2)
        abp_pen = QPen(QColor("#d35400"), 3)
        abp_pen.setCosmetic(True)
        self.abp__line = QGraphicsLineItem(
            QLineF(abp_p1.abp_x, abp_p1.abp_y, abp_p2.abp_x, abp_p2.abp_y)
        )
        self.abp__line.setPen(abp_pen)
        self.abp__line.setZValue(400)
        self.abp_scene.addItem(self.abp__line)
        self.abp__show_scale()

    def abp_apply_scale(self) -> None:
        if self.abp__reference is None:
            self.abp_error.emit(self.abp__texts.abp_scale_draw_first)
            return
        try:
            abp_scale = self.abp__plans.abp_scale_from_reference(
                *self.abp__reference, self.abp_meters_spin.value()
            )
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return
        self.abp__scale = abp_scale
        self.abp__sheet_scale = None
        self.abp__show_scale()
        self.abp_scale_changed.emit(abp_scale)

    def abp__clear_reference(self) -> None:
        if self.abp__line is not None:
            self.abp_scene.removeItem(self.abp__line)
        self.abp__line = None
        self.abp__reference = None

    def abp__show_scale(self) -> None:
        if self.abp__scale:
            abp_text = self.abp__texts.abp_scale_result.format(px_per_m=1.0 / self.abp__scale)
            if self.abp__sheet_scale is not None:
                abp_text = self.abp__pdf_texts.abp_scale_from_sheet.format(
                    n=f"{self.abp__sheet_scale:g}"
                )
            if self.abp__reference is not None:
                abp_a, abp_b = self.abp__reference
                abp_meters = abp_a.abp_distance_to(abp_b) * self.abp__scale
                abp_text += " " + self.abp__pdf_texts.abp_scale_check.format(meters=abp_meters)
            self.abp_result_label.setText(abp_text)
            self.abp_result_label.setStyleSheet(f"color: {abp_SUCCESS}; font-weight: 600;")
        else:
            self.abp_result_label.setText(self.abp__texts.abp_scale_missing)
            self.abp_result_label.setStyleSheet(f"color: {abp_WARNING};")


class abpEditorPage(QWidget):
    abp_error = Signal(str)
    abp_detection_finished = Signal()
    abp_rotate_requested = Signal(int)

    def __init__(
        self,
        abp_plans: abpPlanImportService,
        abp_texts: abpWizardTexts = abp_TEXTS.abp_wizard,
        abp_editor_texts: abpEditorTexts = abp_TEXTS.abp_editor,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__plans = abp_plans
        self.abp__texts = abp_texts
        self.abp__editor_texts = abp_editor_texts
        self.abp__image: abpImage | None = None
        self.abp__vector: abpVectorPlan | None = None
        self.abp_editor = abpPlanEditor(abp_editor_texts)
        self.abp_detect_button = QPushButton(abp_texts.abp_detect)
        self.abp_detect_button.clicked.connect(self.abp_detect)
        self.abp_status_label = abp_muted()
        self.abp_editor.abp_error.connect(self.abp_error)
        self.abp_editor.abp_notice.connect(self.abp_status_label.setText)
        self.abp_diagonal_check = QCheckBox(abp_texts.abp_allow_diagonal)
        self.abp_diagonal_check.setToolTip(abp_texts.abp_allow_diagonal_tip)
        abp_row = QHBoxLayout()
        abp_row.addWidget(self.abp_detect_button)
        self.abp_signs_button = QPushButton(abp_editor_texts.abp_propose_signs)
        self.abp_signs_button.setToolTip(abp_editor_texts.abp_propose_signs_tip)
        self.abp_signs_button.clicked.connect(self.abp_propose_signs)
        self.abp_sign_proposer: Callable[[abpFloorPlan], tuple[abpSign, ...]] | None = None
        abp_row.addWidget(self.abp_signs_button)
        self.abp_elements_button = QPushButton(abp_TEXTS.abp_elements.abp_button)
        self.abp_elements_button.setToolTip(abp_TEXTS.abp_elements.abp_tip)
        self.abp_elements_button.clicked.connect(self.abp_show_elements)
        self.abp_elements_dialog: abpElementsDialog | None = None
        abp_row.addWidget(self.abp_elements_button)
        self.abp_stairs_button = QPushButton(abp_TEXTS.abp_stairs.abp_button)
        self.abp_stairs_button.setToolTip(abp_TEXTS.abp_stairs.abp_tip)
        self.abp_stairs_button.clicked.connect(self.abp_show_stairs)
        self.abp_stairs_dialog: abpStairsDialog | None = None
        self.abp_floors_provider: Callable[[], list[abpFloorPlan]] = list
        abp_row.addWidget(self.abp_stairs_button)
        self.abp_rotate_button = QPushButton(abp_editor_texts.abp_rotate_plan)
        self.abp_rotate_button.setToolTip(abp_editor_texts.abp_rotate_plan_tip)
        self.abp_rotate_button.clicked.connect(lambda: self.abp_rotate_requested.emit(1))
        abp_row.addWidget(self.abp_rotate_button)
        abp_row.addWidget(self.abp_diagonal_check)
        abp_row.addWidget(self.abp_status_label, stretch=1)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(0, 0, 0, 0)
        abp_layout.addWidget(abp_page_title(abp_texts.abp_editor_title))
        abp_layout.addWidget(abp_page_help(abp_texts.abp_editor_help))
        abp_layout.addLayout(abp_row)
        abp_layout.addWidget(self.abp_editor, stretch=1)

    def abp_set_content(
        self,
        abp_plan: abpFloorPlan,
        abp_image: abpImage | None,
        abp_vector: abpVectorPlan | None = None,
    ) -> None:
        self.abp__image = abp_image
        self.abp__vector = abp_vector
        self.abp_editor.abp_set_sources(abp_image, abp_vector)
        self.abp_diagonal_check.setVisible(abp_vector is None)
        self.abp_editor.abp_set_plan(abp_plan, abp_image)
        self.abp_detect_button.setEnabled(abp_image is not None)
        self.abp_status_label.setText("" if abp_image is not None else self.abp__texts.abp_no_image)

    def abp_show_elements(self) -> None:
        if self.abp_elements_dialog is not None:
            self.abp_elements_dialog.close()
        abp_elements = self.abp__plans.abp_inventory(self.abp_editor.abp_plan(), self.abp__vector)
        self.abp_elements_dialog = abpElementsDialog(abp_elements, abp_parent=self)
        self.abp_elements_dialog.abp_picked.connect(self.abp_editor.abp_highlight)
        self.abp_elements_dialog.finished.connect(
            lambda abp__code: self.abp_editor.abp_highlight(None)
        )
        self.abp_elements_dialog.show()

    def abp_show_stairs(self) -> None:
        if self.abp_stairs_dialog is not None:
            self.abp_stairs_dialog.close()
        abp_dialog = abpStairsDialog(
            self.abp_editor,
            self.abp_floors_provider(),
            abp_can_analyze=self.abp__vector is not None
            and bool(self.abp_editor.abp_plan().abp_walls),
            abp_parent=self,
        )
        abp_dialog.abp_analyze_requested.connect(self.abp_analyze_stairs)
        abp_dialog.finished.connect(lambda abp__code: self.abp_editor.abp_highlight(None))
        self.abp_stairs_dialog = abp_dialog
        abp_dialog.show()

    def abp_analyze_stairs(self) -> None:
        abp_plan = self.abp_editor.abp_plan()
        abp_new = self.abp__plans.abp_analyze_stairs(abp_plan, self.abp__vector)
        abp_texts = abp_TEXTS.abp_stairs
        if abp_new == abp_plan:
            self.abp_status_label.setText(abp_texts.abp_analyzed_same)
            return
        self.abp_editor.abp_apply(abp_new, abp_texts.abp_analyze.lower())
        self.abp_status_label.setText(abp_texts.abp_analyzed.format(count=len(abp_new.abp_stairs)))

    def abp_propose_signs(self) -> None:
        if self.abp_sign_proposer is None:
            return
        abp_plan = self.abp_editor.abp_plan()
        try:
            abp_signs = self.abp_sign_proposer(abp_plan)
        except abpUserFacingError as abp_exc:
            self.abp_error.emit(abp_exc.abp_message)
            return
        abp_texts = self.abp__editor_texts
        if not abp_signs:
            self.abp_status_label.setText(abp_texts.abp_propose_signs_none)
            return
        abp_new = dataclasses.replace(abp_plan, abp_signs=(*abp_plan.abp_signs, *abp_signs))
        self.abp_editor.abp_apply(abp_new, abp_texts.abp_propose_signs.lower())
        self.abp_status_label.setText(abp_texts.abp_propose_signs_done.format(count=len(abp_signs)))

    def abp_needs_detection(self) -> bool:
        abp_plan = self.abp_editor.abp_plan()
        return self.abp__image is not None and not (
            abp_plan.abp_walls or abp_plan.abp_doors or abp_plan.abp_exits
        )

    def abp_detect(self) -> None:
        if self.abp__image is None:
            self.abp_error.emit(self.abp__texts.abp_no_image)
            return
        abp_image, abp_plan, abp_vector = (
            self.abp__image,
            self.abp_editor.abp_plan(),
            self.abp__vector,
        )
        self.abp_detect_button.setEnabled(False)
        self.abp_editor.setEnabled(False)
        self.abp_status_label.setText(self.abp__texts.abp_detecting)
        self.setCursor(Qt.CursorShape.BusyCursor)
        abp_diagonal = self.abp_diagonal_check.isChecked()
        abp_run_in_background(
            lambda: self.abp__plans.abp_detect(
                abp_image, abp_plan, abp_allow_diagonal=abp_diagonal, abp_vector=abp_vector
            ),
            self.abp__on_detected,
            self.abp__on_failed,
        )

    def abp__on_detected(self, abp_result: object) -> None:
        self.unsetCursor()
        self.abp_detect_button.setEnabled(True)
        self.abp_editor.setEnabled(True)
        if isinstance(abp_result, abpFloorPlan):
            self.abp_editor.abp_apply(abp_result, self.abp__editor_texts.abp_cmd_detect)
            self.abp_status_label.setText(
                self.abp__texts.abp_detect_done.format(
                    walls=len(abp_result.abp_walls),
                    doors=len(abp_result.abp_doors),
                    exits=len(abp_result.abp_exits),
                    stairs=len(abp_result.abp_stairs),
                    obstacles=len(abp_result.abp_obstacles),
                )
            )
        self.abp_detection_finished.emit()

    def abp__on_failed(self, abp_message: str) -> None:
        self.unsetCursor()
        self.abp_detect_button.setEnabled(True)
        self.abp_editor.setEnabled(True)
        self.abp_status_label.setText("")
        self.abp_error.emit(abp_message)
        self.abp_detection_finished.emit()
