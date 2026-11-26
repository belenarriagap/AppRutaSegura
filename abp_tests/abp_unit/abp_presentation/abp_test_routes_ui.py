from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_presentation.abp_norms_page import abp_COL_TRAVEL, abpNormsPage
from abp_rutasegura.abp_presentation.abp_simulation_viewer import (
    abp_add_arrow_polyline,
    abpSimulationViewer,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_two_rooms


def abp_test_arrow_polyline_has_heads() -> None:
    abp_path = QPainterPath()
    abp_add_arrow_polyline(
        abp_path, [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)], abp_head=5
    )
    assert abp_path.elementCount() > 3 + 4


def abp_test_viewer_draws_routes_of_the_floor(qtbot: QtBot) -> None:
    abp_viewer = abpSimulationViewer()
    qtbot.addWidget(abp_viewer)
    abp_plan = abp_two_rooms()
    abp_viewer.abp_set_floors([(abp_plan, None)])
    abp_routes = abpNormsService.abp_routes(abp_plan)
    abp_viewer.abp_set_routes(abp_routes)
    assert abp_viewer.abp_route_count == 2
    assert not abp_viewer.abp_routes_item.path().isEmpty()
    assert not abp_viewer.abp_routes_item.isVisible()
    abp_viewer.abp_routes_check.setChecked(True)
    assert abp_viewer.abp_routes_item.isVisible()
    abp_viewer.abp_set_routes(())
    assert abp_viewer.abp_routes_item.path().isEmpty()


def abp_test_norms_table_shows_travel_distance(qtbot: QtBot, abp_services: abpAppServices) -> None:
    abp_page = abpNormsPage(abp_services.abp_norms)
    qtbot.addWidget(abp_page)
    abp_page.abp_set_content(abp_two_rooms(), None)
    abp_item = abp_page.abp_table.item(0, abp_COL_TRAVEL)
    assert abp_item is not None
    assert 9 < float(abp_item.text()) < 16
