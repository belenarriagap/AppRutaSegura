from __future__ import annotations

import numpy as np
import numpy.typing as npt

abpIntArray = npt.NDArray[np.int64]


def abp_neighbor_pairs(
    abp_positions: npt.NDArray[np.float64], abp_cutoff: float
) -> tuple[abpIntArray, abpIntArray]:
    abp_n = len(abp_positions)
    if abp_n < 2:
        abp_empty = np.zeros(0, dtype=np.int64)
        return abp_empty, abp_empty
    abp_cells = np.floor(abp_positions / abp_cutoff).astype(np.int64)
    abp_cells -= abp_cells.min(axis=0) - 1
    abp_width = int(abp_cells[:, 1].max()) + 2
    abp_keys = abp_cells[:, 0] * abp_width + abp_cells[:, 1]
    abp_order = np.argsort(abp_keys, kind="stable")
    abp_unique, abp_starts, abp_counts = np.unique(
        abp_keys[abp_order], return_index=True, return_counts=True
    )
    abp_agents = np.arange(abp_n, dtype=np.int64)
    abp_firsts: list[abpIntArray] = []
    abp_seconds: list[abpIntArray] = []
    for abp_dx in (-1, 0, 1):
        for abp_dy in (-1, 0, 1):
            abp_target = (abp_cells[:, 0] + abp_dx) * abp_width + (abp_cells[:, 1] + abp_dy)
            abp_pos = np.searchsorted(abp_unique, abp_target)
            abp_pos_clipped = np.minimum(abp_pos, len(abp_unique) - 1)
            abp_found = abp_unique[abp_pos_clipped] == abp_target
            abp_cnt = np.where(abp_found, abp_counts[abp_pos_clipped], 0)
            abp_total = int(abp_cnt.sum())
            if abp_total == 0:
                continue
            abp_first = np.repeat(abp_agents, abp_cnt)
            abp_begin = np.repeat(np.where(abp_found, abp_starts[abp_pos_clipped], 0), abp_cnt)
            abp_offsets = np.arange(abp_total) - np.repeat(np.cumsum(abp_cnt) - abp_cnt, abp_cnt)
            abp_second = abp_order[abp_begin + abp_offsets]
            abp_firsts.append(abp_first)
            abp_seconds.append(abp_second)
    if not abp_firsts:
        abp_empty = np.zeros(0, dtype=np.int64)
        return abp_empty, abp_empty
    abp_i = np.concatenate(abp_firsts)
    abp_j = np.concatenate(abp_seconds)
    abp_keep = abp_i != abp_j
    return abp_i[abp_keep], abp_j[abp_keep]
