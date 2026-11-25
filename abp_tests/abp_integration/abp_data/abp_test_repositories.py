from __future__ import annotations

import dataclasses
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError

from abp_rutasegura.abp_data.abp_database import abp_plain_sqlite_engine, abpDatabase
from abp_rutasegura.abp_data.abp_models import (
    abpElementRecord,
    abpOccupancyRecord,
    abpPersonProfileRecord,
    abpRoomRecord,
)
from abp_rutasegura.abp_data.abp_repositories import abpNotFoundError
from abp_rutasegura.abp_domain import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObservation,
    abpObservationType,
    abpObstacle,
    abpOccupancy,
    abpPersonProfile,
    abpPoint,
    abpPolygon,
    abpProject,
    abpRealDrill,
    abpRoom,
    abpSafeZone,
    abpScenario,
    abpSegment,
    abpSimulationResult,
    abpStair,
    abpUseType,
    abpWall,
)


def abp__rect(abp_x: float, abp_y: float, abp_w: float, abp_h: float) -> abpPolygon:
    return abpPolygon(
        (
            abpPoint(abp_x, abp_y),
            abpPoint(abp_x + abp_w, abp_y),
            abpPoint(abp_x + abp_w, abp_y + abp_h),
            abpPoint(abp_x, abp_y + abp_h),
        )
    )


def abp__plan(abp_level: int = 0) -> abpFloorPlan:
    return abpFloorPlan(
        abp_level=abp_level,
        abp_image_path="planos/colegio.png",
        abp_scale_m_per_px=0.02,
        abp_walls=(
            abpWall(abpSegment(abpPoint(0, 0), abpPoint(500, 0))),
            abpWall(abpSegment(abpPoint(0, 0), abpPoint(0, 300)), abp_confidence=0.8),
        ),
        abp_doors=(abpDoor(abpSegment(abpPoint(100, 0), abpPoint(150, 0)), abp_confidence=0.9),),
        abp_exits=(
            abpExit(
                abpSegment(abpPoint(400, 300), abpPoint(460, 300)), abp_name="Salida principal"
            ),
        ),
        abp_stairs=(abpStair(abp__rect(450, 10, 40, 80), abp_connects_to_level=1),),
        abp_obstacles=(abpObstacle(abp__rect(200, 100, 20, 20)),),
        abp_safe_zones=(abpSafeZone(abp__rect(600, 0, 100, 100), abp_name="Patio"),),
        abp_rooms=(
            abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp__rect(0, 0, 250, 300)),
            abpRoom("Dirección", abpUseType.abp_OFFICE, abp__rect(250, 0, 250, 300)),
        ),
    )


def abp__project(abp_db: abpDatabase) -> int:
    with abp_db.abp_unit_of_work() as abp_uow:
        return abp_uow.abp_projects.abp_add(
            abpProject("I.E. San Martín", abpUseType.abp_EDUCATION, "Av. Lima 123")
        )


class abpTestProjects:
    def abp_test_crud(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_project = abp_uow.abp_projects.abp_get(abp_pid)
            assert abp_project.abp_name == "I.E. San Martín"
            assert abp_project.abp_use is abpUseType.abp_EDUCATION
            assert isinstance(abp_project.abp_created_at, datetime)
            abp_uow.abp_projects.abp_update(
                abp_pid, dataclasses.replace(abp_project, abp_name="Colegio San Martín")
            )
        with abp_db.abp_unit_of_work() as abp_uow:
            assert [abp_p.abp_name for _, abp_p in abp_uow.abp_projects.abp_list_all()] == [
                "Colegio San Martín"
            ]
            abp_uow.abp_projects.abp_delete(abp_pid)
        with abp_db.abp_unit_of_work() as abp_uow, pytest.raises(abpNotFoundError):
            abp_uow.abp_projects.abp_get(abp_pid)

    def abp_test_transaction_rolls_back_on_error(self, abp_db: abpDatabase) -> None:
        def abp_add_then_fail() -> None:
            with abp_db.abp_unit_of_work() as abp_uow:
                abp_uow.abp_projects.abp_add(abpProject("Temporal", abpUseType.abp_COMMERCE))
                raise RuntimeError("falla a mitad")

        with pytest.raises(RuntimeError, match="falla a mitad"):
            abp_add_then_fail()
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_projects.abp_list_all() == []


class abpTestFloors:
    def abp_test_round_trip_preserves_plan(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_plan = abp__plan()
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp_plan)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_floors.abp_get(abp_pid, 0) == abp_plan
            assert abp_uow.abp_floors.abp_levels(abp_pid) == [0]

    def abp_test_widths_and_areas_in_meters(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_rooms = abp_uow.abp_session.scalars(
                select(abpRoomRecord).order_by(abpRoomRecord.abp_id)
            ).all()
            assert abp_rooms[0].abp_area_m2 == pytest.approx(250 * 300 * 0.02**2)
            abp_rows = abp_uow.abp_session.execute(
                select(abpElementRecord.abp_kind, abpElementRecord.abp_width_m).where(
                    abpElementRecord.abp_kind.in_(["puerta", "salida"])
                )
            )
            abp_widths = {abp_kind: abp_width for abp_kind, abp_width in abp_rows}
            assert abp_widths["puerta"] == pytest.approx(1.0)
            assert abp_widths["salida"] == pytest.approx(1.2)

    def abp_test_unscaled_plan_has_no_widths(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(
                abp_pid, dataclasses.replace(abp__plan(), abp_scale_m_per_px=None)
            )
            abp_rooms = abp_uow.abp_session.scalars(select(abpRoomRecord)).all()
            assert all(abp_r.abp_area_m2 is None for abp_r in abp_rooms)

    def abp_test_resave_keeps_occupancies_of_unchanged_rooms(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            abp_uow.abp_scenarios.abp_save(
                abp_pid,
                abpScenario(
                    "Base",
                    abp_seed=7,
                    abp_occupancies=(
                        abpOccupancy("Aula 1", "niño", 30),
                        abpOccupancy("Dirección", "adulto", 2),
                    ),
                ),
            )
        abp_edited = dataclasses.replace(
            abp__plan(),
            abp_rooms=(abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp__rect(0, 0, 260, 300)),),
        )
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp_edited)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_scenario = abp_uow.abp_scenarios.abp_get(
                abp_uow.abp_scenarios.abp_find_id(abp_pid, "Base")
            )
            assert abp_scenario.abp_occupancies == (abpOccupancy("Aula 1", "niño", 30),)
            assert abp_uow.abp_floors.abp_get(abp_pid, 0).abp_rooms == abp_edited.abp_rooms

    def abp_test_duplicate_room_names_rejected(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_room = abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp__rect(0, 0, 10, 10))
        with abp_db.abp_unit_of_work() as abp_uow, pytest.raises(ValueError, match="mismo nombre"):
            abp_uow.abp_floors.abp_save(abp_pid, abpFloorPlan(abp_rooms=(abp_room, abp_room)))

    def abp_test_missing_floor(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow, pytest.raises(abpNotFoundError):
            abp_uow.abp_floors.abp_get(abp_pid, 3)

    def abp_test_delete_project_cascades(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            abp_uow.abp_scenarios.abp_save(
                abp_pid, abpScenario("Base", 1, (abpOccupancy("Aula 1", "niño", 5),))
            )
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_projects.abp_delete(abp_pid)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_session.scalar(select(func.count()).select_from(abpRoomRecord)) == 0
            assert (
                abp_uow.abp_session.scalar(select(func.count()).select_from(abpOccupancyRecord))
                == 0
            )


class abpTestProfiles:
    def abp_test_defaults_are_seeded(self, abp_db: abpDatabase) -> None:
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_profiles.abp_get("adulto").abp_max_speed_mps > 0
            assert len(abp_uow.abp_profiles.abp_list_all()) == 3

    def abp_test_user_edits_survive_reseeding(self, tmp_path: Path) -> None:
        abp_path = tmp_path / "db.sqlite"
        abp_db = abpDatabase.abp_open(abp_path)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_adult = abp_uow.abp_profiles.abp_get("adulto")
            abp_uow.abp_profiles.abp_save(dataclasses.replace(abp_adult, abp_max_speed_mps=1.1))
        abp_db.abp_close()
        abp_db = abpDatabase.abp_open(abp_path)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_profiles.abp_get("adulto").abp_max_speed_mps == pytest.approx(1.1)
        abp_db.abp_close()

    def abp_test_custom_profile_and_missing(self, abp_db: abpDatabase) -> None:
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_profiles.abp_save(abpPersonProfile("docente", 1.3, 15, 5, 0.25))
            assert abp_uow.abp_profiles.abp_get("docente").abp_reaction_mean_s == 15
            with pytest.raises(abpNotFoundError):
                abp_uow.abp_profiles.abp_get("astronauta")

    def abp_test_profile_in_use_cannot_be_deleted(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            abp_uow.abp_scenarios.abp_save(
                abp_pid, abpScenario("Base", 1, (abpOccupancy("Aula 1", "adulto", 5),))
            )
        with pytest.raises(IntegrityError), abp_db.abp_session() as abp_session:
            abp_session.execute(
                delete(abpPersonProfileRecord).where(abpPersonProfileRecord.abp_name == "adulto")
            )


class abpTestScenarios:
    def abp_test_round_trip_and_replace(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_scenario = abpScenario(
            "Salida bloqueada",
            abp_seed=123,
            abp_occupancies=(
                abpOccupancy("Aula 1", "niño", 28),
                abpOccupancy("Aula 1", "adulto", 1),
            ),
            abp_blocked_exits=frozenset({"Salida principal"}),
        )
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            abp_sid = abp_uow.abp_scenarios.abp_save(abp_pid, abp_scenario)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_scenarios.abp_get(abp_sid) == abp_scenario
            abp_changed = dataclasses.replace(
                abp_scenario, abp_seed=5, abp_occupancies=abp_scenario.abp_occupancies[:1]
            )
            assert abp_uow.abp_scenarios.abp_save(abp_pid, abp_changed) == abp_sid
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_scenarios.abp_get(abp_sid) == abp_changed
            assert [abp_s.abp_name for _, abp_s in abp_uow.abp_scenarios.abp_list_all(abp_pid)] == [
                "Salida bloqueada"
            ]
            abp_uow.abp_scenarios.abp_delete(abp_sid)
            assert abp_uow.abp_scenarios.abp_list_all(abp_pid) == []

    def abp_test_multi_floor_rooms_with_same_name(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_scenario = abpScenario(
            "Dos pisos",
            abp_seed=1,
            abp_occupancies=(
                abpOccupancy("Aula 1", "niño", 10),
                abpOccupancy("Aula 1", "niño", 20, abp_level=1),
            ),
        )
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan(0))
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan(1))
            abp_sid = abp_uow.abp_scenarios.abp_save(abp_pid, abp_scenario)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert abp_uow.abp_scenarios.abp_get(abp_sid) == abp_scenario
            assert abp_uow.abp_floors.abp_levels(abp_pid) == [0, 1]

    @pytest.mark.parametrize(
        ("abp_occupancy", "abp_message"),
        [
            (abpOccupancy("Aula 9", "niño", 1), "ambiente"),
            (abpOccupancy("Aula 1", "astronauta", 1), "perfil"),
        ],
    )
    def abp_test_unknown_references(
        self, abp_db: abpDatabase, abp_occupancy: abpOccupancy, abp_message: str
    ) -> None:
        abp_pid = abp__project(abp_db)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            with pytest.raises(ValueError, match=abp_message):
                abp_uow.abp_scenarios.abp_save(abp_pid, abpScenario("X", 1, (abp_occupancy,)))


class abpTestSimulationsAndDrills:
    def abp_test_simulation_summary_and_observations(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_result = abpSimulationResult(
            abp_seed=42,
            abp_total_time_s=183.5,
            abp_time_per_exit_s=(("Salida principal", 183.5), ("Salida 2", 120.0)),
            abp_curve_times_s=np.array([0.0, 1.0]),
            abp_curve_evacuated=np.array([0, 3], dtype=np.int32),
            abp_density_map=np.zeros((2, 2)),
            abp_trajectories_path="trayectorias/sim_1.npz",
        )
        abp_observations = [
            abpObservation(
                abpObservationType.abp_NORM,
                "La puerta del Aula 1 mide menos que el mínimo.",
                "Ensanchar la puerta.",
                abp_location=abpPoint(3.0, 0.5),
                abp_norm="RNE A.130",
                abp_article="Art. (por verificar)",
                abp_verified=False,
            ),
            abpObservation(abpObservationType.abp_CONGESTION, "Congestión en pasillo", "Señalizar"),
        ]
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_floors.abp_save(abp_pid, abp__plan())
            abp_sid = abp_uow.abp_scenarios.abp_save(abp_pid, abpScenario("Base", 42))
            abp_sim_id = abp_uow.abp_simulations.abp_add(abp_sid, abp_result, abp_observations)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_summary = abp_uow.abp_simulations.abp_get(abp_sim_id)
            assert abp_summary.abp_total_time_s == pytest.approx(183.5)
            assert abp_summary.abp_time_per_exit_s == abp_result.abp_time_per_exit_s
            assert abp_summary.abp_seed == 42
            assert abp_uow.abp_simulations.abp_observations(abp_sim_id) == abp_observations
            assert [abp_i for abp_i, _ in abp_uow.abp_simulations.abp_list_all(abp_sid)] == [
                abp_sim_id
            ]

    def abp_test_real_drills(self, abp_db: abpDatabase) -> None:
        abp_pid = abp__project(abp_db)
        abp_later = abpRealDrill(date(2026, 10, 8), 310, 240.0, (("Salida principal", 240.0),))
        abp_earlier = abpRealDrill(date(2026, 5, 31), 300, 260.0)
        with abp_db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_drills.abp_add(abp_pid, abp_later)
            abp_first = abp_uow.abp_drills.abp_add(abp_pid, abp_earlier)
        with abp_db.abp_unit_of_work() as abp_uow:
            assert [abp_d for _, abp_d in abp_uow.abp_drills.abp_list_all(abp_pid)] == [
                abp_earlier,
                abp_later,
            ]
            abp_uow.abp_drills.abp_delete(abp_first)
            assert [abp_d for _, abp_d in abp_uow.abp_drills.abp_list_all(abp_pid)] == [abp_later]


def abp_test_custom_engine_factory_is_used(tmp_path: Path) -> None:
    abp_calls: list[Path] = []

    def abp_factory(abp_path: Path) -> Engine:
        abp_calls.append(abp_path)
        return abp_plain_sqlite_engine(abp_path)

    abp_db = abpDatabase.abp_open(tmp_path / "x.db", abp_engine_factory=abp_factory)
    abp_db.abp_close()
    assert abp_calls == [tmp_path / "x.db"]
