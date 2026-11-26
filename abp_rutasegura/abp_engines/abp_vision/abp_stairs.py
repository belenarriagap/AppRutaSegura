from __future__ import annotations

import math
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np

from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorText
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_plain
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp_point_segments_distance,
    abp_regular_patterns,
)

abp_TREAD_M = (0.2, 0.42)
abp_LANDING_M = (0.6, 2.6)
abp_SNAP_M = 0.4
abp_MIN_NUMBERS = 4
abp_TWO_FLIGHTS_M = 1.7
abp_JOIN_M = 0.6
abp_STEP_OUT_M = 0.6
abp_LEVEL_REACH_M = 9.0
abp_RISE_M = (0.25, 2.6)
abp_RISER_M = (0.1, 0.22)
abp_LEVEL = re.compile(r"N\.?\s*P\.?\s*T\.?\s*([+-]?)\s*(\d+[.,]\d+)")
abp_FAN_STEP_DEG = (6.0, 40.0)
abp_FAN_MIN = 4


@dataclass(frozen=True, eq=False, slots=True)
class abpFoundStair:
    abp_area: abpFloatArray
    abp_use: abpStairUse = abpStairUse.abp_AUTO
    abp_entry: abpFloatArray | None = None


@dataclass(eq=False, slots=True)
class abp__Flight:
    abp_box: abpFloatArray
    abp_numbers: list[tuple[int, abpFloatArray]]

    def abp_end(self, abp_index: int) -> abpFloatArray:
        abp_a, abp_b = (0, 1) if abp_index == 0 else (2, 3)
        return np.asarray((self.abp_box[abp_a] + self.abp_box[abp_b]) / 2, np.float64)

    def abp_outward(self, abp_index: int) -> abpFloatArray:
        abp_d = self.abp_end(abp_index) - self.abp_end(1 - abp_index)
        return np.asarray(abp_d / max(float(np.hypot(*abp_d)), 1e-9), np.float64)

    @property
    def abp_low_end(self) -> int | None:
        if len(self.abp_numbers) < 2:
            return None
        abp_first = min(self.abp_numbers)[1]
        return (
            0
            if abp__apart(abp_first, self.abp_end(0)) < abp__apart(abp_first, self.abp_end(1))
            else 1
        )


def abp_find_stairs(
    abp_lines: abpFloatArray,
    abp_walls: abpFloatArray,
    abp_texts: Collection[abpVectorText] = (),
    abp_scale: float = 1.0,
) -> list[abpFoundStair]:
    if len(abp_walls) == 0 or len(abp_lines) == 0:
        return []
    abp_points = np.vstack([abp_walls[:, :2], abp_walls[:, 2:]])
    abp_lo, abp_hi = abp_points.min(axis=0) - 0.3, abp_points.max(axis=0) + 0.3
    abp_flights = abp__flights(abp_lines, abp_texts, abp_scale)
    abp_flights = [
        abp_f
        for abp_f in abp_flights
        if ((abp_f.abp_box >= abp_lo) & (abp_f.abp_box <= abp_hi)).all()
    ]
    abp_levels = abp_floor_levels(abp_texts, abp_scale)
    abp_out: list[abpFoundStair] = []
    abp_climbing: list[abp__Flight] = []
    for abp_flight in abp_flights:
        if abp__same_floor(abp_flight, abp_walls, abp_levels):
            abp_out.append(
                abpFoundStair(
                    abp__fit_to_walls(abp_flight.abp_box, abp_walls, abp_landing=False),
                    abpStairUse.abp_SAME_FLOOR,
                )
            )
        else:
            abp_climbing.append(abp_flight)
    for abp_area, abp_members in abp__join(abp_climbing):
        abp_fitted = abp__fit_to_walls(abp_area, abp_walls)
        abp_numbered = [abp_f for abp_f in abp_members if abp_f.abp_low_end is not None]
        abp_use, abp_entry = abpStairUse.abp_AUTO, None
        if abp_numbered:
            abp_first = min(abp_numbered, key=lambda abp_f: min(abp_f.abp_numbers)[0])
            abp_use, abp_entry = abpStairUse.abp_UP, abp_first.abp_end(abp_first.abp_low_end or 0)
        abp_out.append(abpFoundStair(abp_fitted, abp_use, abp_entry))
    abp_out += [
        abpFoundStair(abp_f)
        for abp_f in abp_fan_stairs(abp_lines)
        if ((abp_f >= abp_lo) & (abp_f <= abp_hi)).all()
    ]
    return abp_out


def abp_floor_levels(
    abp_texts: Collection[abpVectorText], abp_scale: float
) -> list[tuple[abpFloatArray, float]]:
    abp_out: list[tuple[abpFloatArray, float]] = []
    for abp_t in abp_texts:
        abp_match = abp_LEVEL.search(abp_plain(abp_t.abp_text))
        if abp_match:
            abp_value = float(abp_match[2].replace(",", "."))
            abp_out.append(
                (
                    np.array([abp_t.abp_x, abp_t.abp_y]) * abp_scale,
                    -abp_value if abp_match[1] == "-" else abp_value,
                )
            )
    return abp_out


def abp__flights(
    abp_lines: abpFloatArray, abp_texts: Collection[abpVectorText], abp_scale: float
) -> list[abp__Flight]:
    abp__flags, abp_series = abp_regular_patterns(abp_lines)
    abp_boxes = [np.asarray(abp_b, np.float64) for abp_b in abp_series]
    abp_numbered = abp_numbered_flights(abp_texts, abp_lines, abp_scale)
    for abp_box in abp_numbered:
        abp_same = next(
            (
                abp_k
                for abp_k, abp_other in enumerate(abp_boxes)
                if abp__shared(abp_other, abp_box) > 0.4
            ),
            None,
        )
        if abp_same is None:
            abp_boxes.append(abp_box)
        else:
            abp_boxes[abp_same] = abp__union(abp_boxes[abp_same], abp_box)
    abp_chains = abp_number_chains(abp_texts, abp_scale, abp_shortest=2)
    abp_out: list[abp__Flight] = []
    for abp_box in abp_boxes:
        abp_inside = [
            abp_c
            for abp_c in abp_chains
            if np.mean([abp__contains(abp_box, abp_p, 0.25) for abp__n, abp_p in abp_c]) > 0.6
        ]
        abp_best = max(abp_inside, key=len) if abp_inside else []
        abp_out.append(abp__Flight(abp_box, abp_best))
    return abp_out


def abp__same_floor(
    abp_flight: abp__Flight,
    abp_walls: abpFloatArray,
    abp_levels: Sequence[tuple[abpFloatArray, float]],
) -> bool:
    abp_found: list[float] = []
    for abp_end in (0, 1):
        abp_place = abp_flight.abp_end(abp_end) + abp_flight.abp_outward(abp_end) * abp_STEP_OUT_M
        if not abp__visible(abp_flight.abp_end(abp_end), abp_place, abp_walls):
            return False
        abp_seen = [
            (abp__apart(abp_place, abp_where), abp_level)
            for abp_where, abp_level in abp_levels
            if abp__apart(abp_place, abp_where) < abp_LEVEL_REACH_M
            and abp__visible(abp_place, abp_where, abp_walls)
        ]
        if not abp_seen:
            return False
        abp_found.append(min(abp_seen)[1])
    abp_rise = abs(abp_found[1] - abp_found[0])
    if not abp_RISE_M[0] <= abp_rise <= abp_RISE_M[1]:
        return False
    abp_low = abp_flight.abp_low_end
    if abp_low is None:
        return True
    if abp_found[abp_low] > abp_found[1 - abp_low]:
        return False
    abp_steps = max(abp_n for abp_n, abp__p in abp_flight.abp_numbers)
    return abp_RISER_M[0] * abp_steps <= abp_rise + 0.05 and abp_rise <= abp_RISER_M[1] * (
        abp_steps + 1
    )


def abp__apart(abp_a: abpFloatArray, abp_b: abpFloatArray) -> float:
    return float(np.hypot(*(abp_a - abp_b)))


def abp__contains(abp_box: abpFloatArray, abp_p: abpFloatArray, abp_pad: float) -> bool:
    abp_u, abp_n = abp__frame(abp_box)
    abp_x, abp_y = abp_box @ abp_u, abp_box @ abp_n
    abp_px, abp_py = float(abp_p @ abp_u), float(abp_p @ abp_n)
    return bool(
        abp_x.min() - abp_pad <= abp_px <= abp_x.max() + abp_pad
        and abp_y.min() - abp_pad <= abp_py <= abp_y.max() + abp_pad
    )


def abp__shared(abp_a: abpFloatArray, abp_b: abpFloatArray) -> float:
    abp_u, abp_n = abp__frame(abp_a)
    abp_sizes = []
    for abp_axis in (abp_u, abp_n):
        abp_pa, abp_pb = abp_a @ abp_axis, abp_b @ abp_axis
        abp_sizes.append(
            max(0.0, float(min(abp_pa.max(), abp_pb.max()) - max(abp_pa.min(), abp_pb.min())))
        )
    abp_areas = [abp__rect_area(abp_x) for abp_x in (abp_a, abp_b)]
    return abp_sizes[0] * abp_sizes[1] / max(min(abp_areas), 1e-9)


def abp__rect_area(abp_box: abpFloatArray) -> float:
    return abp__apart(abp_box[0], abp_box[1]) * abp__apart(abp_box[1], abp_box[2])


def abp__visible(abp_a: abpFloatArray, abp_b: abpFloatArray, abp_walls: abpFloatArray) -> bool:
    abp_d = abp_b - abp_a
    abp_normal = np.array([-abp_d[1], abp_d[0]])
    abp_side = ((abp_walls[:, :2] - abp_a) @ abp_normal) * (
        (abp_walls[:, 2:] - abp_a) @ abp_normal
    ) < 0
    abp_w = abp_walls[:, 2:] - abp_walls[:, :2]
    abp_wn = np.c_[-abp_w[:, 1], abp_w[:, 0]]
    abp_ours = np.einsum("ij,ij->i", abp_a - abp_walls[:, :2], abp_wn) * np.einsum(
        "ij,ij->i", abp_b - abp_walls[:, :2], abp_wn
    )
    return not bool((abp_side & (abp_ours < 0)).any())


def abp_number_chains(
    abp_texts: Collection[abpVectorText], abp_scale: float, abp_shortest: int = abp_MIN_NUMBERS
) -> list[list[tuple[int, abpFloatArray]]]:
    abp_numbers = [
        (int(abp_t.abp_text), np.array([abp_t.abp_x, abp_t.abp_y]) * abp_scale)
        for abp_t in abp_texts
        if abp_t.abp_text.strip().isdigit() and len(abp_t.abp_text.strip()) <= 3
    ]
    abp_used: set[int] = set()
    abp_chains: list[list[tuple[int, abpFloatArray]]] = []
    abp_order = sorted(range(len(abp_numbers)), key=lambda abp_i: abp_numbers[abp_i][0])
    for abp_start in abp_order:
        if abp_start in abp_used:
            continue
        abp_chain = [abp_start]
        abp_heading: abpFloatArray | None = None
        while True:
            abp_value, abp_place = abp_numbers[abp_chain[-1]]
            abp_best: tuple[float, int] | None = None
            for abp_j, (abp_other, abp_position) in enumerate(abp_numbers):
                if abp_j in abp_used or abp_j in abp_chain or abp_other != abp_value + 1:
                    continue
                abp_step = abp_position - abp_place
                abp_size = float(np.hypot(*abp_step))
                if not abp_TREAD_M[0] <= abp_size <= abp_TREAD_M[1]:
                    continue
                if abp_heading is not None and float(abp_step @ abp_heading) / abp_size < math.cos(
                    0.35
                ):
                    continue
                if abp_best is None or abp_size < abp_best[0]:
                    abp_best = (abp_size, abp_j)
            if abp_best is None:
                break
            abp_step = abp_numbers[abp_best[1]][1] - abp_place
            abp_heading = abp_step / float(np.hypot(*abp_step))
            abp_chain.append(abp_best[1])
        abp_least = abp_MIN_NUMBERS if abp_numbers[abp_start][0] == 1 else max(abp_shortest, 2)
        if len(abp_chain) >= abp_least:
            abp_used.update(abp_chain)
            abp_chains.append([abp_numbers[abp_i] for abp_i in abp_chain])
    return abp_chains


def abp_numbered_flights(
    abp_texts: Collection[abpVectorText], abp_lines: abpFloatArray, abp_scale: float
) -> list[abpFloatArray]:
    abp_out: list[abpFloatArray] = []
    abp_d = abp_lines[:, 2:] - abp_lines[:, :2]
    abp_length = np.maximum(np.hypot(abp_d[:, 0], abp_d[:, 1]), 1e-9)
    for abp_chain in abp_number_chains(abp_texts, abp_scale):
        abp_a, abp_b = abp_chain[0][1], abp_chain[-1][1]
        abp_along = (abp_b - abp_a) / max(float(np.hypot(*(abp_b - abp_a))), 1e-9)
        abp_across = np.array([-abp_along[1], abp_along[0]])
        abp_treads = (np.abs(abp_d @ abp_along) / abp_length < math.sin(math.radians(12))) & (
            abp_length > 0.5
        )
        abp_treads &= abp_length < 4.0
        abp_lefts: list[float] = []
        abp_rights: list[float] = []
        for abp__value, abp_p in abp_chain:
            abp_near = abp_treads & (abp_point_segments_distance(abp_p, abp_lines) < 0.25)
            if not abp_near.any():
                continue
            abp_i = int(np.argmax(np.where(abp_near, abp_length, 0.0)))
            abp_t = sorted(
                (
                    float((abp_lines[abp_i, :2] - abp_a) @ abp_across),
                    float((abp_lines[abp_i, 2:] - abp_a) @ abp_across),
                )
            )
            abp_lefts.append(abp_t[0])
            abp_rights.append(abp_t[1])
        if len(abp_lefts) < 3:
            continue
        abp_step = float(np.hypot(*(abp_b - abp_a))) / (len(abp_chain) - 1)
        abp_t0, abp_t1 = float(np.median(abp_lefts)), float(np.median(abp_rights))
        abp_s0, abp_s1 = -0.6 * abp_step, float((abp_b - abp_a) @ abp_along) + 0.6 * abp_step
        abp_out.append(
            np.array(
                [
                    abp_a + abp_across * abp_t0 + abp_along * abp_s0,
                    abp_a + abp_across * abp_t1 + abp_along * abp_s0,
                    abp_a + abp_across * abp_t1 + abp_along * abp_s1,
                    abp_a + abp_across * abp_t0 + abp_along * abp_s1,
                ]
            )
        )
    return abp_out


def abp__frame(abp_box: abpFloatArray) -> tuple[abpFloatArray, abpFloatArray]:
    abp_u = abp_box[1] - abp_box[0]
    abp_u = abp_u / max(float(np.hypot(*abp_u)), 1e-9)
    return abp_u, np.array([-abp_u[1], abp_u[0]])


def abp__union(abp_a: abpFloatArray, abp_b: abpFloatArray) -> abpFloatArray:
    abp_u, abp_n = abp__frame(abp_a)
    abp_points = np.vstack([abp_a, abp_b])
    abp_x, abp_y = abp_points @ abp_u, abp_points @ abp_n
    return np.array(
        [
            abp_u * abp_x.min() + abp_n * abp_y.min(),
            abp_u * abp_x.max() + abp_n * abp_y.min(),
            abp_u * abp_x.max() + abp_n * abp_y.max(),
            abp_u * abp_x.min() + abp_n * abp_y.max(),
        ]
    )


def abp__join(abp_flights: Sequence[abp__Flight]) -> list[tuple[abpFloatArray, list[abp__Flight]]]:
    abp_rest = list(abp_flights)
    abp_out: list[tuple[abpFloatArray, list[abp__Flight]]] = []
    while abp_rest:
        abp_first = abp_rest.pop(0)
        abp_current, abp_members = abp_first.abp_box, [abp_first]
        abp_joined = True
        while abp_joined:
            abp_joined = False
            for abp_k, abp_other in enumerate(abp_rest):
                if abp__gap(abp_current, abp_other.abp_box) < abp_JOIN_M:
                    abp_current = abp__union(abp_current, abp_other.abp_box)
                    abp_members.append(abp_rest.pop(abp_k))
                    abp_joined = True
                    break
        abp_out.append((abp_current, abp_members))
    return abp_out


def abp__gap(abp_a: abpFloatArray, abp_b: abpFloatArray) -> float:
    abp_u, abp_n = abp__frame(abp_a)
    abp_gaps = []
    for abp_axis in (abp_u, abp_n):
        abp_pa, abp_pb = abp_a @ abp_axis, abp_b @ abp_axis
        abp_gaps.append(
            max(0.0, float(max(abp_pb.min() - abp_pa.max(), abp_pa.min() - abp_pb.max())))
        )
    return math.hypot(abp_gaps[0], abp_gaps[1])


def abp__fit_to_walls(
    abp_box: abpFloatArray, abp_walls: abpFloatArray, *, abp_landing: bool = True
) -> abpFloatArray:
    abp_u, abp_n = abp__frame(abp_box)
    abp_x, abp_y = abp_box @ abp_u, abp_box @ abp_n
    abp_x0, abp_x1, abp_y0, abp_y1 = (
        float(abp_x.min()),
        float(abp_x.max()),
        float(abp_y.min()),
        float(abp_y.max()),
    )
    for abp_side in (-1.0, 1.0):
        abp_edge = abp_x0 if abp_side < 0 else abp_x1
        abp_reach = [
            abp__wall_distance(
                abp_u * abp_edge + abp_n * (abp_y0 + abp_t * (abp_y1 - abp_y0)),
                abp_u * abp_side,
                abp_walls,
            )
            for abp_t in (0.25, 0.5, 0.75)
        ]
        abp_close = [abp_r for abp_r in abp_reach if abp_r is not None and abp_r <= abp_SNAP_M]
        if len(abp_close) >= 2:
            if abp_side < 0:
                abp_x0 -= min(abp_close)
            else:
                abp_x1 += min(abp_close)
    if abp_landing and abp_x1 - abp_x0 >= abp_TWO_FLIGHTS_M:
        abp_ends: list[tuple[float, float]] = []
        for abp_side in (-1.0, 1.0):
            abp_edge = abp_y0 if abp_side < 0 else abp_y1
            abp_found = [
                abp__wall_distance(
                    abp_u * (abp_x0 + abp_t * (abp_x1 - abp_x0)) + abp_n * abp_edge,
                    abp_n * abp_side,
                    abp_walls,
                )
                for abp_t in (0.15, 0.35, 0.65, 0.85)
            ]
            abp_valid = [
                abp_f for abp_f in abp_found if abp_f is not None and abp_f <= abp_LANDING_M[1]
            ]
            if len(abp_valid) >= 3 and max(abp_valid) - min(abp_valid) < 0.5:
                abp_ends.append((float(np.median(abp_valid)), abp_side))
        if abp_ends:
            abp_reach_m, abp_side = min(abp_ends)
            if abp_side < 0:
                abp_y0 -= abp_reach_m
            else:
                abp_y1 += abp_reach_m
    return np.array(
        [
            abp_u * abp_x0 + abp_n * abp_y0,
            abp_u * abp_x1 + abp_n * abp_y0,
            abp_u * abp_x1 + abp_n * abp_y1,
            abp_u * abp_x0 + abp_n * abp_y1,
        ]
    )


def abp__wall_distance(
    abp_p: abpFloatArray, abp_direction: abpFloatArray, abp_walls: abpFloatArray
) -> float | None:
    abp_normal = np.array([-abp_direction[1], abp_direction[0]])
    abp_a, abp_b = (abp_walls[:, :2] - abp_p) @ abp_normal, (abp_walls[:, 2:] - abp_p) @ abp_normal
    abp_crossing = abp_a * abp_b <= 0
    if not abp_crossing.any():
        return None
    abp_w, abp_a, abp_b = abp_walls[abp_crossing], abp_a[abp_crossing], abp_b[abp_crossing]
    abp_span = np.where(np.abs(abp_a - abp_b) < 1e-9, 1.0, abp_a - abp_b)
    abp_ta, abp_tb = (abp_w[:, :2] - abp_p) @ abp_direction, (abp_w[:, 2:] - abp_p) @ abp_direction
    abp_t = abp_ta + (abp_tb - abp_ta) * abp_a / abp_span
    abp_t = abp_t[abp_t > -0.15]
    return max(0.0, float(abp_t.min())) if len(abp_t) else None


def abp_fan_stairs(abp_lines: abpFloatArray) -> list[abpFloatArray]:
    abp_d = abp_lines[:, 2:] - abp_lines[:, :2]
    abp_length = np.hypot(abp_d[:, 0], abp_d[:, 1])
    abp_candidates = np.flatnonzero((abp_length > 0.7) & (abp_length < 2.6))
    abp_out: list[abpFloatArray] = []
    abp_used: set[int] = set()
    for abp_i in abp_candidates:
        if int(abp_i) in abp_used:
            continue
        for abp_k in (0, 2):
            abp_pivot = abp_lines[abp_i, abp_k : abp_k + 2]
            abp_rays: list[tuple[float, int, abpFloatArray]] = []
            for abp_j in abp_candidates:
                for abp_m in (0, 2):
                    if float(np.hypot(*(abp_lines[abp_j, abp_m : abp_m + 2] - abp_pivot))) < 0.12:
                        abp_end = abp_lines[abp_j, 2 - abp_m : 4 - abp_m]
                        abp_angle = math.degrees(math.atan2(*(abp_end - abp_pivot)[::-1]))
                        abp_rays.append((abp_angle, int(abp_j), abp_end))
            if len(abp_rays) < abp_FAN_MIN:
                continue
            abp_rays.sort(key=lambda abp_r: abp_r[0])
            abp_angles = np.array([abp_r[0] for abp_r in abp_rays])
            abp_steps = np.diff(abp_angles)
            if (
                len(abp_steps) == 0
                or not ((abp_steps > abp_FAN_STEP_DEG[0]) & (abp_steps < abp_FAN_STEP_DEG[1])).all()
            ):
                continue
            if float(abp_steps.std()) > 0.35 * float(abp_steps.mean()):
                continue
            abp_used.update(abp_r[1] for abp_r in abp_rays)
            abp_out.append(np.vstack([abp_pivot, *[abp_r[2] for abp_r in abp_rays]]))
            break
    return abp_out
