from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from importlib import resources

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_data.abp_database import abpDatabase
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_norms import (
    abpNormEvaluation,
    abpNormRule,
    abpRoomCapacity,
    abpRuleVerification,
)
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpRoom
from abp_rutasegura.abp_domain.abp_results import abpObservation, abpRoomRoute
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_engines.abp_navigation.abp_fields import abp_distance_field
from abp_rutasegura.abp_engines.abp_navigation.abp_grid import abp_build_grid, abp_polygon_to_m
from abp_rutasegura.abp_engines.abp_navigation.abp_routes import abp_room_routes
from abp_rutasegura.abp_engines.abp_norms.abp_evaluate import abp_evaluate
from abp_rutasegura.abp_engines.abp_norms.abp_rules import (
    abp_apply_verifications,
    abp_parse_rules,
    abpRuleError,
    abpRuleSet,
)
from abp_rutasegura.abp_engines.abp_simulation.abp_population import abpRoomArea


def abp_load_packaged_rules() -> abpRuleSet:
    abp_folder = resources.files("abp_rutasegura.abp_resources").joinpath("abp_norms")
    abp_documents = sorted(
        (abp_item.name, abp_item.read_text(encoding="utf-8"))
        for abp_item in abp_folder.iterdir()
        if abp_item.name.endswith(".yaml")
    )
    try:
        return abp_parse_rules(abp_documents)
    except abpRuleError as abp_exc:
        raise abpUserFacingError(f"Las reglas normativas tienen un error: {abp_exc}") from abp_exc


abp_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "banos",
        (
            "baño",
            "bano",
            "ss.hh",
            "sshh",
            "s.h.",
            "higiénico",
            "higienico",
            "sanitario",
            "wc",
            "toilet",
            "restroom",
            "rest room",
            "vestidor",
        ),
    ),
    ("cocina", ("cocina", "kitchen", "kitchenette")),
    ("deposito", ("depósito", "deposito", "almacén", "almacen", "bodega", "storage", "archivo")),
    ("patio", ("patio", "jardín", "jardin", "terraza", "losa", "explanada")),
    ("mesas", ("comedor", "dining", "restaurante", "mesas", "bar", "cafetería", "cafeteria")),
    ("comedor", ("comedor", "cafetería", "cafeteria", "dining")),
    (
        "pasillo",
        (
            "pasillo",
            "corredor",
            "hall",
            "circulación",
            "circulacion",
            "escalera",
            "vestíbulo",
            "vestibulo",
            "pasadizo",
        ),
    ),
    (
        "administrativo",
        ("dirección", "direccion", "secretaría", "secretaria", "administración", "administracion"),
    ),
    ("taller", ("taller", "laboratorio", "biblioteca", "cómputo", "computo")),
    ("sum", ("sum", "auditorio", "usos múltiples", "usos multiples", "salón de actos")),
    ("aula", ("aula", "salón", "salon", "clase", "inicial", "primaria", "secundaria")),
    ("oficina", ("oficina", "office", "gerencia", "reuniones")),
)


abp_USE_SHORT_NAMES = {
    abpUseType.abp_EDUCATION: "Educación",
    abpUseType.abp_OFFICE: "Oficinas",
    abpUseType.abp_COMMERCE: "Comercio",
}


def abp__words(abp_text: str) -> str:
    return f" {abp_text.lower().replace('_', ' ').replace('-', ' ')} "


class abpNormsService:
    def __init__(
        self, abp_rules: abpRuleSet | None = None, abp_db: abpDatabase | None = None
    ) -> None:
        self.abp__packaged = abp_rules or abp_load_packaged_rules()
        self.abp__db = abp_db
        self.abp__rules = self.abp__packaged
        self.abp_reload()

    def abp_reload(self) -> None:
        if self.abp__db is None:
            self.abp__rules = self.abp__packaged
            return
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_verifications = abp_uow.abp_rule_verifications.abp_list_all()
        try:
            self.abp__rules = abp_apply_verifications(self.abp__packaged, abp_verifications)
        except abpRuleError as abp_exc:
            raise abpUserFacingError(f"Una regla verificada tiene un error: {abp_exc}") from abp_exc

    def abp_catalog(self) -> list[abpNormRule]:
        return [abp_r.abp_as_domain() for abp_r in self.abp__rules.abp_rules]

    def abp_original(self, abp_rule_id: str) -> abpNormRule:
        for abp_rule in self.abp__packaged.abp_rules:
            if abp_rule.abp_id == abp_rule_id:
                return abp_rule.abp_as_domain()
        raise abpUserFacingError(f"No existe la regla «{abp_rule_id}».")

    def abp_verify_rule(self, abp_verification: abpRuleVerification) -> abpNormRule:
        self.abp_original(abp_verification.abp_rule_id)
        if self.abp__db is None:
            raise abpUserFacingError("No hay base de datos para guardar la verificación.")
        abp_current = next(
            abp_r
            for abp_r in self.abp__packaged.abp_rules
            if abp_r.abp_id == abp_verification.abp_rule_id
        )
        try:
            abp_current.abp_verified_with(abp_verification)
        except abpRuleError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_rule_verifications.abp_save(abp_verification)
        self.abp_reload()
        return next(
            abp_r for abp_r in self.abp_catalog() if abp_r.abp_id == abp_verification.abp_rule_id
        )

    def abp_reset_rule(self, abp_rule_id: str) -> None:
        if self.abp__db is None:
            return
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_rule_verifications.abp_delete(abp_rule_id)
        self.abp_reload()

    def abp_suggest_category(self, abp_room_name: str, abp_use: abpUseType) -> str:
        abp_available = {abp_c.abp_id for abp_c in self.abp__rules.abp_categories(abp_use)}
        abp_name = abp__words(abp_room_name)
        for abp_category, abp_words in abp_CATEGORY_KEYWORDS:
            if abp_category in abp_available and any(
                abp__words(abp_w).rstrip() in abp_name for abp_w in abp_words
            ):
                return abp_category
        return ""

    def abp_effective_category(self, abp_room: abpRoom) -> str:
        abp_chosen = abp_room.abp_category or self.abp_suggest_category(
            abp_room.abp_name, abp_room.abp_use
        )
        abp_category = self.abp__rules.abp_category(abp_room.abp_use, abp_chosen)
        return abp_category.abp_id if abp_category is not None else abp_chosen

    def abp_room_types(
        self, abp_first_use: abpUseType | None = None
    ) -> list[tuple[abpUseType, str, str]]:
        abp_uses = sorted(abpUseType, key=lambda abp_u: abp_u != abp_first_use)
        return [
            (
                abp_use,
                abp_category.abp_id,
                f"{abp_USE_SHORT_NAMES[abp_use]} › {abp_category.abp_label}",
            )
            for abp_use in abp_uses
            for abp_category in self.abp__rules.abp_categories(abp_use)
        ]

    def abp_with_suggested_categories(self, abp_plan: abpFloorPlan) -> abpFloorPlan:
        abp_rooms = tuple(
            dataclasses.replace(
                abp_r, abp_category=self.abp_suggest_category(abp_r.abp_name, abp_r.abp_use)
            )
            if not abp_r.abp_category
            else abp_r
            for abp_r in abp_plan.abp_rooms
        )
        return (
            abp_plan
            if abp_rooms == abp_plan.abp_rooms
            else dataclasses.replace(abp_plan, abp_rooms=abp_rooms)
        )

    def abp_categories(self, abp_use: abpUseType) -> list[tuple[str, str]]:
        return [
            (abp_c.abp_id, abp_c.abp_label) for abp_c in self.abp__rules.abp_categories(abp_use)
        ]

    def abp_evaluate(
        self,
        abp_plan: abpFloorPlan,
        abp_scenario: abpScenario | None,
        *,
        abp_exit_occupants: int | None = None,
    ) -> abpNormEvaluation:
        abp_occupancies = abp_scenario.abp_occupancies if abp_scenario is not None else ()
        abp_plan = self.abp_with_suggested_categories(abp_plan)
        try:
            abp_routes = self.abp_routes(abp_plan, abp_upper_floor=abp_exit_occupants == 0)
            return abp_evaluate(
                abp_plan,
                abp_occupancies,
                self.abp__rules,
                abp_exit_occupants=abp_exit_occupants,
                abp_routes=abp_routes,
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_routes(
        abp_plan: abpFloorPlan, *, abp_blocked: Sequence[str] = (), abp_upper_floor: bool = False
    ) -> tuple[abpRoomRoute, ...]:
        abp_scale = abp_plan.abp_scale_m_per_px
        if abp_scale is None or not abp_plan.abp_rooms:
            return ()
        try:
            abp_grid = abp_build_grid(
                abp_plan,
                abp_blocked_exits=abp_blocked,
                abp_stairs_as_targets=abp_upper_floor,
                abp_exits_as_targets=not abp_upper_floor,
            )
        except ValueError:
            return ()
        if not abp_grid.abp_targets.any():
            return ()
        abp_distance = abp_distance_field(
            abp_grid.abp_walkable, abp_grid.abp_targets, abp_grid.abp_cell_size
        )
        abp_rooms = [
            abpRoomArea(
                abp_r.abp_name, abp_plan.abp_level, abp_polygon_to_m(abp_r.abp_area, abp_scale)
            )
            for abp_r in abp_plan.abp_rooms
        ]
        return abp_room_routes(abp_grid, abp_distance, abp_rooms)

    def abp_evaluate_building(
        self, abp_floors: Sequence[abpFloorPlan], abp_scenario: abpScenario | None
    ) -> abpNormEvaluation:
        abp_ordered = sorted(abp_floors, key=lambda abp_f: abp_f.abp_level)
        if len(abp_ordered) <= 1:
            return (
                self.abp_evaluate(abp_ordered[0], abp_scenario)
                if abp_ordered
                else abpNormEvaluation()
            )
        abp_total = abp_scenario.abp_total_occupants if abp_scenario is not None else 0
        abp_capacities: list[abpRoomCapacity] = []
        abp_observations: list[abpObservation] = []
        abp_routes: list[abpRoomRoute] = []
        abp_rules: dict[str, abpNormRule] = {}
        for abp_k, abp_plan in enumerate(abp_ordered):
            abp_result = self.abp_evaluate(
                abp_plan, abp_scenario, abp_exit_occupants=abp_total if abp_k == 0 else 0
            )
            abp_capacities.extend(abp_result.abp_capacities)
            abp_routes.extend(abp_result.abp_routes)
            abp_observations.extend(
                dataclasses.replace(
                    abp_o, abp_description=f"Piso {abp_plan.abp_level + 1}: {abp_o.abp_description}"
                )
                for abp_o in abp_result.abp_observations
            )
            abp_rules.update({abp_r.abp_id: abp_r for abp_r in abp_result.abp_rules_used})
        return abpNormEvaluation(
            abp_capacities=tuple(abp_capacities),
            abp_observations=tuple(abp_observations),
            abp_rules_used=tuple(abp_rules[abp_k] for abp_k in sorted(abp_rules)),
            abp_routes=tuple(abp_routes),
        )
