from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpWall
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_editor.abp_view import abpTool


def abp__s(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


abp_CORNER = abpFloorPlan(
    abp_scale_m_per_px=0.02,
    abp_walls=(abpWall(abp__s(100, 100, 300, 100)), abpWall(abp__s(300, 100, 300, 300))),
)


@pytest.fixture
def abp_editor(qtbot: QtBot) -> abpPlanEditor:
    abp_widget = abpPlanEditor()
    qtbot.addWidget(abp_widget)
    abp_widget.resize(1000, 700)
    abp_widget.show()
    qtbot.waitExposed(abp_widget)
    abp_widget.abp_set_plan(abp_CORNER, np.full((400, 400, 3), 255, np.uint8))
    abp_widget.abp_view.abp_fit_all()
    return abp_widget


def abp_test_nodes_are_shown_only_with_select(abp_editor: abpPlanEditor) -> None:
    assert abp_editor.abp_scene.abp_visible_node_count == 3
    abp_editor.abp_set_tool(abpTool.abp_WALL)
    assert abp_editor.abp_scene.abp_visible_node_count == 0
    abp_editor.abp_set_tool(abpTool.abp_SELECT)
    abp_editor.abp_nodes_action.setChecked(False)
    assert abp_editor.abp_scene.abp_visible_node_count == 0


def abp_test_dragging_a_node_moves_the_corner(abp_editor: abpPlanEditor) -> None:
    abp_editor.abp_view.abp_drag_node(QPointF(300, 100), QPointF(320, 80))
    abp_walls = [abp_w.abp_segment for abp_w in abp_editor.abp_plan().abp_walls]
    assert abp_walls == [abp__s(100, 100, 320, 80), abp__s(320, 80, 300, 300)]
    assert abp_editor.abp_undo_stack.undoText() == "Mover nodo"
    abp_editor.abp_undo_stack.undo()
    assert abp_editor.abp_plan() == abp_CORNER


def abp_test_dragged_node_snaps_to_another_node(abp_editor: abpPlanEditor) -> None:
    abp_editor.abp_view.abp_drag_node(QPointF(300, 300), QPointF(101, 101))
    assert abp_editor.abp_plan().abp_walls[1].abp_segment == abp__s(300, 100, 100, 100)


def abp_test_snap_while_drawing_and_length_label(abp_editor: abpPlanEditor) -> None:
    abp_snapped = abp_editor.abp__snap(QPointF(298, 103), None)
    assert abp_snapped is not None
    assert abp_snapped[0] == QPointF(300, 100)
    assert abp_snapped[1] == "nodo"
    abp_editor.abp_snap_action.setChecked(False)
    assert abp_editor.abp__snap(QPointF(298, 103), None) is None
    assert abp_editor.abp_format_length(150) == "3.00 m"


def abp_test_ortho_toggle(abp_editor: abpPlanEditor) -> None:
    abp_editor.abp_ortho_action.setChecked(True)
    assert abp_editor.abp_view.abp_ortho


def abp_test_exact_length_from_the_properties_panel(abp_editor: abpPlanEditor) -> None:
    abp_editor.abp_scene.abp_select_only((abpElementType.abp_WALL, 0))
    assert abp_editor.abp_properties_box.isVisibleTo(abp_editor)
    assert abp_editor.abp_length_spin.value() == pytest.approx(4.0)
    assert abp_editor.abp_length_spin.suffix() == " m"
    abp_editor.abp_length_spin.setValue(5.0)
    abp_editor.abp_length_spin.editingFinished.emit()
    abp_walls = [abp_w.abp_segment for abp_w in abp_editor.abp_plan().abp_walls]
    assert abp_walls[0] == abp__s(100, 100, 350, 100)
    assert abp_walls[1].abp_start == abpPoint(350, 100)


def abp_test_clean_plan_action(abp_editor: abpPlanEditor, qtbot: QtBot) -> None:
    abp_messy = abpFloorPlan(
        abp_scale_m_per_px=0.02,
        abp_walls=(
            abpWall(abp__s(100, 100, 295, 100)),
            abpWall(abp__s(300, 100, 300, 300)),
            abpWall(abp__s(150, 101, 250, 101)),
        ),
    )
    abp_editor.abp_set_plan(abp_messy, None)
    with qtbot.waitSignal(abp_editor.abp_notice) as abp_blocker:
        abp_editor.abp_clean_action.trigger()
    assert "se unieron 1" in abp_blocker.args[0]
    assert len(abp_editor.abp_plan().abp_walls) == 2
    with qtbot.waitSignal(abp_editor.abp_notice) as abp_blocker:
        abp_editor.abp_clean_action.trigger()
    assert "ya estaba limpio" in abp_blocker.args[0]
