from __future__ import annotations

import dataclasses

import pytest
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_simulation_service import abp_BASE_SCENARIO
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSafeZone
from abp_rutasegura.abp_domain.abp_results import abpRunStatistics
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_presentation.abp_scenario_dialogs import (
    abp_TEMPLATE_BLOCKED,
    abp_TEMPLATE_CROWD,
    abp_TEMPLATE_SLOW_REACTION,
    abpScenarioChoice,
    abpScenarioDialog,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_room_with_patio, abp_single_room

abp_OCCUPANTS = (abpOccupancy("Aula 1", "adulto", 15),)


def abp__project(abp_services: abpAppServices, abp_plan: abpFloorPlan) -> tuple[int, abpScenario]:
    abp_project_id = abp_services.abp_projects.abp_create_project(
        "Colegio", abpUseType.abp_EDUCATION
    )
    abp_services.abp_projects.abp_save_floor(abp_project_id, abp_plan)
    abp_base = dataclasses.replace(
        abp_services.abp_simulations.abp_load_scenario(abp_project_id),
        abp_occupancies=abp_OCCUPANTS,
    )
    abp_services.abp_simulations.abp_save_scenario(abp_project_id, abp_base)
    return abp_project_id, abp_base


class abpTestScenarioDomain:
    def abp_test_validation(self) -> None:
        with pytest.raises(ValueError, match="reacción"):
            abpScenario("x", 1, abp_reaction_factor=0)
        with pytest.raises(ValueError, match="velocidad"):
            abpScenario("x", 1, abp_speed_factor=9)
        with pytest.raises(ValueError, match="corridas"):
            abpScenario("x", 1, abp_runs=0)
        assert abpScenario("x", 10, abp_runs=3).abp_seeds == (10, 11, 12)

    def abp_test_statistics(self) -> None:
        abp_stats = abpRunStatistics(
            abp_seeds=(1, 2, 3, 4),
            abp_total_times_s=(100.0, 110.0, 120.0, 130.0),
            abp_ninety_times_s=(80.0, None, 90.0, 100.0),
            abp_completed=(True, True, False, True),
            abp_representative_seed=2,
        )
        assert abp_stats.abp_runs == 4
        assert abp_stats.abp_total_mean_s == pytest.approx(115)
        assert abp_stats.abp_total_std_s == pytest.approx(12.91, abs=0.01)
        assert (abp_stats.abp_total_min_s, abp_stats.abp_total_max_s) == (100, 130)
        assert abp_stats.abp_total_p95_s == pytest.approx(128.5)
        assert abp_stats.abp_ninety_mean_s == pytest.approx(90)
        assert not abp_stats.abp_all_completed


class abpTestService:
    def abp_test_settings_are_saved_and_reloaded(self, abp_services: abpAppServices) -> None:
        abp_project_id, abp_base = abp__project(abp_services, abp_single_room())
        abp_variant = abp_services.abp_simulations.abp_save_variant(
            abp_project_id,
            "Noche",
            abp_base,
            100,
            (),
            abp_description="Sismo de madrugada",
            abp_reaction_factor=2.0,
            abp_speed_factor=0.8,
            abp_runs=3,
        )
        abp_loaded = abp_services.abp_simulations.abp_load_scenario(abp_project_id, "Noche")
        assert abp_loaded == abp_variant
        assert (
            abp_loaded.abp_description,
            abp_loaded.abp_reaction_factor,
            abp_loaded.abp_speed_factor,
            abp_loaded.abp_runs,
        ) == (
            "Sismo de madrugada",
            2.0,
            0.8,
            3,
        )
        with pytest.raises(abpUserFacingError, match="corridas"):
            abp_services.abp_simulations.abp_save_variant(
                abp_project_id, "Mal", abp_base, 100, (), abp_runs=99
            )

    def abp_test_factors_change_the_profiles_and_the_result(
        self, abp_services: abpAppServices
    ) -> None:
        abp__project_id, abp_base = abp__project(abp_services, abp_single_room())
        abp_slow = dataclasses.replace(abp_base, abp_reaction_factor=2.0, abp_speed_factor=0.5)
        abp_adult = next(
            abp_p
            for abp_p in abp_services.abp_simulations.abp_profiles()
            if abp_p.abp_name == "adulto"
        )
        abp_adjusted = next(
            abp_p
            for abp_p in abp_services.abp_simulations.abp_profiles_for(abp_slow)
            if abp_p.abp_name == "adulto"
        )
        assert abp_adjusted.abp_reaction_mean_s == pytest.approx(2 * abp_adult.abp_reaction_mean_s)
        assert abp_adjusted.abp_max_speed_mps == pytest.approx(0.5 * abp_adult.abp_max_speed_mps)
        abp_plan = abp_single_room()
        abp_fast_time = abp_services.abp_simulations.abp_simulate(
            abp_plan, abp_base
        ).abp_result.abp_total_time_s
        abp_slow_time = abp_services.abp_simulations.abp_simulate(
            abp_plan, abp_slow
        ).abp_result.abp_total_time_s
        assert abp_slow_time > abp_fast_time

    def abp_test_several_runs_give_statistics(self, abp_services: abpAppServices) -> None:
        abp_project_id, abp_base = abp__project(abp_services, abp_single_room())
        abp_scenario = dataclasses.replace(abp_base, abp_runs=4)
        abp_progress: list[float] = []
        abp_run = abp_services.abp_simulations.abp_run(
            abp_project_id, abp_single_room(), abp_scenario, abp_progress=abp_progress.append
        )
        abp_stats = abp_run.abp_statistics
        assert abp_stats is not None
        assert abp_stats.abp_seeds == abp_scenario.abp_seeds
        assert len(set(abp_stats.abp_total_times_s)) > 1
        assert abp_stats.abp_total_min_s <= abp_stats.abp_total_mean_s <= abp_stats.abp_total_max_s
        assert abp_run.abp_result.abp_seed == abp_stats.abp_representative_seed
        assert abp_run.abp_result.abp_total_time_s == pytest.approx(
            abp_stats.abp_total_times_s[
                abp_stats.abp_seeds.index(abp_stats.abp_representative_seed)
            ]
        )
        assert abp_progress == sorted(abp_progress)
        assert abp_progress[-1] == 1.0
        abp_reloaded = abp_services.abp_simulations.abp_last_run(abp_project_id, abp_BASE_SCENARIO)
        assert abp_reloaded is not None
        assert abp_reloaded.abp_statistics == abp_stats
        abp_again = abp_services.abp_simulations.abp_run_statistics(abp_single_room(), abp_scenario)
        assert abp_again == abp_stats

    def abp_test_blocked_safe_zone(self, abp_services: abpAppServices) -> None:
        abp_patio = abp_room_with_patio()
        abp_named = dataclasses.replace(
            abp_patio, abp_safe_zones=(abpSafeZone(abp_rect(7, 1, 2, 3), "Patio"),)
        )
        abp__project_id, abp_base = abp__project(abp_services, abp_named)
        abp_services.abp_simulations.abp_simulate(abp_named, abp_base)
        with pytest.raises(abpUserFacingError, match="zona segura"):
            abp_services.abp_simulations.abp_simulate(
                abp_named, dataclasses.replace(abp_base, abp_blocked_exits=frozenset({"Patio"}))
            )


def abp_test_dialog_templates_and_choice(qtbot: QtBot) -> None:
    abp_dialog = abpScenarioDialog(["Salida 1", "Salida 2", "Patio"], 40)
    qtbot.addWidget(abp_dialog)
    abp_dialog.abp_template_combo.setCurrentIndex(abp_TEMPLATE_CROWD)
    assert abp_dialog.abp_percent_spin.value() == 150
    assert "60 personas" in abp_dialog.abp_result_label.text()
    abp_dialog.abp_name_edit.clear()
    abp_dialog.abp_template_combo.setCurrentIndex(abp_TEMPLATE_BLOCKED)
    assert abp_dialog.abp_name_edit.text() == "Salida 1 bloqueada"
    abp_dialog.abp_template_combo.setCurrentIndex(abp_TEMPLATE_SLOW_REACTION)
    abp_dialog.abp_runs_spin.setValue(5)
    abp_dialog.abp_description_edit.setText("De noche")
    abp_choice = abp_dialog.abp_choice()
    assert abp_choice == abpScenarioChoice(
        abp_name="Salida 1 bloqueada",
        abp_percent=100,
        abp_blocked=frozenset(),
        abp_description="De noche",
        abp_reaction_factor=2.0,
        abp_speed_factor=1.0,
        abp_runs=5,
    )
