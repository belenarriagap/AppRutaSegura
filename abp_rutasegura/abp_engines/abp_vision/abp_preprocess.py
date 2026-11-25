from __future__ import annotations

import itertools

import cv2
import numpy as np

from abp_rutasegura.abp_engines.abp_vision.abp_images import abpGrayImage, abpMask, abpRGBImage


def abp_to_gray(abp_image: abpRGBImage) -> abpGrayImage:
    if abp_image.ndim == 2:
        return np.ascontiguousarray(abp_image, dtype=np.uint8)
    return np.ascontiguousarray(cv2.cvtColor(abp_image, cv2.COLOR_RGB2GRAY), dtype=np.uint8)


def abp_binarize(abp_gray: abpGrayImage, *, abp_min_component_px: int = 12) -> abpMask:
    abp_smoothed = cv2.medianBlur(abp_gray, 3)
    abp_block = max(31, (min(abp_gray.shape) // 25) | 1)
    abp_adaptive = cv2.adaptiveThreshold(
        abp_smoothed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, abp_block, 15
    )
    abp_otsu_value, _ = cv2.threshold(abp_smoothed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    abp_dark = abp_smoothed < abp_otsu_value * 0.6
    abp_mask = (abp_adaptive > 0) | abp_dark
    return abp_remove_small_components(abp_mask, abp_min_component_px)


def abp_remove_small_components(abp_mask: abpMask, abp_min_area: int) -> abpMask:
    abp_count, abp_labels, abp_stats, _ = cv2.connectedComponentsWithStats(
        abp_mask.astype(np.uint8), connectivity=8
    )
    if abp_count <= 1:
        return abp_mask.copy()
    abp_keep = abp_stats[:, cv2.CC_STAT_AREA] >= abp_min_area
    abp_keep[0] = False
    return np.asarray(abp_keep[abp_labels], dtype=np.bool_)


def abp_thin(abp_mask: abpMask) -> abpMask:
    abp_img = np.pad(abp_mask.astype(np.uint8), 1)
    while True:
        abp_changed = False
        for abp_step in (0, 1):
            abp_p2 = abp_img[:-2, 1:-1]
            abp_p3 = abp_img[:-2, 2:]
            abp_p4 = abp_img[1:-1, 2:]
            abp_p5 = abp_img[2:, 2:]
            abp_p6 = abp_img[2:, 1:-1]
            abp_p7 = abp_img[2:, :-2]
            abp_p8 = abp_img[1:-1, :-2]
            abp_p9 = abp_img[:-2, :-2]
            abp_center = abp_img[1:-1, 1:-1]
            abp_neighbours = [
                abp_p2,
                abp_p3,
                abp_p4,
                abp_p5,
                abp_p6,
                abp_p7,
                abp_p8,
                abp_p9,
                abp_p2,
            ]
            abp_count = abp_p2 + abp_p3 + abp_p4 + abp_p5 + abp_p6 + abp_p7 + abp_p8 + abp_p9
            abp_transitions = sum(
                ((abp_a == 0) & (abp_b == 1)).astype(np.uint8)
                for abp_a, abp_b in itertools.pairwise(abp_neighbours)
            )
            if abp_step == 0:
                abp_cond = (abp_p2 * abp_p4 * abp_p6 == 0) & (abp_p4 * abp_p6 * abp_p8 == 0)
            else:
                abp_cond = (abp_p2 * abp_p4 * abp_p8 == 0) & (abp_p2 * abp_p6 * abp_p8 == 0)
            abp_remove = (
                (abp_center == 1)
                & (abp_count >= 2)
                & (abp_count <= 6)
                & (abp_transitions == 1)
                & abp_cond
            )
            if abp_remove.any():
                abp_changed = True
                abp_center[abp_remove] = 0
        if not abp_changed:
            break
    return np.asarray(abp_img[1:-1, 1:-1] == 1, dtype=np.bool_)


def abp_estimate_wall_thickness(abp_mask: abpMask) -> float:
    if not abp_mask.any():
        return 0.0
    abp_dist = cv2.distanceTransform(abp_mask.astype(np.uint8), cv2.DIST_L2, 5)
    abp_ridge = abp_dist >= cv2.dilate(abp_dist, np.ones((3, 3), np.uint8)) - 1e-6
    abp_values = abp_dist[abp_ridge & (abp_dist >= 1.5)]
    if abp_values.size == 0:
        return float(2 * abp_dist.max())
    return float(2.0 * np.percentile(abp_values, 80))
