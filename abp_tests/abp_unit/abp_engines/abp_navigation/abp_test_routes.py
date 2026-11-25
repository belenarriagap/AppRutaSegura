from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpRoomRoute
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import (
    abp_build_grid,
    abp_polygon_to_m,
    abpNavGrid,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_routes import abp_descend, abp_room_routes
from abp_rutasegura.abp_engines.abp_norms.abp_evaluate import abp_evaluate
from abp_rutasegura.abp_engines.abp_norms.abp_rules import abp_parse_rules, abpRuleError
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea
from abp_tests.abp_fixtures.abp_simple_plans import abp_SCALE, abp_single_room, abp_two_rooms
from abp_tests.abp_unit.abp_norms.abp_helpers import abp_packaged_rules


def abp__routes(
    abp_plan: abpFloorPlan | None = None,
) -> tuple[abpNavGrid, npt.NDArray[np.float64], tuple[abpRoomRoute, ...]]:
    abp_plan = abp_plan or abp_two_rooms()
    abp_grid = abp_build_grid(abp_plan)
    abp_dist = abp_distance_field(
        abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
    )
    abp_rooms = [
        abpRoomArea(abp_r.abp_name, abp_plan.abp_level, abp_polygon_to_m(abp_r.abp_area, abp_SCALE))
        for abp_r in abp_plan.abp_rooms
    ]
    return abp_grid, abp_dist, abp_room_routes(abp_grid, abp_dist, abp_rooms)


def abp_test_route_goes_through_the_door_to_the_exit() -> None:
    _, _, abp_routes = abp__routes()
    abp_first, abp_second = abp_routes
    assert abp_first.abp_room_name == "Aula 1"
    assert abp_first.abp_target_name == "Salida principal"
    abp_xs = [abp_p.abp_x for abp_p in abp_first.abp_path_m]
    assert abp_xs[0] < 4
    assert abp_xs[-1] > 11
    abp_crossing = next(
        abp_a.abp_y + (abp_b.abp_y - abp_a.abp_y) * (6 - abp_a.abp_x) / (abp_b.abp_x - abp_a.abp_x)
        for abp_a, abp_b in zip(abp_first.abp_path_m, abp_first.abp_path_m[1:], strict=False)
        if abp_a.abp_x < 6 <= abp_b.abp_x
    )
    assert 2.3 <= abp_crossing <= 3.7
    assert abp_first.abp_farthest_m.abp_x < 1.5
    assert abp_first.abp_max_distance_m > abp_second.abp_max_distance_m
    assert 9 < abp_first.abp_max_distance_m < 16


def abp_test_descent_always_reaches_a_target() -> None:
    abp_grid, abp_dist, _ = abp__routes()
    abp_path = abp_descend(abp_grid, abp_dist, (int(abp_grid.abp_shape[0] / 2), 3))
    abp_r, abp_c = abp_path[-1]
    assert abp_grid.abp_target_ids[abp_r, abp_c] >= 0
    abp_values = [abp_dist[abp_r, abp_c] for abp_r, abp_c in abp_path]
    assert abp_values == sorted(abp_values, reverse=True)


def abp_test_unreachable_rooms_have_no_route() -> None:
    abp_plan = abp_single_room()
    abp_grid = abp_build_grid(abp_plan, abp_blocked_exits={"Salida 1"})
    abp_dist = abp_distance_field(
        abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
    )
    abp_rooms = [
        abpRoomArea("Aula 1", 0, abp_polygon_to_m(abp_plan.abp_rooms[0].abp_area, abp_SCALE))
    ]
    assert abp_room_routes(abp_grid, abp_dist, abp_rooms) == ()


def abp_test_travel_distance_rule() -> None:
    _, _, abp_routes = abp__routes()
    abp_strict = abp_parse_rules(
        [
            (
                "recorrido.yaml",
                """
reglas:
  - id: PRUEBA-RECORRIDO
    tipo: distancia_recorrido
    descripcion: prueba
    metros: 10
    norma: RNE A.130
    articulo: Art. X
    verificado: false
    recomendacion: Acorte el recorrido.
""",
            )
        ]
    )
    abp_result = abp_evaluate(abp_two_rooms(), (), abp_strict, abp_routes=abp_routes)
    abp_texts = [abp_o.abp_description for abp_o in abp_result.abp_observations]
    assert any("«Aula 1»" in abp_t and "máximo es 10 m" in abp_t for abp_t in abp_texts)
    assert not any("«Aula 2»" in abp_t for abp_t in abp_texts)
    assert abp_result.abp_routes == abp_routes
    with pytest.raises(abpRuleError, match="metros"):
        abp_parse_rules([("x.yaml", "reglas:\n" + abp__bad_travel_rule())])


def abp__bad_travel_rule() -> str:
    return """  - id: MALA
    tipo: distancia_recorrido
    descripcion: x
    metros: 0
    norma: x
    articulo: x
    verificado: false
    recomendacion: x
"""


def abp_test_packaged_rule_is_unverified_and_service_computes_routes() -> None:
    abp_rule = abp_packaged_rules().abp_first("distancia_recorrido")
    assert abp_rule is not None
    assert not abp_rule.abp_verified
    abp_evaluation = abpNormsService().abp_evaluate(abp_two_rooms(), None)
    assert [abp_r.abp_room_name for abp_r in abp_evaluation.abp_routes] == ["Aula 1", "Aula 2"]
    assert not any("recorren" in abp_o.abp_description for abp_o in abp_evaluation.abp_observations)
