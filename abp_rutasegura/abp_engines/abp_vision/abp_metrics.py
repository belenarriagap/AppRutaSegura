from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpSegment


@dataclass(frozen=True, slots=True)
class abpScore:
    abp_precision: float
    abp_recall: float

    @property
    def abp_f1(self) -> float:
        abp_total = self.abp_precision + self.abp_recall
        return 0.0 if abp_total == 0 else 2 * self.abp_precision * self.abp_recall / abp_total


def abp__sample(abp_segments: Sequence[abpSegment], abp_step: float) -> npt.NDArray[np.float64]:
    abp_points = []
    for abp_seg in abp_segments:
        abp_n = max(2, int(np.ceil(abp_seg.abp_length / abp_step)) + 1)
        abp_t = np.linspace(0.0, 1.0, abp_n)
        abp_xs = abp_seg.abp_start.abp_x + abp_t * (abp_seg.abp_end.abp_x - abp_seg.abp_start.abp_x)
        abp_ys = abp_seg.abp_start.abp_y + abp_t * (abp_seg.abp_end.abp_y - abp_seg.abp_start.abp_y)
        abp_points.append(np.column_stack([abp_xs, abp_ys]))
    return np.vstack(abp_points) if abp_points else np.zeros((0, 2))


def abp__distance_to_segments(
    abp_points: npt.NDArray[np.float64], abp_segments: Sequence[abpSegment]
) -> npt.NDArray[np.float64]:
    if not abp_segments:
        return np.full(len(abp_points), np.inf)
    abp_a = np.array([[abp_s.abp_start.abp_x, abp_s.abp_start.abp_y] for abp_s in abp_segments])
    abp_b = np.array([[abp_s.abp_end.abp_x, abp_s.abp_end.abp_y] for abp_s in abp_segments])
    abp_ab = abp_b - abp_a
    abp_len2 = np.maximum((abp_ab**2).sum(axis=1), 1e-12)
    abp_ap = abp_points[:, None, :] - abp_a[None, :, :]
    abp_t = np.clip((abp_ap * abp_ab[None]).sum(axis=2) / abp_len2[None], 0.0, 1.0)
    abp_closest = abp_a[None] + abp_t[..., None] * abp_ab[None]
    abp_dist = np.hypot(*(abp_points[:, None, :] - abp_closest).transpose(2, 0, 1))
    return np.asarray(abp_dist.min(axis=1), dtype=np.float64)


def abp_coverage(
    abp_source: Sequence[abpSegment], abp_reference: Sequence[abpSegment], abp_tol: float
) -> float:
    abp_points = abp__sample(abp_source, abp_step=max(abp_tol / 2, 1.0))
    if len(abp_points) == 0:
        return 1.0 if not abp_reference else 0.0
    return float((abp__distance_to_segments(abp_points, abp_reference) <= abp_tol).mean())


def abp_wall_score(
    abp_predicted: Sequence[abpSegment], abp_truth: Sequence[abpSegment], abp_tol: float
) -> abpScore:
    return abpScore(
        abp_precision=abp_coverage(abp_predicted, abp_truth, abp_tol),
        abp_recall=abp_coverage(abp_truth, abp_predicted, abp_tol),
    )


def abp_opening_score(
    abp_predicted: Sequence[abpSegment], abp_truth: Sequence[abpSegment], abp_tol: float
) -> abpScore:
    if not abp_predicted and not abp_truth:
        return abpScore(1.0, 1.0)
    abp_pairs = []
    for abp_i, abp_p in enumerate(abp_predicted):
        for abp_j, abp_t in enumerate(abp_truth):
            abp_d = abp_p.abp_midpoint.abp_distance_to(abp_t.abp_midpoint)
            if abp_d <= abp_tol + abp_t.abp_length / 2:
                abp_pairs.append((abp_d, abp_i, abp_j))
    abp_used_p: set[int] = set()
    abp_used_t: set[int] = set()
    for _, abp_i, abp_j in sorted(abp_pairs):
        if abp_i not in abp_used_p and abp_j not in abp_used_t:
            abp_used_p.add(abp_i)
            abp_used_t.add(abp_j)
    abp_matched = len(abp_used_p)
    abp_precision = abp_matched / len(abp_predicted) if abp_predicted else 1.0
    abp_recall = abp_matched / len(abp_truth) if abp_truth else 1.0
    return abpScore(abp_precision, abp_recall)
