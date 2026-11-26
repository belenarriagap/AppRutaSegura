from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpSimulationResult
from abp_rutasegura.abp_domain.abp_scenario import abpScenario

(
    abp_STEP_LOAD,
    abp_STEP_SCALE,
    abp_STEP_EDIT,
    abp_STEP_ROOMS,
    abp_STEP_NORMS,
    abp_STEP_SIMULATE,
    abp_STEP_REPORT,
) = range(7)
abp_STEP_COUNT = 7


class abpStepState(Enum):
    abp_TODO = "pendiente"
    abp_WARNING = "revisar"
    abp_DONE = "completo"


class abpIssue(Enum):
    abp_NO_IMAGE = "sin_imagen"
    abp_NO_SCALE = "sin_escala"
    abp_NO_WALLS = "sin_muros"
    abp_NO_EXITS = "sin_salidas"
    abp_PENDING_EXITS = "salidas_por_confirmar"
    abp_NO_ROOMS = "sin_ambientes"
    abp_NO_OCCUPANTS = "sin_ocupantes"
    abp_NO_RUN = "sin_simulacion"
    abp_RUN_INCOMPLETE = "simulacion_incompleta"


abp_PREREQUISITES: dict[int, tuple[int, ...]] = {
    abp_STEP_LOAD: (),
    abp_STEP_SCALE: (abp_STEP_LOAD,),
    abp_STEP_EDIT: (abp_STEP_LOAD,),
    abp_STEP_ROOMS: (abp_STEP_SCALE, abp_STEP_EDIT),
    abp_STEP_NORMS: (abp_STEP_SCALE, abp_STEP_ROOMS),
    abp_STEP_SIMULATE: (abp_STEP_SCALE, abp_STEP_EDIT, abp_STEP_ROOMS),
    abp_STEP_REPORT: (),
}


@dataclass(frozen=True)
class abpStepProgress:
    abp_state: abpStepState
    abp_issue: abpIssue | None = None


@dataclass(frozen=True)
class abpBlocker:
    abp_step: int
    abp_issue: abpIssue


@dataclass(frozen=True)
class abpWizardProgress:
    abp_steps: tuple[abpStepProgress, ...]

    def abp_blocker(self, abp_step: int) -> abpBlocker | None:
        for abp_previous in abp_PREREQUISITES.get(abp_step, ()):
            abp_progress = self.abp_steps[abp_previous]
            if (
                abp_progress.abp_state is abpStepState.abp_TODO
                and abp_progress.abp_issue is not None
            ):
                return abpBlocker(abp_previous, abp_progress.abp_issue)
        return None


def abp__has_way_out(abp_plan: abpFloorPlan, abp_is_lowest: bool) -> bool:
    if any(abp_e.abp_confirmed for abp_e in abp_plan.abp_exits) or abp_plan.abp_safe_zones:
        return True
    return not abp_is_lowest and any(abp_s.abp_confirmed for abp_s in abp_plan.abp_stairs)


def abp_wizard_progress(
    abp_plan: abpFloorPlan,
    *,
    abp_has_image: bool,
    abp_scenario: abpScenario | None,
    abp_result: abpSimulationResult | None,
    abp_is_lowest_floor: bool = True,
) -> abpWizardProgress:
    abp_steps: list[abpStepProgress] = []
    abp_steps.append(
        abpStepProgress(abpStepState.abp_DONE)
        if abp_has_image
        else abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_IMAGE)
    )
    abp_has_scale = abp_plan.abp_scale_m_per_px is not None
    abp_steps.append(
        abpStepProgress(abpStepState.abp_DONE)
        if abp_has_scale
        else abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_SCALE)
    )
    if not abp_plan.abp_walls:
        abp_steps.append(abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_WALLS))
    elif not abp__has_way_out(abp_plan, abp_is_lowest_floor):
        abp_steps.append(abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_EXITS))
    elif not all(abp_e.abp_confirmed for abp_e in abp_plan.abp_exits) or not all(
        abp_s.abp_confirmed for abp_s in abp_plan.abp_stairs
    ):
        abp_steps.append(abpStepProgress(abpStepState.abp_WARNING, abpIssue.abp_PENDING_EXITS))
    else:
        abp_steps.append(abpStepProgress(abpStepState.abp_DONE))
    abp_occupants = 0
    if abp_scenario is not None:
        abp_occupants = sum(
            abp_o.abp_count
            for abp_o in abp_scenario.abp_occupancies
            if abp_o.abp_level == abp_plan.abp_level
        )
    if not abp_plan.abp_rooms:
        abp_steps.append(abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_ROOMS))
    elif abp_occupants == 0:
        abp_steps.append(abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_OCCUPANTS))
    else:
        abp_steps.append(abpStepProgress(abpStepState.abp_DONE))
    abp_ready = abp_has_scale and bool(abp_plan.abp_rooms)
    abp_steps.append(abpStepProgress(abpStepState.abp_DONE if abp_ready else abpStepState.abp_TODO))
    if abp_result is None:
        abp_steps.append(abpStepProgress(abpStepState.abp_TODO, abpIssue.abp_NO_RUN))
    elif not abp_result.abp_completed:
        abp_steps.append(abpStepProgress(abpStepState.abp_WARNING, abpIssue.abp_RUN_INCOMPLETE))
    else:
        abp_steps.append(abpStepProgress(abpStepState.abp_DONE))
    abp_steps.append(abpStepProgress(abpStepState.abp_TODO))
    return abpWizardProgress(tuple(abp_steps))
