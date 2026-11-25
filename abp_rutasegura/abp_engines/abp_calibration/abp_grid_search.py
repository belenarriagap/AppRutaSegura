from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from abp_rutasegura.abp_domain.abp_calibration import abpCalibrationPoint, abpCalibrationResult
from abp_rutasegura.abp_domain.abp_people import abpPersonProfile
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill

abp_DEFAULT_REACTION_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
abp_DEFAULT_SPEED_FACTORS = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2)


class abpCalibrationCancelled(Exception):
    pass


@dataclass(frozen=True)
class abpOutcome:
    abp_total_time_s: float
    abp_per_exit_s: Mapping[str, float] = field(default_factory=dict)


abpEvaluate = Callable[[float, float], abpOutcome]


def abp_relative_errors(abp_outcome: abpOutcome, abp_drill: abpRealDrill) -> list[float]:
    abp_errors = [
        (abp_outcome.abp_total_time_s - abp_drill.abp_total_time_s) / abp_drill.abp_total_time_s
    ]
    for abp_name, abp_observed in abp_drill.abp_time_per_exit_s:
        if abp_observed > 0 and abp_name in abp_outcome.abp_per_exit_s:
            abp_errors.append((abp_outcome.abp_per_exit_s[abp_name] - abp_observed) / abp_observed)
    return abp_errors


def abp_calibration_error(abp_outcome: abpOutcome, abp_drill: abpRealDrill) -> float:
    abp_errors = abp_relative_errors(abp_outcome, abp_drill)
    return math.sqrt(sum(abp_e * abp_e for abp_e in abp_errors) / len(abp_errors))


def abp_scale_profiles(
    abp_profiles: Sequence[abpPersonProfile], abp_reaction_factor: float, abp_speed_factor: float
) -> list[abpPersonProfile]:
    if abp_reaction_factor <= 0 or abp_speed_factor <= 0:
        raise ValueError("Los factores de calibración deben ser positivos.")
    return [
        abpPersonProfile(
            abp_name=abp_p.abp_name,
            abp_max_speed_mps=abp_p.abp_max_speed_mps * abp_speed_factor,
            abp_reaction_mean_s=abp_p.abp_reaction_mean_s * abp_reaction_factor,
            abp_reaction_std_s=abp_p.abp_reaction_std_s * abp_reaction_factor,
            abp_radius_m=abp_p.abp_radius_m,
        )
        for abp_p in abp_profiles
    ]


def abp_grid_search(
    abp_evaluate: abpEvaluate,
    abp_drill: abpRealDrill,
    abp_reaction_factors: Sequence[float] = abp_DEFAULT_REACTION_FACTORS,
    abp_speed_factors: Sequence[float] = abp_DEFAULT_SPEED_FACTORS,
    *,
    abp_progress: Callable[[float], None] | None = None,
    abp_should_cancel: Callable[[], bool] | None = None,
) -> abpCalibrationResult:
    abp_reactions = sorted({*abp_reaction_factors, 1.0})
    abp_speeds = sorted({*abp_speed_factors, 1.0})
    if any(abp_f <= 0 for abp_f in (*abp_reactions, *abp_speeds)):
        raise ValueError("Los factores de calibración deben ser positivos.")
    abp_combos = [(abp_r, abp_s) for abp_r in abp_reactions for abp_s in abp_speeds]
    abp_points: list[abpCalibrationPoint] = []
    for abp_i, (abp_r, abp_s) in enumerate(abp_combos):
        if abp_should_cancel is not None and abp_should_cancel():
            raise abpCalibrationCancelled
        abp_outcome = abp_evaluate(abp_r, abp_s)
        abp_points.append(
            abpCalibrationPoint(
                abp_r,
                abp_s,
                abp_outcome.abp_total_time_s,
                abp_calibration_error(abp_outcome, abp_drill),
            )
        )
        if abp_progress is not None:
            abp_progress((abp_i + 1) / len(abp_combos))
    abp_baseline = next(
        abp_p
        for abp_p in abp_points
        if abp_p.abp_reaction_factor == 1.0 and abp_p.abp_speed_factor == 1.0
    )
    abp_best = min(
        abp_points,
        key=lambda abp_p: (
            round(abp_p.abp_error, 9),
            abs(math.log(abp_p.abp_reaction_factor)) + abs(math.log(abp_p.abp_speed_factor)),
        ),
    )
    return abpCalibrationResult(
        abp_drill.abp_total_time_s, abp_baseline, abp_best, tuple(abp_points)
    )
