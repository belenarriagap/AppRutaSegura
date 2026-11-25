from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_doors import (
    abp_arc_score,
    abp_building_outline,
    abp_is_on_outline,
)
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import (
    abp_binarize,
    abp_estimate_wall_thickness,
    abp_remove_small_components,
    abp_thin,
)
from abp_rutasegura.abp_engines.abp_vision.abp_walls import (
    abp_group_collinear,
    abp_longest_empty_run,
    abp_merge_intervals,
    abp_merge_parallel_groups,
    abp_occupancy,
    abp_segment_coverage,
    abp_snap_endpoints,
    abp_wall_mask,
    abpLineGroup,
)


def abp__bar_mask(abp_thickness: int) -> np.ndarray:
    abp_mask = np.zeros((80, 200), dtype=bool)
    abp_mask[40 - abp_thickness // 2 : 40 - abp_thickness // 2 + abp_thickness, 20:180] = True
    return abp_mask


class abpTestPreprocess:
    def abp_test_binarize_marks_ink(self) -> None:
        abp_gray = np.full((100, 100), 230, np.uint8)
        abp_gray[40:50, 10:90] = 20
        abp_mask = abp_binarize(abp_gray)
        assert abp_mask[45, 50]
        assert not abp_mask[10, 10]

    def abp_test_small_components_are_removed(self) -> None:
        abp_mask = np.zeros((50, 50), bool)
        abp_mask[5, 5] = True
        abp_mask[20:30, 20:30] = True
        abp_cleaned = abp_remove_small_components(abp_mask, 10)
        assert not abp_cleaned[5, 5]
        assert abp_cleaned[25, 25]

    def abp_test_thin_produces_one_pixel_centerline(self) -> None:
        abp_skeleton = abp_thin(abp__bar_mask(11))
        abp_columns = abp_skeleton[:, 50:150]
        assert (abp_columns.sum(axis=0) == 1).all()
        abp_rows = np.nonzero(abp_columns)[0]
        assert abs(abp_rows.mean() - 40) <= 1

    @pytest.mark.parametrize("abp_thickness", [6, 10, 16])
    def abp_test_wall_thickness_estimate(self, abp_thickness: int) -> None:
        abp_mask = abp__bar_mask(abp_thickness)
        abp_mask[60:61, 20:180] = True
        assert abp_estimate_wall_thickness(abp_mask) == pytest.approx(abp_thickness, abs=2.5)

    def abp_test_wall_mask_drops_thin_lines(self) -> None:
        abp_mask = abp__bar_mask(10)
        abp_mask[70, :] = True
        abp_walls = abp_wall_mask(abp_mask, 10)
        assert abp_walls[40, 100]
        assert not abp_walls[70, 100]


class abpTestLineGrouping:
    def abp_test_collinear_pieces_share_a_group_and_parallels_do_not(self) -> None:
        abp_segments = np.array(
            [
                [0, 100, 200, 101],
                [260, 102, 500, 104],
                [0, 140, 500, 140],
            ],
            dtype=float,
        )
        abp_groups = abp_group_collinear(abp_segments, abp_angle_tol_deg=3, abp_dist_tol=6)
        assert sorted(len(abp_g.abp_members) for abp_g in abp_groups) == [1, 2]

    def abp_test_merge_parallel_groups_and_refit(self) -> None:
        abp_a = abpLineGroup(0.0, 100.0, 200.0, [np.array([0, 100, 200, 100], float)])
        abp_b = abpLineGroup(0.0, 103.0, 100.0, [np.array([300, 103, 400, 103], float)])
        abp_merged = abp_merge_parallel_groups([abp_a, abp_b], abp_angle_tol_deg=3, abp_dist_tol=6)
        assert len(abp_merged) == 1
        for abp_x in (0.0, 200.0, 400.0):
            abp_line = abp_merged[0]
            abp_nx, abp_ny = abp_line.abp_normal
            abp_y = (abp_line.abp_rho - abp_nx * abp_x) / abp_ny
            assert 99.0 <= abp_y <= 104.0

    def abp_test_nearly_horizontal_lines_across_zero_angle(self) -> None:
        abp_segments = np.array([[0, 50, 300, 52], [320, 52.2, 600, 50]], dtype=float)
        abp_groups = abp_group_collinear(abp_segments, abp_angle_tol_deg=3, abp_dist_tol=6)
        assert len(abp_groups) == 1

    def abp_test_merge_intervals(self) -> None:
        assert abp_merge_intervals([(0, 10), (12, 20), (40, 50)], abp_gap_tol=3) == [
            (0, 20),
            (40, 50),
        ]

    def abp_test_occupancy_and_longest_empty_run(self) -> None:
        abp_mask = np.zeros((40, 200), bool)
        abp_mask[18:23, 0:60] = True
        abp_mask[18:23, 110:200] = True
        abp_group = abpLineGroup(0.0, 20.0, 1.0)
        abp_ts, abp_occ = abp_occupancy(abp_mask, abp_group, 0, 199, abp_half_width=2)
        abp_run = abp_longest_empty_run(abp_ts, abp_occ)
        assert abp_run is not None
        assert abp_run[0] == pytest.approx(60, abs=1)
        assert abp_run[1] == pytest.approx(109, abs=1)

    def abp_test_snap_endpoints_closes_corner(self) -> None:
        abp_horizontal = abpSegment(abpPoint(5, 0), abpPoint(100, 0))
        abp_vertical = abpSegment(abpPoint(0, 6), abpPoint(0, 100))
        abp_snapped, abp_joined = abp_snap_endpoints([abp_horizontal, abp_vertical], abp_tol=10)
        assert abp_snapped[0].abp_start == abpPoint(0, 0)
        assert abp_snapped[1].abp_start == abpPoint(0, 0)
        assert abp_joined == [(True, False), (True, False)]

    def abp_test_segment_coverage(self) -> None:
        abp_mask = np.zeros((20, 100), bool)
        abp_mask[10, :50] = True
        assert abp_segment_coverage(
            abp_mask, abpSegment(abpPoint(0, 10), abpPoint(99, 10))
        ) == pytest.approx(0.5, abs=0.05)


class abpTestDoors:
    def abp_test_arc_increases_score(self) -> None:
        abp_residual = np.zeros((200, 200), bool)
        abp_gap = abpSegment(abpPoint(50, 100), abpPoint(100, 100))
        assert abp_arc_score(abp_residual, abp_gap) == 0.0
        abp_canvas = np.zeros((200, 200), np.uint8)
        cv2.ellipse(abp_canvas, (50, 100), (50, 50), 0, 0, -90, 255, 1)
        assert abp_arc_score(abp_canvas > 0, abp_gap) > 0.8

    def abp_test_outline_and_points_on_it(self) -> None:
        abp_mask = np.zeros((200, 300), bool)
        abp_mask[40:50, 40:260] = True
        abp_mask[150:160, 40:260] = True
        abp_mask[40:160, 40:50] = True
        abp_mask[40:160, 250:260] = True
        abp_mask[150:160, 120:170] = False
        abp_outline = abp_building_outline(abp_mask, abp_close_px=70)
        assert abp_outline is not None
        assert abp_is_on_outline(abp_outline, abpPoint(145, 155), abp_tol=15)
        assert not abp_is_on_outline(abp_outline, abpPoint(150, 100), abp_tol=15)
        assert abp_building_outline(np.zeros((10, 10), bool), 5) is None


def abp_test_angle_helpers_are_consistent() -> None:
    abp_group = abpLineGroup(math.pi / 2, -30.0, 1.0)
    abp_p = abp_group.abp_point_at(10)
    assert abp_p.abp_x == pytest.approx(30)
    assert abp_p.abp_y == pytest.approx(10)
