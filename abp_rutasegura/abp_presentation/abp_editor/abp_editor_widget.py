from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Any

import numpy as np
import numpy.typing as npt
import shiboken6
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_identify import (
    abp_accept_door,
    abp_confirm,
    abp_CONVERSIONS,
    abp_convert,
    abp_FIELDS,
    abp_identify,
    abp_pending,
    abp_review_items,
    abpReviewItem,
)
from abp_rutasegura.abp_application.abp_nodes import (
    abp_clean_plan,
    abp_connected_ends,
    abp_move_node,
    abp_node_at,
    abp_plan_nodes,
    abp_set_length,
    abp_snap_point,
)
from abp_rutasegura.abp_application.abp_plan_editing import abp_snap_opening
from abp_rutasegura.abp_application.abp_plan_import import abpPlanElement, abpVectorPlan
from abp_rutasegura.abp_domain.abp_enums import abpElementType, abpSignKind, abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpSafeZone,
    abpSign,
    abpStair,
    abpWall,
)
from abp_rutasegura.abp_presentation.abp_editor.abp_review_bar import abpReviewBar
from abp_rutasegura.abp_presentation.abp_editor.abp_scene import (
    abp_sign_size_px,
    abpElementRef,
    abpPlanScene,
)
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpPlanView, abpTool
from abp_rutasegura.abp_presentation.abp_icons import (
    abp_element_icon,
    abp_identify_icon,
    abp_select_icon,
    abp_sign_icon,
)
from abp_rutasegura.abp_presentation.abp_widgets import abp_muted
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpEditorTexts

abp_TOOL_KIND = {
    abpTool.abp_WALL: abpElementType.abp_WALL,
    abpTool.abp_DOOR: abpElementType.abp_DOOR,
    abpTool.abp_EXIT: abpElementType.abp_EXIT,
    abpTool.abp_STAIR: abpElementType.abp_STAIR,
    abpTool.abp_OBSTACLE: abpElementType.abp_OBSTACLE,
    abpTool.abp_SAFE_ZONE: abpElementType.abp_SAFE_ZONE,
    abpTool.abp_SIGN: abpElementType.abp_SIGN,
}

abp_TOOL_SHORTCUTS = {
    abpTool.abp_SELECT: "V",
    abpTool.abp_WALL: "M",
    abpTool.abp_DOOR: "P",
    abpTool.abp_EXIT: "S",
    abpTool.abp_STAIR: "E",
    abpTool.abp_OBSTACLE: "O",
    abpTool.abp_SAFE_ZONE: "Z",
    abpTool.abp_SIGN: "N",
    abpTool.abp_IDENTIFY: "I",
}
abp_IDENTIFIABLE = (
    abpElementType.abp_OBSTACLE,
    abpElementType.abp_EXIT,
    abpElementType.abp_DOOR,
    abpElementType.abp_STAIR,
    abpElementType.abp_SAFE_ZONE,
)
abp_RENAMABLE = frozenset(
    {
        abpElementType.abp_EXIT,
        abpElementType.abp_STAIR,
        abpElementType.abp_SAFE_ZONE,
        abpElementType.abp_OBSTACLE,
    }
)
abp_LINEAR = frozenset({abpElementType.abp_WALL, abpElementType.abp_DOOR, abpElementType.abp_EXIT})
abp_SNAP_PIXELS = 10.0
abp_NODE_PIXELS = 8.0


def abp__qp(abp_point: abpPoint) -> QPointF:
    return QPointF(abp_point.abp_x, abp_point.abp_y)


def abp__pt(abp_point: QPointF) -> abpPoint:
    return abpPoint(abp_point.x(), abp_point.y())


abp__FIELD = abp_FIELDS


class abp__ReplacePlan(QUndoCommand):
    def __init__(
        self,
        abp_editor: abpPlanEditor,
        abp_before: abpFloorPlan,
        abp_after: abpFloorPlan,
        abp_text: str,
    ) -> None:
        super().__init__(abp_text)
        self.abp__editor = abp_editor
        self.abp__before = abp_before
        self.abp__after = abp_after

    def redo(self) -> None:
        self.abp__editor.abp__show(self.abp__after)

    def undo(self) -> None:
        self.abp__editor.abp__show(self.abp__before)


def abp_next_exit_name(abp_plan: abpFloorPlan, abp_template: str) -> str:
    abp_used = {abp_e.abp_name for abp_e in abp_plan.abp_exits}
    abp_number = 1
    while abp_template.format(number=abp_number) in abp_used:
        abp_number += 1
    return abp_template.format(number=abp_number)


def abp_next_stair_name(abp_plan: abpFloorPlan, abp_template: str) -> str:
    abp_used = {abp_s.abp_name for abp_s in abp_plan.abp_stairs}
    for abp_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        abp_name = abp_template.format(letter=abp_letter)
        if abp_name not in abp_used:
            return abp_name
    return abp_template.format(letter=str(len(abp_plan.abp_stairs) + 1))


class abpPlanEditor(QWidget):
    abp_plan_changed = Signal(object)
    abp_error = Signal(str)
    abp_notice = Signal(str)

    def __init__(
        self, abp_texts: abpEditorTexts = abp_TEXTS.abp_editor, abp_parent: QWidget | None = None
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.abp__plan = abpFloorPlan()
        self.abp__image: npt.NDArray[np.uint8] | None = None
        self.abp__vector: abpVectorPlan | None = None
        self.abp__review_done = 0
        self.abp__review_skipped: set[abpElementRef] = set()
        self.abp_undo_stack = QUndoStack(self)
        self.abp_scene = abpPlanScene(self)
        self.abp_view = abpPlanView(self.abp_scene)
        self.abp_view.abp_segment_drawn.connect(self.abp__on_segment)
        self.abp_view.abp_area_drawn.connect(self.abp__on_area)
        self.abp_view.abp_delete_requested.connect(self.abp_delete_selected)
        self.abp_view.abp_context_menu_requested.connect(self.abp__on_context_menu)
        self.abp_view.abp_double_clicked.connect(self.abp__on_double_click)
        self.abp_view.abp_node_moved.connect(self.abp__on_node_moved)
        self.abp_view.abp_point_picked.connect(self.abp__on_point)
        self.abp_view.abp_snapper = self.abp__snap
        self.abp_view.abp_node_finder = self.abp__find_node
        self.abp_view.abp_length_formatter = self.abp_format_length
        self.abp_scene.selectionChanged.connect(self.abp__update_actions)
        self.abp__build_ui()
        self.abp_set_tool(abpTool.abp_SELECT)

    def abp__build_ui(self) -> None:
        abp_t = self.abp__texts
        self.abp_toolbar = QToolBar()
        self.abp_toolbar.setIconSize(QSize(18, 18))
        self.abp_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.abp_tool_actions: dict[abpTool, QAction] = {}
        abp_group = QActionGroup(self)
        abp_group.setExclusive(True)
        for abp_tool, abp_label, abp_tip in (
            (abpTool.abp_SELECT, abp_t.abp_tool_select, abp_t.abp_tip_select),
            (abpTool.abp_IDENTIFY, abp_t.abp_tool_identify, abp_t.abp_tip_identify),
            (abpTool.abp_WALL, abp_t.abp_tool_wall, abp_t.abp_tip_wall),
            (abpTool.abp_DOOR, abp_t.abp_tool_door, abp_t.abp_tip_door),
            (abpTool.abp_EXIT, abp_t.abp_tool_exit, abp_t.abp_tip_exit),
            (abpTool.abp_STAIR, abp_t.abp_tool_stair, abp_t.abp_tip_stair),
            (abpTool.abp_OBSTACLE, abp_t.abp_tool_obstacle, abp_t.abp_tip_obstacle),
            (abpTool.abp_SAFE_ZONE, abp_t.abp_tool_safe_zone, abp_t.abp_tip_safe_zone),
            (abpTool.abp_SIGN, abp_t.abp_tool_sign, abp_t.abp_tip_sign),
        ):
            abp_kind = abp_TOOL_KIND.get(abp_tool)
            abp_icon = abp_element_icon(abp_kind) if abp_kind is not None else abp_select_icon()
            if abp_tool is abpTool.abp_IDENTIFY:
                abp_icon = abp_identify_icon()
            abp_action = QAction(abp_icon, abp_label, self)
            abp_action.setCheckable(True)
            abp_key = abp_TOOL_SHORTCUTS[abp_tool]
            abp_action.setShortcut(QKeySequence(abp_key))
            abp_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            abp_action.setToolTip(abp_t.abp_tip_shortcut.format(tip=abp_tip, key=abp_key))
            abp_action.triggered.connect(lambda _=False, abp_tl=abp_tool: self.abp_set_tool(abp_tl))
            abp_group.addAction(abp_action)
            self.abp_toolbar.addAction(abp_action)
            self.addAction(abp_action)
            self.abp_tool_actions[abp_tool] = abp_action
        self.abp__sign_kind = abpSignKind.abp_EXIT
        self.abp_sign_combo = QComboBox()
        for abp_sign_kind, abp_art in abp_SIGNS.items():
            self.abp_sign_combo.addItem(
                abp_sign_icon(abp_sign_kind), abp_art.abp_label, abp_sign_kind
            )
        self.abp_sign_combo.setToolTip(abp_t.abp_sign_combo_tip)
        self.abp_sign_combo.currentIndexChanged.connect(self.abp__on_sign_kind)
        self.abp_sign_combo.setVisible(False)
        self.abp_sign_combo_action = self.abp_toolbar.addWidget(self.abp_sign_combo)
        self.abp_identify_combo = QComboBox()
        for abp_kind in abp_IDENTIFIABLE:
            abp_label = dict(abp_t.abp_kind_names).get(abp_kind.value, abp_kind.value)
            self.abp_identify_combo.addItem(abp_element_icon(abp_kind), abp_label, abp_kind.value)
        self.abp_identify_combo.setToolTip(abp_t.abp_identify_combo_tip)
        self.abp_identify_combo_action = self.abp_toolbar.addWidget(self.abp_identify_combo)
        self.abp_toolbar.addSeparator()
        self.abp_delete_action = QAction(abp_t.abp_delete, self)
        self.abp_delete_action.triggered.connect(self.abp_delete_selected)
        self.abp_confirm_action = QAction(abp_t.abp_confirm_exit, self)
        self.abp_confirm_action.triggered.connect(self.abp_confirm_selected_exits)
        self.abp_confirm_all_action = QAction(abp_t.abp_confirm_all, self)
        self.abp_confirm_all_action.triggered.connect(self.abp_confirm_all_exits)
        self.abp_confirm_menu = QMenu(self)
        self.abp_confirm_kind_actions: dict[abpElementType | None, QAction] = {}
        for abp_kind_or_all, abp_label in (
            (abpElementType.abp_EXIT, abp_t.abp_confirm_exits),
            (abpElementType.abp_STAIR, abp_t.abp_confirm_stairs),
            (abpElementType.abp_OBSTACLE, abp_t.abp_confirm_obstacles),
            (None, abp_t.abp_confirm_everything),
        ):
            abp_entry = self.abp_confirm_menu.addAction(abp_label)
            abp_entry.triggered.connect(
                lambda _=False, abp_k=abp_kind_or_all: self.abp_confirm_kind(abp_k)
            )
            self.abp_confirm_kind_actions[abp_kind_or_all] = abp_entry
        self.abp_confirm_all_action.setMenu(self.abp_confirm_menu)
        self.abp_undo_action = self.abp_undo_stack.createUndoAction(self, abp_t.abp_undo)
        self.abp_undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.abp_redo_action = self.abp_undo_stack.createRedoAction(self, abp_t.abp_redo)
        self.abp_redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        abp_fit_action = QAction(abp_t.abp_fit, self)
        abp_fit_action.triggered.connect(self.abp_view.abp_fit_all)
        for abp_action in (
            self.abp_delete_action,
            self.abp_confirm_all_action,
        ):
            self.abp_toolbar.addAction(abp_action)

        self.abp_aids_bar = QToolBar()
        self.abp_snap_action = self.abp__toggle(
            abp_t.abp_snap, abp_t.abp_snap_tip, "F3", abp_checked=True
        )
        self.abp_ortho_action = self.abp__toggle(
            abp_t.abp_ortho, abp_t.abp_ortho_tip, "F8", abp_checked=False
        )
        self.abp_ortho_action.toggled.connect(
            lambda abp_on: setattr(self.abp_view, "abp_ortho", abp_on)
        )
        self.abp_nodes_action = self.abp__toggle(
            abp_t.abp_show_nodes, abp_t.abp_show_nodes_tip, "", abp_checked=True
        )
        self.abp_nodes_action.toggled.connect(lambda abp__on: self.abp__refresh_nodes())
        self.abp_clean_action = QAction(abp_t.abp_clean, self)
        self.abp_clean_action.setToolTip(abp_t.abp_clean_tip)
        self.abp_clean_action.triggered.connect(self.abp_clean)
        for abp_action in (self.abp_snap_action, self.abp_ortho_action, self.abp_nodes_action):
            self.abp_aids_bar.addAction(abp_action)
        self.abp_aids_bar.addSeparator()
        self.abp_aids_bar.addAction(self.abp_clean_action)
        self.abp_aids_bar.addSeparator()
        for abp_action in (self.abp_undo_action, self.abp_redo_action, abp_fit_action):
            self.abp_aids_bar.addAction(abp_action)

        self.abp_properties_box = QGroupBox(abp_t.abp_properties)
        abp_form = QFormLayout(self.abp_properties_box)
        self.abp_kind_label = QLabel()
        self.abp_length_spin = QDoubleSpinBox()
        self.abp_length_spin.setRange(0.01, 100_000.0)
        self.abp_length_spin.setDecimals(2)
        self.abp_length_spin.setKeyboardTracking(False)
        self.abp_length_spin.setToolTip(abp_t.abp_prop_hint)
        self.abp_length_spin.editingFinished.connect(self.abp__on_length_edited)
        self.abp_name_edit = QLineEdit()
        self.abp_name_edit.editingFinished.connect(self.abp__on_name_edited)
        abp_form.addRow(abp_t.abp_prop_kind, self.abp_kind_label)
        abp_form.addRow(abp_t.abp_prop_length, self.abp_length_spin)
        abp_form.addRow(abp_t.abp_prop_name, self.abp_name_edit)
        self.abp_rotation_spin = QDoubleSpinBox()
        self.abp_rotation_spin.setRange(-360.0, 360.0)
        self.abp_rotation_spin.setDecimals(0)
        self.abp_rotation_spin.setSingleStep(45.0)
        self.abp_rotation_spin.setSuffix("°")
        self.abp_rotation_spin.setWrapping(True)
        self.abp_rotation_spin.valueChanged.connect(self.abp__on_rotation_edited)
        self.abp_sign_text_edit = QLineEdit()
        self.abp_sign_text_edit.editingFinished.connect(self.abp__on_sign_text_edited)
        abp_form.addRow(abp_t.abp_prop_rotation, self.abp_rotation_spin)
        abp_form.addRow(abp_t.abp_prop_sign_text, self.abp_sign_text_edit)
        self.abp_properties_box.setVisible(False)

        abp_layers = QGroupBox(abp_t.abp_legend_title)
        abp_layers.setObjectName("legend")
        abp_layers_layout = QVBoxLayout(abp_layers)
        self.abp_layer_boxes: dict[abpElementType | None, QCheckBox] = {}
        for abp_kind, abp_label in (
            (None, abp_t.abp_layer_background),
            (abpElementType.abp_WALL, abp_t.abp_layer_walls),
            (abpElementType.abp_DOOR, abp_t.abp_layer_doors),
            (abpElementType.abp_EXIT, abp_t.abp_layer_exits),
            (abpElementType.abp_STAIR, abp_t.abp_layer_stairs),
            (abpElementType.abp_OBSTACLE, abp_t.abp_layer_obstacles),
            (abpElementType.abp_SAFE_ZONE, abp_t.abp_layer_safe_zones),
            (abpElementType.abp_SIGN, abp_t.abp_layer_signs),
        ):
            abp_box = QCheckBox(abp_label)
            abp_box.setIcon(abp_element_icon(abp_kind))
            abp_box.setChecked(True)
            abp_box.toggled.connect(
                lambda abp_checked, abp_k=abp_kind: self.abp_scene.abp_set_layer_visible(
                    abp_k, abp_checked
                )
            )
            abp_layers_layout.addWidget(abp_box)
            self.abp_layer_boxes[abp_kind] = abp_box
        abp_layers_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        self.abp_hint_label = abp_muted()
        self.abp_pending_label = QLabel()
        self.abp_pending_label.setWordWrap(True)
        self.abp_pending_label.setStyleSheet("font-weight: bold;")
        abp_side = QVBoxLayout()
        self.abp_review_button = QPushButton(abp_t.abp_review_start)
        self.abp_review_button.setToolTip(abp_t.abp_review_tip)
        self.abp_review_button.clicked.connect(self.abp_start_review)
        abp_side.addWidget(self.abp_review_button)
        abp_side.addWidget(self.abp_properties_box)
        abp_side.addWidget(abp_layers)
        abp_side.addWidget(abp_muted(abp_t.abp_legend_dashed))
        abp_side.addWidget(abp_muted(abp_t.abp_legend_low))
        abp_side.addWidget(self.abp_pending_label)
        abp_side.addWidget(self.abp_hint_label)
        abp_side.addStretch(1)
        abp_side_widget = QWidget()
        abp_side.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        abp_side_widget.setLayout(abp_side)
        abp_side_area = QScrollArea()
        abp_side_area.setWidget(abp_side_widget)
        abp_side_area.setWidgetResizable(True)
        abp_side_area.setFrameShape(QFrame.Shape.NoFrame)
        abp_side_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        abp_side_area.setFixedWidth(262)

        abp_canvas = QVBoxLayout()
        abp_canvas.setSpacing(4)
        self.abp_review_bar = abpReviewBar(abp_t)
        self.abp_review_bar.abp_answered.connect(self.abp__on_review_answer)
        self.abp_review_bar.setVisible(False)
        abp_canvas.addWidget(self.abp_review_bar)
        abp_canvas.addWidget(self.abp_view, stretch=1)
        abp_canvas.addWidget(self.abp_aids_bar)
        abp_body = QHBoxLayout()
        abp_body.addLayout(abp_canvas, stretch=1)
        abp_body.addWidget(abp_side_area)
        abp_root = QVBoxLayout(self)
        abp_root.setContentsMargins(0, 0, 0, 0)
        abp_root.setSpacing(6)
        abp_root.addWidget(self.abp_toolbar)
        abp_root.addLayout(abp_body)

    def abp__toggle(
        self, abp_label: str, abp_tip: str, abp_key: str, *, abp_checked: bool
    ) -> QAction:
        abp_action = QAction(abp_label, self)
        abp_action.setCheckable(True)
        abp_action.setChecked(abp_checked)
        abp_action.setToolTip(abp_tip)
        if abp_key:
            abp_action.setShortcut(QKeySequence(abp_key))
            abp_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(abp_action)
        return abp_action

    def abp_set_tool(self, abp_tool: abpTool) -> None:
        self.abp_view.abp_set_tool(abp_tool)
        self.abp__refresh_nodes()
        if abp_tool in self.abp_tool_actions:
            self.abp_tool_actions[abp_tool].setChecked(True)
        self.abp_sign_combo_action.setVisible(abp_tool is abpTool.abp_SIGN)
        self.abp_identify_combo_action.setVisible(abp_tool is abpTool.abp_IDENTIFY)
        abp_t = self.abp__texts
        if abp_tool is abpTool.abp_SELECT:
            abp_hint = abp_t.abp_hint_select
        elif abp_tool in (abpTool.abp_STAIR, abpTool.abp_OBSTACLE, abpTool.abp_SAFE_ZONE):
            abp_hint = abp_t.abp_hint_area
        elif abp_tool is abpTool.abp_SIGN:
            abp_hint = abp_t.abp_hint_sign
        elif abp_tool is abpTool.abp_IDENTIFY:
            abp_hint = abp_t.abp_hint_identify
        else:
            abp_hint = abp_t.abp_hint_segment
        self.abp_hint_label.setText(f"{abp_hint}\n\n{abp_t.abp_hint_zoom}")

    def abp__update_actions(self) -> None:
        if not shiboken6.isValid(self.abp_scene):
            return
        abp_refs = self.abp_scene.abp_selected_refs()
        self.abp_delete_action.setEnabled(bool(abp_refs))
        self.abp__update_properties(abp_refs)
        self.abp_confirm_action.setEnabled(
            any(
                abp_kind is abpElementType.abp_EXIT
                and not self.abp__plan.abp_exits[abp_i].abp_confirmed
                for abp_kind, abp_i in abp_refs
                if abp_kind is abpElementType.abp_EXIT and abp_i < len(self.abp__plan.abp_exits)
            )
        )

    def abp_plan(self) -> abpFloorPlan:
        return self.abp__plan

    def abp_set_plan(self, abp_plan: abpFloorPlan, abp_image: npt.NDArray[np.uint8] | None) -> None:
        self.abp_undo_stack.clear()
        self.abp_scene.abp_set_image(abp_image)
        self.abp__show(abp_plan)
        self.abp_view.abp_fit_all()

    def abp_apply(self, abp_new_plan: abpFloorPlan, abp_text: str) -> None:
        if abp_new_plan != self.abp__plan:
            self.abp_undo_stack.push(abp__ReplacePlan(self, self.abp__plan, abp_new_plan, abp_text))

    def abp__show(self, abp_plan: abpFloorPlan) -> None:
        self.abp__plan = abp_plan
        self.abp_scene.abp_render_plan(abp_plan)
        abp_waiting = abp_pending(abp_plan)
        abp_exits = sum(
            1 for abp_kind, abp__i in abp_waiting if abp_kind is abpElementType.abp_EXIT
        )
        abp_lines = [self.abp__texts.abp_pending_exits.format(count=abp_exits)] if abp_exits else []
        abp_others = len(abp_waiting) - abp_exits
        if abp_others:
            abp_lines.append(self.abp__texts.abp_pending_others.format(count=abp_others))
        self.abp_pending_label.setText("\n".join(abp_lines))
        self.abp_confirm_all_action.setEnabled(bool(abp_waiting))
        for abp_kind_or_all, abp_entry in self.abp_confirm_kind_actions.items():
            abp_entry.setEnabled(
                any(abp_kind_or_all in (None, abp_kind) for abp_kind, abp__i in abp_waiting)
            )
        self.abp_review_button.setEnabled(bool(abp_review_items(abp_plan)))
        self.abp_scene.abp_render_nodes(
            [(abp_p.abp_x, abp_p.abp_y) for abp_p in abp_plan_nodes(abp_plan)]
        )
        self.abp__refresh_nodes()
        self.abp__update_actions()
        self.abp_plan_changed.emit(abp_plan)

    def abp_add_segment(self, abp_kind: abpElementType, abp_segment: abpSegment) -> None:
        abp_plan = self.abp__plan
        abp_t = self.abp__texts
        if abp_kind is abpElementType.abp_WALL:
            abp_new = dataclasses.replace(
                abp_plan, abp_walls=(*abp_plan.abp_walls, abpWall(abp_segment))
            )
            abp_what = abp_t.abp_tool_wall
        elif abp_kind is abpElementType.abp_DOOR:
            abp_snap = abp_snap_opening(abp_plan, abp_segment)
            abp_new = dataclasses.replace(
                abp_plan,
                abp_walls=abp_snap.abp_walls,
                abp_doors=(*abp_plan.abp_doors, abpDoor(abp_snap.abp_opening)),
            )
            abp_what = abp_t.abp_tool_door
        elif abp_kind is abpElementType.abp_EXIT:
            abp_snap = abp_snap_opening(abp_plan, abp_segment)
            abp_name = abp_next_exit_name(abp_plan, abp_t.abp_exit_name)
            abp_new = dataclasses.replace(
                abp_plan,
                abp_walls=abp_snap.abp_walls,
                abp_exits=(*abp_plan.abp_exits, abpExit(abp_snap.abp_opening, abp_name)),
            )
            abp_what = abp_t.abp_tool_exit
        else:
            raise ValueError(f"{abp_kind} no se dibuja como segmento.")
        self.abp_apply(abp_new, abp_t.abp_cmd_add.format(what=abp_what.lower()))

    def abp_add_area(self, abp_kind: abpElementType, abp_area: abpPolygon) -> None:
        abp_plan = self.abp__plan
        abp_t = self.abp__texts
        if abp_kind is abpElementType.abp_STAIR:
            abp_stair = abpStair(
                abp_area, abp_name=abp_next_stair_name(abp_plan, abp_t.abp_stair_name)
            )
            abp_new = dataclasses.replace(abp_plan, abp_stairs=(*abp_plan.abp_stairs, abp_stair))
            abp_what = abp_t.abp_tool_stair
        elif abp_kind is abpElementType.abp_OBSTACLE:
            abp_new = dataclasses.replace(
                abp_plan, abp_obstacles=(*abp_plan.abp_obstacles, abpObstacle(abp_area))
            )
            abp_what = abp_t.abp_tool_obstacle
        elif abp_kind is abpElementType.abp_SAFE_ZONE:
            abp_new = dataclasses.replace(
                abp_plan, abp_safe_zones=(*abp_plan.abp_safe_zones, abpSafeZone(abp_area))
            )
            abp_what = abp_t.abp_tool_safe_zone
        else:
            raise ValueError(f"{abp_kind} no se dibuja como área.")
        self.abp_apply(abp_new, abp_t.abp_cmd_add.format(what=abp_what.lower()))

    def abp_add_sign(
        self, abp_kind: abpSignKind, abp_position: abpPoint, abp_rotation_deg: float = 0.0
    ) -> None:
        abp_text = ""
        if abp_kind is abpSignKind.abp_CAPACITY:
            abp_text = "—"
        abp_sign = abpSign(abp_kind, abp_position, abp_rotation_deg, abp_text)
        abp_new = dataclasses.replace(
            self.abp__plan, abp_signs=(*self.abp__plan.abp_signs, abp_sign)
        )
        self.abp_apply(
            abp_new, self.abp__texts.abp_cmd_add.format(what=abp_SIGNS[abp_kind].abp_label.lower())
        )

    def abp__change_sign(self, abp_index: int, **abp_changes: Any) -> None:
        abp_signs = tuple(
            dataclasses.replace(abp_s, **abp_changes) if abp_i == abp_index else abp_s
            for abp_i, abp_s in enumerate(self.abp__plan.abp_signs)
        )
        self.abp_apply(
            dataclasses.replace(self.abp__plan, abp_signs=abp_signs), self.abp__texts.abp_cmd_sign
        )
        self.abp_scene.abp_select_only((abpElementType.abp_SIGN, abp_index))

    def abp_delete(self, abp_refs: Iterable[abpElementRef]) -> None:
        abp_to_delete: dict[abpElementType, set[int]] = {}
        for abp_kind, abp_index in abp_refs:
            abp_to_delete.setdefault(abp_kind, set()).add(abp_index)
        if not abp_to_delete:
            return
        abp_changes: dict[str, Any] = {
            abp__FIELD[abp_kind]: tuple(
                abp_el
                for abp_i, abp_el in enumerate(getattr(self.abp__plan, abp__FIELD[abp_kind]))
                if abp_i not in abp_indices
            )
            for abp_kind, abp_indices in abp_to_delete.items()
        }
        abp_count = sum(len(abp_v) for abp_v in abp_to_delete.values())
        self.abp_apply(
            dataclasses.replace(self.abp__plan, **abp_changes),
            self.abp__texts.abp_cmd_delete.format(count=abp_count),
        )

    def abp_delete_selected(self) -> None:
        self.abp_delete(self.abp_scene.abp_selected_refs())

    def abp_confirm_exits(self, abp_indices: Iterable[int]) -> None:
        abp_wanted = {abp_i for abp_i in abp_indices if 0 <= abp_i < len(self.abp__plan.abp_exits)}
        abp_pending = {
            abp_i for abp_i in abp_wanted if not self.abp__plan.abp_exits[abp_i].abp_confirmed
        }
        if not abp_pending:
            return
        abp_exits = tuple(
            dataclasses.replace(abp_e, abp_confirmed=True) if abp_i in abp_pending else abp_e
            for abp_i, abp_e in enumerate(self.abp__plan.abp_exits)
        )
        self.abp_apply(
            dataclasses.replace(self.abp__plan, abp_exits=abp_exits),
            self.abp__texts.abp_cmd_confirm.format(count=len(abp_pending)),
        )

    def abp_confirm_all_exits(self) -> None:
        self.abp_confirm_exits(range(len(self.abp__plan.abp_exits)))

    def abp_confirm_kind(self, abp_kind: abpElementType | None) -> None:
        abp_refs = (
            abp_pending(self.abp__plan)
            if abp_kind is None
            else abp_pending(self.abp__plan, (abp_kind,))
        )
        if abp_refs:
            self.abp_apply(
                abp_confirm(self.abp__plan, abp_refs),
                self.abp__texts.abp_cmd_confirm.format(count=len(abp_refs)),
            )

    def abp_set_sources(
        self, abp_image: npt.NDArray[np.uint8] | None, abp_vector: abpVectorPlan | None
    ) -> None:
        self.abp__image, self.abp__vector = abp_image, abp_vector

    def abp_identify_at(self, abp_point: abpPoint, abp_kind: abpElementType) -> bool:
        abp_t = self.abp__texts
        if not self.abp__plan.abp_is_scaled:
            self.abp_error.emit(abp_t.abp_identify_no_scale)
            return False
        abp_new = abp_identify(
            self.abp__plan,
            abp_point,
            abp_kind,
            abp_image=self.abp__image,
            abp_vector=self.abp__vector,
        )
        abp_name = dict(abp_t.abp_kind_names).get(abp_kind.value, abp_kind.value).lower()
        if abp_new is None:
            self.abp_notice.emit(abp_t.abp_identify_nothing.format(kind=abp_name))
            return False
        self.abp_apply(abp_new, abp_t.abp_cmd_identify.format(kind=abp_name))
        self.abp_notice.emit(abp_t.abp_identify_done.format(kind=abp_name))
        return True

    def abp_convert_element(self, abp_ref: abpElementRef, abp_kind: abpElementType) -> None:
        abp_names = dict(self.abp__texts.abp_kind_names)
        self.abp_apply(
            abp_convert(self.abp__plan, abp_ref, abp_kind),
            self.abp__texts.abp_cmd_convert.format(
                kind=abp_names.get(abp_kind.value, abp_kind.value).lower()
            ),
        )

    def abp_highlight(self, abp_element: abpPlanElement | None) -> None:
        abp_points = (
            [abp__qp(abp_p) for abp_p in abp_element.abp_points] if abp_element is not None else []
        )
        self.abp_scene.abp_show_highlight(abp_points)
        if not abp_points:
            return
        abp_xs, abp_ys = [abp_p.x() for abp_p in abp_points], [abp_p.y() for abp_p in abp_points]
        abp_center = QPointF((min(abp_xs) + max(abp_xs)) / 2, (min(abp_ys) + max(abp_ys)) / 2)
        abp_extra = (
            2.0 / self.abp__plan.abp_scale_m_per_px if self.abp__plan.abp_scale_m_per_px else 120.0
        )
        self.abp_view.abp_zoom_to(
            abp_center, max(max(abp_xs) - min(abp_xs), max(abp_ys) - min(abp_ys)) / 2 + abp_extra
        )

    def abp_show_area(self, abp_area: abpPolygon) -> None:
        self.abp_highlight(abpPlanElement("escalera", "", abp_area.abp_vertices, ""))

    def abp_start_review(self) -> None:
        self.abp__review_done = 0
        self.abp__review_skipped = set()
        self.abp__show_review()

    def abp__review_queue(self) -> list[abpReviewItem]:
        return [
            abp_i
            for abp_i in abp_review_items(self.abp__plan)
            if abp_i.abp_ref not in self.abp__review_skipped
        ]

    def abp__show_review(self) -> None:
        abp_queue = self.abp__review_queue()
        if not abp_queue:
            self.abp_review_bar.setVisible(False)
            self.abp_notice.emit(
                self.abp__texts.abp_review_finished.format(count=self.abp__review_done)
            )
            self.abp_scene.clearSelection()
            self.abp_view.abp_fit_all()
            return
        abp_item = abp_queue[0]
        abp_kind = abp_item.abp_ref[0]
        self.abp_review_bar.abp_show_item(
            abp_kind,
            self.abp__review_done + 1,
            self.abp__review_done + len(abp_queue),
            abp_CONVERSIONS.get(abp_kind, ()),
        )
        self.abp_review_bar.setVisible(True)
        self.abp_set_tool(abpTool.abp_SELECT)
        self.abp_scene.abp_select_only(abp_item.abp_ref)
        self.abp_view.abp_zoom_to(abp__qp(abp_item.abp_center), abp_item.abp_reach)

    def abp__on_review_answer(self, abp_answer: str) -> None:
        abp_queue = self.abp__review_queue()
        if abp_answer == "fin" or not abp_queue:
            self.abp_review_bar.setVisible(False)
            self.abp_view.abp_fit_all()
            return
        abp_ref = abp_queue[0].abp_ref
        abp_kind, abp_index = abp_ref
        self.abp__review_done += 1
        if abp_answer == "si":
            abp_new = (
                abp_accept_door(self.abp__plan, abp_index)
                if abp_kind is abpElementType.abp_DOOR
                else abp_confirm(self.abp__plan, [abp_ref])
            )
            self.abp_apply(abp_new, self.abp__texts.abp_cmd_confirm.format(count=1))
        elif abp_answer == "no":
            self.abp__review_skipped = {
                (abp_k, abp_i - 1 if abp_k is abp_kind and abp_i > abp_index else abp_i)
                for abp_k, abp_i in self.abp__review_skipped
            }
            if abp_kind in (abpElementType.abp_DOOR, abpElementType.abp_EXIT):
                self.abp_convert_element(abp_ref, abpElementType.abp_WALL)
            else:
                self.abp_delete([abp_ref])
        elif abp_answer == "saltar":
            self.abp__review_skipped.add(abp_ref)
        elif abp_answer == "todos":
            self.abp__review_done += (
                sum(1 for abp_item in abp_queue if abp_item.abp_ref[0] is abp_kind) - 1
            )
            self.abp_confirm_kind(abp_kind)
        else:
            self.abp__review_skipped = {
                (abp_k, abp_i - 1 if abp_k is abp_kind and abp_i > abp_index else abp_i)
                for abp_k, abp_i in self.abp__review_skipped
            }
            self.abp_convert_element(abp_ref, abpElementType(abp_answer))
        self.abp__show_review()

    def abp_confirm_selected_exits(self) -> None:
        self.abp_confirm_exits(
            abp_i
            for abp_kind, abp_i in self.abp_scene.abp_selected_refs()
            if abp_kind is abpElementType.abp_EXIT
        )

    def abp_rename(self, abp_ref: abpElementRef, abp_name: str) -> bool:
        abp_kind, abp_index = abp_ref
        abp_t = self.abp__texts
        abp_name = abp_name.strip()
        if abp_kind not in abp_RENAMABLE or not 0 <= abp_index < len(
            getattr(self.abp__plan, abp__FIELD[abp_kind])
        ):
            return False
        if not abp_name:
            self.abp_error.emit(abp_t.abp_name_empty)
            return False
        abp_elements = getattr(self.abp__plan, abp__FIELD[abp_kind])
        abp_unique = abp_kind is not abpElementType.abp_OBSTACLE
        if abp_unique and any(
            abp_el.abp_name == abp_name
            for abp_i, abp_el in enumerate(abp_elements)
            if abp_i != abp_index
        ):
            self.abp_error.emit(abp_t.abp_name_in_use.format(name=abp_name))
            return False
        if abp_elements[abp_index].abp_name == abp_name:
            return True
        abp_changes: dict[str, Any] = {
            abp__FIELD[abp_kind]: tuple(
                dataclasses.replace(abp_el, abp_name=abp_name) if abp_i == abp_index else abp_el
                for abp_i, abp_el in enumerate(abp_elements)
            )
        }
        self.abp_apply(
            dataclasses.replace(self.abp__plan, **abp_changes),
            abp_t.abp_cmd_rename.format(name=abp_name),
        )
        return True

    def abp_set_stair_use(self, abp_index: int, abp_use: abpStairUse) -> None:
        abp_stairs = list(self.abp__plan.abp_stairs)
        if abp_stairs[abp_index].abp_use is abp_use:
            return
        abp_stairs[abp_index] = dataclasses.replace(abp_stairs[abp_index], abp_use=abp_use)
        self.abp_apply(
            dataclasses.replace(self.abp__plan, abp_stairs=tuple(abp_stairs)),
            self.abp__texts.abp_menu_stair_use,
        )

    def abp_ask_rename(self, abp_ref: abpElementRef) -> None:
        abp_kind, abp_index = abp_ref
        abp_current = getattr(self.abp__plan, abp__FIELD[abp_kind])[abp_index].abp_name
        abp_t = self.abp__texts
        abp_name, abp_ok = QInputDialog.getText(
            self,
            abp_t.abp_rename_title,
            abp_t.abp_rename_label,
            QLineEdit.EchoMode.Normal,
            abp_current,
        )
        if abp_ok:
            self.abp_rename(abp_ref, abp_name)

    def abp_context_menu(self, abp_ref: abpElementRef) -> QMenu:
        abp_t = self.abp__texts
        abp_kind = abp_ref[0]
        abp_menu = QMenu(self)
        if abp_ref in abp_pending(self.abp__plan):
            abp_label = (
                abp_t.abp_menu_confirm
                if abp_kind is abpElementType.abp_EXIT
                else abp_t.abp_menu_confirm_other
            )
            abp_menu.addAction(abp_label).triggered.connect(
                lambda: self.abp_apply(
                    abp_confirm(self.abp__plan, [abp_ref]),
                    self.abp__texts.abp_cmd_confirm.format(count=1),
                )
            )
        abp_names = dict(abp_t.abp_kind_names)
        for abp_other in abp_CONVERSIONS.get(abp_kind, ()):
            abp_label = abp_t.abp_menu_convert.format(
                kind=abp_names.get(abp_other.value, abp_other.value).lower()
            )
            abp_menu.addAction(abp_label).triggered.connect(
                lambda _=False, abp_k=abp_other: self.abp_convert_element(abp_ref, abp_k)
            )
        if abp_kind is abpElementType.abp_STAIR:
            abp_uses = abp_menu.addMenu(abp_t.abp_menu_stair_use)
            for abp_value, abp_label in abp_t.abp_stair_uses:
                abp_use = abpStairUse(abp_value)
                abp_action = abp_uses.addAction(abp_label)
                abp_action.setCheckable(True)
                abp_action.setChecked(self.abp__plan.abp_stairs[abp_ref[1]].abp_use is abp_use)
                abp_action.triggered.connect(
                    lambda _=False, abp_u=abp_use: self.abp_set_stair_use(abp_ref[1], abp_u)
                )
        if abp_kind in abp_RENAMABLE:
            abp_menu.addAction(abp_t.abp_menu_rename).triggered.connect(
                lambda: self.abp_ask_rename(abp_ref)
            )
        abp_menu.addSeparator()
        abp_menu.addAction(abp_t.abp_menu_delete).triggered.connect(
            lambda: self.abp_delete([abp_ref])
        )
        return abp_menu

    def abp__on_context_menu(self, abp_global_pos: QPoint, abp_scene_pos: QPointF) -> None:
        abp_ref = self.abp_scene.abp_ref_at(abp_scene_pos, self.abp_view.abp_scene_tolerance())
        if abp_ref is None:
            return
        self.abp_scene.abp_select_only(abp_ref)
        self.abp_context_menu(abp_ref).exec(abp_global_pos)

    def abp__on_double_click(self, abp_scene_pos: QPointF) -> None:
        abp_ref = self.abp_scene.abp_ref_at(abp_scene_pos, self.abp_view.abp_scene_tolerance())
        if abp_ref is None:
            return
        abp_kind = abp_ref[0]
        if abp_ref in abp_pending(self.abp__plan):
            self.abp_apply(
                abp_confirm(self.abp__plan, [abp_ref]),
                self.abp__texts.abp_cmd_confirm.format(count=1),
            )
        elif abp_kind in abp_RENAMABLE:
            self.abp_ask_rename(abp_ref)

    def abp_format_length(self, abp_length_px: float) -> str:
        abp_scale = self.abp__plan.abp_scale_m_per_px
        return f"{abp_length_px * abp_scale:.2f} m" if abp_scale else f"{abp_length_px:.0f} px"

    def abp__snap(
        self, abp_point: QPointF, abp_exclude: QPointF | None
    ) -> tuple[QPointF, str] | None:
        if not self.abp_snap_action.isChecked():
            return None
        abp_target = abp_snap_point(
            self.abp__plan,
            abp__pt(abp_point),
            self.abp_view.abp_scene_tolerance(abp_SNAP_PIXELS),
            abp_exclude=None if abp_exclude is None else abp__pt(abp_exclude),
        )
        return (
            None
            if abp_target is None
            else (abp__qp(abp_target.abp_point), abp_target.abp_kind.value)
        )

    def abp__find_node(self, abp_point: QPointF) -> tuple[QPointF, list[QPointF]] | None:
        if (
            not self.abp_nodes_action.isChecked()
            or self.abp_view.abp_tool is not abpTool.abp_SELECT
        ):
            return None
        abp_sign = self.abp__sign_at(abp_point)
        if abp_sign is not None:
            return abp__qp(self.abp__plan.abp_signs[abp_sign].abp_position), []
        abp_node = abp_node_at(
            self.abp__plan, abp__pt(abp_point), self.abp_view.abp_scene_tolerance(abp_NODE_PIXELS)
        )
        if abp_node is None:
            return None
        return abp__qp(abp_node), [
            abp__qp(abp_p) for abp_p in abp_connected_ends(self.abp__plan, abp_node)
        ]

    def abp__refresh_nodes(self) -> None:
        self.abp_scene.abp_set_nodes_visible(
            self.abp_nodes_action.isChecked() and self.abp_view.abp_tool is abpTool.abp_SELECT
        )

    def abp__sign_at(self, abp_point: QPointF) -> int | None:
        if not self.abp_scene.abp_is_layer_visible(abpElementType.abp_SIGN):
            return None
        abp_reach = 0.45 * abp_sign_size_px(self.abp__plan)
        for abp_index in reversed(range(len(self.abp__plan.abp_signs))):
            abp_p = self.abp__plan.abp_signs[abp_index].abp_position
            if (
                abs(abp_p.abp_x - abp_point.x()) <= abp_reach
                and abs(abp_p.abp_y - abp_point.y()) <= abp_reach
            ):
                return abp_index
        return None

    def abp__on_node_moved(self, abp_node: QPointF, abp_to: QPointF) -> None:
        for abp_index, abp_sign in enumerate(self.abp__plan.abp_signs):
            if abp__qp(abp_sign.abp_position) == abp_node:
                self.abp__change_sign(abp_index, abp_position=abp__pt(abp_to))
                return
        self.abp_apply(
            abp_move_node(self.abp__plan, abp__pt(abp_node), abp__pt(abp_to)),
            self.abp__texts.abp_cmd_move_node,
        )

    def abp_clean(self) -> None:
        abp_t = self.abp__texts
        abp_report = abp_clean_plan(self.abp__plan)
        if not abp_report.abp_changed:
            self.abp_notice.emit(abp_t.abp_clean_nothing)
            return
        self.abp_apply(abp_report.abp_plan, abp_t.abp_cmd_clean)
        self.abp_notice.emit(
            abp_t.abp_clean_done.format(
                merged=abp_report.abp_merged,
                joined=abp_report.abp_joined,
                removed=abp_report.abp_removed,
            )
        )

    def abp_set_element_length(self, abp_ref: abpElementRef, abp_value: float) -> None:
        abp_kind, abp_index = abp_ref
        abp_scale = self.abp__plan.abp_scale_m_per_px
        abp_length_px = abp_value / abp_scale if abp_scale else abp_value
        try:
            abp_new = abp_set_length(self.abp__plan, abp_kind, abp_index, abp_length_px)
        except ValueError as abp_exc:
            self.abp_error.emit(str(abp_exc))
            return
        self.abp_apply(abp_new, self.abp__texts.abp_cmd_length)

    def abp__update_properties(self, abp_refs: list[abpElementRef]) -> None:
        if len(abp_refs) != 1:
            self.abp_properties_box.setVisible(False)
            return
        abp_kind, abp_index = abp_refs[0]
        abp_elements = getattr(self.abp__plan, abp__FIELD[abp_kind])
        if abp_index >= len(abp_elements):
            self.abp_properties_box.setVisible(False)
            return
        abp_element = abp_elements[abp_index]
        self.abp_properties_box.setVisible(True)
        self.abp_kind_label.setText(
            dict(self.abp__texts.abp_kind_names).get(abp_kind.value, abp_kind.value)
        )
        abp_linear = abp_kind in abp_LINEAR
        self.abp_length_spin.setVisible(abp_linear)
        abp_form = self.abp_properties_box.layout()
        if isinstance(abp_form, QFormLayout):
            abp_form.setRowVisible(self.abp_length_spin, abp_linear)
            abp_form.setRowVisible(self.abp_name_edit, abp_kind in abp_RENAMABLE)
        if abp_linear:
            abp_scale = self.abp__plan.abp_scale_m_per_px
            self.abp_length_spin.blockSignals(True)
            self.abp_length_spin.setSuffix(" m" if abp_scale else " px")
            abp_length = abp_element.abp_segment.abp_length
            self.abp_length_spin.setValue(abp_length * abp_scale if abp_scale else abp_length)
            self.abp_length_spin.blockSignals(False)
        if abp_kind in abp_RENAMABLE:
            self.abp_name_edit.setText(abp_element.abp_name)
        if isinstance(abp_form, QFormLayout):
            abp_rotates = (
                abp_kind is abpElementType.abp_SIGN and abp_SIGNS[abp_element.abp_kind].abp_rotates
            )
            abp_labelled = (
                abp_kind is abpElementType.abp_SIGN
                and abp_element.abp_kind is abpSignKind.abp_CAPACITY
            )
            abp_form.setRowVisible(self.abp_rotation_spin, abp_rotates)
            abp_form.setRowVisible(self.abp_sign_text_edit, abp_labelled)
        if abp_kind is abpElementType.abp_SIGN:
            self.abp_kind_label.setText(abp_SIGNS[abp_element.abp_kind].abp_label)
            self.abp_rotation_spin.blockSignals(True)
            self.abp_rotation_spin.setValue(abp_element.abp_rotation_deg)
            self.abp_rotation_spin.blockSignals(False)
            self.abp_sign_text_edit.setText(abp_element.abp_text)

    def abp__selected_single(self) -> abpElementRef | None:
        abp_refs = self.abp_scene.abp_selected_refs()
        return abp_refs[0] if len(abp_refs) == 1 else None

    def abp__on_length_edited(self) -> None:
        abp_ref = self.abp__selected_single()
        if abp_ref is None or abp_ref[0] not in abp_LINEAR:
            return
        abp_element = getattr(self.abp__plan, abp__FIELD[abp_ref[0]])[abp_ref[1]]
        abp_scale = self.abp__plan.abp_scale_m_per_px
        abp_current = (
            abp_element.abp_segment.abp_length * abp_scale
            if abp_scale
            else abp_element.abp_segment.abp_length
        )
        if abs(abp_current - self.abp_length_spin.value()) > 0.005:
            self.abp_set_element_length(abp_ref, self.abp_length_spin.value())

    def abp__on_name_edited(self) -> None:
        abp_ref = self.abp__selected_single()
        if abp_ref is not None and abp_ref[0] in abp_RENAMABLE:
            self.abp_rename(abp_ref, self.abp_name_edit.text())

    def abp__on_rotation_edited(self, abp_value: float) -> None:
        abp_ref = self.abp__selected_single()
        if abp_ref is not None and abp_ref[0] is abpElementType.abp_SIGN:
            self.abp__change_sign(abp_ref[1], abp_rotation_deg=abp_value)

    def abp__on_sign_text_edited(self) -> None:
        abp_ref = self.abp__selected_single()
        if abp_ref is not None and abp_ref[0] is abpElementType.abp_SIGN:
            self.abp__change_sign(abp_ref[1], abp_text=self.abp_sign_text_edit.text().strip())

    def abp__on_sign_kind(self, abp__index: int) -> None:
        self.abp__sign_kind = abpSignKind(str(self.abp_sign_combo.currentData()))

    def abp__on_point(self, abp_point: QPointF) -> None:
        if self.abp_view.abp_tool is abpTool.abp_SIGN:
            self.abp_add_sign(self.abp__sign_kind, abp__pt(abp_point))
        elif self.abp_view.abp_tool is abpTool.abp_IDENTIFY:
            self.abp_identify_at(
                abp__pt(abp_point), abpElementType(str(self.abp_identify_combo.currentData()))
            )

    def abp__on_segment(self, abp_tool: abpTool, abp_start: QPointF, abp_end: QPointF) -> None:
        abp_kind = abp_TOOL_KIND.get(abp_tool)
        if abp_kind is not None:
            self.abp_add_segment(
                abp_kind,
                abpSegment(
                    abpPoint(abp_start.x(), abp_start.y()), abpPoint(abp_end.x(), abp_end.y())
                ),
            )

    def abp__on_area(self, abp_tool: abpTool, abp_rect: QRectF) -> None:
        abp_kind = abp_TOOL_KIND.get(abp_tool)
        if abp_kind is not None:
            abp_area = abpPolygon(
                (
                    abpPoint(abp_rect.left(), abp_rect.top()),
                    abpPoint(abp_rect.right(), abp_rect.top()),
                    abpPoint(abp_rect.right(), abp_rect.bottom()),
                    abpPoint(abp_rect.left(), abp_rect.bottom()),
                )
            )
            self.abp_add_area(abp_kind, abp_area)
