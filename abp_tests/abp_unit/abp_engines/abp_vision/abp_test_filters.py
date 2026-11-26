from __future__ import annotations

import cv2
import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_filters import (
    abp_aligned,
    abp_dominant_angle,
    abp_main_network,
    abp_opening_supported,
    abp_stroke_thickness,
    abp_suppress_light_fills,
    abp_thick_enough,
)
from abp_rutasegura.abp_engines.abp_vision.abp_metrics import abp_opening_score, abp_wall_score
from abp_rutasegura.abp_engines.abp_vision.abp_pipeline import abp_detect_plan, abpVisionParams
from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan


def abp__s(abp_x1: float, abp_y1: float, abp_x2: float, abp_y2: float) -> abpSegment:
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


def abp_test_light_fills_are_removed_but_dark_walls_stay() -> None:
    abp_image = np.full((40, 60, 3), 255, np.uint8)
    abp_image[5:15, 5:30] = (246, 222, 140)
    abp_image[20:30, 5:30] = (20, 40, 120)
    abp_gray = np.asarray(cv2.cvtColor(abp_image, cv2.COLOR_RGB2GRAY), np.uint8)
    abp_out = abp_suppress_light_fills(abp_image, abp_gray)
    assert (abp_out[5:15, 5:30] == 255).all()
    assert (abp_out[20:30, 5:30] == abp_gray[20:30, 5:30]).all()
    assert abp_suppress_light_fills(abp_gray, abp_gray) is abp_gray


def abp_test_stroke_thickness_separates_walls_from_outlines() -> None:
    abp_binary = np.zeros((100, 200), bool)
    abp_binary[20:30, 10:190] = True
    abp_binary[70:73, 10:190] = True
    abp_wall, abp_outline = abp__s(10, 24.5, 190, 24.5), abp__s(10, 71, 190, 71)
    assert abp_stroke_thickness(abp_binary, abp_wall) == pytest.approx(10, abs=2)
    assert abp_thick_enough(abp_binary, [abp_wall, abp_outline], abp_thickness=10) == [True, False]


def abp_test_orientation_follows_the_dominant_directions() -> None:
    abp_rotated = 3.0
    abp_segs = []
    for abp_angle in (abp_rotated, abp_rotated + 90):
        abp_rad = np.radians(abp_angle)
        abp_segs.append(abp__s(0, 0, 200 * np.cos(abp_rad), 200 * np.sin(abp_rad)))
    abp_diagonal = abp__s(0, 0, 50, 50)
    assert abp_dominant_angle(abp_segs) == pytest.approx(abp_rotated, abs=0.5)
    assert abp_aligned([*abp_segs, abp_diagonal], abp_tolerance_deg=6) == [True, True, False]
    assert abp_dominant_angle([]) is None


def abp_test_islands_are_dropped_but_pieces_joined_by_doors_are_kept() -> None:
    abp_walls = [
        abp__s(0, 0, 400, 0),
        abp__s(400, 0, 400, 300),
        abp__s(0, 0, 0, 300),
        abp__s(0, 300, 120, 300),
        abp__s(170, 300, 400, 300),
        abp__s(200, 100, 260, 100),
        abp__s(200, 140, 260, 140),
    ]
    assert abp_main_network(abp_walls, abp_tol=8) == [True] * 5 + [False, False]
    abp_piece = [
        *abp_walls[:3],
        abp__s(0, 300, 100, 300),
        abp__s(150, 300, 250, 300),
        abp__s(300, 300, 400, 300),
    ]
    abp_doors = [abp__s(100, 300, 150, 300), abp__s(250, 300, 300, 300)]
    assert all(abp_main_network(abp_piece, abp_tol=8, abp_links=abp_doors))


def abp_test_openings_need_wall_on_both_sides() -> None:
    abp_walls = [abp__s(0, 0, 100, 0), abp__s(150, 0, 300, 0)]
    assert abp_opening_supported(abp__s(100, 0, 150, 0), abp_walls, abp_tol=5)
    assert not abp_opening_supported(abp__s(100, 0, 150, 60), abp_walls, abp_tol=5)


@pytest.mark.parametrize("abp_seed", [7, 8, 10])
def abp_test_furnished_plans_meet_the_target(abp_seed: int) -> None:
    abp_plan = abp_generate_plan(abp_seed, abp_furnished=True)
    abp_result = abp_detect_plan(
        abp_plan.abp_image, abpVisionParams(abp_scale_m_per_px=abp_plan.abp_scale_m_per_px)
    )
    abp_tol = 0.2 / abp_plan.abp_scale_m_per_px
    abp_walls = abp_wall_score(
        [abp_w.abp_segment for abp_w in abp_result.abp_walls], abp_plan.abp_walls, abp_tol
    )
    abp_openings = abp_opening_score(
        [abp_d.abp_segment for abp_d in abp_result.abp_doors]
        + [abp_e.abp_segment for abp_e in abp_result.abp_exits],
        abp_plan.abp_openings,
        abp_tol,
    )
    assert abp_walls.abp_precision >= 0.95
    assert abp_walls.abp_recall >= 0.9
    assert abp_openings.abp_precision >= 0.85
    assert abp_openings.abp_recall >= 0.85
    abp_without = abp_detect_plan(
        abp_plan.abp_image,
        abpVisionParams(
            abp_scale_m_per_px=abp_plan.abp_scale_m_per_px, abp_furniture_filters=False
        ),
    )
    assert len(abp_without.abp_walls) >= len(abp_result.abp_walls)
