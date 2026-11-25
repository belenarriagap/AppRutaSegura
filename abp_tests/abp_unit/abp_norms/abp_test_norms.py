from __future__ import annotations

import dataclasses

import pytest

from abp_rutasegura.abp_domain.abp_enums import abpObservationType, abpUseType
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpExit, abpFloorPlan, abpRoom
from abp_rutasegura.abp_engines.abp_norms.abp_evaluate import (
    abp_corridor_width,
    abp_distance_to_boundary,
    abp_evaluate,
)
from abp_rutasegura.abp_engines.abp_norms.abp_rules import abp_parse_rules, abpRuleError
from abp_tests.abp_fixtures.abp_simple_plans import (
    abp__seg,
    abp_rect,
    abp_SCALE,
    abp_single_room,
    abp_two_rooms,
)
from abp_tests.abp_unit.abp_norms.abp_helpers import abp_packaged_rules

abp_RULES = abp_packaged_rules()


def abp__ids(abp_observations: object) -> list[str]:
    return [abp_o.abp_description for abp_o in abp_observations]


class abpTestRules:
    def abp_test_packaged_rules_are_valid_and_unverified(self) -> None:
        assert len(abp_RULES.abp_rules) >= 10
        assert all(not abp_r.abp_verified for abp_r in abp_RULES.abp_rules)
        for abp_use in abpUseType:
            abp_categories = abp_RULES.abp_categories(abp_use)
            assert abp_categories, abp_use
            assert abp_categories[0].abp_default
            assert any(abp_c.abp_circulation for abp_c in abp_categories)

    def abp_test_category_lookup_falls_back_to_default(self) -> None:
        assert abp_RULES.abp_category(abpUseType.abp_EDUCATION, "taller").abp_id == "taller"
        assert abp_RULES.abp_category(abpUseType.abp_EDUCATION, "").abp_id == "aula"
        assert abp_RULES.abp_category(abpUseType.abp_OFFICE, "no-existe").abp_id == "oficina"

    @pytest.mark.parametrize(
        ("abp_yaml_text", "abp_message"),
        [
            ("otra: 1", "lista «reglas»"),
            ("reglas: [1]", "diccionario"),
            ("reglas:\n  - id: X\n    tipo: indice_ocupacion", "falta el campo"),
            (
                "reglas:\n  - {id: X, tipo: rara, descripcion: d, norma: n, articulo: a, "
                "verificado: false, recomendacion: r}",
                "tipo desconocido",
            ),
            (
                "reglas:\n  - {id: X, tipo: ancho_minimo, descripcion: d, norma: n, articulo: a, "
                "verificado: 'no', recomendacion: r, elemento: puerta, metros: 1}",
                "true o false",
            ),
            (
                "reglas:\n  - {id: X, tipo: ancho_minimo, descripcion: d, norma: n, articulo: a, "
                "verificado: false, recomendacion: r, elemento: ventana, metros: 1}",
                "elemento desconocido",
            ),
            (
                "reglas:\n  - {id: X, tipo: indice_ocupacion, descripcion: d, norma: n, "
                "articulo: a, verificado: false, recomendacion: r, uso: hotel, categoria: c, "
                "m2_por_persona: 1}",
                "uso desconocido",
            ),
            (
                "reglas:\n  - {id: X, tipo: indice_ocupacion, descripcion: d, norma: n, "
                "articulo: a, verificado: false, recomendacion: r, uso: oficinas, categoria: c}",
                "m2_por_persona",
            ),
            ("reglas: [", "no es válido"),
        ],
    )
    def abp_test_invalid_files(self, abp_yaml_text: str, abp_message: str) -> None:
        with pytest.raises(abpRuleError, match=abp_message):
            abp_parse_rules([("prueba.yaml", abp_yaml_text)])

    def abp_test_duplicate_ids(self) -> None:
        abp_rule = (
            "reglas:\n  - {id: X, tipo: barra_antipanico, descripcion: d, norma: n, articulo: a, "
            "verificado: true, recomendacion: r, umbral_personas: 100}"
        )
        with pytest.raises(abpRuleError, match="repetido"):
            abp_parse_rules([("a.yaml", abp_rule), ("b.yaml", abp_rule)])


class abpTestEvaluation:
    def abp_test_capacity_and_overcrowding(self) -> None:
        abp_plan = abp_single_room()
        abp_ok = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "niño", 40)], abp_RULES)
        assert abp_ok.abp_capacities[0].abp_capacity == 40
        assert not abp_ok.abp_capacities[0].abp_exceeded
        assert abp_ok.abp_total_capacity == 40
        assert not any("aforo" in abp_d for abp_d in abp__ids(abp_ok.abp_observations))
        abp_over = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "niño", 45)], abp_RULES)
        assert abp_over.abp_capacities[0].abp_exceeded
        abp_observation = next(
            abp_o for abp_o in abp_over.abp_observations if "aforo es 40" in abp_o.abp_description
        )
        assert abp_observation.abp_kind is abpObservationType.abp_NORM
        assert abp_observation.abp_norm == "RNE A.040"
        assert abp_observation.abp_article
        assert not abp_observation.abp_verified
        assert any(abp_r.abp_id == "OCU-EDU-AULA" for abp_r in abp_over.abp_unverified_rules)

    def abp_test_door_width_per_person(self) -> None:
        abp_plan = abp_two_rooms()
        abp_fine = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "niño", 20)], abp_RULES)
        assert not any(
            "puertas de «Aula 1»" in abp_d for abp_d in abp__ids(abp_fine.abp_observations)
        )
        abp_crowded = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "niño", 200)], abp_RULES)
        assert any(
            "puertas de «Aula 1» suman 0.90 m" in abp_d
            for abp_d in abp__ids(abp_crowded.abp_observations)
        )

    def abp_test_minimum_widths_of_doors_and_exits(self) -> None:
        abp_narrow = dataclasses.replace(
            abp_two_rooms(),
            abp_doors=(abpDoor(abp__seg(6, 2.7, 6, 3.3)),),
            abp_exits=(abpExit(abp__seg(12, 2.6, 12, 3.4), "Salida principal"),),
        )
        abp_result = abp_evaluate(abp_narrow, [], abp_RULES)
        abp_texts = abp__ids(abp_result.abp_observations)
        assert any("Una puerta de «Aula 1» y «Aula 2» mide 0.60 m" in abp_t for abp_t in abp_texts)
        assert any("«Salida principal» mide 0.80 m" in abp_t for abp_t in abp_texts)

    def abp_test_total_exit_width(self) -> None:
        abp_plan = abp_single_room(abp_exit_width=1.2)
        abp_result = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "adulto", 300)], abp_RULES)
        assert any(
            "salidas confirmadas suman 1.20 m" in abp_d
            for abp_d in abp__ids(abp_result.abp_observations)
        )
        abp_unconfirmed = abp_evaluate(
            abp_single_room(abp_confirmed=False), [abpOccupancy("Aula 1", "a", 1)], abp_RULES
        )
        assert any("suman 0.00 m" in abp_d for abp_d in abp__ids(abp_unconfirmed.abp_observations))

    def abp_test_antipanic_warning(self) -> None:
        abp_plan = abp_single_room(abp_width=20, abp_height=10)
        abp_result = abp_evaluate(abp_plan, [abpOccupancy("Aula 1", "adulto", 101)], abp_RULES)
        assert any("más de 100" in abp_d for abp_d in abp__ids(abp_result.abp_observations))
        assert not any(
            "más de 100" in abp_d
            for abp_d in abp__ids(
                abp_evaluate(
                    abp_plan, [abpOccupancy("Aula 1", "adulto", 100)], abp_RULES
                ).abp_observations
            )
        )

    def abp_test_corridor_width(self) -> None:
        abp_corridor = abpRoom(
            "Pasillo", abpUseType.abp_EDUCATION, abp_rect(0, 0, 1.0, 10.0), "pasillo"
        )
        abp_plan = abpFloorPlan(abp_scale_m_per_px=abp_SCALE, abp_rooms=(abp_corridor,))
        abp_result = abp_evaluate(abp_plan, [], abp_RULES)
        assert abp_result.abp_capacities[0].abp_capacity is None
        assert any("pasillo «Pasillo»" in abp_d for abp_d in abp__ids(abp_result.abp_observations))
        abp_wide = dataclasses.replace(
            abp_plan,
            abp_rooms=(dataclasses.replace(abp_corridor, abp_area=abp_rect(0, 0, 2.0, 10.0)),),
        )
        assert not abp_evaluate(abp_wide, [], abp_RULES).abp_observations

    def abp_test_requires_scale(self) -> None:
        with pytest.raises(ValueError, match="escala"):
            abp_evaluate(
                dataclasses.replace(abp_single_room(), abp_scale_m_per_px=None), [], abp_RULES
            )

    def abp_test_other_levels_are_ignored(self) -> None:
        abp_result = abp_evaluate(
            abp_single_room(), [abpOccupancy("Aula 1", "niño", 500, abp_level=1)], abp_RULES
        )
        assert abp_result.abp_capacities[0].abp_occupants == 0


def abp_test_geometry_helpers() -> None:
    abp_poly = abp_rect(0, 0, 4, 2)
    abp_poly_m = type(abp_poly)(
        tuple(
            type(abp_p)(abp_p.abp_x * abp_SCALE, abp_p.abp_y * abp_SCALE)
            for abp_p in abp_poly.abp_vertices
        )
    )
    assert abp_corridor_width(abp_poly_m) == pytest.approx(2.0, abs=0.15)
    assert abp_distance_to_boundary(
        abp_poly_m, type(abp_poly.abp_vertices[0])(2.0, 1.0)
    ) == pytest.approx(1.0)
