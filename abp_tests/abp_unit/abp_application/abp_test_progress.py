from __future__ import annotations

import dataclasses

from abp_rutasegura.abp_application.abp_progress import (
    abp_STEP_EDIT,
    abp_STEP_LOAD,
    abp_STEP_NORMS,
    abp_STEP_REPORT,
    abp_STEP_ROOMS,
    abp_STEP_SCALE,
    abp_STEP_SIMULATE,
    abp_wizard_progress,
    abpBlocker,
    abpIssue,
    abpStepState,
)
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpStair
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_tests.abp_fixtures.abp_simple_plans import abp__seg, abp_rect, abp_single_room

abp_SCENARIO = abpScenario("Escenario base", 1, (abpOccupancy("Aula 1", "adulto", 10),))


def abp_test_empty_project_needs_everything() -> None:
    abp_progress = abp_wizard_progress(
        abpFloorPlan(), abp_has_image=False, abp_scenario=None, abp_result=None
    )
    abp_states = [abp_s.abp_state for abp_s in abp_progress.abp_steps]
    assert abp_states == [abpStepState.abp_TODO] * 7
    assert abp_progress.abp_steps[abp_STEP_LOAD].abp_issue is abpIssue.abp_NO_IMAGE
    assert abp_progress.abp_steps[abp_STEP_EDIT].abp_issue is abpIssue.abp_NO_WALLS
    assert abp_progress.abp_blocker(abp_STEP_SIMULATE) == abpBlocker(
        abp_STEP_SCALE, abpIssue.abp_NO_SCALE
    )
    assert abp_progress.abp_blocker(abp_STEP_SCALE) == abpBlocker(
        abp_STEP_LOAD, abpIssue.abp_NO_IMAGE
    )
    assert abp_progress.abp_blocker(abp_STEP_LOAD) is None
    assert abp_progress.abp_blocker(abp_STEP_REPORT) is None


def abp_test_complete_plan_until_simulation() -> None:
    abp_progress = abp_wizard_progress(
        abp_single_room(), abp_has_image=True, abp_scenario=abp_SCENARIO, abp_result=None
    )
    abp_states = [abp_s.abp_state for abp_s in abp_progress.abp_steps]
    assert abp_states[:abp_STEP_SIMULATE] == [abpStepState.abp_DONE] * abp_STEP_SIMULATE
    assert abp_progress.abp_steps[abp_STEP_SIMULATE].abp_issue is abpIssue.abp_NO_RUN
    assert abp_progress.abp_blocker(abp_STEP_SIMULATE) is None
    assert abp_progress.abp_steps[abp_STEP_NORMS].abp_state is abpStepState.abp_DONE


def abp_test_exits_pending_and_missing() -> None:
    abp_pending = abp_single_room(abp_confirmed=False)
    abp_progress = abp_wizard_progress(
        abp_pending, abp_has_image=True, abp_scenario=abp_SCENARIO, abp_result=None
    )
    assert abp_progress.abp_steps[abp_STEP_EDIT].abp_issue is abpIssue.abp_NO_EXITS
    assert abp_progress.abp_blocker(abp_STEP_SIMULATE) == abpBlocker(
        abp_STEP_EDIT, abpIssue.abp_NO_EXITS
    )
    abp_both = dataclasses.replace(
        abp_pending,
        abp_exits=(
            *abp_pending.abp_exits,
            abpExit(abp__seg(0, 2, 0, 3), "Salida 2", abp_confirmed=True),
        ),
    )
    abp_progress = abp_wizard_progress(
        abp_both, abp_has_image=True, abp_scenario=abp_SCENARIO, abp_result=None
    )
    assert abp_progress.abp_steps[abp_STEP_EDIT].abp_state is abpStepState.abp_WARNING
    assert abp_progress.abp_steps[abp_STEP_EDIT].abp_issue is abpIssue.abp_PENDING_EXITS
    assert abp_progress.abp_blocker(abp_STEP_SIMULATE) is None


def abp_test_upper_floor_leaves_by_the_stairs() -> None:
    abp_upper = dataclasses.replace(
        abp_single_room(),
        abp_level=1,
        abp_exits=(),
        abp_stairs=(abpStair(abp_rect(1, 1, 2, 2), abp_name="Escalera A"),),
    )
    abp_lowest = abp_wizard_progress(
        abp_upper, abp_has_image=True, abp_scenario=None, abp_result=None
    )
    assert abp_lowest.abp_steps[abp_STEP_EDIT].abp_issue is abpIssue.abp_NO_EXITS
    abp_progress = abp_wizard_progress(
        abp_upper, abp_has_image=True, abp_scenario=None, abp_result=None, abp_is_lowest_floor=False
    )
    assert abp_progress.abp_steps[abp_STEP_EDIT].abp_state is abpStepState.abp_DONE


def abp_test_rooms_without_occupants() -> None:
    abp_empty = abpScenario("Escenario base", 1)
    abp_progress = abp_wizard_progress(
        abp_single_room(), abp_has_image=True, abp_scenario=abp_empty, abp_result=None
    )
    assert abp_progress.abp_steps[abp_STEP_ROOMS].abp_issue is abpIssue.abp_NO_OCCUPANTS
    abp_no_rooms = dataclasses.replace(abp_single_room(), abp_rooms=())
    abp_progress = abp_wizard_progress(
        abp_no_rooms, abp_has_image=True, abp_scenario=abp_SCENARIO, abp_result=None
    )
    assert abp_progress.abp_steps[abp_STEP_ROOMS].abp_issue is abpIssue.abp_NO_ROOMS
    assert abp_progress.abp_blocker(abp_STEP_NORMS) == abpBlocker(
        abp_STEP_ROOMS, abpIssue.abp_NO_ROOMS
    )
