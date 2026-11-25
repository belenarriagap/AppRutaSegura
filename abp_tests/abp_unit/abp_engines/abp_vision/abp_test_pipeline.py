from __future__ import annotations

import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_metrics import (
    abp_coverage,
    abp_opening_score,
    abp_wall_score,
    abpScore,
)
from abp_rutasegura.abp_engines.abp_vision.abp_pipeline import abp_detect_plan, abpVisionParams
from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan, abpSyntheticPlan

abp_SEEDS = range(6)
abp_TARGET = 0.85


def abp__scores(
    abp_plan: abpSyntheticPlan, abp_params: abpVisionParams
) -> tuple[abpScore, abpScore, abpScore]:
    abp_result = abp_detect_plan(abp_plan.abp_image, abp_params)
    abp_tol = 0.2 / abp_plan.abp_scale_m_per_px
    abp_walls = abp_wall_score(
        [abp_w.abp_segment for abp_w in abp_result.abp_walls], abp_plan.abp_walls, abp_tol
    )
    abp_predicted = [abp_d.abp_segment for abp_d in abp_result.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_result.abp_exits
    ]
    abp_openings = abp_opening_score(abp_predicted, abp_plan.abp_openings, abp_tol)
    abp_exits = abp_opening_score(
        [abp_e.abp_segment for abp_e in abp_result.abp_exits], abp_plan.abp_exits, abp_tol
    )
    return abp_walls, abp_openings, abp_exits


@pytest.fixture(scope="module")
def abp_plans() -> list[abpSyntheticPlan]:
    return [abp_generate_plan(abp_seed) for abp_seed in abp_SEEDS]


def abp_test_synthetic_plans_meet_target_with_scale(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_rows = [
        abp__scores(abp_p, abpVisionParams(abp_scale_m_per_px=abp_p.abp_scale_m_per_px))
        for abp_p in abp_plans
    ]
    abp_walls = np.mean(
        [[abp_w.abp_precision, abp_w.abp_recall] for abp_w, _, _ in abp_rows], axis=0
    )
    abp_openings = np.mean(
        [[abp_o.abp_precision, abp_o.abp_recall] for _, abp_o, _ in abp_rows], axis=0
    )
    abp_exits = np.mean(
        [[abp_e.abp_precision, abp_e.abp_recall] for _, _, abp_e in abp_rows], axis=0
    )
    assert (abp_walls >= abp_TARGET).all(), abp_walls
    assert (abp_openings >= abp_TARGET).all(), abp_openings
    assert (abp_exits >= abp_TARGET).all(), abp_exits


def abp_test_detection_without_scale_still_works(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_rows = [abp__scores(abp_p, abpVisionParams()) for abp_p in abp_plans[:3]]
    assert np.mean([abp_w.abp_f1 for abp_w, _, _ in abp_rows]) >= abp_TARGET
    assert np.mean([abp_o.abp_f1 for _, abp_o, _ in abp_rows]) >= abp_TARGET


def abp_test_exits_are_proposals_pending_confirmation(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_plan = abp_plans[0]
    abp_result = abp_detect_plan(
        abp_plan.abp_image, abpVisionParams(abp_scale_m_per_px=abp_plan.abp_scale_m_per_px)
    )
    assert abp_result.abp_exits
    assert all(not abp_e.abp_confirmed for abp_e in abp_result.abp_exits)
    assert [abp_e.abp_name for abp_e in abp_result.abp_exits] == [
        f"Salida {abp_i + 1}" for abp_i in range(len(abp_result.abp_exits))
    ]
    assert all(0.0 <= abp_d.abp_confidence <= 1.0 for abp_d in abp_result.abp_doors)
    assert all(0.0 <= abp_w.abp_confidence <= 1.0 for abp_w in abp_result.abp_walls)


def abp_test_door_widths_are_accurate(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_plan = abp_plans[1]
    abp_result = abp_detect_plan(
        abp_plan.abp_image, abpVisionParams(abp_scale_m_per_px=abp_plan.abp_scale_m_per_px)
    )
    for abp_truth in abp_plan.abp_doors:
        abp_nearest = min(
            abp_result.abp_doors,
            key=lambda abp_d: abp_d.abp_segment.abp_midpoint.abp_distance_to(
                abp_truth.abp_midpoint
            ),
        )
        abp_error_m = (
            abs(abp_nearest.abp_segment.abp_length - abp_truth.abp_length)
            * abp_plan.abp_scale_m_per_px
        )
        assert abp_error_m < 0.1


def abp_test_opening_widths_have_no_systematic_bias(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_errors = []
    for abp_plan in abp_plans:
        abp_result = abp_detect_plan(
            abp_plan.abp_image, abpVisionParams(abp_scale_m_per_px=abp_plan.abp_scale_m_per_px)
        )
        abp_found = [abp_d.abp_segment for abp_d in abp_result.abp_doors] + [
            abp_e.abp_segment for abp_e in abp_result.abp_exits
        ]
        for abp_truth in abp_plan.abp_openings:
            abp_nearest = min(
                abp_found,
                key=lambda abp_s: abp_s.abp_midpoint.abp_distance_to(abp_truth.abp_midpoint),
            )
            if abp_nearest.abp_midpoint.abp_distance_to(abp_truth.abp_midpoint) < 20:
                abp_errors.append(
                    (abp_nearest.abp_length - abp_truth.abp_length) * abp_plan.abp_scale_m_per_px
                )
    assert abs(float(np.mean(abp_errors))) < 0.02


def abp_test_detection_is_deterministic(abp_plans: list[abpSyntheticPlan]) -> None:
    abp_plan = abp_plans[2]
    assert abp_detect_plan(abp_plan.abp_image) == abp_detect_plan(abp_plan.abp_image)


def abp_test_blank_image_returns_nothing() -> None:
    abp_result = abp_detect_plan(np.full((300, 400, 3), 255, np.uint8))
    assert abp_result.abp_walls == ()
    assert abp_result.abp_doors == ()


def abp_test_synthetic_generator_is_reproducible() -> None:
    abp_a, abp_b = abp_generate_plan(11), abp_generate_plan(11)
    assert np.array_equal(abp_a.abp_image, abp_b.abp_image)
    assert abp_a.abp_walls == abp_b.abp_walls
    assert not np.array_equal(abp_a.abp_image, abp_generate_plan(12).abp_image)


class abpTestMetrics:
    def abp_test_perfect_and_shifted_walls(self) -> None:
        abp_truth = [abpSegment(abpPoint(0, 0), abpPoint(100, 0))]
        assert abp_wall_score(abp_truth, abp_truth, abp_tol=2) == abpScore(1.0, 1.0)
        abp_shifted = [abpSegment(abpPoint(0, 10), abpPoint(100, 10))]
        assert abp_wall_score(abp_shifted, abp_truth, abp_tol=2) == abpScore(0.0, 0.0)

    def abp_test_partial_coverage(self) -> None:
        abp_truth = [abpSegment(abpPoint(0, 0), abpPoint(100, 0))]
        abp_half = [abpSegment(abpPoint(0, 0), abpPoint(50, 0))]
        assert abp_coverage(abp_truth, abp_half, abp_tol=1) == pytest.approx(0.5, abs=0.05)
        assert abp_coverage([], [], abp_tol=1) == 1.0

    def abp_test_openings_matched_one_to_one(self) -> None:
        abp_truth = [
            abpSegment(abpPoint(0, 0), abpPoint(40, 0)),
            abpSegment(abpPoint(200, 0), abpPoint(240, 0)),
        ]
        abp_predicted = [
            abpSegment(abpPoint(2, 1), abpPoint(41, 1)),
            abpSegment(abpPoint(5, 0), abpPoint(38, 0)),
        ]
        abp_score = abp_opening_score(abp_predicted, abp_truth, abp_tol=5)
        assert abp_score.abp_precision == 0.5
        assert abp_score.abp_recall == 0.5
        assert abp_score.abp_f1 == pytest.approx(0.5)
        assert abp_opening_score([], [], abp_tol=5) == abpScore(1.0, 1.0)
