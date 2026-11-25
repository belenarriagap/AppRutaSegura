from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpObservationType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint


@dataclass(frozen=True, slots=True)
class abpBottleneck:
    abp_location: abpPoint
    abp_mean_density: float
    abp_duration_s: float
    abp_severity: float
    abp_level: int = 0


@dataclass(frozen=True, eq=False, slots=True)
class abpFloorMap:
    abp_level: int
    abp_density_map: npt.NDArray[np.float64]
    abp_grid_origin_m: tuple[float, float]
    abp_cell_size_m: float


@dataclass(frozen=True, eq=False, slots=True)
class abpSimulationResult:
    abp_seed: int
    abp_total_time_s: float
    abp_time_per_exit_s: tuple[tuple[str, float], ...]
    abp_curve_times_s: npt.NDArray[np.float64]
    abp_curve_evacuated: npt.NDArray[np.int32]
    abp_density_map: npt.NDArray[np.float64]
    abp_bottlenecks: tuple[abpBottleneck, ...] = field(default_factory=tuple)
    abp_trajectories_path: str | None = None
    abp_agents_total: int = 0
    abp_agents_evacuated: int = 0
    abp_completed: bool = True
    abp_grid_origin_m: tuple[float, float] = (0.0, 0.0)
    abp_cell_size_m: float = 0.4
    abp_floor_maps: tuple[abpFloorMap, ...] = ()

    def __post_init__(self) -> None:
        if self.abp_curve_times_s.shape != self.abp_curve_evacuated.shape:
            raise ValueError("La curva de evacuados necesita tiempos y conteos del mismo largo.")

    def abp_maps(self) -> tuple[abpFloorMap, ...]:
        if self.abp_floor_maps:
            return self.abp_floor_maps
        return (abpFloorMap(0, self.abp_density_map, self.abp_grid_origin_m, self.abp_cell_size_m),)

    def abp_time_to_evacuate(self, abp_fraction: float) -> float | None:
        if not 0 < abp_fraction <= 1:
            raise ValueError("La fracción debe estar entre 0 y 1.")
        abp_needed = abp_fraction * self.abp_agents_total
        abp_reached = np.flatnonzero(self.abp_curve_evacuated >= abp_needed - 1e-9)
        if self.abp_agents_total == 0 or abp_reached.size == 0:
            return None
        return float(self.abp_curve_times_s[abp_reached[0]])


@dataclass(frozen=True, eq=False, slots=True)
class abpTrajectories:
    abp_times_s: npt.NDArray[np.float64]
    abp_positions: npt.NDArray[np.float32]
    abp_status: npt.NDArray[np.int8]
    abp_radius_m: npt.NDArray[np.float32]
    abp_profile_index: npt.NDArray[np.int32]
    abp_profile_names: tuple[str, ...]
    abp_level: npt.NDArray[np.int8] | None = None

    def __post_init__(self) -> None:
        abp_frames, abp_agents = self.abp_status.shape
        if self.abp_level is not None and self.abp_level.shape != (abp_frames, abp_agents):
            raise ValueError("Las trayectorias tienen dimensiones inconsistentes.")
        if self.abp_positions.shape != (abp_frames, abp_agents, 2) or self.abp_times_s.shape != (
            abp_frames,
        ):
            raise ValueError("Las trayectorias tienen dimensiones inconsistentes.")
        if self.abp_radius_m.shape != (abp_agents,) or self.abp_profile_index.shape != (
            abp_agents,
        ):
            raise ValueError("Las trayectorias tienen dimensiones inconsistentes.")

    @property
    def abp_frame_count(self) -> int:
        return int(self.abp_times_s.shape[0])

    @property
    def abp_agent_count(self) -> int:
        return int(self.abp_status.shape[1])

    def abp_levels_at(self, abp_frame: int) -> npt.NDArray[np.int8]:
        if self.abp_level is None:
            return np.zeros(self.abp_agent_count, dtype=np.int8)
        return np.asarray(self.abp_level[abp_frame], dtype=np.int8)


@dataclass(frozen=True, slots=True)
class abpFloorClearance:
    abp_level: int
    abp_people: int
    abp_descended: int
    abp_cleared_s: float | None


@dataclass(frozen=True, slots=True)
class abpRoomRoute:
    abp_room_name: str
    abp_level: int
    abp_target_name: str
    abp_max_distance_m: float
    abp_farthest_m: abpPoint
    abp_path_m: tuple[abpPoint, ...]
    abp_farthest_path_m: tuple[abpPoint, ...] = ()
    abp_manual: bool = False
    abp_from_stair: bool = False


@dataclass(frozen=True, slots=True)
class abpRouteBranch:
    abp_points_m: tuple[abpPoint, ...]
    abp_level: int
    abp_target_name: str = ""
    abp_trunk: bool = False


@dataclass(frozen=True, slots=True)
class abpRoomEscape:
    abp_room_name: str
    abp_level: int
    abp_target_name: str
    abp_door_width_m: float | None
    abp_distance_m: float
    abp_meeting_distance_m: float
    abp_path_m: tuple[abpPoint, ...]


@dataclass(frozen=True, slots=True)
class abpEvacuationNetwork:
    abp_level: int
    abp_branches: tuple[abpRouteBranch, ...]
    abp_escapes: tuple[abpRoomEscape, ...]
    abp_meeting_links: tuple[tuple[str, tuple[abpPoint, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class abpRunStatistics:
    abp_seeds: tuple[int, ...]
    abp_total_times_s: tuple[float, ...]
    abp_ninety_times_s: tuple[float | None, ...]
    abp_completed: tuple[bool, ...]
    abp_representative_seed: int

    @property
    def abp_runs(self) -> int:
        return len(self.abp_seeds)

    @property
    def abp_total_mean_s(self) -> float:
        return sum(self.abp_total_times_s) / len(self.abp_total_times_s)

    @property
    def abp_total_std_s(self) -> float:
        abp_n = len(self.abp_total_times_s)
        if abp_n < 2:
            return 0.0
        abp_mean = self.abp_total_mean_s
        return math.sqrt(
            sum((abp_t - abp_mean) ** 2 for abp_t in self.abp_total_times_s) / (abp_n - 1)
        )

    @property
    def abp_total_min_s(self) -> float:
        return min(self.abp_total_times_s)

    @property
    def abp_total_max_s(self) -> float:
        return max(self.abp_total_times_s)

    @property
    def abp_total_p95_s(self) -> float:
        return abp__percentile(sorted(self.abp_total_times_s), 0.95)

    @property
    def abp_ninety_mean_s(self) -> float | None:
        abp_values = [abp_t for abp_t in self.abp_ninety_times_s if abp_t is not None]
        return sum(abp_values) / len(abp_values) if abp_values else None

    @property
    def abp_all_completed(self) -> bool:
        return all(self.abp_completed)


def abp__percentile(abp_values: list[float], abp_q: float) -> float:
    if len(abp_values) == 1:
        return abp_values[0]
    abp_position = abp_q * (len(abp_values) - 1)
    abp_low = int(abp_position)
    abp_high = min(abp_low + 1, len(abp_values) - 1)
    return abp_values[abp_low] + (abp_values[abp_high] - abp_values[abp_low]) * (
        abp_position - abp_low
    )


@dataclass(frozen=True, slots=True)
class abpSimulationSummary:
    abp_seed: int
    abp_total_time_s: float
    abp_time_per_exit_s: tuple[tuple[str, float], ...]
    abp_trajectories_path: str | None = None
    abp_created_at: datetime | None = None
    abp_statistics: abpRunStatistics | None = None
    abp_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class abpObservation:
    abp_kind: abpObservationType
    abp_description: str
    abp_recommendation: str
    abp_location: abpPoint | None = None
    abp_norm: str | None = None
    abp_article: str | None = None
    abp_verified: bool = True

    def __post_init__(self) -> None:
        if self.abp_kind is abpObservationType.abp_NORM and not (
            self.abp_norm and self.abp_article
        ):
            raise ValueError("Una observación normativa debe citar norma y artículo.")
