from __future__ import annotations

from collections.abc import Collection, Sequence

import numpy as np

from abp_rutasegura.abp_domain.abp_vector import abpBoolArray, abpFloatArray, abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_plain
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp__angle_diff,
    abp__angles,
    abp__cut_openings,
    abp__double_door,
    abp__drop_shadows,
    abp__ends_near,
    abp__lengths,
    abp__onto_wall,
    abp__snap,
    abp__unit,
    abp_as_detection,
    abp_collapse_parallel,
    abp_detect_vector_plan,
    abp_door_arcs,
    abp_DOOR_MAX_M,
    abp_DOOR_MIN_M,
    abp_doors_from_arcs,
    abp_gaps_between_walls,
    abp_JAMB_REACH_M,
    abp_main_network,
    abp_merge_collinear,
    abp_MIN_WALL_LAYER_M,
    abp_point_segments_distance,
    abp_ray_hit,
    abp_wall_axes,
    abpVectorDetection,
)

abp_WALLS = ("muro", "wall", "tabique", "pared", "drywall", "driwall")
abp_NOT_WALLS = ("fuego", "acab", "texto", "cota")
abp_LOW = ("bajo", "low", "parapeto", "baranda", "melamina")
abp_WINDOWS = ("ventana", "window", "mampara", "vidrio")
abp_COLUMNS = ("columna", "column", "placa")
abp_DOORS = ("puerta", "door")
abp_PIECE_M = 0.12
abp_LOW_SINGLE_M = 0.5
abp_COLUMN_M = (0.12, 1.4)
abp_COLUMN_REACH_M = 0.3
abp_ARC_CHORD_M = 0.7
abp_SMALL_GAP_M = 0.3
abp_LEAF_M = (0.6, 2.4)


def abp_layer_ids(
    abp_vector: abpVectorPlan, abp_words: Collection[str], abp_but: Collection[str] = ()
) -> list[int]:
    abp_out = []
    for abp_i, abp_name in enumerate(abp_vector.abp_layers):
        abp_lowered = abp_plain(abp_name).lower()
        if any(abp_w in abp_lowered for abp_w in abp_words) and not any(
            abp_w in abp_lowered for abp_w in abp_but
        ):
            abp_out.append(abp_i)
    return abp_out


def abp_has_layers(abp_vector: abpVectorPlan, abp_scale: float) -> bool:
    abp_lengths = (
        abp__lengths(abp_vector.abp_segments) * abp_scale
        if len(abp_vector.abp_segments)
        else np.zeros(0)
    )

    def abp_total(abp_ids: list[int]) -> float:
        return float(abp_lengths[np.isin(abp_vector.abp_segment_layer, abp_ids)].sum())

    abp_walls = abp_total(abp_layer_ids(abp_vector, abp_WALLS, abp_NOT_WALLS))
    abp_doors = abp_layer_ids(abp_vector, abp_DOORS)
    abp_arcs = int(np.isin(abp_vector.abp_arc_layer, abp_doors).sum())
    abp_windows = abp_total(abp_layer_ids(abp_vector, abp_WINDOWS))
    return abp_walls >= abp_MIN_WALL_LAYER_M and (
        abp_arcs >= 2 or abp_windows >= abp_MIN_WALL_LAYER_M
    )


def abp_detect_drawing(
    abp_vector: abpVectorPlan, abp_scale: float, *, abp_anchors_px: abpFloatArray | None = None
) -> abpVectorDetection:
    if abp_has_layers(abp_vector, abp_scale):
        abp_found = abp_detect_layered_plan(abp_vector, abp_scale, abp_anchors_px=abp_anchors_px)
        if len(abp_found.abp_walls) >= 4:
            return abp_found
    return abp_detect_vector_plan(abp_vector, abp_scale, abp_anchors_px=abp_anchors_px)


def abp_detect_layered_plan(
    abp_vector: abpVectorPlan, abp_scale: float, *, abp_anchors_px: abpFloatArray | None = None
) -> abpVectorDetection:
    abp_walls_l = abp_layer_ids(abp_vector, abp_WALLS, abp_NOT_WALLS)
    abp_low_l = [
        abp_i
        for abp_i in abp_walls_l
        if any(abp_w in abp_plain(abp_vector.abp_layers[abp_i]).lower() for abp_w in abp_LOW)
    ]
    abp_solid = abp__lines(
        abp_vector, abp_scale, [abp_i for abp_i in abp_walls_l if abp_i not in abp_low_l]
    )
    abp_low = abp__lines(abp_vector, abp_scale, abp_low_l)
    abp_glass = abp__lines(abp_vector, abp_scale, abp_layer_ids(abp_vector, abp_WINDOWS))
    abp_lines = abp_merge_collinear(np.vstack([abp_solid, abp_low, abp_glass]))
    abp_pairs = abp_wall_axes(abp_lines)
    abp_axes = abp_collapse_parallel(abp_pairs)
    abp_axes = (
        np.vstack([abp_axes, abp__single(abp_merge_collinear(abp_low), abp_axes)])
        if len(abp_low)
        else abp_axes
    )
    abp_axes = abp_axes[abp__lengths(abp_axes) >= abp_PIECE_M]
    abp_columns = abp_column_boxes(abp_vector, abp_scale, abp_axes)
    abp_arcs = abp__door_arcs(abp_vector, abp_scale)
    abp_links = (
        np.vstack(
            [np.r_[abp_a[:2], abp_a[abp_k : abp_k + 2]] for abp_a in abp_arcs for abp_k in (3, 5)]
        )
        if len(abp_arcs)
        else np.zeros((0, 4))
    )
    abp_crossing = np.array(
        [np.r_[abp_b[abp_k], abp_b[(abp_k + 2) % 4]] for abp_b in abp_columns for abp_k in (0, 1)]
    )
    abp_links = np.vstack([abp_links, abp_crossing.reshape(-1, 4)])
    abp_anchors = np.zeros((0, 2)) if abp_anchors_px is None else abp_anchors_px * abp_scale
    if len(abp_anchors) == 0 and len(abp_arcs):
        abp_anchors = abp_arcs[:, :2]
    abp_axes = abp_axes[abp_main_network(abp_axes, abp_links, abp_anchors)]
    abp_walls = abp__drop_shadows(abp_axes)
    abp_walls = abp_merge_collinear(
        abp__into_columns(abp_walls, abp_columns),
        abp_angle_deg=4.0,
        abp_offset=0.12,
        abp_gap=abp_SMALL_GAP_M,
    )
    abp_openings = [
        (abp_segment, abp_conf)
        for abp_segment, abp_conf in abp__swing_doors(abp_vector, abp_scale, abp_arcs, abp_walls)
        if abp_DOOR_MIN_M * 0.8 <= float(abp__lengths(abp_segment[None, :])[0]) <= abp_DOOR_MAX_M
    ]
    abp_walls = abp__cut_openings(abp_walls, [abp_o[0] for abp_o in abp_openings])
    abp_walls = abp__snap(abp_walls, [abp_o[0] for abp_o in abp_openings])
    abp_openings += abp__sliding(
        abp_vector, abp_scale, abp_walls, [abp_o[0] for abp_o in abp_openings]
    )
    abp_leaves = [abp_o[0] for abp_o in abp_openings]
    abp_walls = abp__cut_openings(abp_walls, abp_leaves)
    abp_openings += [
        abp_g
        for abp_g in abp_gaps_between_walls(abp_walls, abp_leaves)
        if not abp__bridged(abp_g[0], abp_lines)
    ]
    abp_leaves = [abp_o[0] for abp_o in abp_openings]
    abp_walls, abp_found = abp__free_ends(abp_walls, abp_leaves, abp_lines)
    abp_openings += abp_found
    abp_walls = abp__reach_jambs(abp_walls, [abp_o[0] for abp_o in abp_openings])
    abp_openings = [
        abp_o for abp_o in abp_openings if abp__ends_near(abp_o[0], abp_walls, abp_JAMB_REACH_M)
    ]
    return abp_as_detection(abp_walls, abp_openings, abp_scale)


def abp__lines(
    abp_vector: abpVectorPlan, abp_scale: float, abp_ids: Sequence[int]
) -> abpFloatArray:
    abp_keep = np.isin(abp_vector.abp_segment_layer, list(abp_ids)) & ~abp_vector.abp_filled
    abp_raw = abp_vector.abp_segments[abp_keep] * abp_scale
    abp_raw = abp_raw[abp__lengths(abp_raw) > 0.02] if len(abp_raw) else abp_raw
    abp_chords: list[abpFloatArray] = []
    for abp_arc in abp_vector.abp_arcs[np.isin(abp_vector.abp_arc_layer, list(abp_ids))]:
        abp_radius = abp_arc[2] * abp_scale
        if abp_radius < 2.5:
            continue
        abp_n = max(1, round(abs(abp_arc[4]) * abp_radius / abp_ARC_CHORD_M))
        abp_a = abp_arc[3] + abp_arc[4] * np.linspace(0, 1, abp_n + 1)
        abp_p = (abp_arc[:2] + abp_arc[2] * np.c_[np.cos(abp_a), np.sin(abp_a)]) * abp_scale
        abp_chords.append(np.c_[abp_p[:-1], abp_p[1:]])
    return np.vstack([abp_raw.reshape(-1, 4), *abp_chords])


def abp__door_arcs(abp_vector: abpVectorPlan, abp_scale: float) -> abpFloatArray:
    abp_ids = abp_layer_ids(abp_vector, abp_DOORS)
    abp_others = [
        abp_n for abp_i, abp_n in enumerate(abp_vector.abp_layers) if abp_i not in abp_ids
    ]
    return abp_door_arcs(abp_vector, abp_scale, abp_others)


def abp__single(abp_low: abpFloatArray, abp_axes: abpFloatArray) -> abpFloatArray:
    abp_keep: list[abpFloatArray] = []
    for abp_s in abp_low[abp__lengths(abp_low) >= abp_LOW_SINGLE_M]:
        abp_middle = (abp_s[:2] + abp_s[2:]) / 2
        abp_angle = float(abp__angles(abp_s[None, :])[0])
        abp_near = len(abp_axes) > 0 and bool(
            (
                (abp_point_segments_distance(abp_middle, abp_axes) < 0.3)
                & (abp__angle_diff(abp__angles(abp_axes), abp_angle) < 8)
            ).any()
        )
        if not abp_near:
            abp_keep.append(abp_s)
    return np.array(abp_keep, np.float64).reshape(-1, 4)


def abp_column_boxes(
    abp_vector: abpVectorPlan, abp_scale: float, abp_axes: abpFloatArray
) -> list[abpFloatArray]:
    import cv2

    abp_raw = abp__lines(abp_vector, abp_scale, abp_layer_ids(abp_vector, abp_COLUMNS))
    if len(abp_raw) == 0 or len(abp_axes) == 0:
        return []
    abp_out: list[abpFloatArray] = []
    for abp_group in abp__touching(abp_raw):
        abp_points = np.vstack([abp_group[:, :2], abp_group[:, 2:]]).astype(np.float32)
        abp_box = np.asarray(cv2.boxPoints(cv2.minAreaRect(abp_points)), np.float64)
        abp_sides = (
            float(np.hypot(*(abp_box[1] - abp_box[0]))),
            float(np.hypot(*(abp_box[2] - abp_box[1]))),
        )
        if not abp_COLUMN_M[0] <= min(abp_sides) or max(abp_sides) > abp_COLUMN_M[1]:
            continue
        abp_ends = np.vstack([abp_axes[:, :2], abp_axes[:, 2:]])
        if float(abp__box_distance(abp_box, abp_ends).min()) < abp_COLUMN_REACH_M:
            abp_out.append(abp_box)
    return abp_out


def abp__touching(abp_s: abpFloatArray, abp_gap: float = 0.03) -> list[abpFloatArray]:
    abp_parent = list(range(len(abp_s)))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = abp_parent[abp_i]
        return abp_i

    for abp_i in range(len(abp_s)):
        for abp_e in (abp_s[abp_i, :2], abp_s[abp_i, 2:]):
            for abp_j in np.flatnonzero(abp_point_segments_distance(abp_e, abp_s) <= abp_gap):
                abp_parent[abp_find(abp_i)] = abp_find(int(abp_j))
    abp_groups: dict[int, list[int]] = {}
    for abp_i in range(len(abp_s)):
        abp_groups.setdefault(abp_find(abp_i), []).append(abp_i)
    return [abp_s[abp_m] for abp_m in abp_groups.values()]


def abp__box_distance(abp_box: abpFloatArray, abp_points: abpFloatArray) -> abpFloatArray:
    abp_center = abp_box.mean(axis=0)
    abp_u, abp_v = abp_box[1] - abp_box[0], abp_box[2] - abp_box[1]
    abp_hu, abp_hv = float(np.hypot(*abp_u)) / 2, float(np.hypot(*abp_v)) / 2
    abp_d = abp_points - abp_center
    abp_a = np.abs(abp_d @ (abp_u / max(2 * abp_hu, 1e-9))) - abp_hu
    abp_b = np.abs(abp_d @ (abp_v / max(2 * abp_hv, 1e-9))) - abp_hv
    return np.asarray(np.hypot(np.maximum(abp_a, 0), np.maximum(abp_b, 0)), np.float64)


def abp__into_columns(
    abp_walls: abpFloatArray, abp_columns: Sequence[abpFloatArray]
) -> abpFloatArray:
    abp_walls = abp_walls.copy()
    for abp_box in abp_columns:
        abp_center = abp_box.mean(axis=0)
        for abp_i in range(len(abp_walls)):
            abp_u, abp_n = abp__unit(abp_walls[abp_i])
            if abs(float((abp_center - abp_walls[abp_i, :2]) @ abp_n)) > 0.45:
                continue
            abp_ends = abp_walls[abp_i].reshape(2, 2)
            abp_away = abp__box_distance(abp_box, abp_ends)
            abp_k = int(np.argmin(abp_away))
            if abp_away[abp_k] < abp_COLUMN_REACH_M:
                abp_base = abp_walls[abp_i, :2].copy()
                abp_walls[abp_i, 2 * abp_k : 2 * abp_k + 2] = abp_base + abp_u * float(
                    (abp_center - abp_base) @ abp_u
                )
    return abp_walls[abp__lengths(abp_walls) > abp_PIECE_M]


def abp__reach_jambs(
    abp_walls: abpFloatArray, abp_openings: Sequence[abpFloatArray]
) -> abpFloatArray:
    abp_extra: list[abpFloatArray] = []
    for abp_o in abp_openings:
        for abp_e in (abp_o[:2], abp_o[2:]):
            if len(abp_walls) == 0:
                continue
            abp_j = int(np.argmin(abp_point_segments_distance(abp_e, abp_walls)))
            abp_w = abp_walls[abp_j]
            abp_t = float(
                np.clip(
                    (abp_e - abp_w[:2])
                    @ (abp_w[2:] - abp_w[:2])
                    / ((abp_w[2:] - abp_w[:2]) ** 2).sum(),
                    0,
                    1,
                )
            )
            abp_q = abp_w[:2] + abp_t * (abp_w[2:] - abp_w[:2])
            if 0.03 < float(np.hypot(*(abp_e - abp_q))) < abp_JAMB_REACH_M:
                abp_extra.append(np.r_[abp_e, abp_q])
    return (
        np.vstack([abp_walls, *[abp_x[None, :] for abp_x in abp_extra]]) if abp_extra else abp_walls
    )


def abp__sliding(
    abp_vector: abpVectorPlan,
    abp_scale: float,
    abp_walls: abpFloatArray,
    abp_taken: Sequence[abpFloatArray],
) -> list[tuple[abpFloatArray, float]]:
    abp_ids = abp_layer_ids(abp_vector, abp_DOORS)
    abp_raw = abp__lines(abp_vector, abp_scale, abp_ids)
    abp_arcs = abp__door_arcs(abp_vector, abp_scale)
    abp_out: list[tuple[abpFloatArray, float]] = []
    if len(abp_raw) == 0 or len(abp_walls) == 0:
        return abp_out
    abp_leaves = abp_merge_collinear(abp_raw)
    abp_length = abp__lengths(abp_leaves)
    for abp_s in abp_leaves[(abp_length >= abp_LEAF_M[0]) & (abp_length <= abp_LEAF_M[1])]:
        abp_middle = (abp_s[:2] + abp_s[2:]) / 2
        if (
            len(abp_arcs)
            and min(abp__hinge_gap(abp_arcs, abp_s[:2]), abp__hinge_gap(abp_arcs, abp_s[2:])) < 0.2
        ):
            continue
        if any(
            float(abp_point_segments_distance(abp_middle, abp_t[None, :])[0]) < 0.5
            for abp_t in [*abp_taken, *(abp_o[0] for abp_o in abp_out)]
        ):
            continue
        if all(
            float(abp_point_segments_distance(abp_e, abp_walls).min()) < 0.6
            for abp_e in (abp_s[:2], abp_s[2:])
        ):
            abp_out.append((abp_s, 0.8))
    return abp_out


def abp__hinge_gap(abp_arcs: abpFloatArray, abp_p: abpFloatArray) -> float:
    return float(np.hypot(*(abp_arcs[:, :2] - abp_p).T).min())


def abp__swing_doors(
    abp_vector: abpVectorPlan, abp_scale: float, abp_arcs: abpFloatArray, abp_walls: abpFloatArray
) -> list[tuple[abpFloatArray, float]]:
    abp_leaves = abp__lines(abp_vector, abp_scale, abp_layer_ids(abp_vector, abp_DOORS))
    abp_out: list[tuple[abpFloatArray, float]] = []
    abp_rest: list[int] = []
    abp_paired: set[int] = set()
    for abp_i in range(len(abp_arcs)):
        for abp_j in range(abp_i + 1, len(abp_arcs)):
            if (
                abp_i not in abp_paired
                and abp_j not in abp_paired
                and abp__double_door(abp_arcs[abp_i], abp_arcs[abp_j])
            ):
                abp_out.append(
                    (
                        abp__onto_wall(np.r_[abp_arcs[abp_i][:2], abp_arcs[abp_j][:2]], abp_walls),
                        0.95,
                    )
                )
                abp_paired |= {abp_i, abp_j}
    for abp_i in range(len(abp_arcs)):
        if abp_i in abp_paired:
            continue
        abp_hinge, abp_radius = abp_arcs[abp_i][:2], float(abp_arcs[abp_i][2])
        abp_scores = []
        for abp_end in (abp_arcs[abp_i][3:5], abp_arcs[abp_i][5:7]):
            abp_marks = [abp_hinge + (abp_end - abp_hinge) * abp_t for abp_t in (0.35, 0.6, 0.85)]
            abp_near = [
                len(abp_leaves) > 0
                and float(abp_point_segments_distance(abp_p, abp_leaves).min()) < 0.08 * abp_radius
                for abp_p in abp_marks
            ]
            abp_scores.append(sum(abp_near))
        if abp_scores[0] == abp_scores[1]:
            abp_rest.append(abp_i)
            continue
        abp_closed = abp_arcs[abp_i][5:7] if abp_scores[0] > abp_scores[1] else abp_arcs[abp_i][3:5]
        abp_out.append((abp__onto_wall(np.r_[abp_hinge, abp_closed], abp_walls), 0.95))
    return abp_out + (abp_doors_from_arcs(abp_arcs[abp_rest], abp_walls) if abp_rest else [])


def abp__free_ends(
    abp_walls: abpFloatArray, abp_openings: Sequence[abpFloatArray], abp_lines: abpFloatArray
) -> tuple[abpFloatArray, list[tuple[abpFloatArray, float]]]:
    abp_walls = abp_walls.copy()
    abp_jambs = [abp_e for abp_o in abp_openings for abp_e in (abp_o[:2], abp_o[2:])]
    abp_found: list[tuple[abpFloatArray, float]] = []
    for abp_i in range(len(abp_walls)):
        for abp_k in (0, 2):
            abp_e = abp_walls[abp_i, abp_k : abp_k + 2].copy()
            abp_others = np.delete(abp_walls, abp_i, axis=0)
            if (
                len(abp_others) == 0
                or float(abp_point_segments_distance(abp_e, abp_others).min()) < 0.08
            ):
                continue
            if any(float(np.hypot(*(abp_e - abp_j))) < 0.35 for abp_j in abp_jambs):
                continue
            abp_u, abp__n = abp__unit(abp_walls[abp_i])
            abp_reach = abp_ray_hit(abp_e, abp_u if abp_k == 2 else -abp_u, abp_others)
            if abp_reach is None or abp_reach > abp_DOOR_MAX_M:
                continue
            abp_target = abp_e + (abp_u if abp_k == 2 else -abp_u) * abp_reach
            abp_gap = np.r_[abp_e, abp_target]
            abp_middle = (abp_e + abp_target) / 2
            if abp_reach < abp_DOOR_MIN_M or abp__bridged(abp_gap, abp_lines):
                abp_walls[abp_i, abp_k : abp_k + 2] = abp_target
            elif all(
                float(abp_point_segments_distance(abp_middle, abp_o[None, :])[0]) > 0.5
                for abp_o in [*abp_openings, *(abp_f[0] for abp_f in abp_found)]
            ):
                abp_found.append((abp_gap, 0.5))
    return abp_walls, abp_found


def abp__bridged(abp_gap: abpFloatArray, abp_lines: abpFloatArray) -> bool:
    abp_u, abp_n = abp__unit(abp_gap)
    abp_size = float(abp__lengths(abp_gap[None, :])[0])
    abp_same = abp__angle_diff(abp__angles(abp_lines), float(abp__angles(abp_gap[None, :])[0])) < 10
    abp_near: abpBoolArray = abp_same & (
        np.abs(((abp_lines[:, :2] + abp_lines[:, 2:]) / 2 - abp_gap[:2]) @ abp_n) < 0.3
    )
    abp_t = np.sort(
        np.c_[
            (abp_lines[abp_near, :2] - abp_gap[:2]) @ abp_u,
            (abp_lines[abp_near, 2:] - abp_gap[:2]) @ abp_u,
        ],
        axis=1,
    )
    abp_inside = np.clip(abp_t, 0, abp_size)
    return bool(
        len(abp_inside) and float((abp_inside[:, 1] - abp_inside[:, 0]).max()) > 0.6 * abp_size
    )
