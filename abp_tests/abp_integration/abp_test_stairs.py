from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_serialization import abp_plan_from_dict, abp_plan_to_dict
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_stairs_service import abp_entry_side, abp_with_entry_side
from abp_rutasegura.abp_domain.abp_enums import abpCellType, abpStairUse, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpStair
from abp_rutasegura.abp_domain.abp_vector import abpVectorText
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_build_grid,
    abp_landing_cells,
    abp_polygon_to_m,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_multifloor import abp_pair_stairs
from abp_rutasegura.abp_engines.abp_vision.abp_stairs import (
    abp_find_stairs,
    abp_floor_levels,
    abpFoundStair,
)
from abp_rutasegura.abp_presentation.abp_editor.abp_editor_widget import abpPlanEditor
from abp_rutasegura.abp_presentation.abp_stairs_dialog import abpStairsDialog
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_SCALE, abp_two_rooms


def abp__with(
    abp_use: abpStairUse, abp_area: tuple[float, float, float, float] = (8, 0.2, 1.6, 3.5)
) -> abpFloorPlan:
    abp_stair = abpStair(abp_rect(*abp_area), abp_name="Escalera A", abp_use=abp_use)
    return dataclasses.replace(abp_two_rooms(), abp_stairs=(abp_stair,))


@pytest.mark.parametrize(
    ("abp_use", "abp_walkable"),
    [
        (abpStairUse.abp_UP, False),
        (abpStairUse.abp_CLOSED, False),
        (abpStairUse.abp_BOTH, False),
        (abpStairUse.abp_SAME_FLOOR, True),
        (abpStairUse.abp_AUTO, False),
    ],
)
def abp_test_ground_floor_roles(abp_use: abpStairUse, abp_walkable: bool) -> None:
    abp_grid = abp_build_grid(abp__with(abp_use))
    abp_kind = int(abpCellType.abp_STAIR if abp_walkable else abpCellType.abp_OBSTACLE)
    assert (abp_grid.abp_cells == abp_kind).any()
    assert bool(abp_grid.abp_closed_stairs) is not abp_walkable


def abp_test_automatic_opens_only_if_needed() -> None:
    abp_grid = abp_build_grid(abp__with(abpStairUse.abp_AUTO, (8, 0, 1.6, 6)))
    assert abp_grid.abp_closed_stairs == ()
    abp_closed = abp_build_grid(abp__with(abpStairUse.abp_UP, (8, 0, 1.6, 6)))
    assert abp_closed.abp_closed_stairs == (0,)


def abp_test_outside_is_an_exit_and_upper_floor_goes_down() -> None:
    assert "Escalera A" in abp_build_grid(abp__with(abpStairUse.abp_OUTSIDE)).abp_target_names
    abp_upper = abp_build_grid(
        abp__with(abpStairUse.abp_AUTO), abp_stairs_as_targets=True, abp_exits_as_targets=False
    )
    assert abp_upper.abp_target_names == ("Escalera A",)
    abp_going_up = abp_build_grid(
        abp__with(abpStairUse.abp_UP), abp_stairs_as_targets=True, abp_exits_as_targets=False
    )
    assert abp_going_up.abp_target_names == ()


def abp_test_people_land_at_the_foot() -> None:
    abp_plan = abp__with(abpStairUse.abp_UP)
    abp_area = abp_polygon_to_m(abp_plan.abp_stairs[0].abp_area, abp_SCALE)
    abp_grid = abp_build_grid(abp_plan)
    abp_distance = abp_distance_field(
        abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
    )
    abp_foot = abp_landing_cells(abp_grid, abp_distance, abp_area, abpPoint(8.8, 3.7))
    assert len(abp_foot)
    assert (abp_foot[:, 1] > 3.6).all()


def abp_test_nobody_crosses_a_stair_that_goes_up(abp_services: abpAppServices) -> None:
    abp_plan = abp__with(abpStairUse.abp_UP)
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Gradas", abpUseType.abp_EDUCATION
    )
    abp_plan = abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
    assert abp_plan.abp_stairs[0].abp_use is abpStairUse.abp_UP
    abp_scenario = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "adulto", 25),),
    )
    abp_output = abp_services.abp_simulations.abp_simulate(abp_plan, abp_scenario)
    assert abp_output.abp_result.abp_completed
    abp_xy = abp_output.abp_trajectories.abp_positions
    abp_inside = (
        (abp_xy[..., 0] > 8.4)
        & (abp_xy[..., 0] < 9.2)
        & (abp_xy[..., 1] > 0.6)
        & (abp_xy[..., 1] < 3.2)
    )
    assert not np.any(abp_inside)


def abp_test_round_trip() -> None:
    abp_plan = abp__with(abpStairUse.abp_SAME_FLOOR)
    abp_stair = dataclasses.replace(
        abp_plan.abp_stairs[0], abp_entry=abpPoint(1, 2), abp_leads_to="B"
    )
    abp_plan = dataclasses.replace(abp_plan, abp_stairs=(abp_stair,))
    assert abp_plan_from_dict(abp_plan_to_dict(abp_plan)).abp_stairs == abp_plan.abp_stairs


abp_WALLS = [(0, 0, 12, 0), (12, 0, 12, 6), (12, 6, 0, 6), (0, 6, 0, 0), (5, 3, 8, 3)]


def abp__flight(
    abp_x0: float, abp_y0: float, abp_y1: float, abp_steps: int, abp_tread: float = 0.3
) -> list[list[float]]:
    return [
        [abp_x0 + abp_k * abp_tread, abp_y0, abp_x0 + abp_k * abp_tread, abp_y1]
        for abp_k in range(abp_steps + 1)
    ]


def abp__texts(
    abp_numbers: dict[int, tuple[float, float]], abp_levels: dict[str, tuple[float, float]]
):
    abp_out = [
        abpVectorText(str(abp_n), abp_x, abp_y, 0.2, 0.15, 0.0)
        for abp_n, (abp_x, abp_y) in abp_numbers.items()
    ]
    return abp_out + [
        abpVectorText(abp_t, abp_x, abp_y, 0.2, 0.15, 0.0)
        for abp_t, (abp_x, abp_y) in abp_levels.items()
    ]


def abp__found(abp_levels: dict[str, tuple[float, float]]) -> list[abpFoundStair]:
    abp_lines = np.array(
        abp__flight(5, 3.1, 5.9, 10) + abp__flight(5, 0.1, 2.9, 8) + abp_WALLS, float
    )
    abp_numbers = {abp_n: (8 - 0.3 * abp_n + 0.15, 4.5) for abp_n in range(1, 11)}
    abp_numbers |= {abp_n: (5 + 0.3 * (abp_n - 10) - 0.15, 1.5) for abp_n in (11, 12, 13)}
    return abp_find_stairs(
        abp_lines, np.array(abp_WALLS, float), abp__texts(abp_numbers, abp_levels)
    )


def abp_test_flights_are_classified_by_level_and_numbers() -> None:
    abp_found = abp__found({"NPT. +0.00": (9.5, 4.5), "NPT. +1.50": (3.0, 4.5)})
    abp_steps = [abp_f for abp_f in abp_found if abp_f.abp_use is abpStairUse.abp_SAME_FLOOR]
    abp_up = [abp_f for abp_f in abp_found if abp_f.abp_use is abpStairUse.abp_UP]
    assert len(abp_steps) == 1
    assert len(abp_up) == 1
    assert abp_steps[0].abp_area[:, 1].min() > 2.8
    assert abp_up[0].abp_entry is not None
    assert abp_up[0].abp_entry[0] < 5.6


def abp_test_without_levels_a_numbered_flight_goes_up() -> None:
    abp_found = abp__found({})
    assert abp_found
    assert all(abp_f.abp_use is abpStairUse.abp_UP for abp_f in abp_found)


def abp_test_floor_levels() -> None:
    abp_texts = abp__texts({}, {"N.P.T. +1.50": (1, 2), "NPT: - 0.15": (3, 4), "NPT 0.00": (5, 6)})
    abp_values = sorted(abp_v for abp__p, abp_v in abp_floor_levels(abp_texts, 1.0))
    assert abp_values in ([-0.15, 0.0, 1.5], [0.0, 1.5])


def abp_test_analysis_keeps_names_and_choices(abp_services: abpAppServices) -> None:
    abp_plan = dataclasses.replace(
        abp_two_rooms(),
        abp_stairs=(
            abpStair(abp_rect(8, 0.2, 1.6, 3.5), abp_name="Principal"),
            abpStair(abp_rect(8, 4, 1.6, 1.5), abp_name="Otra", abp_use=abpStairUse.abp_CLOSED),
        ),
    )
    abp_new = abp_services.abp_plans.abp_analyze_stairs(abp_plan, None)
    assert abp_new.abp_stairs == abp_plan.abp_stairs


def abp_test_rotation_turns_the_entry(abp_services: abpAppServices) -> None:
    abp_stair = abp_with_entry_side(abpStair(abp_rect(1, 1, 2, 3), abp_name="A"), "arriba")
    abp_plan = dataclasses.replace(abp_two_rooms(), abp_stairs=(abp_stair,))
    abp_turned = abp_services.abp_plans.abp_rotate_plan(abp_plan, (1000, 800), 1)
    assert abp_entry_side(abp_turned.abp_stairs[0]) == "derecha"


def abp__cell(abp_table: QTableWidget, abp_row: int, abp_column: int) -> QTableWidgetItem:
    abp_item = abp_table.item(abp_row, abp_column)
    assert abp_item is not None
    return abp_item


def abp_test_dialog(qtbot: QtBot) -> None:
    abp_editor = abpPlanEditor()
    qtbot.addWidget(abp_editor)
    abp_editor.abp_set_plan(abp__with(abpStairUse.abp_AUTO), None)
    abp_dialog = abpStairsDialog(abp_editor)
    qtbot.addWidget(abp_dialog)
    assert abp_dialog.abp_table.rowCount() == 1
    assert abp__cell(abp_dialog.abp_table, 0, 4).text() == "Nadie la cruza"
    abp_dialog.abp_set_use(0, "mismo_piso")
    assert abp_editor.abp_plan().abp_stairs[0].abp_use is abpStairUse.abp_SAME_FLOOR
    assert "Se cruza" in abp__cell(abp_dialog.abp_table, 0, 4).text()
    abp_dialog.abp_set_side(0, "abajo")
    assert abp_entry_side(abp_editor.abp_plan().abp_stairs[0]) == "abajo"
    abp__cell(abp_dialog.abp_table, 0, 0).setText("Gradas")
    assert abp_editor.abp_plan().abp_stairs[0].abp_name == "Gradas"
    abp_editor.abp_undo_stack.undo()
    assert abp_editor.abp_plan().abp_stairs[0].abp_name == "Escalera A"
    assert abp_dialog.abp_table.isColumnHidden(3)


def abp_test_dialog_on_an_upper_floor(qtbot: QtBot) -> None:
    abp_lower = dataclasses.replace(abp__with(abpStairUse.abp_UP), abp_level=0)
    abp_upper = dataclasses.replace(
        abp_two_rooms(),
        abp_level=1,
        abp_stairs=(abpStair(abp_rect(8, 0.2, 1.6, 3.5), abp_name="Norte"),),
    )
    abp_editor = abpPlanEditor()
    qtbot.addWidget(abp_editor)
    abp_editor.abp_set_plan(abp_upper, None)
    abp_dialog = abpStairsDialog(abp_editor, [abp_lower, abp_upper])
    qtbot.addWidget(abp_dialog)
    assert not abp_dialog.abp_table.isColumnHidden(3)
    assert "baja" in abp__cell(abp_dialog.abp_table, 0, 4).text()
    abp_dialog.abp_set_below(0, "Escalera A")
    assert abp_pair_stairs(abp_editor.abp_plan(), abp_lower) == {0: 0}
