from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_people import abpOccupancy

abp_MAX_RUNS = 50
abp_FACTOR_RANGE = (0.2, 5.0)


@dataclass(frozen=True, slots=True)
class abpManualRoute:
    abp_source: str
    abp_level: int
    abp_exit_name: str = ""
    abp_waypoints: tuple[abpPoint, ...] = ()
    abp_from_stair: bool = False

    @property
    def abp_key(self) -> tuple[int, bool, str]:
        return (self.abp_level, self.abp_from_stair, self.abp_source)

    @property
    def abp_is_empty(self) -> bool:
        return not self.abp_exit_name and not self.abp_waypoints


@dataclass(frozen=True, slots=True)
class abpScenario:
    abp_name: str
    abp_seed: int
    abp_occupancies: tuple[abpOccupancy, ...] = field(default_factory=tuple)
    abp_blocked_exits: frozenset[str] = field(default_factory=frozenset)
    abp_description: str = ""
    abp_reaction_factor: float = 1.0
    abp_speed_factor: float = 1.0
    abp_runs: int = 1
    abp_routes: tuple[abpManualRoute, ...] = ()

    def __post_init__(self) -> None:
        if self.abp_seed < 0:
            raise ValueError("La semilla debe ser un entero no negativo.")
        abp_low, abp_high = abp_FACTOR_RANGE
        for abp_label, abp_value in (
            ("reacción", self.abp_reaction_factor),
            ("velocidad", self.abp_speed_factor),
        ):
            if not abp_low <= abp_value <= abp_high:
                raise ValueError(
                    f"El factor de {abp_label} debe estar entre {abp_low} y {abp_high}."
                )
        if not 1 <= self.abp_runs <= abp_MAX_RUNS:
            raise ValueError(f"El número de corridas debe estar entre 1 y {abp_MAX_RUNS}.")

    def abp_route_of(
        self, abp_level: int, abp_source: str, *, abp_from_stair: bool = False
    ) -> abpManualRoute | None:
        abp_key = (abp_level, abp_from_stair, abp_source)
        return next((abp_r for abp_r in self.abp_routes if abp_r.abp_key == abp_key), None)

    def abp_with_route(self, abp_route: abpManualRoute) -> abpScenario:
        abp_rest = tuple(abp_r for abp_r in self.abp_routes if abp_r.abp_key != abp_route.abp_key)
        return replace(
            self, abp_routes=abp_rest if abp_route.abp_is_empty else (*abp_rest, abp_route)
        )

    def abp_renamed_room(self, abp_level: int, abp_old: str, abp_new: str) -> abpScenario:
        return replace(
            self,
            abp_occupancies=tuple(
                replace(abp_o, abp_room_name=abp_new)
                if (abp_o.abp_level, abp_o.abp_room_name) == (abp_level, abp_old)
                else abp_o
                for abp_o in self.abp_occupancies
            ),
            abp_routes=tuple(
                replace(abp_r, abp_source=abp_new)
                if abp_r.abp_key == (abp_level, False, abp_old)
                else abp_r
                for abp_r in self.abp_routes
            ),
        )

    def abp_moved_routes(
        self, abp_level: int, abp_move: Callable[[abpPoint], abpPoint] | None
    ) -> abpScenario:
        abp_kept = [
            abp_r
            if abp_r.abp_level != abp_level
            else None
            if abp_move is None
            else replace(
                abp_r, abp_waypoints=tuple(abp_move(abp_p) for abp_p in abp_r.abp_waypoints)
            )
            for abp_r in self.abp_routes
        ]
        return replace(self, abp_routes=tuple(abp_r for abp_r in abp_kept if abp_r is not None))

    @property
    def abp_seeds(self) -> tuple[int, ...]:
        return tuple(range(self.abp_seed, self.abp_seed + self.abp_runs))

    @property
    def abp_total_occupants(self) -> int:
        return sum(abp_o.abp_count for abp_o in self.abp_occupancies)


@dataclass(frozen=True, slots=True)
class abpRealDrill:
    abp_drill_date: date
    abp_participants: int
    abp_total_time_s: float
    abp_time_per_exit_s: tuple[tuple[str, float], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.abp_participants <= 0:
            raise ValueError("Debe haber al menos un participante.")
        if self.abp_total_time_s <= 0:
            raise ValueError("El tiempo total debe ser positivo.")
