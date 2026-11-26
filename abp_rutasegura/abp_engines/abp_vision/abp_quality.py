from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpSegment
from abp_rutasegura.abp_domain.abp_vector import abpFloatArray
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import abp_point_segments_distance

abp_CELL_M = 0.1
abp_ROOM_M2 = (2.0, 400.0)
abp_TOUCH_M = 0.3
abp_REPEATED_M = 0.4


@dataclass(frozen=True, slots=True)
class abpQuality:
    abp_rooms: int
    abp_enclosed_m2: float
    abp_length_m: float
    abp_dangling: float
    abp_repeated: float
    abp_openings: int

    @property
    def abp_score(self) -> float:
        abp_base = 2.0 * self.abp_rooms + 1.5 * min(self.abp_openings, 3 * self.abp_rooms + 2)
        abp_base += 0.15 * min(self.abp_length_m, 12.0 * (self.abp_rooms + 2))
        return abp_base * (1.0 - 0.6 * self.abp_dangling) * (1.0 - 0.9 * self.abp_repeated)


def abp_assess(
    abp_walls: Sequence[abpSegment], abp_openings: Sequence[abpSegment], abp_scale: float
) -> abpQuality:
    abp_w, abp_o = abp__array(abp_walls) * abp_scale, abp__array(abp_openings) * abp_scale
    if len(abp_w) == 0:
        return abpQuality(0, 0.0, 0.0, 1.0, 0.0, len(abp_o))
    abp_length = np.hypot(abp_w[:, 2] - abp_w[:, 0], abp_w[:, 3] - abp_w[:, 1])
    abp_rooms, abp_area = abp__rooms(np.vstack([abp_w, abp_o]))
    abp_loose = 0
    for abp_i in range(len(abp_w)):
        abp_others = np.vstack([np.delete(abp_w, abp_i, axis=0), abp_o])
        for abp_e in (abp_w[abp_i, :2], abp_w[abp_i, 2:]):
            abp_loose += int(
                len(abp_others) == 0
                or abp_point_segments_distance(abp_e, abp_others).min() > abp_TOUCH_M
            )
    return abpQuality(
        abp_rooms=abp_rooms,
        abp_enclosed_m2=abp_area,
        abp_length_m=float(abp_length.sum()),
        abp_dangling=abp_loose / (2 * len(abp_w)),
        abp_repeated=abp__repeated(abp_w, abp_length),
        abp_openings=len(abp_o),
    )


def abp__array(abp_segments: Sequence[abpSegment]) -> abpFloatArray:
    abp_rows = [
        (abp_s.abp_start.abp_x, abp_s.abp_start.abp_y, abp_s.abp_end.abp_x, abp_s.abp_end.abp_y)
        for abp_s in abp_segments
    ]
    return np.array(abp_rows, np.float64).reshape(-1, 4)


def abp__rooms(abp_s: abpFloatArray) -> tuple[int, float]:
    abp_lo = np.minimum(abp_s[:, :2], abp_s[:, 2:]).min(axis=0) - 1.0
    abp_hi = np.maximum(abp_s[:, :2], abp_s[:, 2:]).max(axis=0) + 1.0
    abp_w, abp_h = (int(abp_v) for abp_v in np.ceil((abp_hi - abp_lo) / abp_CELL_M))
    abp_free = np.ones((max(abp_h, 1), max(abp_w, 1)), np.uint8)
    for abp_x in abp_s:
        abp_a, abp_b = (abp_x[:2] - abp_lo) / abp_CELL_M, (abp_x[2:] - abp_lo) / abp_CELL_M
        cv2.line(abp_free, (int(abp_a[0]), int(abp_a[1])), (int(abp_b[0]), int(abp_b[1])), 0, 2)
    abp__count, abp_labels, abp_stats, _ = cv2.connectedComponentsWithStats(
        abp_free, connectivity=4
    )
    abp_outside = int(abp_labels[0, 0])
    abp_areas = np.delete(abp_stats[:, cv2.CC_STAT_AREA], [0, abp_outside]) * abp_CELL_M**2
    abp_good = abp_areas[(abp_areas >= abp_ROOM_M2[0]) & (abp_areas <= abp_ROOM_M2[1])]
    return len(abp_good), float(abp_good.sum())


def abp__repeated(abp_w: abpFloatArray, abp_length: abpFloatArray) -> float:
    abp_angle = np.degrees(np.arctan2(abp_w[:, 3] - abp_w[:, 1], abp_w[:, 2] - abp_w[:, 0])) % 180.0
    abp_middle = (abp_w[:, :2] + abp_w[:, 2:]) / 2
    abp_total = 0.0
    for abp_i in range(len(abp_w)):
        abp_parallel = np.abs((abp_angle - abp_angle[abp_i] + 90) % 180 - 90) < 5
        abp_parallel[abp_i] = False
        if not abp_parallel.any():
            continue
        abp_distance = float(
            abp_point_segments_distance(abp_middle[abp_i], abp_w[abp_parallel]).min()
        )
        abp_total += float(abp_length[abp_i]) if 0.03 < abp_distance < abp_REPEATED_M else 0.0
    return abp_total / max(float(abp_length.sum()), 1e-9)
