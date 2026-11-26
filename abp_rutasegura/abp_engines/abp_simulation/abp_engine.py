from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_agents import abpAgentArrays
from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus, abpCellType
from abp_rutasegura.abp_domain.abp_results import abpSimulationResult, abpTrajectories
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import (
    abp_direction_field,
    abp_distance_field,
    abp_wall_distance,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abpNavGrid
from abp_rutasegura.abp_engines.abp_simulation.abp_metrics import abp_find_bottlenecks
from abp_rutasegura.abp_engines.abp_simulation.abp_neighbors import abp_neighbor_pairs
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams

abpFloatArray = npt.NDArray[np.float64]
abpProgressCallback = Callable[[float], None]
abpCancelCheck = Callable[[], bool]

abp_WAITING = int(abpAgentStatus.abp_WAITING)
abp_MOVING = int(abpAgentStatus.abp_MOVING)
abp_EVACUATED = int(abpAgentStatus.abp_EVACUATED)


class abpSimulationCancelled(Exception):
    pass


@dataclass(frozen=True, eq=False)
class abpSimulationOutput:
    abp_result: abpSimulationResult
    abp_trajectories: abpTrajectories
    abp_exit_index: npt.NDArray[np.int16]
    abp_evacuation_time_s: abpFloatArray


def abp_bilinear(
    abp_field: abpFloatArray, abp_grid: abpNavGrid, abp_xy: abpFloatArray
) -> abpFloatArray:
    abp_rows, abp_cols = abp_field.shape[:2]
    abp_u = (abp_xy[:, 0] - abp_grid.abp_origin[0]) / abp_grid.abp_cell_size - 0.5
    abp_v = (abp_xy[:, 1] - abp_grid.abp_origin[1]) / abp_grid.abp_cell_size - 0.5
    abp_c0 = np.clip(np.floor(abp_u).astype(np.int64), 0, abp_cols - 1)
    abp_r0 = np.clip(np.floor(abp_v).astype(np.int64), 0, abp_rows - 1)
    abp_c1 = np.minimum(abp_c0 + 1, abp_cols - 1)
    abp_r1 = np.minimum(abp_r0 + 1, abp_rows - 1)
    abp_fu = np.clip(abp_u - abp_c0, 0.0, 1.0)
    abp_fv = np.clip(abp_v - abp_r0, 0.0, 1.0)
    if abp_field.ndim == 3:
        abp_fu, abp_fv = abp_fu[:, None], abp_fv[:, None]
    abp_top = abp_field[abp_r0, abp_c0] * (1 - abp_fu) + abp_field[abp_r0, abp_c1] * abp_fu
    abp_bottom = abp_field[abp_r1, abp_c0] * (1 - abp_fu) + abp_field[abp_r1, abp_c1] * abp_fu
    return np.asarray(abp_top * (1 - abp_fv) + abp_bottom * abp_fv, dtype=np.float64)


class abpSimulation:
    def __init__(
        self,
        abp_grid: abpNavGrid,
        abp_agents: abpAgentArrays,
        abp_params: abpSimulationParams,
        *,
        abp_seed: int,
        abp_profile_names: Sequence[str] = (),
        abp_distance: abpFloatArray | None = None,
        abp_record: bool = True,
        abp_guides: Sequence[abpFloatArray] = (),
        abp_guide_of: npt.NDArray[np.int32] | None = None,
    ) -> None:
        self.abp_grid = abp_grid
        self.abp_agents = abp_agents
        self.abp_params = abp_params
        self.abp_seed = abp_seed
        self.abp_profile_names = tuple(abp_profile_names)
        abp_walkable = abp_grid.abp_walkable
        self.abp__walkable = abp_walkable
        self.abp_distance = (
            abp_distance
            if abp_distance is not None
            else abp_distance_field(abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size)
        )
        self.abp__directions = abp_direction_field(self.abp_distance, abp_walkable)
        self.abp__guides = [self.abp__guided(abp_field) for abp_field in abp_guides]
        self.abp_guide_of = (
            np.full(len(abp_agents), -1, np.int32) if abp_guide_of is None else abp_guide_of.copy()
        )
        self.abp__pace = np.where(
            (abp_grid.abp_cells == int(abpCellType.abp_STAIR)) & ~abp_grid.abp_targets,
            abp_params.abp_stair_speed_factor,
            1.0,
        )
        self.abp__wall_dist, self.abp__wall_grad = abp_wall_distance(
            abp_walkable, abp_grid.abp_cell_size
        )
        abp_n = len(abp_agents)
        self.abp_time_s = 0.0
        self.abp_steps = 0
        self.abp_exit_index = np.full(abp_n, -1, dtype=np.int16)
        self.abp_evacuation_time = np.full(abp_n, np.nan)
        abp_shape = abp_grid.abp_shape
        self.abp_density_accumulated = np.zeros(abp_shape)
        self.abp_time_above = np.zeros(abp_shape)
        self.abp_density_when_above = np.zeros(abp_shape)
        self.abp__record_every = max(1, round(abp_params.abp_record_every_s / abp_params.abp_dt_s))
        self.abp__frames_t: list[float] = []
        self.abp__frames_pos: list[npt.NDArray[np.float32]] = []
        self.abp__frames_status: list[npt.NDArray[np.int8]] = []
        self.abp__curve_t: list[float] = []
        self.abp__curve_n: list[int] = []
        self.abp__recording = abp_record
        self.abp__record()

    @property
    def abp_evacuated(self) -> int:
        return self.abp_agents.abp_evacuated_count

    @property
    def abp_finished(self) -> bool:
        return (
            self.abp_evacuated == len(self.abp_agents)
            or self.abp_time_s >= self.abp_params.abp_max_time_s - 1e-9
        )

    def abp__guided(self, abp_field: abpFloatArray) -> abpFloatArray:
        abp_own = abp_direction_field(abp_field, self.abp__walkable)
        abp_known = np.isfinite(abp_field)[:, :, None]
        return np.asarray(np.where(abp_known, abp_own, self.abp__directions), np.float64)

    def abp__desired(
        self, abp_active: npt.NDArray[np.int64], abp_pos: abpFloatArray
    ) -> abpFloatArray:
        abp_direction = abp_bilinear(self.abp__directions, self.abp_grid, abp_pos)
        if self.abp__guides:
            abp_guide = self.abp_guide_of[abp_active]
            for abp_k, abp_field in enumerate(self.abp__guides):
                abp_mine = abp_guide == abp_k
                if abp_mine.any():
                    abp_direction[abp_mine] = abp_bilinear(
                        abp_field, self.abp_grid, abp_pos[abp_mine]
                    )
        return abp_direction

    def abp__cells_walkable(self, abp_xy: abpFloatArray) -> npt.NDArray[np.bool_]:
        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_xy)
        return np.asarray(self.abp__walkable[abp_r, abp_c], dtype=np.bool_)

    def abp_step(self) -> None:
        abp_p = self.abp_params
        abp_dt = abp_p.abp_dt_s
        abp_a = self.abp_agents
        abp_status = abp_a.abp_status
        abp_status[(abp_status == abp_WAITING) & (abp_a.abp_reaction_time <= self.abp_time_s)] = (
            abp_MOVING
        )
        abp_active = np.flatnonzero(abp_status != abp_EVACUATED)
        if abp_active.size == 0:
            self.abp_time_s += abp_dt
            self.abp_steps += 1
            return
        abp_pos = abp_a.abp_position[abp_active]
        abp_vel = abp_a.abp_velocity[abp_active]
        abp_radius = abp_a.abp_radius[abp_active]
        abp_moving = abp_status[abp_active] == abp_MOVING

        abp_density = self.abp__density(abp_pos)
        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_pos)
        abp_rho = abp_density[abp_r, abp_c]

        abp_direction = self.abp__desired(abp_active, abp_pos)
        abp_norm = np.linalg.norm(abp_direction, axis=1, keepdims=True)
        abp_direction = np.where(abp_norm > 1e-9, abp_direction / np.maximum(abp_norm, 1e-12), 0.0)
        abp_factor = np.maximum(abp_p.abp_min_speed_factor, 1.0 - abp_rho / abp_p.abp_jam_density)
        abp_desired_speed = (
            abp_a.abp_max_speed[abp_active] * abp_factor * self.abp__pace[abp_r, abp_c]
        )
        abp_accel = (abp_desired_speed[:, None] * abp_direction - abp_vel) / abp_p.abp_relaxation_s

        abp_i, abp_j, abp_dist, abp_nx, abp_ny = self.abp__pairs(abp_pos, abp_radius)
        if abp_i.size:
            abp_overlap_term = abp_radius[abp_i] + abp_radius[abp_j] - abp_dist
            abp_force = abp_p.abp_agent_strength * np.exp(
                abp_overlap_term / abp_p.abp_agent_range_m
            )
            abp_n_act = abp_active.size
            abp_accel[:, 0] += np.bincount(abp_i, weights=abp_force * abp_nx, minlength=abp_n_act)
            abp_accel[:, 1] += np.bincount(abp_i, weights=abp_force * abp_ny, minlength=abp_n_act)

        abp_wall_d = abp_bilinear(self.abp__wall_dist, self.abp_grid, abp_pos)
        abp_wall_g = abp_bilinear(self.abp__wall_grad, self.abp_grid, abp_pos)
        abp_wall_force = abp_p.abp_wall_strength * np.exp(
            (abp_radius - abp_wall_d) / abp_p.abp_wall_range_m
        )
        abp_wall_acc = abp_wall_force[:, None] * abp_wall_g
        abp_backward = np.minimum(np.einsum("ij,ij->i", abp_wall_acc, abp_direction), 0.0)
        abp_accel += abp_wall_acc - abp_backward[:, None] * abp_direction

        abp_new_vel = abp_vel + abp_accel * abp_dt
        abp_speed = np.linalg.norm(abp_new_vel, axis=1)
        abp_limit = abp_a.abp_max_speed[abp_active]
        abp_too_fast = abp_speed > abp_limit
        abp_new_vel[abp_too_fast] *= (abp_limit[abp_too_fast] / abp_speed[abp_too_fast])[:, None]
        abp_new_vel[~abp_moving] = 0.0
        abp_new_pos = self.abp__move_with_walls(abp_pos, abp_new_vel * abp_dt)

        abp_i, abp_j, abp_dist, abp_nx, abp_ny = self.abp__pairs(abp_new_pos, abp_radius)
        if abp_i.size:
            abp_overlap = np.maximum(abp_radius[abp_i] + abp_radius[abp_j] - abp_dist, 0.0)
            abp_push = np.minimum(0.5 * abp_overlap, 0.05)
            abp_n_act = abp_active.size
            abp_shift = np.column_stack(
                [
                    np.bincount(abp_i, weights=abp_push * abp_nx, minlength=abp_n_act),
                    np.bincount(abp_i, weights=abp_push * abp_ny, minlength=abp_n_act),
                ]
            )
            abp_shift[~abp_moving] *= 0.5
            abp_candidate = abp_new_pos + abp_shift
            abp_ok = self.abp__cells_walkable(abp_candidate)
            abp_new_pos[abp_ok] = abp_candidate[abp_ok]

        abp_a.abp_position[abp_active] = abp_new_pos
        abp_a.abp_velocity[abp_active] = (abp_new_pos - abp_pos) / abp_dt
        abp_a.abp_velocity[abp_active[~abp_moving]] = 0.0

        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_new_pos)
        abp_target = self.abp_grid.abp_target_ids[abp_r, abp_c]
        abp_out = (abp_target >= 0) & abp_moving
        if abp_out.any():
            abp_leaving = abp_active[abp_out]
            abp_status[abp_leaving] = abp_EVACUATED
            self.abp_exit_index[abp_leaving] = abp_target[abp_out]
            self.abp_evacuation_time[abp_leaving] = self.abp_time_s + abp_dt

        abp_flow = (
            self.abp__density(abp_pos[abp_moving])
            if abp_moving.any()
            else np.zeros_like(abp_density)
        )
        self.abp_density_accumulated += abp_flow * abp_dt
        abp_above = abp_flow >= abp_p.abp_congestion_density
        self.abp_time_above[abp_above] += abp_dt
        self.abp_density_when_above[abp_above] += abp_flow[abp_above] * abp_dt

        self.abp_time_s += abp_dt
        self.abp_steps += 1
        if self.abp_steps % self.abp__record_every == 0:
            self.abp__record()

    def abp__density(self, abp_pos: abpFloatArray) -> abpFloatArray:
        abp_r, abp_c = self.abp_grid.abp_to_cell(abp_pos)
        abp_rows, abp_cols = self.abp_grid.abp_shape
        abp_counts = np.bincount(abp_r * abp_cols + abp_c, minlength=abp_rows * abp_cols).reshape(
            abp_rows, abp_cols
        )
        abp_window = cv2.boxFilter(
            abp_counts.astype(np.float64),
            -1,
            (3, 3),
            normalize=False,
            borderType=cv2.BORDER_CONSTANT,
        )
        abp_result = abp_window / (9.0 * self.abp_grid.abp_cell_size**2)
        return np.asarray(np.where(self.abp__walkable, abp_result, 0.0), dtype=np.float64)

    def abp__pairs(
        self, abp_pos: abpFloatArray, abp_radius: abpFloatArray
    ) -> tuple[
        npt.NDArray[np.int64], npt.NDArray[np.int64], abpFloatArray, abpFloatArray, abpFloatArray
    ]:
        abp_cutoff = self.abp_params.abp_interaction_cutoff_m
        abp_i, abp_j = abp_neighbor_pairs(abp_pos, abp_cutoff)
        abp_delta = abp_pos[abp_i] - abp_pos[abp_j]
        abp_dist = np.hypot(abp_delta[:, 0], abp_delta[:, 1])
        abp_close = abp_dist < abp_cutoff
        abp_i, abp_j, abp_delta, abp_dist = (
            abp_i[abp_close],
            abp_j[abp_close],
            abp_delta[abp_close],
            abp_dist[abp_close],
        )
        abp_same = abp_dist < 1e-9
        abp_safe = np.where(abp_same, 1.0, abp_dist)
        abp_nx = np.where(
            abp_same, np.sign(abp_i - abp_j).astype(np.float64), abp_delta[:, 0] / abp_safe
        )
        abp_ny = np.where(abp_same, 0.0, abp_delta[:, 1] / abp_safe)
        return abp_i, abp_j, np.maximum(abp_dist, 1e-9), abp_nx, abp_ny

    def abp__move_with_walls(
        self, abp_pos: abpFloatArray, abp_delta: abpFloatArray
    ) -> abpFloatArray:
        abp_target = abp_pos + abp_delta
        abp_blocked = ~self.abp__cells_walkable(abp_target)
        if abp_blocked.any():
            abp_only_x = abp_pos[abp_blocked] + np.column_stack(
                [abp_delta[abp_blocked, 0], np.zeros(abp_blocked.sum())]
            )
            abp_only_y = abp_pos[abp_blocked] + np.column_stack(
                [np.zeros(abp_blocked.sum()), abp_delta[abp_blocked, 1]]
            )
            abp_ok_x = self.abp__cells_walkable(abp_only_x)
            abp_ok_y = self.abp__cells_walkable(abp_only_y) & ~abp_ok_x
            abp_fallback = abp_pos[abp_blocked].copy()
            abp_fallback[abp_ok_x] = abp_only_x[abp_ok_x]
            abp_fallback[abp_ok_y] = abp_only_y[abp_ok_y]
            abp_target[abp_blocked] = abp_fallback
        return abp_target

    def abp__record(self) -> None:
        if self.abp__recording:
            self.abp__frames_t.append(self.abp_time_s)
            self.abp__frames_pos.append(self.abp_agents.abp_position.astype(np.float32))
            self.abp__frames_status.append(self.abp_agents.abp_status.copy())
        self.abp__curve_t.append(self.abp_time_s)
        self.abp__curve_n.append(self.abp_evacuated)

    def abp_run(
        self,
        abp_progress: abpProgressCallback | None = None,
        abp_should_cancel: abpCancelCheck | None = None,
    ) -> abpSimulationOutput:
        abp_total = max(len(self.abp_agents), 1)
        abp_last_report = -1.0
        while not self.abp_finished:
            self.abp_step()
            if abp_should_cancel is not None and self.abp_steps % 10 == 0 and abp_should_cancel():
                raise abpSimulationCancelled
            if abp_progress is not None:
                abp_fraction = max(
                    self.abp_evacuated / abp_total, self.abp_time_s / self.abp_params.abp_max_time_s
                )
                if abp_fraction - abp_last_report >= 0.01:
                    abp_last_report = abp_fraction
                    abp_progress(min(abp_fraction, 1.0))
        if self.abp__curve_t[-1] != self.abp_time_s:
            self.abp__record()
        if abp_progress is not None:
            abp_progress(1.0)
        return self.abp_output()

    def abp_output(self) -> abpSimulationOutput:
        abp_names = self.abp_grid.abp_target_names
        abp_per_exit: list[tuple[str, float]] = []
        for abp_k, abp_name in enumerate(abp_names):
            abp_used = self.abp_exit_index == abp_k
            if abp_used.any():
                abp_per_exit.append(
                    (abp_name, round(float(np.nanmax(self.abp_evacuation_time[abp_used])), 2))
                )
        abp_completed = self.abp_evacuated == len(self.abp_agents)
        if abp_completed and len(self.abp_agents):
            abp_total_time = float(np.nanmax(self.abp_evacuation_time))
        else:
            abp_total_time = self.abp_time_s if len(self.abp_agents) else 0.0
        abp_bottlenecks = abp_find_bottlenecks(
            self.abp_grid,
            self.abp_time_above,
            self.abp_density_when_above,
            abp_min_duration_s=self.abp_params.abp_congestion_min_duration_s,
        )
        abp_result = abpSimulationResult(
            abp_seed=self.abp_seed,
            abp_total_time_s=round(abp_total_time, 2),
            abp_time_per_exit_s=tuple(abp_per_exit),
            abp_curve_times_s=np.array(self.abp__curve_t, dtype=np.float64),
            abp_curve_evacuated=np.array(self.abp__curve_n, dtype=np.int32),
            abp_density_map=self.abp_density_accumulated.copy(),
            abp_bottlenecks=abp_bottlenecks,
            abp_agents_total=len(self.abp_agents),
            abp_agents_evacuated=self.abp_evacuated,
            abp_completed=abp_completed,
            abp_grid_origin_m=self.abp_grid.abp_origin,
            abp_cell_size_m=self.abp_grid.abp_cell_size,
        )
        abp_trajectories = abpTrajectories(
            abp_times_s=np.array(self.abp__frames_t, dtype=np.float64),
            abp_positions=np.stack(self.abp__frames_pos).astype(np.float32)
            if self.abp__frames_pos
            else np.zeros((0, len(self.abp_agents), 2), np.float32),
            abp_status=np.stack(self.abp__frames_status).astype(np.int8)
            if self.abp__frames_status
            else np.zeros((0, len(self.abp_agents)), np.int8),
            abp_radius_m=self.abp_agents.abp_radius.astype(np.float32),
            abp_profile_index=self.abp_agents.abp_profile_index.astype(np.int32),
            abp_profile_names=self.abp_profile_names,
        )
        return abpSimulationOutput(
            abp_result,
            abp_trajectories,
            self.abp_exit_index.copy(),
            self.abp_evacuation_time.copy(),
        )
