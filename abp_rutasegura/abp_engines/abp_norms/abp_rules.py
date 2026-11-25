from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml

from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_norms import abpNormRule, abpRuleVerification

abp_KIND_OCCUPANCY = "indice_ocupacion"
abp_KIND_WIDTH_PER_PERSON = "ancho_por_persona"
abp_KIND_MIN_WIDTH = "ancho_minimo"
abp_KIND_ANTIPANIC = "barra_antipanico"
abp_KIND_TRAVEL = "distancia_recorrido"
abp_KINDS = frozenset(
    {
        abp_KIND_OCCUPANCY,
        abp_KIND_WIDTH_PER_PERSON,
        abp_KIND_MIN_WIDTH,
        abp_KIND_ANTIPANIC,
        abp_KIND_TRAVEL,
    }
)
abp_ELEMENTS = frozenset({"puerta", "salida", "pasillo"})
abp__COMMON = ("id", "tipo", "descripcion", "norma", "articulo", "verificado", "recomendacion")
abp_USE_NAMES = {"educacion": "educación", "oficinas": "oficinas", "comercio": "comercio"}
abp_VALUE_KEYS: dict[str, tuple[str, str]] = {
    abp_KIND_OCCUPANCY: ("m2_por_persona", "m²/persona"),
    abp_KIND_WIDTH_PER_PERSON: ("metros_por_persona", "m/persona"),
    abp_KIND_MIN_WIDTH: ("metros", "m"),
    abp_KIND_ANTIPANIC: ("umbral_personas", "personas"),
    abp_KIND_TRAVEL: ("metros", "m"),
}


class abpRuleError(ValueError):
    pass


@dataclass(frozen=True)
class abpRule:
    abp_id: str
    abp_kind: str
    abp_description: str
    abp_norm: str
    abp_article: str
    abp_verified: bool
    abp_recommendation: str
    abp_params: Mapping[str, Any] = field(default_factory=dict)
    abp_source: str = ""
    abp_verified_by: str = ""
    abp_verified_on: date | None = None

    @property
    def abp_value(self) -> float | None:
        abp_key, _ = abp_VALUE_KEYS[self.abp_kind]
        abp_raw = self.abp_params.get(abp_key)
        return None if abp_raw is None else float(abp_raw)

    @property
    def abp_label(self) -> str:
        abp_label = str(self.abp_params.get("etiqueta", ""))
        abp_use = self.abp_params.get("uso")
        return (
            f"{abp_label} ({abp_USE_NAMES.get(str(abp_use), str(abp_use))})"
            if abp_label and abp_use
            else abp_label
        )

    @property
    def abp_unit(self) -> str:
        return abp_VALUE_KEYS[self.abp_kind][1]

    def abp_as_domain(self) -> abpNormRule:
        return abpNormRule(
            self.abp_id,
            self.abp_kind,
            self.abp_description,
            self.abp_norm,
            self.abp_article,
            self.abp_verified,
            abp_value=self.abp_value,
            abp_unit=self.abp_unit,
            abp_source=self.abp_source,
            abp_verified_by=self.abp_verified_by,
            abp_verified_on=self.abp_verified_on,
            abp_label=self.abp_label,
        )

    def abp_verified_with(self, abp_verification: abpRuleVerification) -> abpRule:
        abp_key, _ = abp_VALUE_KEYS[self.abp_kind]
        if abp_verification.abp_value is None and self.abp_kind != abp_KIND_OCCUPANCY:
            raise abpRuleError(f"{self.abp_id}: esta regla necesita un valor.")
        abp_params = dict(self.abp_params)
        abp_params[abp_key] = abp_verification.abp_value
        return dataclasses.replace(
            self,
            abp_params=abp_params,
            abp_norm=abp_verification.abp_norm.strip(),
            abp_article=abp_verification.abp_article.strip(),
            abp_verified=abp_verification.abp_verified,
            abp_source=abp_verification.abp_source.strip(),
            abp_verified_by=abp_verification.abp_verified_by.strip(),
            abp_verified_on=abp_verification.abp_verified_on,
        )

    def abp_number(self, abp_key: str) -> float:
        return float(self.abp_params[abp_key])


@dataclass(frozen=True)
class abpCategory:
    abp_id: str
    abp_label: str
    abp_use: abpUseType
    abp_m2_per_person: float | None
    abp_circulation: bool
    abp_default: bool
    abp_rule: abpRule


class abpRuleSet:
    def __init__(self, abp_rules: Iterable[abpRule]) -> None:
        self.abp_rules: tuple[abpRule, ...] = tuple(abp_rules)
        abp_ids = [abp_r.abp_id for abp_r in self.abp_rules]
        abp_duplicated = sorted({abp_i for abp_i in abp_ids if abp_ids.count(abp_i) > 1})
        if abp_duplicated:
            raise abpRuleError(f"Hay reglas con id repetido: {', '.join(abp_duplicated)}.")
        self.abp__categories: dict[abpUseType, list[abpCategory]] = {
            abp_u: [] for abp_u in abpUseType
        }
        for abp_rule in self.abp_rules:
            if abp_rule.abp_kind != abp_KIND_OCCUPANCY:
                continue
            abp_m2 = abp_rule.abp_params.get("m2_por_persona")
            abp_use = abpUseType(abp_rule.abp_params["uso"])
            self.abp__categories[abp_use].append(
                abpCategory(
                    abp_id=str(abp_rule.abp_params["categoria"]),
                    abp_label=str(
                        abp_rule.abp_params.get("etiqueta", abp_rule.abp_params["categoria"])
                    ),
                    abp_use=abp_use,
                    abp_m2_per_person=None if abp_m2 is None else float(abp_m2),
                    abp_circulation=bool(abp_rule.abp_params.get("circulacion", False)),
                    abp_default=bool(abp_rule.abp_params.get("por_defecto", False)),
                    abp_rule=abp_rule,
                )
            )

    def abp_categories(self, abp_use: abpUseType) -> list[abpCategory]:
        return sorted(self.abp__categories[abp_use], key=lambda abp_c: not abp_c.abp_default)

    def abp_category(self, abp_use: abpUseType, abp_category_id: str) -> abpCategory | None:
        abp_options = self.abp_categories(abp_use)
        for abp_option in abp_options:
            if abp_option.abp_id == abp_category_id:
                return abp_option
        return abp_options[0] if abp_options else None

    def abp_of_kind(self, abp_kind: str, abp_element: str | None = None) -> list[abpRule]:
        return [
            abp_r
            for abp_r in self.abp_rules
            if abp_r.abp_kind == abp_kind
            and (abp_element is None or abp_r.abp_params.get("elemento") == abp_element)
        ]

    def abp_first(self, abp_kind: str, abp_element: str | None = None) -> abpRule | None:
        abp_found = self.abp_of_kind(abp_kind, abp_element)
        return abp_found[0] if abp_found else None


def abp__require(abp_item: Mapping[str, Any], abp_key: str, abp_where: str) -> Any:
    if abp_key not in abp_item or abp_item[abp_key] is None or abp_item[abp_key] == "":
        raise abpRuleError(f"{abp_where}: falta el campo «{abp_key}».")
    return abp_item[abp_key]


def abp__parse_rule(abp_item: Any, abp_source: str) -> abpRule:
    if not isinstance(abp_item, dict):
        raise abpRuleError(f"{abp_source}: cada regla debe ser un diccionario.")
    abp_where = f"{abp_source}, regla {abp_item.get('id', '?')}"
    for abp_key in abp__COMMON:
        abp__require(abp_item, abp_key, abp_where)
    abp_kind = str(abp_item["tipo"])
    if abp_kind not in abp_KINDS:
        raise abpRuleError(f"{abp_where}: tipo desconocido «{abp_kind}».")
    if not isinstance(abp_item["verificado"], bool):
        raise abpRuleError(f"{abp_where}: «verificado» debe ser true o false.")
    if abp_kind == abp_KIND_OCCUPANCY:
        abp__require(abp_item, "uso", abp_where)
        abp__require(abp_item, "categoria", abp_where)
        try:
            abpUseType(abp_item["uso"])
        except ValueError as abp_exc:
            raise abpRuleError(f"{abp_where}: uso desconocido «{abp_item['uso']}».") from abp_exc
        if "m2_por_persona" not in abp_item:
            raise abpRuleError(
                f"{abp_where}: falta el campo «m2_por_persona» (use null si no aplica)."
            )
        abp_m2 = abp_item["m2_por_persona"]
        if abp_m2 is not None and float(abp_m2) <= 0:
            raise abpRuleError(f"{abp_where}: «m2_por_persona» debe ser positivo.")
    elif abp_kind in (abp_KIND_WIDTH_PER_PERSON, abp_KIND_MIN_WIDTH):
        abp_element = abp__require(abp_item, "elemento", abp_where)
        if abp_element not in abp_ELEMENTS:
            raise abpRuleError(f"{abp_where}: elemento desconocido «{abp_element}».")
        abp_key = "metros_por_persona" if abp_kind == abp_KIND_WIDTH_PER_PERSON else "metros"
        if float(abp__require(abp_item, abp_key, abp_where)) <= 0:
            raise abpRuleError(f"{abp_where}: «{abp_key}» debe ser positivo.")
    elif (
        abp_kind == abp_KIND_ANTIPANIC
        and int(abp__require(abp_item, "umbral_personas", abp_where)) <= 0
    ):
        raise abpRuleError(f"{abp_where}: «umbral_personas» debe ser positivo.")
    elif abp_kind == abp_KIND_TRAVEL and float(abp__require(abp_item, "metros", abp_where)) <= 0:
        raise abpRuleError(f"{abp_where}: «metros» debe ser positivo.")
    abp_params = {abp_k: abp_v for abp_k, abp_v in abp_item.items() if abp_k not in abp__COMMON}
    return abpRule(
        abp_id=str(abp_item["id"]),
        abp_kind=abp_kind,
        abp_description=str(abp_item["descripcion"]),
        abp_norm=str(abp_item["norma"]),
        abp_article=str(abp_item["articulo"]),
        abp_verified=bool(abp_item["verificado"]),
        abp_recommendation=" ".join(str(abp_item["recomendacion"]).split()),
        abp_params=abp_params,
    )


def abp_parse_rules(abp_documents: Iterable[tuple[str, str]]) -> abpRuleSet:
    abp_rules: list[abpRule] = []
    for abp_source, abp_text in abp_documents:
        try:
            abp_data = yaml.safe_load(abp_text)
        except yaml.YAMLError as abp_exc:
            raise abpRuleError(f"{abp_source}: el YAML no es válido ({abp_exc}).") from abp_exc
        if not isinstance(abp_data, dict) or not isinstance(abp_data.get("reglas"), list):
            raise abpRuleError(f"{abp_source}: debe tener una lista «reglas».")
        abp_rules.extend(abp__parse_rule(abp_item, abp_source) for abp_item in abp_data["reglas"])
    return abpRuleSet(abp_rules)


def abp_apply_verifications(
    abp_rules: abpRuleSet, abp_verifications: Iterable[abpRuleVerification]
) -> abpRuleSet:
    abp_by_id = {abp_v.abp_rule_id: abp_v for abp_v in abp_verifications}
    return abpRuleSet(
        abp_r.abp_verified_with(abp_by_id[abp_r.abp_id]) if abp_r.abp_id in abp_by_id else abp_r
        for abp_r in abp_rules.abp_rules
    )
