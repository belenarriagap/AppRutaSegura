from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_results import (
    abpBottleneck,
    abpFloorMap,
    abpSimulationResult,
    abpTrajectories,
)

abp_FORMAT_VERSION = 2
abp_READABLE_VERSIONS = frozenset({1, 2})


@dataclass(frozen=True, eq=False)
class abpStoredRun:
    abp_trajectories: abpTrajectories
    abp_curve_times_s: npt.NDArray[np.float64]
    abp_curve_evacuated: npt.NDArray[np.int32]
    abp_density_map: npt.NDArray[np.float64]
    abp_bottlenecks: tuple[abpBottleneck, ...]
    abp_grid_origin_m: tuple[float, float]
    abp_cell_size_m: float
    abp_agents_total: int
    abp_agents_evacuated: int
    abp_completed: bool
    abp_floor_maps: tuple[abpFloorMap, ...] = ()


def abp_save_run(
    abp_path: Path, abp_result: abpSimulationResult, abp_trajectories: abpTrajectories
) -> None:
    abp_path.parent.mkdir(parents=True, exist_ok=True)
    abp_bottlenecks = np.array(
        [
            [
                abp_b.abp_location.abp_x,
                abp_b.abp_location.abp_y,
                abp_b.abp_mean_density,
                abp_b.abp_duration_s,
                abp_b.abp_severity,
                abp_b.abp_level,
            ]
            for abp_b in abp_result.abp_bottlenecks
        ],
        dtype=np.float64,
    ).reshape(-1, 6)
    abp_floors: dict[str, Any] = {}
    if abp_result.abp_floor_maps:
        abp_floors["floor_levels"] = np.array(
            [abp_m.abp_level for abp_m in abp_result.abp_floor_maps], dtype=np.int32
        )
        abp_floors["floor_origins"] = np.array(
            [abp_m.abp_grid_origin_m for abp_m in abp_result.abp_floor_maps], dtype=np.float64
        )
        abp_floors["floor_cells"] = np.array(
            [abp_m.abp_cell_size_m for abp_m in abp_result.abp_floor_maps]
        )
        for abp_k, abp_floor_map in enumerate(abp_result.abp_floor_maps):
            abp_floors[f"floor_density_{abp_k}"] = abp_floor_map.abp_density_map
    if abp_trajectories.abp_level is not None:
        abp_floors["level"] = abp_trajectories.abp_level
    with abp_path.open("wb") as abp_handle:
        abp_arrays: dict[str, Any] = dict(
            version=np.array(abp_FORMAT_VERSION),
            times=abp_trajectories.abp_times_s,
            positions=abp_trajectories.abp_positions,
            status=abp_trajectories.abp_status,
            radius=abp_trajectories.abp_radius_m,
            profile_index=abp_trajectories.abp_profile_index,
            profile_names=np.array(abp_trajectories.abp_profile_names, dtype=np.str_),
            curve_times=abp_result.abp_curve_times_s,
            curve_evacuated=abp_result.abp_curve_evacuated,
            density=abp_result.abp_density_map,
            bottlenecks=abp_bottlenecks,
            origin=np.array(abp_result.abp_grid_origin_m, dtype=np.float64),
            cell_size=np.array(abp_result.abp_cell_size_m),
            counts=np.array(
                [
                    abp_result.abp_agents_total,
                    abp_result.abp_agents_evacuated,
                    int(abp_result.abp_completed),
                ]
            ),
            **abp_floors,
        )
        np.savez_compressed(abp_handle, **abp_arrays)


def abp_load_run(abp_path: Path) -> abpStoredRun:
    with np.load(abp_path, allow_pickle=False) as abp_data:
        abp_version = int(abp_data["version"])
        if abp_version not in abp_READABLE_VERSIONS:
            raise ValueError("El archivo de simulación tiene un formato no reconocido.")
        abp_trajectories = abpTrajectories(
            abp_times_s=abp_data["times"].astype(np.float64),
            abp_positions=abp_data["positions"].astype(np.float32),
            abp_status=abp_data["status"].astype(np.int8),
            abp_radius_m=abp_data["radius"].astype(np.float32),
            abp_profile_index=abp_data["profile_index"].astype(np.int32),
            abp_profile_names=tuple(str(abp_n) for abp_n in abp_data["profile_names"]),
            abp_level=abp_data["level"].astype(np.int8) if "level" in abp_data.files else None,
        )
        abp_bottlenecks = tuple(
            abpBottleneck(
                abpPoint(float(abp_row[0]), float(abp_row[1])),
                float(abp_row[2]),
                float(abp_row[3]),
                float(abp_row[4]),
                int(abp_row[5]) if len(abp_row) > 5 else 0,
            )
            for abp_row in abp_data["bottlenecks"]
        )
        abp_floor_maps: tuple[abpFloorMap, ...] = ()
        if "floor_levels" in abp_data.files:
            abp_floor_maps = tuple(
                abpFloorMap(
                    abp_level=int(abp_level),
                    abp_density_map=abp_data[f"floor_density_{abp_k}"].astype(np.float64),
                    abp_grid_origin_m=(
                        float(abp_data["floor_origins"][abp_k][0]),
                        float(abp_data["floor_origins"][abp_k][1]),
                    ),
                    abp_cell_size_m=float(abp_data["floor_cells"][abp_k]),
                )
                for abp_k, abp_level in enumerate(abp_data["floor_levels"])
            )
        abp_origin = abp_data["origin"]
        abp_total, abp_evacuated, abp_completed = (int(abp_v) for abp_v in abp_data["counts"])
        return abpStoredRun(
            abp_trajectories=abp_trajectories,
            abp_curve_times_s=abp_data["curve_times"].astype(np.float64),
            abp_curve_evacuated=abp_data["curve_evacuated"].astype(np.int32),
            abp_density_map=abp_data["density"].astype(np.float64),
            abp_bottlenecks=abp_bottlenecks,
            abp_grid_origin_m=(float(abp_origin[0]), float(abp_origin[1])),
            abp_cell_size_m=float(abp_data["cell_size"]),
            abp_agents_total=abp_total,
            abp_agents_evacuated=abp_evacuated,
            abp_completed=bool(abp_completed),
            abp_floor_maps=abp_floor_maps,
        )
