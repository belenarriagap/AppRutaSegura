from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from abp_rutasegura.abp_application.abp_errors import abpOperationCancelled, abpUserFacingError
from abp_rutasegura.abp_application.abp_simulation_service import (
    abp_scale_occupancies,
    abpSimulationService,
)
from abp_rutasegura.abp_data.abp_database import abpDatabase
from abp_rutasegura.abp_domain.abp_calibration import abpCalibrationResult
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill, abpScenario
from abp_rutasegura.abp_engines.abp_calibration.abp_grid_search import (
    abp_DEFAULT_REACTION_FACTORS,
    abp_DEFAULT_SPEED_FACTORS,
    abp_grid_search,
    abp_scale_profiles,
    abpCalibrationCancelled,
    abpOutcome,
)


class abpCalibrationService:
    def __init__(self, abp_db: abpDatabase, abp_simulations: abpSimulationService) -> None:
        self.abp__db = abp_db
        self.abp__simulations = abp_simulations

    def abp_drills(self, abp_project_id: int) -> list[abpRealDrill]:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            return [abp_d for _, abp_d in abp_uow.abp_drills.abp_list_all(abp_project_id)]

    def abp_calibrate(
        self,
        abp_project_id: int,
        abp_plan: abpFloorPlan | Sequence[abpFloorPlan],
        abp_scenario: abpScenario,
        abp_drill: abpRealDrill,
        *,
        abp_reaction_factors: Sequence[float] = abp_DEFAULT_REACTION_FACTORS,
        abp_speed_factors: Sequence[float] = abp_DEFAULT_SPEED_FACTORS,
        abp_progress: Callable[[float], None] | None = None,
        abp_should_cancel: Callable[[], bool] | None = None,
    ) -> abpCalibrationResult:
        if abp_scenario.abp_total_occupants == 0:
            raise abpUserFacingError(
                "Primero indique cómo se reparten las personas en los ambientes (paso 4)."
            )
        abp_drill_scenario = dataclasses.replace(
            abp_scenario,
            abp_occupancies=abp_scale_occupancies(
                abp_scenario.abp_occupancies, abp_drill.abp_participants
            ),
        )
        abp_base_profiles = self.abp__simulations.abp_profiles()
        abp_combos = len({*abp_reaction_factors, 1.0}) * len({*abp_speed_factors, 1.0})
        abp_done = 0

        def abp_evaluate(abp_reaction: float, abp_speed: float) -> abpOutcome:
            nonlocal abp_done
            abp_profiles = abp_scale_profiles(abp_base_profiles, abp_reaction, abp_speed)

            def abp_inner(abp_fraction: float) -> None:
                if abp_progress is not None:
                    abp_progress(min(1.0, (abp_done + abp_fraction) / abp_combos))

            abp_output = self.abp__simulations.abp_simulate(
                abp_plan,
                abp_drill_scenario,
                abp_profiles,
                abp_progress=abp_inner,
                abp_should_cancel=abp_should_cancel,
            )
            abp_done += 1
            return abpOutcome(
                abp_output.abp_result.abp_total_time_s,
                dict(abp_output.abp_result.abp_time_per_exit_s),
            )

        try:
            abp_result = abp_grid_search(
                abp_evaluate,
                abp_drill,
                abp_reaction_factors,
                abp_speed_factors,
                abp_should_cancel=abp_should_cancel,
            )
        except abpCalibrationCancelled as abp_exc:
            raise abpOperationCancelled from abp_exc
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_drills.abp_add(abp_project_id, abp_drill)
        return abp_result

    def abp_apply(self, abp_result: abpCalibrationResult) -> None:
        abp_best = abp_result.abp_best
        with self.abp__db.abp_unit_of_work() as abp_uow:
            for abp_profile in abp_scale_profiles(
                abp_uow.abp_profiles.abp_list_all(),
                abp_best.abp_reaction_factor,
                abp_best.abp_speed_factor,
            ):
                abp_uow.abp_profiles.abp_save(abp_profile)
