from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpRoom
from abp_rutasegura.abp_engines.abp_norms.abp_evaluate import abp_evaluate
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_SCALE
from abp_tests.abp_unit.abp_norms.abp_helpers import abp_packaged_rules

abp_CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "abp_casos_aforo.yaml").read_text(encoding="utf-8")
)["casos"]


def abp_test_there_are_ten_cases() -> None:
    assert len(abp_CASES) == 10
    assert len({abp_c["id"] for abp_c in abp_CASES}) == 10


@pytest.mark.parametrize("abp_case", abp_CASES, ids=[abp_c["id"] for abp_c in abp_CASES])
def abp_test_capacity_case(abp_case: dict[str, Any]) -> None:
    abp_room = abpRoom(
        "Ambiente",
        abpUseType(abp_case["uso"]),
        abp_rect(0, 0, float(abp_case["ancho_m"]), float(abp_case["largo_m"])),
        abp_case["categoria"],
    )
    abp_plan = abpFloorPlan(abp_scale_m_per_px=abp_SCALE, abp_rooms=(abp_room,))
    abp_result = abp_evaluate(abp_plan, (), abp_packaged_rules())
    abp_capacity = abp_result.abp_capacities[0]
    assert abp_capacity.abp_category == abp_case["categoria"]
    assert abp_capacity.abp_capacity == abp_case["aforo_esperado"], abp_case["descripcion"]
