from __future__ import annotations

from enum import Enum

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpStairUse
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon
from abp_rutasegura.abp_domain.abp_plan import abpStair

abpFloatArray = npt.NDArray[np.float64]
abpBoolArray = npt.NDArray[np.bool_]
abp_MIN_GAIN_CELLS = 3


class abpStairRole(Enum):
    abp_PASS = "paso"
    abp_DOWN = "baja"
    abp_OUTSIDE = "exterior"
    abp_CLOSED = "cerrada"


def abp_stair_role(abp_stair: abpStair, *, abp_upper_floor: bool) -> abpStairRole | None:
    match abp_stair.abp_use:
        case abpStairUse.abp_SAME_FLOOR:
            return abpStairRole.abp_PASS
        case abpStairUse.abp_OUTSIDE:
            return abpStairRole.abp_OUTSIDE
        case abpStairUse.abp_CLOSED | abpStairUse.abp_UP:
            return abpStairRole.abp_CLOSED
        case abpStairUse.abp_AUTO if not abp_upper_floor:
            return None
    return abpStairRole.abp_DOWN if abp_upper_floor else abpStairRole.abp_CLOSED


def abp_needed(
    abp_walkable: abpBoolArray, abp_targets: abpBoolArray, abp_masks: list[abpBoolArray]
) -> list[bool]:
    abp_closed = abp__reached(abp_walkable, abp_targets)
    abp_everything = abp_walkable.copy()
    for abp_mask in abp_masks:
        abp_everything |= abp_mask
    abp_gained = abp__reached(abp_everything, abp_targets) & abp_walkable & ~abp_closed
    if int(abp_gained.sum()) < abp_MIN_GAIN_CELLS:
        return [False] * len(abp_masks)
    abp_alone = [
        int((abp__reached(abp_walkable | abp_m, abp_targets) & abp_walkable & ~abp_closed).sum())
        >= abp_MIN_GAIN_CELLS
        for abp_m in abp_masks
    ]
    return abp_alone if any(abp_alone) else [True] * len(abp_masks)


def abp__reached(abp_walkable: abpBoolArray, abp_targets: abpBoolArray) -> abpBoolArray:
    abp__count, abp_labels = cv2.connectedComponents(abp_walkable.astype(np.uint8), connectivity=4)
    abp_near = np.unique(abp_labels[abp_targets & abp_walkable])
    return np.asarray(np.isin(abp_labels, abp_near[abp_near > 0]), np.bool_)


def abp_edges(abp_area: abpPolygon) -> list[tuple[abpPoint, abpPoint]]:
    abp_v = abp_area.abp_vertices
    return list(zip(abp_v, (*abp_v[1:], abp_v[0]), strict=True))


def abp_edge_index(abp_area: abpPolygon, abp_point: abpPoint) -> int:
    abp_sides = abp_edges(abp_area)
    abp_place = np.array([[abp_point.abp_x, abp_point.abp_y]])
    return min(
        range(len(abp_sides)),
        key=lambda abp_k: float(abp_edge_distance(abp_place, *abp_sides[abp_k])[0]),
    )


def abp_edge_distance(abp_points: abpFloatArray, abp_a: abpPoint, abp_b: abpPoint) -> abpFloatArray:
    abp_p = np.array([abp_a.abp_x, abp_a.abp_y])
    abp_d = np.array([abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y])
    abp_l2 = max(float(abp_d @ abp_d), 1e-12)
    abp_t = np.clip(((abp_points - abp_p) @ abp_d) / abp_l2, 0.0, 1.0)
    abp_q = abp_p + abp_t[:, None] * abp_d
    return np.asarray(
        np.hypot(abp_points[:, 0] - abp_q[:, 0], abp_points[:, 1] - abp_q[:, 1]), np.float64
    )
