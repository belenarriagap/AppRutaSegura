from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment

abp_RGB = npt.NDArray[np.uint8]


@dataclass(frozen=True)
class abpSyntheticPlan:
    abp_image: abp_RGB
    abp_walls: tuple[abpSegment, ...]
    abp_doors: tuple[abpSegment, ...]
    abp_exits: tuple[abpSegment, ...]
    abp_wall_thickness_px: float
    abp_scale_m_per_px: float
    abp_seed: int

    @property
    def abp_openings(self) -> tuple[abpSegment, ...]:
        return self.abp_doors + self.abp_exits


@dataclass
class abp__Line:
    abp_start: tuple[float, float]
    abp_end: tuple[float, float]
    abp_openings: list[tuple[float, float, bool]] = field(default_factory=list)

    @property
    def abp_length(self) -> float:
        return math.dist(self.abp_start, self.abp_end)

    def abp_at(self, abp_t: float) -> tuple[float, float]:
        abp_f = abp_t / self.abp_length
        return (
            self.abp_start[0] + abp_f * (self.abp_end[0] - self.abp_start[0]),
            self.abp_start[1] + abp_f * (self.abp_end[1] - self.abp_start[1]),
        )


def abp__splits(
    abp_rng: np.random.Generator, abp_total: float, abp_count: int, abp_min_gap: float
) -> list[float]:
    for _ in range(100):
        abp_values = sorted(
            abp_rng.uniform(abp_min_gap, abp_total - abp_min_gap, size=abp_count).tolist()
        )
        abp_points = [0.0, *abp_values, abp_total]
        if all(abp_b - abp_a >= abp_min_gap for abp_a, abp_b in itertools.pairwise(abp_points)):
            return abp_values
    return [abp_total * (abp_i + 1) / (abp_count + 1) for abp_i in range(abp_count)]


def abp__place_opening(
    abp_rng: np.random.Generator,
    abp_line: abp__Line,
    abp_a: float,
    abp_b: float,
    abp_width: float,
    abp_clearance: float,
) -> tuple[float, float] | None:
    abp_lo, abp_hi = abp_a + abp_clearance, abp_b - abp_clearance - abp_width
    if abp_hi <= abp_lo:
        return None
    abp_start = float(abp_rng.uniform(abp_lo, abp_hi))
    return abp_start, abp_start + abp_width


def abp_generate_plan(
    abp_seed: int,
    *,
    abp_px_per_m: float = 50.0,
    abp_max_rotation_deg: float = 4.0,
    abp_photo_effects: bool = True,
    abp_clutter: bool = True,
    abp_furnished: bool = False,
) -> abpSyntheticPlan:
    abp_rng = np.random.default_rng(abp_seed)
    abp_width_m = float(abp_rng.uniform(12, 22))
    abp_height_m = float(abp_rng.uniform(8, 14))
    abp_t = round(float(abp_rng.uniform(0.15, 0.25)) * abp_px_per_m)
    abp_margin = int(2.0 * abp_px_per_m)
    abp_bw, abp_bh = abp_width_m * abp_px_per_m, abp_height_m * abp_px_per_m
    abp_canvas_w, abp_canvas_h = int(abp_bw + 2 * abp_margin), int(abp_bh + 2 * abp_margin)
    abp_x0, abp_y0, abp_x1, abp_y1 = (
        abp_margin,
        abp_margin,
        abp_margin + abp_bw,
        abp_margin + abp_bh,
    )

    abp_xs = [
        abp_x0 + abp_v
        for abp_v in abp__splits(abp_rng, abp_bw, int(abp_rng.integers(1, 4)), 3.5 * abp_px_per_m)
    ]
    abp_ys = [
        abp_y0 + abp_v
        for abp_v in abp__splits(abp_rng, abp_bh, int(abp_rng.integers(0, 2)), 3.5 * abp_px_per_m)
    ]

    abp_outer = [
        abp__Line((abp_x0, abp_y0), (abp_x1, abp_y0)),
        abp__Line((abp_x1, abp_y0), (abp_x1, abp_y1)),
        abp__Line((abp_x1, abp_y1), (abp_x0, abp_y1)),
        abp__Line((abp_x0, abp_y1), (abp_x0, abp_y0)),
    ]
    abp_inner = [abp__Line((abp_x, abp_y0), (abp_x, abp_y1)) for abp_x in abp_xs] + [
        abp__Line((abp_x0, abp_y), (abp_x1, abp_y)) for abp_y in abp_ys
    ]

    abp_door_w = 0.9 * abp_px_per_m
    abp_clearance = 0.4 * abp_px_per_m + abp_t
    for abp_line in abp_inner:
        abp_vertical = abp_line.abp_start[0] == abp_line.abp_end[0]
        abp_cuts = (
            [abp_y - abp_y0 for abp_y in abp_ys]
            if abp_vertical
            else [abp_x - abp_x0 for abp_x in abp_xs]
        )
        abp_bounds = [0.0, *abp_cuts, abp_line.abp_length]
        for abp_a, abp_b in itertools.pairwise(abp_bounds):
            if abp_rng.random() < 0.85:
                abp_placed = abp__place_opening(
                    abp_rng,
                    abp_line,
                    abp_a + abp_t / 2,
                    abp_b - abp_t / 2,
                    abp_door_w,
                    abp_clearance,
                )
                if abp_placed:
                    abp_line.abp_openings.append((*abp_placed, False))
    for abp_side in abp_rng.choice(4, size=int(abp_rng.integers(1, 3)), replace=False):
        abp_line = abp_outer[int(abp_side)]
        abp_exit_w = float(abp_rng.uniform(1.0, 1.8)) * abp_px_per_m
        abp_placed = abp__place_opening(
            abp_rng,
            abp_line,
            abp_t / 2,
            abp_line.abp_length - abp_t / 2,
            abp_exit_w,
            abp_clearance + 20,
        )
        if abp_placed:
            abp_line.abp_openings.append((*abp_placed, True))

    abp_gray = np.full((abp_canvas_h, abp_canvas_w), 255, dtype=np.uint8)

    def abp_draw_wall(abp_line: abp__Line) -> None:
        (abp_ax, abp_ay), (abp_bx, abp_by) = abp_line.abp_start, abp_line.abp_end
        abp_ux, abp_uy = (
            (abp_bx - abp_ax) / abp_line.abp_length,
            (abp_by - abp_ay) / abp_line.abp_length,
        )
        abp_nx, abp_ny = -abp_uy, abp_ux
        abp_half = abp_t / 2
        abp_corners = np.array(
            [
                (
                    abp_ax - abp_ux * abp_half + abp_nx * abp_half,
                    abp_ay - abp_uy * abp_half + abp_ny * abp_half,
                ),
                (
                    abp_bx + abp_ux * abp_half + abp_nx * abp_half,
                    abp_by + abp_uy * abp_half + abp_ny * abp_half,
                ),
                (
                    abp_bx + abp_ux * abp_half - abp_nx * abp_half,
                    abp_by + abp_uy * abp_half - abp_ny * abp_half,
                ),
                (
                    abp_ax - abp_ux * abp_half - abp_nx * abp_half,
                    abp_ay - abp_uy * abp_half - abp_ny * abp_half,
                ),
            ]
        )
        cv2.fillConvexPoly(abp_gray, abp_corners.round().astype(np.int32), 0)

    for abp_line in abp_outer + abp_inner:
        abp_draw_wall(abp_line)

    for abp_line in abp_outer + abp_inner:
        (abp_ax, abp_ay), (abp_bx, abp_by) = abp_line.abp_start, abp_line.abp_end
        abp_ux, abp_uy = (
            (abp_bx - abp_ax) / abp_line.abp_length,
            (abp_by - abp_ay) / abp_line.abp_length,
        )
        abp_nx, abp_ny = -abp_uy, abp_ux
        for abp_a, abp_b, _ in abp_line.abp_openings:
            abp_pa, abp_pb = abp_line.abp_at(abp_a), abp_line.abp_at(abp_b)
            abp_ext = abp_t / 2 + 2
            abp_gap = np.array(
                [
                    (abp_pa[0] + abp_nx * abp_ext, abp_pa[1] + abp_ny * abp_ext),
                    (abp_pb[0] + abp_nx * abp_ext, abp_pb[1] + abp_ny * abp_ext),
                    (abp_pb[0] - abp_nx * abp_ext, abp_pb[1] - abp_ny * abp_ext),
                    (abp_pa[0] - abp_nx * abp_ext, abp_pa[1] - abp_ny * abp_ext),
                ]
            )
            cv2.fillConvexPoly(abp_gray, abp_gap.round().astype(np.int32), 255)
            abp_hinge, abp_other = (abp_pa, abp_pb) if abp_rng.random() < 0.5 else (abp_pb, abp_pa)
            abp_side = 1.0 if abp_rng.random() < 0.5 else -1.0
            abp_r = abp_b - abp_a
            abp_dx, abp_dy = abp_other[0] - abp_hinge[0], abp_other[1] - abp_hinge[1]
            abp_base = math.degrees(math.atan2(abp_dy, abp_dx))
            abp_sweep = 90.0 * abp_side
            abp_leaf_angle = math.radians(abp_base + abp_sweep)
            cv2.ellipse(
                abp_gray,
                (round(abp_hinge[0]), round(abp_hinge[1])),
                (round(abp_r), round(abp_r)),
                0.0,
                abp_base,
                abp_base + abp_sweep,
                0,
                1,
                cv2.LINE_AA,
            )
            abp_leaf_end = (
                abp_hinge[0] + abp_r * math.cos(abp_leaf_angle),
                abp_hinge[1] + abp_r * math.sin(abp_leaf_angle),
            )
            cv2.line(
                abp_gray,
                (round(abp_hinge[0]), round(abp_hinge[1])),
                (round(abp_leaf_end[0]), round(abp_leaf_end[1])),
                0,
                2,
                cv2.LINE_AA,
            )

    if abp_clutter:
        abp__draw_clutter(
            abp_gray, abp_rng, (abp_x0, abp_y0, abp_x1, abp_y1), abp_xs, abp_ys, abp_px_per_m
        )
    abp_color: npt.NDArray[np.uint8] | None = None
    if abp_furnished:
        abp_color = np.dstack([abp_gray, abp_gray, abp_gray]).copy()
        abp__draw_furniture(
            abp_color,
            abp_rng,
            (abp_x0, abp_y0, abp_x1, abp_y1),
            abp_xs,
            abp_ys,
            abp_px_per_m,
            abp_t,
        )

    abp_walls: list[abpSegment] = []
    abp_doors: list[abpSegment] = []
    abp_exits: list[abpSegment] = []
    for abp_line in abp_outer + abp_inner:
        abp_line_openings = sorted(abp_line.abp_openings)
        abp_pos = 0.0
        for abp_a, abp_b, abp_is_exit in abp_line_openings:
            if abp_a - abp_pos > 1:
                abp_walls.append(
                    abpSegment(
                        abpPoint(*abp_line.abp_at(abp_pos)), abpPoint(*abp_line.abp_at(abp_a))
                    )
                )
            (abp_exits if abp_is_exit else abp_doors).append(
                abpSegment(abpPoint(*abp_line.abp_at(abp_a)), abpPoint(*abp_line.abp_at(abp_b)))
            )
            abp_pos = abp_b
        if abp_line.abp_length - abp_pos > 1:
            abp_walls.append(
                abpSegment(
                    abpPoint(*abp_line.abp_at(abp_pos)),
                    abpPoint(*abp_line.abp_at(abp_line.abp_length)),
                )
            )

    abp_angle = float(abp_rng.uniform(-abp_max_rotation_deg, abp_max_rotation_deg))
    abp_image, abp_matrix = abp__rotate(abp_gray, abp_angle)

    def abp_tf(abp_seg: abpSegment) -> abpSegment:
        abp_pts = (
            np.array(
                [
                    [abp_seg.abp_start.abp_x, abp_seg.abp_start.abp_y, 1.0],
                    [abp_seg.abp_end.abp_x, abp_seg.abp_end.abp_y, 1.0],
                ]
            )
            @ abp_matrix.T
        )
        return abpSegment(abpPoint(*abp_pts[0]), abpPoint(*abp_pts[1]))

    if abp_color is not None:
        abp_channels = [
            abp__rotate(np.ascontiguousarray(abp_color[:, :, abp_c]), abp_angle)[0]
            for abp_c in range(3)
        ]
        if abp_photo_effects:
            abp_channels = [abp__photo_effects(abp_ch, abp_rng) for abp_ch in abp_channels]
        abp_rgb = np.ascontiguousarray(np.dstack(abp_channels))
        return abpSyntheticPlan(
            abp_image=abp_rgb,
            abp_walls=tuple(abp_tf(abp_s) for abp_s in abp_walls),
            abp_doors=tuple(abp_tf(abp_s) for abp_s in abp_doors),
            abp_exits=tuple(abp_tf(abp_s) for abp_s in abp_exits),
            abp_wall_thickness_px=float(abp_t),
            abp_scale_m_per_px=1.0 / abp_px_per_m,
            abp_seed=abp_seed,
        )
    if abp_photo_effects:
        abp_image = abp__photo_effects(abp_image, abp_rng)
    abp_rgb = np.ascontiguousarray(
        np.dstack([abp_image, abp_image, (abp_image * 0.97).astype(np.uint8)])
    )
    return abpSyntheticPlan(
        abp_image=abp_rgb,
        abp_walls=tuple(abp_tf(abp_s) for abp_s in abp_walls),
        abp_doors=tuple(abp_tf(abp_s) for abp_s in abp_doors),
        abp_exits=tuple(abp_tf(abp_s) for abp_s in abp_exits),
        abp_wall_thickness_px=float(abp_t),
        abp_scale_m_per_px=1.0 / abp_px_per_m,
        abp_seed=abp_seed,
    )


def abp__draw_clutter(
    abp_gray: npt.NDArray[np.uint8],
    abp_rng: np.random.Generator,
    abp_box: tuple[float, float, float, float],
    abp_xs: list[float],
    abp_ys: list[float],
    abp_px_per_m: float,
) -> None:
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_box
    abp_cols = [abp_x0, *abp_xs, abp_x1]
    abp_rows = [abp_y0, *abp_ys, abp_y1]
    abp_n = 1
    for abp_ca, abp_cb in itertools.pairwise(abp_cols):
        for abp_ra, abp_rb in itertools.pairwise(abp_rows):
            abp_label = f"AULA {abp_n}" if abp_rng.random() < 0.6 else f"OF. {abp_n}"
            abp_n += 1
            abp_org = (
                int(abp_ca + 0.25 * (abp_cb - abp_ca)),
                int(abp_ra + 0.5 * (abp_rb - abp_ra)),
            )
            cv2.putText(
                abp_gray, abp_label, abp_org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2, cv2.LINE_AA
            )
            for _ in range(int(abp_rng.integers(1, 4))):
                abp_w, abp_h = (
                    abp_rng.uniform(0.6, 1.4) * abp_px_per_m,
                    abp_rng.uniform(0.5, 0.8) * abp_px_per_m,
                )
                abp_px = abp_rng.uniform(
                    abp_ca + 0.7 * abp_px_per_m,
                    max(abp_ca + 0.8 * abp_px_per_m, abp_cb - abp_w - 0.7 * abp_px_per_m),
                )
                abp_py = abp_rng.uniform(
                    abp_ra + 0.7 * abp_px_per_m,
                    max(abp_ra + 0.8 * abp_px_per_m, abp_rb - abp_h - 0.7 * abp_px_per_m),
                )
                cv2.rectangle(
                    abp_gray,
                    (int(abp_px), int(abp_py)),
                    (int(abp_px + abp_w), int(abp_py + abp_h)),
                    0,
                    1,
                )
    abp_yd = int(abp_y0 - 0.9 * abp_px_per_m)
    cv2.line(abp_gray, (int(abp_x0), abp_yd), (int(abp_x1), abp_yd), 0, 1)
    for abp_x in (abp_x0, abp_x1):
        cv2.line(abp_gray, (int(abp_x), abp_yd - 8), (int(abp_x), abp_yd + 8), 0, 1)
    abp_text = f"{(abp_x1 - abp_x0) / abp_px_per_m:.2f}"
    cv2.putText(
        abp_gray,
        abp_text,
        (int((abp_x0 + abp_x1) / 2), abp_yd - 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        0,
        1,
    )


abp__FILLS = (
    (238, 176, 150),
    (246, 222, 140),
    (178, 210, 236),
    (200, 228, 176),
    (226, 190, 226),
    (215, 215, 215),
)


def abp__draw_furniture(
    abp_rgb: npt.NDArray[np.uint8],
    abp_rng: np.random.Generator,
    abp_box: tuple[float, float, float, float],
    abp_xs: list[float],
    abp_ys: list[float],
    abp_px_per_m: float,
    abp_t: int,
) -> None:
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_box
    abp_cols = [abp_x0, *abp_xs, abp_x1]
    abp_rows = [abp_y0, *abp_ys, abp_y1]
    abp_outline_dark = (70, 70, 70)
    abp_pad = 0.8 * abp_px_per_m

    def abp_poly(
        abp_points: npt.NDArray[np.float64], abp_fill: tuple[int, ...], abp_width: int
    ) -> None:
        abp_pts = abp_points.round().astype(np.int32)
        cv2.fillPoly(abp_rgb, [abp_pts], abp_fill)
        cv2.polylines(abp_rgb, [abp_pts], True, abp_outline_dark, abp_width, cv2.LINE_AA)

    def abp_rect(
        abp_cx: float, abp_cy: float, abp_w: float, abp_h: float, abp_angle: float
    ) -> npt.NDArray[np.float64]:
        abp_c, abp_s_ = math.cos(abp_angle), math.sin(abp_angle)
        abp_corners = [
            (-abp_w / 2, -abp_h / 2),
            (abp_w / 2, -abp_h / 2),
            (abp_w / 2, abp_h / 2),
            (-abp_w / 2, abp_h / 2),
        ]
        return np.array(
            [
                (abp_cx + abp_c * abp_a - abp_s_ * abp_b, abp_cy + abp_s_ * abp_a + abp_c * abp_b)
                for abp_a, abp_b in abp_corners
            ]
        )

    for abp_ca, abp_cb in itertools.pairwise(abp_cols):
        for abp_ra, abp_rb in itertools.pairwise(abp_rows):
            if (
                abp_cb - abp_ca < 2 * abp_pad + abp_px_per_m
                or abp_rb - abp_ra < 2 * abp_pad + abp_px_per_m
            ):
                continue
            abp_kind = int(abp_rng.integers(0, 4))
            abp_fill = tuple(
                int(abp_v) for abp_v in abp__FILLS[int(abp_rng.integers(0, len(abp__FILLS)))]
            )
            abp_width = int(abp_rng.integers(2, max(3, round(0.4 * abp_t)) + 1))
            if abp_kind == 0:
                for _ in range(int(abp_rng.integers(2, 5))):
                    abp_cx = abp_rng.uniform(abp_ca + abp_pad, abp_cb - abp_pad)
                    abp_cy = abp_rng.uniform(abp_ra + abp_pad, abp_rb - abp_pad)
                    abp_poly(
                        abp_rect(
                            abp_cx, abp_cy, 1.2 * abp_px_per_m, 0.7 * abp_px_per_m, math.pi / 4
                        ),
                        abp_fill,
                        abp_width,
                    )
            elif abp_kind == 1:
                for _ in range(int(abp_rng.integers(1, 4))):
                    abp_cx = int(abp_rng.uniform(abp_ca + abp_pad, abp_cb - abp_pad))
                    abp_cy = int(abp_rng.uniform(abp_ra + abp_pad, abp_rb - abp_pad))
                    abp_r = int(0.45 * abp_px_per_m)
                    cv2.circle(abp_rgb, (abp_cx, abp_cy), abp_r, abp_fill, -1)
                    cv2.circle(
                        abp_rgb, (abp_cx, abp_cy), abp_r, abp_outline_dark, abp_width, cv2.LINE_AA
                    )
                    for abp_k in range(4):
                        abp_a = abp_k * math.pi / 2 + math.pi / 4
                        abp_chair = (
                            int(abp_cx + 1.6 * abp_r * math.cos(abp_a)),
                            int(abp_cy + 1.6 * abp_r * math.sin(abp_a)),
                        )
                        cv2.circle(abp_rgb, abp_chair, int(0.3 * abp_r), (246, 222, 140), -1)
                        cv2.circle(
                            abp_rgb, abp_chair, int(0.3 * abp_r), abp_outline_dark, 1, cv2.LINE_AA
                        )
            elif abp_kind == 2:
                abp_length = min(abp_cb - abp_ca - 2 * abp_pad, 3.0 * abp_px_per_m)
                abp_cx = (abp_ca + abp_cb) / 2
                abp_cy = abp_rng.uniform(abp_ra + abp_pad, abp_rb - abp_pad)
                abp_poly(
                    abp_rect(abp_cx, abp_cy, abp_length, 0.5 * abp_px_per_m, 0.0),
                    (246, 222, 140),
                    abp_width + 1,
                )
                abp_rug = abp_rect(
                    abp_cx, abp_cy + 1.2 * abp_px_per_m, 1.6 * abp_px_per_m, 1.0 * abp_px_per_m, 0.0
                )
                if abp_rug[:, 1].max() < abp_rb - 0.3 * abp_px_per_m:
                    abp_poly(abp_rug, (214, 160, 150), abp_width + 1)
            else:
                abp_cx = abp_rng.uniform(abp_ca + abp_pad, abp_cb - abp_pad)
                abp_cy = abp_rng.uniform(abp_ra + abp_pad, abp_rb - abp_pad)
                abp_poly(
                    abp_rect(abp_cx, abp_cy, 1.8 * abp_px_per_m, 0.8 * abp_px_per_m, 0.0),
                    (150, 150, 150),
                    abp_width,
                )


def abp__rotate(
    abp_gray: npt.NDArray[np.uint8], abp_angle_deg: float
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.float64]]:
    abp_h, abp_w = abp_gray.shape
    abp_matrix = cv2.getRotationMatrix2D((abp_w / 2, abp_h / 2), abp_angle_deg, 1.0)
    abp_cos, abp_sin = abs(abp_matrix[0, 0]), abs(abp_matrix[0, 1])
    abp_new_w, abp_new_h = (
        int(abp_h * abp_sin + abp_w * abp_cos),
        int(abp_h * abp_cos + abp_w * abp_sin),
    )
    abp_matrix[0, 2] += abp_new_w / 2 - abp_w / 2
    abp_matrix[1, 2] += abp_new_h / 2 - abp_h / 2
    abp_rotated = cv2.warpAffine(
        abp_gray, abp_matrix, (abp_new_w, abp_new_h), flags=cv2.INTER_LINEAR, borderValue=255
    )
    return np.asarray(abp_rotated, dtype=np.uint8), np.asarray(abp_matrix, dtype=np.float64)


def abp__photo_effects(
    abp_gray: npt.NDArray[np.uint8], abp_rng: np.random.Generator
) -> npt.NDArray[np.uint8]:
    abp_sigma = float(abp_rng.uniform(0.5, 1.2))
    abp_img = cv2.GaussianBlur(abp_gray, (0, 0), abp_sigma).astype(np.float64)
    abp_h, abp_w = abp_img.shape
    abp_gx = np.linspace(0, 1, abp_w)[None, :]
    abp_gy = np.linspace(0, 1, abp_h)[:, None]
    abp_light = 1.0 - float(abp_rng.uniform(0.05, 0.25)) * (
        abp_gx * abp_rng.uniform(0, 1) + abp_gy * abp_rng.uniform(0, 1)
    )
    abp_img = abp_img * abp_light + abp_rng.normal(
        0.0, float(abp_rng.uniform(3, 9)), size=abp_img.shape
    )
    return np.clip(abp_img, 0, 255).astype(np.uint8)
