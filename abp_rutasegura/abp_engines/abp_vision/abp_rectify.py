from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage


def abp_order_corners(abp_corners: Sequence[abpPoint]) -> npt.NDArray[np.float32]:
    if len(abp_corners) != 4:
        raise ValueError("Se necesitan exactamente 4 esquinas.")
    abp_pts = np.array([[abp_p.abp_x, abp_p.abp_y] for abp_p in abp_corners], dtype=np.float32)
    abp_sums = abp_pts.sum(axis=1)
    abp_diffs = abp_pts[:, 1] - abp_pts[:, 0]
    abp_ordered = np.array(
        [
            abp_pts[np.argmin(abp_sums)],
            abp_pts[np.argmin(abp_diffs)],
            abp_pts[np.argmax(abp_sums)],
            abp_pts[np.argmax(abp_diffs)],
        ],
        dtype=np.float32,
    )
    if len({tuple(abp_p) for abp_p in abp_ordered.tolist()}) != 4:
        raise ValueError("Las 4 esquinas deben ser puntos distintos de un cuadrilátero.")
    abp_area = 0.5 * abs(
        float(
            np.dot(abp_ordered[:, 0], np.roll(abp_ordered[:, 1], -1))
            - np.dot(abp_ordered[:, 1], np.roll(abp_ordered[:, 0], -1))
        )
    )
    if abp_area < 100.0:
        raise ValueError("Las esquinas marcadas encierran un área demasiado pequeña.")
    return abp_ordered


def abp_rectify(abp_image: abpRGBImage, abp_corners: Sequence[abpPoint]) -> abpRGBImage:
    abp_src = abp_order_corners(abp_corners)
    abp_tl, abp_tr, abp_br, abp_bl = abp_src
    abp_width = round(max(np.linalg.norm(abp_tr - abp_tl), np.linalg.norm(abp_br - abp_bl)))
    abp_height = round(max(np.linalg.norm(abp_bl - abp_tl), np.linalg.norm(abp_br - abp_tr)))
    abp_dst = np.array(
        [[0, 0], [abp_width - 1, 0], [abp_width - 1, abp_height - 1], [0, abp_height - 1]],
        np.float32,
    )
    abp_matrix = cv2.getPerspectiveTransform(abp_src, abp_dst)
    abp_warped = cv2.warpPerspective(
        abp_image,
        abp_matrix,
        (abp_width, abp_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return np.ascontiguousarray(abp_warped, dtype=np.uint8)
