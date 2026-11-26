from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from abp_rutasegura.abp_domain.abp_results import abpObservation, abpRoomRoute


@dataclass(frozen=True, slots=True)
class abpNormRule:
    abp_id: str
    abp_kind: str
    abp_description: str
    abp_norm: str
    abp_article: str
    abp_verified: bool
    abp_value: float | None = None
    abp_unit: str = ""
    abp_source: str = ""
    abp_verified_by: str = ""
    abp_verified_on: date | None = None
    abp_label: str = ""

    @property
    def abp_citation(self) -> str:
        return f"{self.abp_norm}, {self.abp_article}"

    @property
    def abp_value_text(self) -> str:
        if self.abp_value is None:
            return "sin aforo propio" if self.abp_kind == "indice_ocupacion" else "—"
        return f"{self.abp_value:g} {self.abp_unit}".strip()


@dataclass(frozen=True, slots=True)
class abpRuleVerification:
    abp_rule_id: str
    abp_value: float | None
    abp_norm: str
    abp_article: str
    abp_source: str = ""
    abp_verified: bool = True
    abp_verified_by: str = ""
    abp_verified_on: date | None = None

    def __post_init__(self) -> None:
        if self.abp_value is not None and self.abp_value <= 0:
            raise ValueError("El valor de la regla debe ser positivo.")
        if not self.abp_norm.strip() or not self.abp_article.strip():
            raise ValueError("Indique la norma y el artículo.")


@dataclass(frozen=True, slots=True)
class abpRoomCapacity:
    abp_room_name: str
    abp_level: int
    abp_category: str
    abp_category_label: str
    abp_area_m2: float
    abp_m2_per_person: float | None
    abp_capacity: int | None
    abp_occupants: int
    abp_rule_id: str | None

    @property
    def abp_exceeded(self) -> bool:
        return self.abp_capacity is not None and self.abp_occupants > self.abp_capacity


@dataclass(frozen=True, slots=True)
class abpNormEvaluation:
    abp_capacities: tuple[abpRoomCapacity, ...] = field(default_factory=tuple)
    abp_routes: tuple[abpRoomRoute, ...] = field(default_factory=tuple)
    abp_observations: tuple[abpObservation, ...] = field(default_factory=tuple)
    abp_rules_used: tuple[abpNormRule, ...] = field(default_factory=tuple)

    @property
    def abp_total_capacity(self) -> int:
        return sum(abp_c.abp_capacity or 0 for abp_c in self.abp_capacities)

    @property
    def abp_total_occupants(self) -> int:
        return sum(abp_c.abp_occupants for abp_c in self.abp_capacities)

    @property
    def abp_unverified_rules(self) -> tuple[abpNormRule, ...]:
        return tuple(abp_r for abp_r in self.abp_rules_used if not abp_r.abp_verified)
