from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpWall
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import (
    abp_next_exit_name,
    abpPlanEditor,
)
from abp_rutasegura.abp_presentation.abp_editor.abp_view import (
    abp_snap_to_angle,
    abpPlanView,
    abpTool,
)


def abp__seg(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


def abp__square(abp_x: float, abp_y: float, abp_s: float) -> abpPolygon:
    return abpPolygon(
        (
            abpPoint(abp_x, abp_y),
            abpPoint(abp_x + abp_s, abp_y),
            abpPoint(abp_x + abp_s, abp_y + abp_s),
            abpPoint(abp_x, abp_y + abp_s),
        )
    )


@pytest.fixture
def abp_editor(qtbot: QtBot) -> abpPlanEditor:
    abp_widget = abpPlanEditor()
    qtbot.addWidget(abp_widget)
    abp_widget.resize(900, 600)
    abp_widget.abp_set_plan(abpFloorPlan(), np.full((400, 600, 3), 255, np.uint8))
    return abp_widget


def abp__send(
    abp_view: abpPlanView, abp_kind: QEvent.Type, abp_pos: QPoint, abp_buttons: Qt.MouseButton
) -> None:
    abp_button = (
        Qt.MouseButton.LeftButton if abp_kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    )
    abp_event = QMouseEvent(
        abp_kind,
        QPointF(abp_pos),
        QPointF(abp_view.viewport().mapToGlobal(abp_pos)),
        abp_button,
        abp_buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(abp_view.viewport(), abp_event)


def abp__drag(abp_view: abpPlanView, abp_start: QPoint, abp_end: QPoint) -> None:
    abp_left = Qt.MouseButton.LeftButton
    abp__send(abp_view, QEvent.Type.MouseButtonPress, abp_start, abp_left)
    abp__send(abp_view, QEvent.Type.MouseMove, abp_end, abp_left)
    abp__send(abp_view, QEvent.Type.MouseButtonRelease, abp_end, Qt.MouseButton.NoButton)


class abpTestEditing:
    def abp_test_add_undo_redo(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 100, 0))
        abp_editor.abp_add_segment(abpElementType.abp_DOOR, abp__seg(20, 0, 60, 0))
        assert [abp_w.abp_segment for abp_w in abp_editor.abp_plan().abp_walls] == [
            abp__seg(0, 0, 20, 0),
            abp__seg(60, 0, 100, 0),
        ]
        assert len(abp_editor.abp_plan().abp_doors) == 1
        abp_editor.abp_undo_stack.undo()
        assert abp_editor.abp_plan().abp_doors == ()
        assert abp_editor.abp_plan().abp_walls == (abpWall(abp__seg(0, 0, 100, 0)),)
        abp_editor.abp_undo_stack.undo()
        assert abp_editor.abp_plan().abp_walls == ()
        abp_editor.abp_undo_stack.redo()
        assert abp_editor.abp_plan().abp_walls == (abpWall(abp__seg(0, 0, 100, 0)),)
        assert abp_editor.abp_undo_stack.undoText() == "Agregar muro"

    def abp_test_areas_and_delete(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_area(abpElementType.abp_STAIR, abp__square(0, 0, 10))
        abp_editor.abp_add_area(abpElementType.abp_OBSTACLE, abp__square(20, 20, 5))
        abp_editor.abp_add_area(abpElementType.abp_SAFE_ZONE, abp__square(50, 50, 30))
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 1, 1))
        assert len(abp_editor.abp_scene.abp_all_element_items()) == 4
        abp_editor.abp_delete([(abpElementType.abp_OBSTACLE, 0), (abpElementType.abp_WALL, 0)])
        abp_plan = abp_editor.abp_plan()
        assert (
            len(abp_plan.abp_stairs),
            len(abp_plan.abp_obstacles),
            len(abp_plan.abp_safe_zones),
            len(abp_plan.abp_walls),
        ) == (
            1,
            0,
            1,
            0,
        )
        abp_editor.abp_undo_stack.undo()
        assert len(abp_editor.abp_plan().abp_obstacles) == 1

    def abp_test_delete_selected_items(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 100, 0))
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 50, 100, 50))
        abp_editor.abp_scene.abp_items_of(abpElementType.abp_WALL)[1].setSelected(True)
        assert abp_editor.abp_delete_action.isEnabled()
        abp_editor.abp_delete_selected()
        assert abp_editor.abp_plan().abp_walls == (abpWall(abp__seg(0, 0, 100, 0)),)

    def abp_test_exit_names_are_unique(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_EXIT, abp__seg(0, 0, 50, 0))
        abp_editor.abp_add_segment(abpElementType.abp_EXIT, abp__seg(0, 100, 50, 100))
        assert [abp_e.abp_name for abp_e in abp_editor.abp_plan().abp_exits] == [
            "Salida 1",
            "Salida 2",
        ]
        abp_plan = abpFloorPlan(abp_exits=(abpExit(abp__seg(0, 0, 1, 0), "Salida 2"),))
        assert abp_next_exit_name(abp_plan, "Salida {number}") == "Salida 1"

    def abp_test_confirm_proposed_exits(self, abp_editor: abpPlanEditor) -> None:
        abp_proposed = abpFloorPlan(
            abp_exits=(
                abpExit(abp__seg(0, 0, 50, 0), "Salida 1", abp_confirmed=False),
                abpExit(abp__seg(0, 90, 50, 90), "Salida 2", abp_confirmed=False),
            )
        )
        abp_editor.abp_set_plan(abp_proposed, None)
        assert "2 salida(s)" in abp_editor.abp_pending_label.text()
        abp_editor.abp_scene.abp_items_of(abpElementType.abp_EXIT)[0].setSelected(True)
        assert abp_editor.abp_confirm_action.isEnabled()
        abp_editor.abp_confirm_selected_exits()
        assert [abp_e.abp_confirmed for abp_e in abp_editor.abp_plan().abp_exits] == [True, False]
        assert "1 salida(s)" in abp_editor.abp_pending_label.text()
        abp_editor.abp_undo_stack.undo()
        assert [abp_e.abp_confirmed for abp_e in abp_editor.abp_plan().abp_exits] == [False, False]

    def abp_test_set_plan_clears_history(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 10, 0))
        abp_editor.abp_set_plan(abpFloorPlan(), None)
        assert not abp_editor.abp_undo_stack.canUndo()

    def abp_test_plan_changed_signal(self, abp_editor: abpPlanEditor, qtbot: QtBot) -> None:
        with qtbot.waitSignal(abp_editor.abp_plan_changed) as abp_blocker:
            abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 10, 0))
        assert isinstance(abp_blocker.args[0], abpFloorPlan)


class abpTestLayersAndView:
    def abp_test_layer_visibility(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 0, 100, 0))
        abp_editor.abp_add_segment(abpElementType.abp_DOOR, abp__seg(10, 0, 50, 0))
        abp_editor.abp_layer_boxes[abpElementType.abp_WALL].setChecked(False)
        assert not abp_editor.abp_scene.abp_items_of(abpElementType.abp_WALL)[0].isVisible()
        assert abp_editor.abp_scene.abp_items_of(abpElementType.abp_DOOR)[0].isVisible()
        abp_editor.abp_add_segment(abpElementType.abp_WALL, abp__seg(0, 10, 100, 10))
        assert not any(
            abp_i.isVisible()
            for abp_i in abp_editor.abp_scene.abp_items_of(abpElementType.abp_WALL)
        )
        abp_editor.abp_layer_boxes[None].setChecked(False)
        assert not abp_editor.abp_scene.abp_is_layer_visible(None)

    def abp_test_low_confidence_items_are_dashed(self, abp_editor: abpPlanEditor) -> None:
        abp_editor.abp_set_plan(
            abpFloorPlan(abp_walls=(abpWall(abp__seg(0, 0, 9, 0), abp_confidence=0.3),)), None
        )
        abp_item = abp_editor.abp_scene.abp_items_of(abpElementType.abp_WALL)[0]
        assert abp_item.pen().style() == Qt.PenStyle.DashLine

    def abp_test_drawing_with_the_mouse(self, abp_editor: abpPlanEditor, qtbot: QtBot) -> None:
        abp_editor.show()
        qtbot.waitExposed(abp_editor)
        abp_editor.abp_set_tool(abpTool.abp_WALL)
        abp__drag(abp_editor.abp_view, QPoint(100, 100), QPoint(300, 100))
        assert len(abp_editor.abp_plan().abp_walls) == 1
        abp_wall = abp_editor.abp_plan().abp_walls[0].abp_segment
        assert abp_wall.abp_length > 50
        abp_editor.abp_set_tool(abpTool.abp_OBSTACLE)
        abp__drag(abp_editor.abp_view, QPoint(120, 150), QPoint(200, 230))
        assert len(abp_editor.abp_plan().abp_obstacles) == 1
        abp_editor.abp_undo_action.trigger()
        assert abp_editor.abp_plan().abp_obstacles == ()

    def abp_test_tiny_drags_are_ignored(self, abp_editor: abpPlanEditor, qtbot: QtBot) -> None:
        abp_editor.show()
        qtbot.waitExposed(abp_editor)
        abp_editor.abp_set_tool(abpTool.abp_DOOR)
        abp__drag(abp_editor.abp_view, QPoint(100, 100), QPoint(100, 100))
        assert abp_editor.abp_plan().abp_doors == ()

    def abp_test_zoom_limits(self, abp_editor: abpPlanEditor) -> None:
        for _ in range(100):
            abp_editor.abp_view.abp_zoom_by(2.0)
        assert abp_editor.abp_view.abp_zoom_factor() == pytest.approx(40.0)
        for _ in range(100):
            abp_editor.abp_view.abp_zoom_by(0.5)
        assert abp_editor.abp_view.abp_zoom_factor() == pytest.approx(0.02)

    def abp_test_snap_to_angle(self) -> None:
        abp_end = abp_snap_to_angle(QPointF(0, 0), QPointF(100, 7))
        assert abp_end.y() == pytest.approx(0, abs=1e-9)
        assert abp_end.x() == pytest.approx(100.24, abs=0.01)
        abp_diag = abp_snap_to_angle(QPointF(0, 0), QPointF(50, 46))
        assert abp_diag.x() == pytest.approx(abp_diag.y())
