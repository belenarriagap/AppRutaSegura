from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import pytest

from abp_rutasegura.abp_domain import (
    abpAgentArrays,
    abpAgentStatus,
    abpDoor,
    abpFloorPlan,
    abpObservation,
    abpObservationType,
    abpOccupancy,
    abpPersonProfile,
    abpPoint,
    abpPolygon,
    abpRealDrill,
    abpRoom,
    abpScenario,
    abpSegment,
    abpSimulationResult,
    abpUseType,
    abpWall,
)


def abp__square(abp_side: float) -> abpPolygon:
    return abpPolygon(
        (abpPoint(0, 0), abpPoint(abp_side, 0), abpPoint(abp_side, abp_side), abpPoint(0, abp_side))
    )


class abpTestGeometry:
    def abp_test_segment_length_and_midpoint(self) -> None:
        abp_seg = abpSegment(abpPoint(0, 0), abpPoint(3, 4))
        assert abp_seg.abp_length == pytest.approx(5.0)
        assert abp_seg.abp_midpoint == abpPoint(1.5, 2.0)

    def abp_test_polygon_area_is_positive_in_both_orientations(self) -> None:
        abp_square = abp__square(10)
        abp_reversed_square = abpPolygon(tuple(reversed(abp_square.abp_vertices)))
        assert abp_square.abp_area == pytest.approx(100.0)
        assert abp_reversed_square.abp_area == pytest.approx(100.0)
        assert abp_square.abp_centroid == abpPoint(5, 5)

    def abp_test_polygon_needs_three_vertices(self) -> None:
        with pytest.raises(ValueError, match="al menos 3"):
            abpPolygon((abpPoint(0, 0), abpPoint(1, 1)))


class abpTestFloorPlan:
    def abp_test_conversion_to_meters(self) -> None:
        abp_plan = abpFloorPlan(abp_scale_m_per_px=0.05)
        assert abp_plan.abp_is_scaled
        assert abp_plan.abp_to_meters(20) == pytest.approx(1.0)
        assert abp_plan.abp_area_m2(abp__square(100)) == pytest.approx(25.0)

    def abp_test_unscaled_plan_refuses_conversion(self) -> None:
        abp_plan = abpFloorPlan()
        assert not abp_plan.abp_is_scaled
        with pytest.raises(ValueError, match="escala"):
            abp_plan.abp_to_meters(10)
        with pytest.raises(ValueError, match="escala"):
            abp_plan.abp_area_m2(abp__square(1))

    def abp_test_invalid_scale(self) -> None:
        with pytest.raises(ValueError, match="escala"):
            abpFloorPlan(abp_scale_m_per_px=0)

    def abp_test_plan_is_immutable_and_replaceable(self) -> None:
        abp_wall = abpWall(abpSegment(abpPoint(0, 0), abpPoint(100, 0)))
        abp_plan = abpFloorPlan(abp_walls=(abp_wall,))
        with pytest.raises(dataclasses.FrozenInstanceError):
            abp_plan.abp_level = 2
        abp_edited = dataclasses.replace(
            abp_plan, abp_rooms=(abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp__square(5)),)
        )
        assert abp_edited.abp_walls == abp_plan.abp_walls
        assert len(abp_edited.abp_rooms) == 1
        assert len(abp_plan.abp_rooms) == 0

    @pytest.mark.parametrize("abp_confidence", [-0.1, 1.5])
    def abp_test_confidence_range(self, abp_confidence: float) -> None:
        with pytest.raises(ValueError, match="confianza"):
            abpDoor(abpSegment(abpPoint(0, 0), abpPoint(1, 0)), abp_confidence=abp_confidence)


class abpTestPeopleAndScenario:
    def abp_test_profile_validation(self) -> None:
        with pytest.raises(ValueError, match="velocidad"):
            abpPersonProfile(
                "x",
                abp_max_speed_mps=0,
                abp_reaction_mean_s=1,
                abp_reaction_std_s=0,
                abp_radius_m=0.2,
            )
        with pytest.raises(ValueError, match="reacción"):
            abpPersonProfile(
                "x",
                abp_max_speed_mps=1,
                abp_reaction_mean_s=-1,
                abp_reaction_std_s=0,
                abp_radius_m=0.2,
            )
        with pytest.raises(ValueError, match="radio"):
            abpPersonProfile(
                "x",
                abp_max_speed_mps=1,
                abp_reaction_mean_s=1,
                abp_reaction_std_s=0,
                abp_radius_m=0,
            )

    def abp_test_occupancy_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="negativa"):
            abpOccupancy("Aula 1", "adulto", -1)

    def abp_test_scenario_total_and_seed(self) -> None:
        abp_scenario = abpScenario(
            "Base",
            abp_seed=42,
            abp_occupancies=(
                abpOccupancy("Aula 1", "niño", 30),
                abpOccupancy("Aula 1", "adulto", 1),
            ),
            abp_blocked_exits=frozenset({"Salida 2"}),
        )
        assert abp_scenario.abp_total_occupants == 31
        with pytest.raises(ValueError, match="semilla"):
            abpScenario("Mala", abp_seed=-1)

    def abp_test_real_drill_validation(self) -> None:
        abpRealDrill(date(2026, 5, 31), abp_participants=200, abp_total_time_s=180.0)
        with pytest.raises(ValueError, match="participante"):
            abpRealDrill(date(2026, 5, 31), abp_participants=0, abp_total_time_s=180.0)
        with pytest.raises(ValueError, match="tiempo total"):
            abpRealDrill(date(2026, 5, 31), abp_participants=10, abp_total_time_s=0)


class abpTestAgentArrays:
    def abp_test_empty_has_consistent_shapes(self) -> None:
        abp_agents = abpAgentArrays.abp_empty(5)
        assert len(abp_agents) == 5
        assert abp_agents.abp_position.shape == (5, 2)
        assert abp_agents.abp_evacuated_count == 0
        abp_agents.abp_status[:2] = abpAgentStatus.abp_EVACUATED
        assert abp_agents.abp_evacuated_count == 2

    def abp_test_inconsistent_shapes_are_rejected(self) -> None:
        abp_agents = abpAgentArrays.abp_empty(3)
        with pytest.raises(ValueError, match="radius"):
            dataclasses.replace(abp_agents, abp_radius=np.zeros(4))
        with pytest.raises(ValueError, match="position y velocity"):
            dataclasses.replace(abp_agents, abp_velocity=np.zeros((3, 3)))


class abpTestResults:
    def abp_test_norm_observation_must_cite_article(self) -> None:
        with pytest.raises(ValueError, match="artículo"):
            abpObservation(abpObservationType.abp_NORM, "Puerta angosta", "Ensanchar la puerta")
        abp_obs = abpObservation(
            abpObservationType.abp_NORM,
            "Puerta angosta",
            "Ensanchar la puerta",
            abp_norm="RNE A.130",
            abp_article="Art. X",
            abp_verified=False,
        )
        assert not abp_obs.abp_verified

    def abp_test_congestion_observation_without_article(self) -> None:
        abp_obs = abpObservation(
            abpObservationType.abp_CONGESTION, "Congestión", "Abrir segunda salida"
        )
        assert abp_obs.abp_article is None

    def abp_test_result_curve_shapes_must_match(self) -> None:
        with pytest.raises(ValueError, match="curva"):
            abpSimulationResult(
                abp_seed=1,
                abp_total_time_s=10.0,
                abp_time_per_exit_s=(),
                abp_curve_times_s=np.zeros(3),
                abp_curve_evacuated=np.zeros(2, dtype=np.int32),
                abp_density_map=np.zeros((2, 2)),
            )
