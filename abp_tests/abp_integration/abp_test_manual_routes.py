from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_serialization import (
    abp_scenario_from_dict,
    abp_scenario_to_dict,
)
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetService
from abp_rutasegura.abp_domain.abp_enums import abpStairUse, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpRoom, abpStair, abpWall
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute, abpScenario
from abp_rutasegura.abp_presentation.abp_simulation_page import abpSimulationPage
from abp_tests.abp_fixtures.abp_simple_plans import abp_PX_PER_M, abp_rect, abp_SCALE, abp_two_rooms


def abp_px(abp_x: float, abp_y: float) -> abpPoint:
    return abpPoint(abp_x * abp_PX_PER_M, abp_y * abp_PX_PER_M)


def abp__cell(abp_table: QTableWidget, abp_row: int, abp_column: int) -> QTableWidgetItem:
    abp_item = abp_table.item(abp_row, abp_column)
    assert abp_item is not None
    return abp_item


def abp_hall() -> abpFloorPlan:
    abp_sides = [
        ((0, 0), (12, 0)),
        ((0, 8), (12, 8)),
        ((0, 0), (0, 3)),
        ((0, 4.5), (0, 8)),
        ((12, 0), (12, 3)),
        ((12, 4.5), (12, 8)),
    ]
    abp_walls = [abpWall(abpSegment(abp_px(*abp_a), abp_px(*abp_b))) for abp_a, abp_b in abp_sides]
    return abpFloorPlan(
        abp_level=0,
        abp_scale_m_per_px=abp_SCALE,
        abp_walls=tuple(abp_walls),
        abp_exits=(
            abpExit(abpSegment(abp_px(0, 3), abp_px(0, 4.5)), abp_name="Salida 1"),
            abpExit(abpSegment(abp_px(12, 3), abp_px(12, 4.5)), abp_name="Salida 2"),
        ),
        abp_rooms=(abpRoom("Aula", abpUseType.abp_EDUCATION, abp_rect(1, 1, 3, 2)),),
    )


def abp__scenario(*abp_routes: abpManualRoute) -> abpScenario:
    return abpScenario(
        "Escenario base", 7, (abpOccupancy("Aula", "adulto", 12),), abp_routes=abp_routes
    )


class abpTestSimulation:
    def abp_test_people_leave_by_the_chosen_exit(self, abp_services: abpAppServices) -> None:
        abp_free = abp_services.abp_simulations.abp_simulate(abp_hall(), abp__scenario())
        assert [abp_n for abp_n, abp__t in abp_free.abp_result.abp_time_per_exit_s] == ["Salida 1"]
        abp_sent = abp_services.abp_simulations.abp_simulate(
            abp_hall(), abp__scenario(abpManualRoute("Aula", 0, "Salida 2"))
        )
        assert abp_sent.abp_result.abp_completed
        assert [abp_n for abp_n, abp__t in abp_sent.abp_result.abp_time_per_exit_s] == ["Salida 2"]

    def abp_test_people_go_through_the_points(self, abp_services: abpAppServices) -> None:
        abp_low = abpManualRoute("Aula", 0, "Salida 2", (abp_px(6, 7),))
        abp_out = abp_services.abp_simulations.abp_simulate(abp_hall(), abp__scenario(abp_low))
        abp_xy = abp_out.abp_trajectories.abp_positions
        abp_crossing = np.abs(abp_xy[..., 0] - 6.0) < 0.4
        abp_moving = abp_out.abp_trajectories.abp_status == 1
        assert np.median(abp_xy[..., 1][abp_crossing & abp_moving]) > 5.8

    def abp_test_same_seed_same_result(self, abp_services: abpAppServices) -> None:
        abp_scenario = abp__scenario(abpManualRoute("Aula", 0, "Salida 2", (abp_px(6, 7),)))
        abp_a, abp_b = (
            abp_services.abp_simulations.abp_simulate(abp_hall(), abp_scenario) for _ in range(2)
        )
        assert np.array_equal(
            abp_a.abp_trajectories.abp_positions, abp_b.abp_trajectories.abp_positions
        )

    def abp_test_a_blocked_exit_falls_back(self, abp_services: abpAppServices) -> None:
        abp_scenario = dataclasses.replace(
            abp__scenario(abpManualRoute("Aula", 0, "Salida 2")),
            abp_blocked_exits=frozenset({"Salida 2"}),
        )
        abp_out = abp_services.abp_simulations.abp_simulate(abp_hall(), abp_scenario)
        assert [abp_n for abp_n, abp__t in abp_out.abp_result.abp_time_per_exit_s] == ["Salida 1"]

    def abp_test_impossible_point(self, abp_services: abpAppServices) -> None:
        abp_bad = abpManualRoute("Aula", 0, "Salida 2", (abp_px(40, 40),))
        with pytest.raises(abpUserFacingError, match="no se puede llegar"):
            abp_services.abp_simulations.abp_simulate(abp_hall(), abp__scenario(abp_bad))
        with pytest.raises(abpUserFacingError, match="no se puede llegar"):
            abp_services.abp_simulations.abp_check_route(
                abp_hall(), abp__scenario(abp_bad), abp_bad
            )

    def abp_test_an_unknown_room_is_ignored(self, abp_services: abpAppServices) -> None:
        abp_out = abp_services.abp_simulations.abp_simulate(
            abp_hall(), abp__scenario(abpManualRoute("Otro", 0, "Salida 2"))
        )
        assert [abp_n for abp_n, abp__t in abp_out.abp_result.abp_time_per_exit_s] == ["Salida 1"]

    def abp_test_same_floor_steps_slow_people_down(self, abp_services: abpAppServices) -> None:
        abp_steps = abpStair(
            abp_rect(5, 0, 2, 8), abp_name="Gradas", abp_use=abpStairUse.abp_SAME_FLOOR
        )
        abp_route = abpManualRoute("Aula", 0, "Salida 2")
        abp_flat = abp_services.abp_simulations.abp_simulate(abp_hall(), abp__scenario(abp_route))
        abp_stepped = abp_services.abp_simulations.abp_simulate(
            dataclasses.replace(abp_hall(), abp_stairs=(abp_steps,)), abp__scenario(abp_route)
        )
        assert abp_stepped.abp_result.abp_total_time_s > abp_flat.abp_result.abp_total_time_s + 0.5

    def abp_test_arriving_by_a_stair(self, abp_services: abpAppServices) -> None:
        abp_stair = abpStair(
            abp_rect(5, 0.3, 1.6, 3),
            abp_name="A",
            abp_use=abpStairUse.abp_UP,
            abp_entry=abp_px(5.8, 3.3),
        )
        abp_lower = dataclasses.replace(abp_hall(), abp_stairs=(abp_stair,))
        abp_upper = dataclasses.replace(
            abp_hall(),
            abp_level=1,
            abp_exits=(),
            abp_walls=tuple(
                abpWall(abpSegment(abp_px(*abp_a), abp_px(*abp_b)))
                for abp_a, abp_b in (
                    ((0, 0), (12, 0)),
                    ((12, 0), (12, 8)),
                    ((12, 8), (0, 8)),
                    ((0, 8), (0, 0)),
                )
            ),
            abp_stairs=(
                abpStair(abp_rect(5, 0.3, 1.6, 3), abp_name="A", abp_entry=abp_px(5.8, 3.3)),
            ),
        )
        abp_base = abpScenario(
            "Escenario base", 7, (abpOccupancy("Aula", "adulto", 6, abp_level=1),)
        )
        abp_names = {
            abp_s.abp_key
            for abp_s in abp_services.abp_simulations.abp_route_sources(
                [abp_lower, abp_upper], abp_base
            )
        }
        assert (0, True, "A") in abp_names
        for abp_goal in ("Salida 1", "Salida 2"):
            abp_sent = abp_base.abp_with_route(
                abpManualRoute("A", 0, abp_goal, abp_from_stair=True)
            )
            abp_out = abp_services.abp_simulations.abp_simulate([abp_lower, abp_upper], abp_sent)
            assert abp_out.abp_result.abp_completed
            assert [abp_n for abp_n, abp__t in abp_out.abp_result.abp_time_per_exit_s] == [abp_goal]


class abpTestData:
    def abp_test_round_trip(self, abp_services: abpAppServices) -> None:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Rutas", abpUseType.abp_EDUCATION
        )
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_hall())
        abp_scenario = abp__scenario(abpManualRoute("Aula", 0, "Salida 2", (abpPoint(10.5, 20.0),)))
        abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_scenario)
        assert (
            abp_services.abp_simulations.abp_load_scenario(abp_project_id).abp_routes
            == abp_scenario.abp_routes
        )
        assert abp_scenario_from_dict(abp_scenario_to_dict(abp_scenario)) == abp_scenario

    def abp_test_variant_keeps_the_routes(self, abp_services: abpAppServices) -> None:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Rutas", abpUseType.abp_EDUCATION
        )
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_hall())
        abp_base = abp__scenario(abpManualRoute("Aula", 0, "Salida 2"))
        abp_variant = abp_services.abp_simulations.abp_save_variant(
            abp_project_id, "V", abp_base, 50, []
        )
        assert abp_variant.abp_routes == abp_base.abp_routes

    def abp_test_fingerprint(self, abp_services: abpAppServices) -> None:
        abp_sims = abp_services.abp_simulations
        assert "rutas" not in abp_scenario_to_dict(abp__scenario())
        abp_before = abp_sims.abp_fingerprint(abp_hall(), abp__scenario())
        assert abp_before != abp_sims.abp_fingerprint(
            abp_hall(), abp__scenario(abpManualRoute("Aula", 0, "Salida 2"))
        )

    def abp_test_routes_follow_the_plan(self, abp_services: abpAppServices) -> None:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Rutas", abpUseType.abp_EDUCATION
        )
        abp_services.abp_projects.abp_save_floor(abp_project_id, abp_hall())
        abp_base = abp__scenario(abpManualRoute("Aula", 0, "Salida 2", (abpPoint(10, 20),)))
        abp_services.abp_simulations.abp_save_variant(abp_project_id, "V", abp_base, 100, [])
        abp_moved = abp_services.abp_simulations.abp_move_routes(
            abp_project_id, abp_base, 0, lambda abp_p: abpPoint(abp_p.abp_y, abp_p.abp_x)
        )
        assert abp_moved.abp_routes[0].abp_waypoints == (abpPoint(20, 10),)
        abp_stored = abp_services.abp_simulations.abp_load_scenario(abp_project_id, "V")
        assert abp_stored.abp_routes[0].abp_waypoints == (abpPoint(20, 10),)
        assert (
            abp_services.abp_simulations.abp_move_routes(
                abp_project_id, abp_base, 0, None
            ).abp_routes
            == ()
        )
        assert abp_base.abp_renamed_room(0, "Aula", "Taller").abp_routes[0].abp_source == "Taller"
        assert abp_base.abp_renamed_room(1, "Aula", "Taller") == abp_base

    def abp_test_shown_routes_and_sheet(self, abp_services: abpAppServices) -> None:
        abp_scenario = abp__scenario(abpManualRoute("Aula", 0, "Salida 2", (abp_px(6, 7),)))
        (abp_route,) = abp_services.abp_simulations.abp_routes(abp_hall(), abp_scenario)
        assert abp_route.abp_manual
        assert abp_route.abp_target_name == "Salida 2"
        assert max(abp_p.abp_y for abp_p in abp_route.abp_path_m) > 5.8
        assert abp_route.abp_max_distance_m > 10
        abp_network = abpSheetService.abp_network(abp_hall(), {"Aula": 12}, abp_manual=(abp_route,))
        (abp_escape,) = abp_network.abp_escapes
        assert abp_escape.abp_target_name == "Salida 2"
        assert max(abp_p.abp_y for abp_p in abp_escape.abp_path_m) > 5.5


class abpTestPage:
    @pytest.fixture
    def abp_page(self, qtbot: QtBot, abp_services: abpAppServices) -> abpSimulationPage:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Rutas", abpUseType.abp_EDUCATION
        )
        abp_plan = abp_services.abp_projects.abp_save_floor(abp_project_id, abp_hall())
        abp_page = abpSimulationPage(abp_services.abp_simulations)
        qtbot.addWidget(abp_page)
        abp_page.resize(1100, 700)
        abp_page.show()
        abp_page.abp_set_content(abp_project_id, [(abp_plan, None)], abp__scenario())
        abp_page.abp_set_route_editing(True)
        return abp_page

    def abp_test_choose_exit_undo_and_reset(self, abp_page: abpSimulationPage) -> None:
        abp_key = (0, False, "Aula")
        assert abp_page.abp_side_stack.currentWidget() is abp_page.abp_route_panel
        assert abp_page.abp_route_panel.abp_table.rowCount() == 1
        abp_page.abp_set_route_exit(abp_key, "Salida 2")
        assert abp_page.abp_current_scenario.abp_route_of(0, "Aula") is not None
        assert abp__cell(abp_page.abp_route_panel.abp_table, 0, 2).text() == "A mano"
        assert abp_page.abp_viewer.abp_route_layer.abp_key == abp_key
        abp_page.abp_undo_route()
        assert abp_page.abp_current_scenario.abp_routes == ()
        abp_page.abp_set_route_exit(abp_key, "Salida 2")
        abp_page.abp_reset_route(abp_key)
        assert abp_page.abp_current_scenario.abp_routes == ()
        abp_page.abp_set_route_exit(abp_key, "Salida 2")
        abp_page.abp_reset_all_routes()
        assert abp_page.abp_current_scenario.abp_routes == ()

    def abp_test_drag_the_line(self, abp_page: abpSimulationPage) -> None:
        abp_view, abp_layer = abp_page.abp_viewer.abp_view, abp_page.abp_viewer.abp_route_layer
        abp_page.abp_set_route_exit((0, False, "Aula"), "Salida 2")
        abp_route = abp_layer.abp_current
        assert abp_route is not None
        abp_middle = abp_px(7, 3.6)
        abp_start = min(abp_route.abp_path, key=lambda abp_p: abs(abp_p.x() - abp_middle.abp_x))
        abp_view.abp_drag_node(abp_start, QPointF(abp_px(7, 7).abp_x, abp_px(7, 7).abp_y))
        abp_manual = abp_page.abp_current_scenario.abp_route_of(0, "Aula")
        assert abp_manual is not None
        assert len(abp_manual.abp_waypoints) == 1
        assert abp_manual.abp_exit_name == "Salida 2"
        abp_point = abp_manual.abp_waypoints[0]
        abp_view.abp_drag_node(
            QPointF(abp_point.abp_x, abp_point.abp_y),
            QPointF(abp_px(6, 1).abp_x, abp_px(6, 1).abp_y),
        )
        abp_moved = abp_page.abp_current_scenario.abp_route_of(0, "Aula")
        assert abp_moved is not None
        assert abp_moved.abp_waypoints[0].abp_y < abp_point.abp_y
        abp_menu = abp_layer.abp_menu_at(
            QPointF(abp_moved.abp_waypoints[0].abp_x, abp_moved.abp_waypoints[0].abp_y)
        )
        assert abp_menu is not None
        assert len(abp_menu.actions()) == 2
        abp_layer.abp_remove_point(0)
        abp_left = abp_page.abp_current_scenario.abp_route_of(0, "Aula")
        assert abp_left is not None
        assert abp_left.abp_waypoints == ()

    def abp_test_drag_the_end_to_another_exit(self, abp_page: abpSimulationPage) -> None:
        abp_view, abp_layer = abp_page.abp_viewer.abp_view, abp_page.abp_viewer.abp_route_layer
        abp_layer.abp_select((0, False, "Aula"))
        abp_route = abp_layer.abp_current
        assert abp_route is not None
        abp_target = abp_px(12, 3.8)
        abp_view.abp_drag_node(abp_route.abp_path[-1], QPointF(abp_target.abp_x, abp_target.abp_y))
        abp_manual = abp_page.abp_current_scenario.abp_route_of(0, "Aula")
        assert abp_manual is not None
        assert abp_manual.abp_exit_name == "Salida 2"
        abp_page.abp_drop_route_end(
            (0, False, "Aula"), QPointF(abp_px(6, 4).abp_x, abp_px(6, 4).abp_y)
        )
        assert "salida" in abp_page.abp_route_panel.abp_message_label.text()

    def abp_test_impossible_route_is_not_saved(self, abp_page: abpSimulationPage) -> None:
        abp_page.abp_set_route_points((0, False, "Aula"), [QPointF(9000, 9000)])
        assert abp_page.abp_current_scenario.abp_routes == ()
        assert "no se puede llegar" in abp_page.abp_route_panel.abp_message_label.text()

    def abp_test_pick_a_room_and_finish(self, abp_page: abpSimulationPage) -> None:
        abp_page.abp_pick_room(QPointF(abp_px(2, 2).abp_x, abp_px(2, 2).abp_y))
        assert abp_page.abp_viewer.abp_route_layer.abp_key == (0, False, "Aula")
        abp_page.abp_route_panel.abp_finished.emit()
        assert not abp_page.abp_editing_routes
        assert abp_page.abp_side_stack.currentIndex() == 0


def abp_test_two_rooms_plan_is_not_affected(abp_services: abpAppServices) -> None:
    abp_routes = abp_services.abp_simulations.abp_routes(abp_two_rooms(), abp__scenario())
    assert abp_routes
    assert not any(abp_r.abp_manual for abp_r in abp_routes)
