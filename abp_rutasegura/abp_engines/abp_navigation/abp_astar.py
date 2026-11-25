from __future__ import annotations

import heapq
import itertools
import math

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_NEIGHBORS

abpCell = tuple[int, int]


def abp__octile(abp_a: abpCell, abp_b: abpCell) -> float:
    abp_dr, abp_dc = abs(abp_a[0] - abp_b[0]), abs(abp_a[1] - abp_b[1])
    return max(abp_dr, abp_dc) + (math.sqrt(2) - 1) * min(abp_dr, abp_dc)


def abp_astar(
    abp_walkable: npt.NDArray[np.bool_], abp_start: abpCell, abp_goal: abpCell
) -> list[abpCell] | None:
    abp_rows, abp_cols = abp_walkable.shape
    abp_walk = abp_walkable.tolist()

    def abp_ok(abp_cell: abpCell) -> bool:
        abp_r, abp_c = abp_cell
        return 0 <= abp_r < abp_rows and 0 <= abp_c < abp_cols and bool(abp_walk[abp_r][abp_c])

    if not abp_ok(abp_start) or not abp_ok(abp_goal):
        return None
    abp_g: dict[abpCell, float] = {abp_start: 0.0}
    abp_parent: dict[abpCell, abpCell] = {}
    abp_heap: list[tuple[float, float, abpCell]] = [
        (abp__octile(abp_start, abp_goal), 0.0, abp_start)
    ]
    abp_closed: set[abpCell] = set()
    while abp_heap:
        _, abp_cost, abp_cell = heapq.heappop(abp_heap)
        if abp_cell == abp_goal:
            abp_path = [abp_cell]
            while abp_cell in abp_parent:
                abp_cell = abp_parent[abp_cell]
                abp_path.append(abp_cell)
            return abp_path[::-1]
        if abp_cell in abp_closed:
            continue
        abp_closed.add(abp_cell)
        abp_r, abp_c = abp_cell
        for abp_dr, abp_dc, abp_step in abp_NEIGHBORS:
            abp_nxt = (abp_r + abp_dr, abp_c + abp_dc)
            if not abp_ok(abp_nxt) or abp_nxt in abp_closed:
                continue
            if (
                abp_dr
                and abp_dc
                and not (abp_walk[abp_r + abp_dr][abp_c] and abp_walk[abp_r][abp_c + abp_dc])
            ):
                continue
            abp_new_cost = abp_cost + abp_step
            if abp_new_cost < abp_g.get(abp_nxt, math.inf):
                abp_g[abp_nxt] = abp_new_cost
                abp_parent[abp_nxt] = abp_cell
                heapq.heappush(
                    abp_heap, (abp_new_cost + abp__octile(abp_nxt, abp_goal), abp_new_cost, abp_nxt)
                )
    return None


def abp_path_length(abp_path: list[abpCell], abp_cell_size: float) -> float:
    abp_total = 0.0
    for abp_a, abp_b in itertools.pairwise(abp_path):
        abp_total += math.hypot(abp_a[0] - abp_b[0], abp_a[1] - abp_b[1]) * abp_cell_size
    return abp_total
