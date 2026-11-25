from __future__ import annotations

import math

import cv2
import numpy as np

from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_fit_arc, abpArcParams
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import abp_to_gray

abp_MIN_SEGMENT_PX = 4.0
abp_CHAIN_GAP_PX = 5.0
abp_CHAIN_PIECE_PX = 60.0
abp_MIN_CHAIN = 3


def abp_vectorize(abp_image: abpRGBImage, abp_dpi: float = 200.0) -> abpVectorPlan:
    abp_gray = abp_to_gray(abp_image)
    abp_h, abp_w = abp_gray.shape
    abp_found = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(abp_gray)[0]
    abp_segments = (
        np.zeros((0, 4)) if abp_found is None else np.asarray(abp_found, np.float64).reshape(-1, 4)
    )
    abp_length = np.hypot(
        abp_segments[:, 2] - abp_segments[:, 0], abp_segments[:, 3] - abp_segments[:, 1]
    )
    abp_segments = abp_segments[abp_length >= abp_MIN_SEGMENT_PX]
    abp_arcs = abp__dedupe(abp_chain_arcs(abp_segments))
    abp_n = len(abp_segments)
    return abpVectorPlan(
        abp_width=float(abp_w),
        abp_height=float(abp_h),
        abp_dpi=abp_dpi,
        abp_layers=("",),
        abp_segments=abp_segments,
        abp_segment_layer=np.zeros(abp_n, np.int64),
        abp_filled=np.zeros(abp_n, np.bool_),
        abp_arcs=np.array(abp_arcs, np.float64).reshape(-1, 5),
        abp_arc_layer=np.zeros(len(abp_arcs), np.int64),
    )


def abp_chain_arcs(abp_segments: abpFloatArray) -> list[abpArcParams]:
    abp_d = abp_segments[:, 2:] - abp_segments[:, :2]
    abp_length = np.hypot(abp_d[:, 0], abp_d[:, 1])
    abp_short = np.flatnonzero(abp_length <= abp_CHAIN_PIECE_PX)
    abp_s, abp_d = abp_segments[abp_short], abp_d[abp_short]
    if len(abp_s) == 0:
        return []
    abp_angle = np.arctan2(abp_d[:, 1], abp_d[:, 0])
    abp_following = np.full(len(abp_s), -1)
    abp_turn_of = np.zeros(len(abp_s))
    for abp_i in range(len(abp_s)):
        abp_gap = np.hypot(abp_s[:, 0] - abp_s[abp_i, 2], abp_s[:, 1] - abp_s[abp_i, 3])
        abp_near = np.flatnonzero(abp_gap <= abp_CHAIN_GAP_PX)
        abp_turns = (abp_angle[abp_near] - abp_angle[abp_i] + np.pi) % (2 * np.pi) - np.pi
        abp_ok = (np.abs(abp_turns) > math.radians(1.5)) & (np.abs(abp_turns) < math.radians(40))
        abp_ok &= abp_near != abp_i
        if abp_ok.any():
            abp_k = int(np.argmin(np.where(abp_ok, abp_gap[abp_near], np.inf)))
            abp_following[abp_i], abp_turn_of[abp_i] = int(abp_near[abp_k]), abp_turns[abp_k]
    abp_used = np.zeros(len(abp_s), bool)
    abp_heads = set(range(len(abp_s))) - set(abp_following[abp_following >= 0].tolist())
    abp_out: list[abpArcParams] = []
    for abp_start in [*sorted(abp_heads), *range(len(abp_s))]:
        if abp_used[abp_start]:
            continue
        abp_chain = [abp_start]
        abp_sign = 0.0
        while abp_following[abp_chain[-1]] >= 0:
            abp_turn = float(abp_turn_of[abp_chain[-1]])
            abp_following_one = int(abp_following[abp_chain[-1]])
            if (
                abp_following_one in abp_chain
                or abp_used[abp_following_one]
                or abp_turn * abp_sign < 0
            ):
                break
            abp_sign = abp_turn
            abp_chain.append(abp_following_one)
        if len(abp_chain) < abp_MIN_CHAIN:
            continue
        abp_used[abp_chain] = True
        abp_middle = (abp_s[abp_chain, :2] + abp_s[abp_chain, 2:]) / 2
        abp_arc = abp_fit_arc(abp_middle)
        if abp_arc is not None:
            abp_ends = np.vstack(
                [abp_s[abp_chain[:1], :2], abp_middle, abp_s[abp_chain[-1:], 2:]]
            ) - np.array(abp_arc[:2])
            abp_turned = np.unwrap(np.arctan2(abp_ends[:, 1], abp_ends[:, 0]))
            abp_out.append(
                (*abp_arc[:3], float(abp_turned[0]), float(abp_turned[-1] - abp_turned[0]))
            )
    return abp_out


def abp__dedupe(abp_arcs: list[abpArcParams]) -> list[abpArcParams]:
    abp_out: list[abpArcParams] = []
    for abp_arc in sorted(abp_arcs, key=lambda abp_a: -abs(abp_a[4]) * abp_a[2]):
        abp_repeated = any(
            math.hypot(abp_arc[0] - abp_o[0], abp_arc[1] - abp_o[1]) < 0.15 * abp_o[2]
            and abs(abp_arc[2] - abp_o[2]) < 0.15 * abp_o[2]
            for abp_o in abp_out
        )
        if not abp_repeated:
            abp_out.append(abp_arc)
    return abp_out
