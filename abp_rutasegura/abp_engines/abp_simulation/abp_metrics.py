from __future__ import annotations

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_results import abpBottleneck, abpFloorClearance, abpTrajectories
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abpNavGrid

abpFloatArray = npt.NDArray[np.float64]


def abp_find_bottlenecks(
    abp_grid: abpNavGrid,
    abp_time_above: abpFloatArray,
    abp_density_when_above: abpFloatArray,
    *,
    abp_min_duration_s: float,
    abp_limit: int = 10,
) -> tuple[abpBottleneck, ...]:
    abp_mask = (abp_time_above >= abp_min_duration_s).astype(np.uint8)
    abp_count, abp_labels = cv2.connectedComponents(abp_mask, connectivity=8)
    abp_found: list[abpBottleneck] = []
    for abp_label in range(1, abp_count):
        abp_rows, abp_cols = np.nonzero(abp_labels == abp_label)
        abp_times = abp_time_above[abp_rows, abp_cols]
        abp_total_time = float(abp_times.sum())
        abp_mean_density = float(
            abp_density_when_above[abp_rows, abp_cols].sum() / max(abp_total_time, 1e-9)
        )
        abp_duration = float(abp_times.max())
        abp_weights = abp_times / max(abp_total_time, 1e-9)
        abp_center = abp_grid.abp_cell_centers(abp_rows, abp_cols)
        abp_location = abpPoint(
            float(abp_center[:, 0] @ abp_weights), float(abp_center[:, 1] @ abp_weights)
        )
        abp_found.append(
            abpBottleneck(
                abp_location=abp_location,
                abp_mean_density=round(abp_mean_density, 3),
                abp_duration_s=round(abp_duration, 2),
                abp_severity=round(abp_duration * abp_mean_density, 2),
            )
        )
    abp_found.sort(
        key=lambda abp_b: (-abp_b.abp_severity, abp_b.abp_location.abp_x, abp_b.abp_location.abp_y)
    )
    return tuple(abp_found[:abp_limit])


def abp_floor_clearance(abp_trajectories: abpTrajectories) -> tuple[abpFloorClearance, ...]:
    abp_levels = abp_trajectories.abp_level
    if abp_levels is None or abp_trajectories.abp_frame_count == 0:
        return ()
    abp_status = abp_trajectories.abp_status
    abp_times = abp_trajectories.abp_times_s
    abp_gone = abp_status == int(abpAgentStatus.abp_EVACUATED)
    abp_start = abp_levels[0]
    abp_out: list[abpFloorClearance] = []
    for abp_level in sorted(int(abp_v) for abp_v in np.unique(abp_start) if abp_v >= 0):
        abp_mine = abp_start == abp_level
        abp_below = ((abp_levels[:, abp_mine] < abp_level) & ~abp_gone[:, abp_mine]).any(axis=0)
        if abp_level == min(int(abp_v) for abp_v in np.unique(abp_start) if abp_v >= 0):
            abp_descended = int(abp_gone[-1, abp_mine].sum())
        else:
            abp_descended = int(abp_below.sum())
        abp_present = ((abp_levels == abp_level) & ~abp_gone).any(axis=1)
        if abp_present[-1]:
            abp_cleared: float | None = None
        else:
            abp_frames = np.flatnonzero(abp_present)
            abp_cleared = (
                float(abp_times[abp_frames[-1] + 1]) if abp_frames.size else float(abp_times[0])
            )
        abp_out.append(
            abpFloorClearance(abp_level, int(abp_mine.sum()), abp_descended, abp_cleared)
        )
    return tuple(abp_out)
