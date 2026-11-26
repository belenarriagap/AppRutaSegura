from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpCellType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_results import abpRoomRoute
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abpNavGrid
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea

abpFloatArray = npt.NDArray[np.float64]
abp_SIMPLIFY_CELLS = 0.75
abp__NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def abp_descend(
    abp_grid: abpNavGrid, abp_distance: abpFloatArray, abp_start: tuple[int, int]
) -> list[tuple[int, int]]:
    abp_rows, abp_cols = abp_distance.shape
    abp_path = [abp_start]
    abp_r, abp_c = abp_start
    for _ in range(abp_rows * abp_cols):
        if abp_grid.abp_target_ids[abp_r, abp_c] >= 0:
            break
        abp_best = (abp_distance[abp_r, abp_c], abp_r, abp_c)
        for abp_dr, abp_dc in abp__NEIGHBORS:
            abp_nr, abp_nc = abp_r + abp_dr, abp_c + abp_dc
            if (
                0 <= abp_nr < abp_rows
                and 0 <= abp_nc < abp_cols
                and abp_distance[abp_nr, abp_nc] < abp_best[0]
            ):
                if (
                    abp_dr
                    and abp_dc
                    and not (
                        np.isfinite(abp_distance[abp_r, abp_nc])
                        and np.isfinite(abp_distance[abp_nr, abp_c])
                    )
                ):
                    continue
                abp_best = (abp_distance[abp_nr, abp_nc], abp_nr, abp_nc)
        if (abp_best[1], abp_best[2]) == (abp_r, abp_c):
            break
        abp_r, abp_c = abp_best[1], abp_best[2]
        abp_path.append((abp_r, abp_c))
    return abp_path


def abp_to_points(
    abp_grid: abpNavGrid, abp_cells: Sequence[tuple[int, int]]
) -> tuple[abpPoint, ...]:
    if not abp_cells:
        return ()
    abp_array = np.array([[abp_c, abp_r] for abp_r, abp_c in abp_cells], dtype=np.int32).reshape(
        -1, 1, 2
    )
    abp_simple = cv2.approxPolyDP(abp_array, abp_SIMPLIFY_CELLS, False).reshape(-1, 2)
    abp_rr = abp_simple[:, 1].astype(np.int64)
    abp_cc = abp_simple[:, 0].astype(np.int64)
    abp_centers = abp_grid.abp_cell_centers(abp_rr, abp_cc)
    return tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_centers)


def abp_room_routes(
    abp_grid: abpNavGrid, abp_distance: abpFloatArray, abp_rooms: Sequence[abpRoomArea]
) -> tuple[abpRoomRoute, ...]:
    abp_usable = (abp_grid.abp_cells == int(abpCellType.abp_FREE)) & np.isfinite(abp_distance)
    abp_out: list[abpRoomRoute] = []
    for abp_room in abp_rooms:
        abp_mask = abp_grid.abp_polygon_mask(abp_room.abp_polygon_m) & abp_usable
        abp_rows, abp_cols = np.nonzero(abp_mask)
        if abp_rows.size == 0:
            continue
        abp_values = abp_distance[abp_rows, abp_cols]
        abp_far = int(np.argmax(abp_values))
        abp_center = abp_room.abp_polygon_m.abp_centroid
        abp_centers = abp_grid.abp_cell_centers(
            abp_rows.astype(np.int64), abp_cols.astype(np.int64)
        )
        abp_near = int(
            np.argmin(
                np.hypot(abp_centers[:, 0] - abp_center.abp_x, abp_centers[:, 1] - abp_center.abp_y)
            )
        )
        abp_start = (int(abp_rows[abp_near]), int(abp_cols[abp_near]))
        abp_path = abp_descend(abp_grid, abp_distance, abp_start)
        abp_far_path = abp_descend(
            abp_grid, abp_distance, (int(abp_rows[abp_far]), int(abp_cols[abp_far]))
        )
        abp_end_r, abp_end_c = abp_far_path[-1]
        abp_target = int(abp_grid.abp_target_ids[abp_end_r, abp_end_c])
        abp_target_name = abp_grid.abp_target_names[abp_target] if abp_target >= 0 else ""
        abp_far_point = abp_grid.abp_cell_centers(
            abp_rows[abp_far : abp_far + 1].astype(np.int64), abp_cols[abp_far : abp_far + 1]
        )
        abp_out.append(
            abpRoomRoute(
                abp_room_name=abp_room.abp_name,
                abp_level=abp_room.abp_level,
                abp_target_name=abp_target_name,
                abp_max_distance_m=round(float(abp_values[abp_far]), 2),
                abp_farthest_m=abpPoint(float(abp_far_point[0, 0]), float(abp_far_point[0, 1])),
                abp_path_m=abp_to_points(abp_grid, abp_path),
                abp_farthest_path_m=abp_to_points(abp_grid, abp_far_path),
            )
        )
    return tuple(abp_out)
