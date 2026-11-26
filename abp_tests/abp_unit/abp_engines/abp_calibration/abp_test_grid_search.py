from __future__ import annotations

from datetime import date

import pytest

from abp_rutasegura.abp_domain.abp_calibration import abpCalibrationPoint, abpCalibrationResult
from abp_rutasegura.abp_domain.abp_people import abpPersonProfile
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill
from abp_rutasegura.abp_engines.abp_calibration.abp_grid_search import (
    abp_calibration_error,
    abp_grid_search,
    abp_relative_errors,
    abp_scale_profiles,
    abpCalibrationCancelled,
    abpOutcome,
)


def abp_toy_model(abp_reaction_factor: float, abp_speed_factor: float) -> abpOutcome:
    abp_total = 40 * abp_reaction_factor + 60 / abp_speed_factor
    return abpOutcome(abp_total, {"Salida 1": abp_total, "Salida 2": 0.8 * abp_total})


abp_DRILL = abpRealDrill(
    date(2026, 10, 8), abp_participants=120, abp_total_time_s=40 * 1.5 + 60 / 0.8
)


def abp_test_errors() -> None:
    abp_outcome = abpOutcome(110.0, {"Salida 1": 110.0})
    abp_drill = abpRealDrill(date(2026, 1, 1), 10, 100.0, (("Salida 1", 100.0), ("Salida 9", 50.0)))
    assert abp_relative_errors(abp_outcome, abp_drill) == pytest.approx([0.1, 0.1])
    assert abp_calibration_error(abp_outcome, abp_drill) == pytest.approx(0.1)
    assert (
        abp_calibration_error(abpOutcome(100.0), abpRealDrill(date(2026, 1, 1), 10, 100.0)) == 0.0
    )


def abp_test_grid_search_recovers_the_true_factors() -> None:
    abp_progress: list[float] = []
    abp_result = abp_grid_search(abp_toy_model, abp_DRILL, abp_progress=abp_progress.append)
    assert abp_result.abp_best.abp_reaction_factor == 1.5
    assert abp_result.abp_best.abp_speed_factor == 0.8
    assert abp_result.abp_best.abp_error == pytest.approx(0.0)
    assert abp_result.abp_baseline.abp_reaction_factor == 1.0
    assert abp_result.abp_baseline.abp_speed_factor == 1.0
    assert abp_result.abp_total_error_before > 0.2
    assert abp_result.abp_total_error_after == pytest.approx(0.0)
    assert abp_result.abp_meets_target
    assert len(abp_result.abp_points) == 36
    assert abp_progress[-1] == 1.0


def abp_test_baseline_is_always_evaluated() -> None:
    abp_result = abp_grid_search(
        abp_toy_model, abp_DRILL, abp_reaction_factors=(2.0,), abp_speed_factors=(0.5,)
    )
    assert {
        (abp_p.abp_reaction_factor, abp_p.abp_speed_factor) for abp_p in abp_result.abp_points
    } == {
        (1.0, 0.5),
        (1.0, 1.0),
        (2.0, 0.5),
        (2.0, 1.0),
    }


def abp_test_ties_prefer_the_smallest_change() -> None:
    abp_flat = abp_grid_search(
        lambda abp_r, abp_s: abpOutcome(abp_DRILL.abp_total_time_s), abp_DRILL
    )
    assert (abp_flat.abp_best.abp_reaction_factor, abp_flat.abp_best.abp_speed_factor) == (1.0, 1.0)


def abp_test_cancel_and_invalid_factors() -> None:
    with pytest.raises(abpCalibrationCancelled):
        abp_grid_search(abp_toy_model, abp_DRILL, abp_should_cancel=lambda: True)
    with pytest.raises(ValueError, match="positivos"):
        abp_grid_search(abp_toy_model, abp_DRILL, abp_reaction_factors=(0.0,))
    with pytest.raises(ValueError, match="positivos"):
        abp_scale_profiles([], 0.0, 1.0)


def abp_test_scale_profiles_keeps_differences() -> None:
    abp_profiles = [
        abpPersonProfile("adulto", 1.3, 30, 10, 0.25),
        abpPersonProfile("niño", 1.0, 20, 8, 0.2),
    ]
    abp_scaled = abp_scale_profiles(abp_profiles, 1.5, 0.8)
    assert abp_scaled[0].abp_reaction_mean_s == pytest.approx(45)
    assert abp_scaled[0].abp_reaction_std_s == pytest.approx(15)
    assert abp_scaled[1].abp_max_speed_mps == pytest.approx(0.8)
    assert abp_scaled[1].abp_radius_m == 0.2
    assert abp_scaled[0].abp_max_speed_mps / abp_scaled[1].abp_max_speed_mps == pytest.approx(1.3)


def abp_test_result_properties() -> None:
    abp_base = abpCalibrationPoint(1.0, 1.0, 150.0, 0.5)
    abp_best = abpCalibrationPoint(0.8, 1.1, 105.0, 0.05)
    abp_result = abpCalibrationResult(100.0, abp_base, abp_best, (abp_base, abp_best))
    assert abp_result.abp_total_error_before == pytest.approx(0.5)
    assert abp_result.abp_total_error_after == pytest.approx(0.05)
    assert abp_result.abp_meets_target
