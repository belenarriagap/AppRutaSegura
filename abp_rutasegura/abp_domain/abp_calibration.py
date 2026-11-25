from __future__ import annotations

from dataclasses import dataclass

abp_TARGET_ERROR = 0.20


@dataclass(frozen=True, slots=True)
class abpCalibrationPoint:
    abp_reaction_factor: float
    abp_speed_factor: float
    abp_total_time_s: float
    abp_error: float


@dataclass(frozen=True, slots=True)
class abpCalibrationResult:
    abp_observed_total_s: float
    abp_baseline: abpCalibrationPoint
    abp_best: abpCalibrationPoint
    abp_points: tuple[abpCalibrationPoint, ...]

    @property
    def abp_total_error_before(self) -> float:
        return (
            abs(self.abp_baseline.abp_total_time_s - self.abp_observed_total_s)
            / self.abp_observed_total_s
        )

    @property
    def abp_total_error_after(self) -> float:
        return (
            abs(self.abp_best.abp_total_time_s - self.abp_observed_total_s)
            / self.abp_observed_total_s
        )

    @property
    def abp_meets_target(self) -> bool:
        return self.abp_total_error_after < abp_TARGET_ERROR
