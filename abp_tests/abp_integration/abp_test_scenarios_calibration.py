from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from abp_rutasegura.abp_application.abp_errors import abpOperationCancelled, abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_simulation_service import (
    abp_BASE_SCENARIO,
    abp_scale_occupancies,
)
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill, abpScenario
from abp_rutasegura.abp_engines.abp_calibration.abp_grid_search import abp_scale_profiles
from abp_tests.abp_fixtures.abp_simple_plans import abp_single_room

abp_PLAN = abp_single_room(abp_exit_width=0.9, abp_second_exit=True)


@pytest.fixture
def abp_project(abp_services: abpAppServices) -> tuple[int, abpScenario]:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_PLAN)
    abp_base = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=(abpOccupancy("Aula 1", "adulto", 30), abpOccupancy("Aula 1", "niño", 10)),
    )
    abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_base)
    return abp_project_id, abp_base


def abp_test_scale_occupancies_keeps_exact_total() -> None:
    abp_occ = (
        abpOccupancy("A", "adulto", 3),
        abpOccupancy("A", "niño", 3),
        abpOccupancy("B", "niño", 1),
    )
    abp_scaled = abp_scale_occupancies(abp_occ, 10)
    assert sum(abp_o.abp_count for abp_o in abp_scaled) == 10
    assert [abp_o.abp_count for abp_o in abp_scaled] == [4, 4, 2]
    assert abp_scale_occupancies(abp_occ, 0) == ()
    assert abp_scale_occupancies((), 5) == ()
    assert sum(abp_o.abp_count for abp_o in abp_scale_occupancies(abp_occ, 1)) == 1


class abpTestScenarios:
    def abp_test_list_create_rename_delete(
        self, abp_services: abpAppServices, abp_project: tuple[int, abpScenario]
    ) -> None:
        abp_project_id, abp_base = abp_project
        assert [
            abp_s.abp_name
            for abp_s in abp_services.abp_simulations.abp_list_scenarios(abp_project_id)
        ] == [abp_BASE_SCENARIO]
        abp_variant = abp_services.abp_simulations.abp_save_variant(
            abp_project_id, "Salida 2 bloqueada", abp_base, 150, {"Salida 2"}
        )
        assert abp_variant.abp_total_occupants == 60
        assert abp_variant.abp_blocked_exits == frozenset({"Salida 2"})
        assert abp_variant.abp_seed == abp_base.abp_seed
        abp_names = [
            abp_s.abp_name
            for abp_s in abp_services.abp_simulations.abp_list_scenarios(abp_project_id)
        ]
        assert abp_names == [abp_BASE_SCENARIO, "Salida 2 bloqueada"]
        abp_renamed = abp_services.abp_simulations.abp_save_variant(
            abp_project_id,
            "Sin salida 2",
            abp_base,
            100,
            {"Salida 2"},
            abp_previous_name="Salida 2 bloqueada",
        )
        assert abp_renamed.abp_total_occupants == 40
        abp_names = [
            abp_s.abp_name
            for abp_s in abp_services.abp_simulations.abp_list_scenarios(abp_project_id)
        ]
        assert abp_names == [abp_BASE_SCENARIO, "Sin salida 2"]
        assert (
            abp_services.abp_simulations.abp_load_scenario(abp_project_id, "Sin salida 2")
            == abp_renamed
        )
        abp_services.abp_simulations.abp_delete_scenario(abp_project_id, "Sin salida 2")
        abp_services.abp_simulations.abp_delete_scenario(abp_project_id, "No existe")
        assert len(abp_services.abp_simulations.abp_list_scenarios(abp_project_id)) == 1

    @pytest.mark.parametrize(
        ("abp_name", "abp_percent", "abp_message"),
        [
            ("", 100, "nombre"),
            (abp_BASE_SCENARIO, 100, "paso 4"),
            ("Otro", 0, "mayor que cero"),
        ],
    )
    def abp_test_variant_validation(
        self,
        abp_services: abpAppServices,
        abp_project: tuple[int, abpScenario],
        abp_name: str,
        abp_percent: float,
        abp_message: str,
    ) -> None:
        abp_project_id, abp_base = abp_project
        with pytest.raises(abpUserFacingError, match=abp_message):
            abp_services.abp_simulations.abp_save_variant(
                abp_project_id, abp_name, abp_base, abp_percent, set()
            )

    def abp_test_duplicate_and_protected_names(
        self, abp_services: abpAppServices, abp_project: tuple[int, abpScenario]
    ) -> None:
        abp_project_id, abp_base = abp_project
        abp_services.abp_simulations.abp_save_variant(abp_project_id, "A", abp_base, 100, set())
        with pytest.raises(abpUserFacingError, match="Ya existe"):
            abp_services.abp_simulations.abp_save_variant(abp_project_id, "A", abp_base, 100, set())
        with pytest.raises(abpUserFacingError, match="no se puede eliminar"):
            abp_services.abp_simulations.abp_delete_scenario(abp_project_id, abp_BASE_SCENARIO)
        with pytest.raises(abpUserFacingError, match="No existe"):
            abp_services.abp_simulations.abp_load_scenario(abp_project_id, "Z")

    def abp_test_blocking_an_exit_takes_longer(
        self, abp_services: abpAppServices, abp_project: tuple[int, abpScenario]
    ) -> None:
        abp_project_id, abp_base = abp_project
        abp_variant = abp_services.abp_simulations.abp_save_variant(
            abp_project_id, "Bloqueada", abp_base, 100, {"Salida 2"}
        )
        abp_base_run = abp_services.abp_simulations.abp_run(abp_project_id, abp_PLAN, abp_base)
        abp_variant_run = abp_services.abp_simulations.abp_run(
            abp_project_id, abp_PLAN, abp_variant
        )
        assert (
            abp_variant_run.abp_result.abp_total_time_s > abp_base_run.abp_result.abp_total_time_s
        )
        assert {abp_n for abp_n, _ in abp_variant_run.abp_result.abp_time_per_exit_s} == {
            "Salida 1"
        }
        abp_last_base = abp_services.abp_simulations.abp_last_run(abp_project_id)
        abp_last_variant = abp_services.abp_simulations.abp_last_run(abp_project_id, "Bloqueada")
        assert abp_last_base is not None
        assert abp_last_variant is not None
        assert abp_last_base.abp_simulation_id == abp_base_run.abp_simulation_id
        assert abp_last_variant.abp_simulation_id == abp_variant_run.abp_simulation_id


class abpTestCalibration:
    def abp_test_recovers_known_factors_and_applies_them(
        self, abp_services: abpAppServices, abp_project: tuple[int, abpScenario]
    ) -> None:
        abp_project_id, abp_base = abp_project
        abp_participants = 30
        abp_drill_scenario = dataclasses.replace(
            abp_base,
            abp_occupancies=abp_scale_occupancies(abp_base.abp_occupancies, abp_participants),
        )
        abp_true_profiles = abp_scale_profiles(
            abp_services.abp_simulations.abp_profiles(), 1.5, 0.8
        )
        abp_truth = abp_services.abp_simulations.abp_simulate(
            abp_PLAN, abp_drill_scenario, abp_true_profiles
        ).abp_result
        abp_drill = abpRealDrill(
            date(2026, 10, 8),
            abp_participants,
            abp_truth.abp_total_time_s,
            abp_truth.abp_time_per_exit_s,
        )
        abp_progress: list[float] = []
        abp_result = abp_services.abp_calibration.abp_calibrate(
            abp_project_id,
            abp_PLAN,
            abp_base,
            abp_drill,
            abp_reaction_factors=(1.0, 1.5),
            abp_speed_factors=(0.8, 1.0),
            abp_progress=abp_progress.append,
        )
        assert (abp_result.abp_best.abp_reaction_factor, abp_result.abp_best.abp_speed_factor) == (
            1.5,
            0.8,
        )
        assert abp_result.abp_best.abp_error == pytest.approx(0.0)
        assert abp_result.abp_total_error_before > abp_result.abp_total_error_after
        assert abp_result.abp_meets_target
        assert abp_progress == sorted(abp_progress)
        assert abp_progress[-1] == pytest.approx(1.0)
        assert abp_services.abp_calibration.abp_drills(abp_project_id) == [abp_drill]

        abp_before = {
            abp_p.abp_name: abp_p for abp_p in abp_services.abp_simulations.abp_profiles()
        }
        abp_services.abp_calibration.abp_apply(abp_result)
        abp_after = {abp_p.abp_name: abp_p for abp_p in abp_services.abp_simulations.abp_profiles()}
        for abp_name, abp_profile in abp_before.items():
            assert abp_after[abp_name].abp_reaction_mean_s == pytest.approx(
                abp_profile.abp_reaction_mean_s * 1.5
            )
            assert abp_after[abp_name].abp_max_speed_mps == pytest.approx(
                abp_profile.abp_max_speed_mps * 0.8
            )

    def abp_test_cancel_and_empty_scenario(
        self, abp_services: abpAppServices, abp_project: tuple[int, abpScenario]
    ) -> None:
        abp_project_id, abp_base = abp_project
        abp_drill = abpRealDrill(date(2026, 10, 8), 20, 60.0)
        with pytest.raises(abpOperationCancelled):
            abp_services.abp_calibration.abp_calibrate(
                abp_project_id, abp_PLAN, abp_base, abp_drill, abp_should_cancel=lambda: True
            )
        assert abp_services.abp_calibration.abp_drills(abp_project_id) == []
        abp_empty = dataclasses.replace(abp_base, abp_occupancies=())
        with pytest.raises(abpUserFacingError, match="paso 4"):
            abp_services.abp_calibration.abp_calibrate(
                abp_project_id, abp_PLAN, abp_empty, abp_drill
            )
