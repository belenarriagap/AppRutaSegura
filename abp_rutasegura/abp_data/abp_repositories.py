from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from abp_rutasegura.abp_data.abp_geojson import (
    abp_feature_dumps,
    abp_feature_loads,
    abp_geometry_dumps,
    abp_geometry_loads,
    abp_point_from_geojson,
    abp_point_to_geojson,
    abp_polygon_from_geojson,
    abp_polygon_to_geojson,
    abp_segment_from_geojson,
    abp_segment_to_geojson,
)
from abp_rutasegura.abp_data.abp_models import (
    abpElementRecord,
    abpFloorRecord,
    abpObservationRecord,
    abpOccupancyRecord,
    abpPersonProfileRecord,
    abpProjectRecord,
    abpRealDrillRecord,
    abpRoomRecord,
    abpRuleVerificationRecord,
    abpScenarioRecord,
    abpSimulationRecord,
)
from abp_rutasegura.abp_domain.abp_enums import (
    abpElementType,
    abpObservationType,
    abpSignKind,
    abpStairUse,
    abpUseType,
)
from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_norms import abpRuleVerification
from abp_rutasegura.abp_domain.abp_people import abpOccupancy, abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpRoom,
    abpSafeZone,
    abpSign,
    abpStair,
    abpWall,
)
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_results import (
    abpObservation,
    abpRunStatistics,
    abpSimulationResult,
    abpSimulationSummary,
)
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute, abpRealDrill, abpScenario


class abpNotFoundError(LookupError):
    pass


def abp__get[abp_T](
    abp_session: Session, abp_model: type[abp_T], abp_record_id: int, abp_label: str
) -> abp_T:
    abp_record = abp_session.get(abp_model, abp_record_id)
    if abp_record is None:
        raise abpNotFoundError(f"No existe {abp_label} con id {abp_record_id}.")
    return abp_record


class abpProjectRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp_add(self, abp_project: abpProject) -> int:
        abp_record = abpProjectRecord(
            abp_name=abp_project.abp_name,
            abp_use_type=abp_project.abp_use,
            abp_address=abp_project.abp_address,
        )
        if abp_project.abp_created_at is not None:
            abp_record.abp_created_at = abp_project.abp_created_at
        self.abp__copy_details(abp_record, abp_project)
        self.abp__s.add(abp_record)
        self.abp__s.flush()
        return abp_record.abp_id

    def abp_get(self, abp_project_id: int) -> abpProject:
        return self.abp__to_domain(
            abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto")
        )

    def abp_list_all(self) -> list[tuple[int, abpProject]]:
        abp_records = self.abp__s.scalars(
            select(abpProjectRecord).order_by(
                abpProjectRecord.abp_created_at.desc(), abpProjectRecord.abp_id.desc()
            )
        )
        return [(abp_r.abp_id, self.abp__to_domain(abp_r)) for abp_r in abp_records]

    def abp_update(self, abp_project_id: int, abp_project: abpProject) -> None:
        abp_record = abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto")
        abp_record.abp_name = abp_project.abp_name
        abp_record.abp_use_type = abp_project.abp_use
        abp_record.abp_address = abp_project.abp_address
        self.abp__copy_details(abp_record, abp_project)
        self.abp__s.flush()

    @staticmethod
    def abp__copy_details(abp_record: abpProjectRecord, abp_project: abpProject) -> None:
        abp_record.abp_district = abp_project.abp_district
        abp_record.abp_province = abp_project.abp_province
        abp_record.abp_department = abp_project.abp_department
        abp_record.abp_responsible = abp_project.abp_responsible
        abp_record.abp_responsible_role = abp_project.abp_responsible_role
        abp_record.abp_phone = abp_project.abp_phone
        abp_record.abp_email = abp_project.abp_email
        abp_record.abp_schedule = abp_project.abp_schedule
        abp_record.abp_notes = abp_project.abp_notes
        abp_record.abp_logo_path = abp_project.abp_logo_path

    def abp_delete(self, abp_project_id: int) -> None:
        self.abp__s.delete(abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto"))
        self.abp__s.flush()

    @staticmethod
    def abp__to_domain(abp_record: abpProjectRecord) -> abpProject:
        return abpProject(
            abp_name=abp_record.abp_name,
            abp_use=abpUseType(abp_record.abp_use_type),
            abp_address=abp_record.abp_address,
            abp_created_at=abp_record.abp_created_at,
            abp_district=abp_record.abp_district or "",
            abp_province=abp_record.abp_province or "",
            abp_department=abp_record.abp_department or "",
            abp_responsible=abp_record.abp_responsible or "",
            abp_responsible_role=abp_record.abp_responsible_role or "",
            abp_phone=abp_record.abp_phone or "",
            abp_email=abp_record.abp_email or "",
            abp_schedule=abp_record.abp_schedule or "",
            abp_notes=abp_record.abp_notes or "",
            abp_logo_path=abp_record.abp_logo_path,
        )


class abpFloorRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp__find(self, abp_project_id: int, abp_level: int) -> abpFloorRecord | None:
        return self.abp__s.scalars(
            select(abpFloorRecord).where(
                abpFloorRecord.abp_project_id == abp_project_id,
                abpFloorRecord.abp_level == abp_level,
            )
        ).one_or_none()

    def abp_save(self, abp_project_id: int, abp_plan: abpFloorPlan) -> int:
        abp_names = [abp_room.abp_name for abp_room in abp_plan.abp_rooms]
        if len(abp_names) != len(set(abp_names)):
            raise ValueError("Hay ambientes con el mismo nombre en este piso.")
        abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto")

        abp_floor = self.abp__find(abp_project_id, abp_plan.abp_level)
        if abp_floor is None:
            abp_floor = abpFloorRecord(abp_project_id=abp_project_id, abp_level=abp_plan.abp_level)
            self.abp__s.add(abp_floor)
        abp_floor.abp_original_image = abp_plan.abp_image_path
        abp_floor.abp_scale_m_per_px = abp_plan.abp_scale_m_per_px

        abp_floor.abp_elements.clear()
        abp_floor.abp_elements.extend(self.abp__elements_to_records(abp_plan))

        abp_existing = {abp_room.abp_name: abp_room for abp_room in abp_floor.abp_rooms}
        for abp_room in abp_plan.abp_rooms:
            abp_record = abp_existing.pop(abp_room.abp_name, None)
            if abp_record is None:
                abp_record = abpRoomRecord(abp_name=abp_room.abp_name)
                abp_floor.abp_rooms.append(abp_record)
            abp_record.abp_use = abp_room.abp_use
            abp_record.abp_category = abp_room.abp_category
            abp_record.abp_exit_name = abp_room.abp_exit_name
            abp_record.abp_polygon = abp_geometry_dumps(abp_polygon_to_geojson(abp_room.abp_area))
            abp_record.abp_area_m2 = (
                abp_plan.abp_area_m2(abp_room.abp_area) if abp_plan.abp_is_scaled else None
            )
        for abp_removed in abp_existing.values():
            abp_floor.abp_rooms.remove(abp_removed)

        self.abp__s.flush()
        return abp_floor.abp_id

    def abp_get(self, abp_project_id: int, abp_level: int) -> abpFloorPlan:
        abp_floor = self.abp__find(abp_project_id, abp_level)
        if abp_floor is None:
            raise abpNotFoundError(f"El proyecto {abp_project_id} no tiene el piso {abp_level}.")
        return self.abp__to_domain(abp_floor)

    def abp_levels(self, abp_project_id: int) -> list[int]:
        return list(
            self.abp__s.scalars(
                select(abpFloorRecord.abp_level)
                .where(abpFloorRecord.abp_project_id == abp_project_id)
                .order_by(abpFloorRecord.abp_level)
            )
        )

    def abp_delete(self, abp_project_id: int, abp_level: int) -> None:
        abp_floor = self.abp__find(abp_project_id, abp_level)
        if abp_floor is None:
            raise abpNotFoundError(f"El proyecto {abp_project_id} no tiene el piso {abp_level}.")
        self.abp__s.delete(abp_floor)
        self.abp__s.flush()

    @staticmethod
    def abp__elements_to_records(abp_plan: abpFloorPlan) -> list[abpElementRecord]:
        def abp_width(abp_length_px: float) -> float | None:
            return abp_plan.abp_to_meters(abp_length_px) if abp_plan.abp_is_scaled else None

        abp_records: list[abpElementRecord] = []

        def abp_add(
            abp_kind: abpElementType,
            abp_geometry: dict[str, object],
            abp_props: dict[str, object],
            abp_width_m: float | None = None,
        ) -> None:
            abp_records.append(
                abpElementRecord(
                    abp_kind=abp_kind,
                    abp_geometry=abp_feature_dumps(abp_geometry, abp_props),
                    abp_width_m=abp_width_m,
                )
            )

        for abp_wall in abp_plan.abp_walls:
            abp_add(
                abpElementType.abp_WALL,
                abp_segment_to_geojson(abp_wall.abp_segment),
                {"confianza": abp_wall.abp_confidence},
            )
        for abp_door in abp_plan.abp_doors:
            abp_add(
                abpElementType.abp_DOOR,
                abp_segment_to_geojson(abp_door.abp_segment),
                {"confianza": abp_door.abp_confidence},
                abp_width(abp_door.abp_segment.abp_length),
            )
        for abp_exit_ in abp_plan.abp_exits:
            abp_add(
                abpElementType.abp_EXIT,
                abp_segment_to_geojson(abp_exit_.abp_segment),
                {"nombre": abp_exit_.abp_name, "confirmada": abp_exit_.abp_confirmed},
                abp_width(abp_exit_.abp_segment.abp_length),
            )
        for abp_stair in abp_plan.abp_stairs:
            abp_add(
                abpElementType.abp_STAIR,
                abp_polygon_to_geojson(abp_stair.abp_area),
                {
                    "conecta_con_nivel": abp_stair.abp_connects_to_level,
                    "confirmada": abp_stair.abp_confirmed,
                    "nombre": abp_stair.abp_name,
                    "uso": abp_stair.abp_use.value,
                    "entrada": [abp_stair.abp_entry.abp_x, abp_stair.abp_entry.abp_y]
                    if abp_stair.abp_entry is not None
                    else None,
                    "lleva_a": abp_stair.abp_leads_to,
                },
            )
        for abp_obstacle in abp_plan.abp_obstacles:
            abp_add(
                abpElementType.abp_OBSTACLE,
                abp_polygon_to_geojson(abp_obstacle.abp_area),
                {"confirmado": abp_obstacle.abp_confirmed, "nombre": abp_obstacle.abp_name},
            )
        for abp_zone in abp_plan.abp_safe_zones:
            abp_add(
                abpElementType.abp_SAFE_ZONE,
                abp_polygon_to_geojson(abp_zone.abp_area),
                {"nombre": abp_zone.abp_name},
            )
        for abp_sign in abp_plan.abp_signs:
            abp_add(
                abpElementType.abp_SIGN,
                {
                    "type": "Point",
                    "coordinates": [abp_sign.abp_position.abp_x, abp_sign.abp_position.abp_y],
                },
                {
                    "senal": abp_sign.abp_kind.value,
                    "giro": abp_sign.abp_rotation_deg,
                    "texto": abp_sign.abp_text,
                },
            )
        return abp_records

    @staticmethod
    def abp__to_domain(abp_floor: abpFloorRecord) -> abpFloorPlan:
        abp_walls: list[abpWall] = []
        abp_doors: list[abpDoor] = []
        abp_exits: list[abpExit] = []
        abp_stairs: list[abpStair] = []
        abp_obstacles: list[abpObstacle] = []
        abp_safe_zones: list[abpSafeZone] = []
        abp_signs: list[abpSign] = []
        for abp_element in abp_floor.abp_elements:
            abp_geometry, abp_props = abp_feature_loads(abp_element.abp_geometry)
            match abpElementType(abp_element.abp_kind):
                case abpElementType.abp_WALL:
                    abp_walls.append(
                        abpWall(
                            abp_segment_from_geojson(abp_geometry),
                            float(abp_props.get("confianza", 1.0)),
                        )
                    )
                case abpElementType.abp_DOOR:
                    abp_doors.append(
                        abpDoor(
                            abp_segment_from_geojson(abp_geometry),
                            float(abp_props.get("confianza", 1.0)),
                        )
                    )
                case abpElementType.abp_EXIT:
                    abp_exits.append(
                        abpExit(
                            abp_segment_from_geojson(abp_geometry),
                            str(abp_props.get("nombre", "")),
                            bool(abp_props.get("confirmada", True)),
                        )
                    )
                case abpElementType.abp_STAIR:
                    abp_level = abp_props.get("conecta_con_nivel")
                    abp_stairs.append(
                        abpStair(
                            abp_polygon_from_geojson(abp_geometry),
                            None if abp_level is None else int(abp_level),
                            bool(abp_props.get("confirmada", True)),
                            str(abp_props.get("nombre", "")),
                            abpStairUse(abp_props.get("uso", abpStairUse.abp_AUTO)),
                            abpPoint(*abp_props["entrada"]) if abp_props.get("entrada") else None,
                            str(abp_props.get("lleva_a", "")),
                        )
                    )
                case abpElementType.abp_OBSTACLE:
                    abp_obstacles.append(
                        abpObstacle(
                            abp_polygon_from_geojson(abp_geometry),
                            bool(abp_props.get("confirmado", True)),
                            str(abp_props.get("nombre", "")),
                        )
                    )
                case abpElementType.abp_SAFE_ZONE:
                    abp_safe_zones.append(
                        abpSafeZone(
                            abp_polygon_from_geojson(abp_geometry), str(abp_props.get("nombre", ""))
                        )
                    )
                case abpElementType.abp_SIGN:
                    abp_x, abp_y = abp_geometry["coordinates"]
                    abp_signs.append(
                        abpSign(
                            abpSignKind(str(abp_props["senal"])),
                            abpPoint(float(abp_x), float(abp_y)),
                            float(abp_props.get("giro", 0.0)),
                            str(abp_props.get("texto", "")),
                        )
                    )
        abp_rooms = tuple(
            abpRoom(
                abp_r.abp_name,
                abpUseType(abp_r.abp_use),
                abp_polygon_from_geojson(abp_geometry_loads(abp_r.abp_polygon)),
                abp_r.abp_category,
                abp_r.abp_exit_name,
            )
            for abp_r in abp_floor.abp_rooms
        )
        return abpFloorPlan(
            abp_level=abp_floor.abp_level,
            abp_image_path=abp_floor.abp_original_image,
            abp_scale_m_per_px=abp_floor.abp_scale_m_per_px,
            abp_walls=tuple(abp_walls),
            abp_doors=tuple(abp_doors),
            abp_exits=tuple(abp_exits),
            abp_stairs=tuple(abp_stairs),
            abp_obstacles=tuple(abp_obstacles),
            abp_safe_zones=tuple(abp_safe_zones),
            abp_rooms=abp_rooms,
            abp_signs=tuple(abp_signs),
        )


class abpProfileRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp__find(self, abp_name: str) -> abpPersonProfileRecord | None:
        return self.abp__s.scalars(
            select(abpPersonProfileRecord).where(abpPersonProfileRecord.abp_name == abp_name)
        ).one_or_none()

    def abp_list_all(self) -> list[abpPersonProfile]:
        abp_records = self.abp__s.scalars(
            select(abpPersonProfileRecord).order_by(abpPersonProfileRecord.abp_id)
        )
        return [self.abp__to_domain(abp_r) for abp_r in abp_records]

    def abp_get(self, abp_name: str) -> abpPersonProfile:
        abp_record = self.abp__find(abp_name)
        if abp_record is None:
            raise abpNotFoundError(f"No existe el perfil «{abp_name}».")
        return self.abp__to_domain(abp_record)

    def abp_save(self, abp_profile: abpPersonProfile) -> int:
        abp_record = self.abp__find(abp_profile.abp_name)
        if abp_record is None:
            abp_record = abpPersonProfileRecord(abp_name=abp_profile.abp_name)
            self.abp__s.add(abp_record)
        abp_record.abp_max_speed_mps = abp_profile.abp_max_speed_mps
        abp_record.abp_reaction_mean_s = abp_profile.abp_reaction_mean_s
        abp_record.abp_reaction_std_s = abp_profile.abp_reaction_std_s
        abp_record.abp_radius_m = abp_profile.abp_radius_m
        self.abp__s.flush()
        return abp_record.abp_id

    def abp_ensure(self, abp_profiles: Iterable[abpPersonProfile]) -> int:
        abp_added = 0
        for abp_profile in abp_profiles:
            if self.abp__find(abp_profile.abp_name) is None:
                self.abp_save(abp_profile)
                abp_added += 1
        return abp_added

    @staticmethod
    def abp__to_domain(abp_record: abpPersonProfileRecord) -> abpPersonProfile:
        return abpPersonProfile(
            abp_name=abp_record.abp_name,
            abp_max_speed_mps=abp_record.abp_max_speed_mps,
            abp_reaction_mean_s=abp_record.abp_reaction_mean_s,
            abp_reaction_std_s=abp_record.abp_reaction_std_s,
            abp_radius_m=abp_record.abp_radius_m,
        )


def abp__route_to_json(abp_route: abpManualRoute) -> dict[str, Any]:
    return {
        "origen": abp_route.abp_source,
        "nivel": abp_route.abp_level,
        "salida": abp_route.abp_exit_name,
        "puntos": [[abp_p.abp_x, abp_p.abp_y] for abp_p in abp_route.abp_waypoints],
        "escalera": abp_route.abp_from_stair,
    }


def abp__route_from_json(abp_data: dict[str, Any]) -> abpManualRoute:
    return abpManualRoute(
        abp_source=str(abp_data["origen"]),
        abp_level=int(abp_data["nivel"]),
        abp_exit_name=str(abp_data.get("salida", "")),
        abp_waypoints=tuple(
            abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_data.get("puntos", [])
        ),
        abp_from_stair=bool(abp_data.get("escalera", False)),
    )


class abpScenarioRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp_save(self, abp_project_id: int, abp_scenario: abpScenario) -> int:
        abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto")
        abp_record = self.abp__s.scalars(
            select(abpScenarioRecord).where(
                abpScenarioRecord.abp_project_id == abp_project_id,
                abpScenarioRecord.abp_name == abp_scenario.abp_name,
            )
        ).one_or_none()
        if abp_record is None:
            abp_record = abpScenarioRecord(
                abp_project_id=abp_project_id, abp_name=abp_scenario.abp_name
            )
            self.abp__s.add(abp_record)
        abp_record.abp_seed = abp_scenario.abp_seed
        abp_record.abp_blocked_exits = sorted(abp_scenario.abp_blocked_exits)
        abp_record.abp_description = abp_scenario.abp_description
        abp_record.abp_reaction_factor = abp_scenario.abp_reaction_factor
        abp_record.abp_speed_factor = abp_scenario.abp_speed_factor
        abp_record.abp_runs = abp_scenario.abp_runs
        abp_record.abp_routes = [abp__route_to_json(abp_r) for abp_r in abp_scenario.abp_routes]
        abp_record.abp_occupancies.clear()
        self.abp__s.flush()
        abp_record.abp_occupancies.extend(
            self.abp__occupancy_records(abp_project_id, abp_scenario.abp_occupancies)
        )
        self.abp__s.flush()
        return abp_record.abp_id

    def abp_get(self, abp_scenario_id: int) -> abpScenario:
        return self.abp__to_domain(
            abp__get(self.abp__s, abpScenarioRecord, abp_scenario_id, "el escenario")
        )

    def abp_find_id(self, abp_project_id: int, abp_name: str) -> int:
        abp_scenario_id = self.abp__s.scalars(
            select(abpScenarioRecord.abp_id).where(
                abpScenarioRecord.abp_project_id == abp_project_id,
                abpScenarioRecord.abp_name == abp_name,
            )
        ).one_or_none()
        if abp_scenario_id is None:
            raise abpNotFoundError(f"No existe el escenario «{abp_name}».")
        return abp_scenario_id

    def abp_list_all(self, abp_project_id: int) -> list[tuple[int, abpScenario]]:
        abp_records = self.abp__s.scalars(
            select(abpScenarioRecord)
            .where(abpScenarioRecord.abp_project_id == abp_project_id)
            .order_by(abpScenarioRecord.abp_id)
        )
        return [(abp_r.abp_id, self.abp__to_domain(abp_r)) for abp_r in abp_records]

    def abp_rename(self, abp_scenario_id: int, abp_name: str) -> None:
        abp__get(
            self.abp__s, abpScenarioRecord, abp_scenario_id, "el escenario"
        ).abp_name = abp_name
        self.abp__s.flush()

    def abp_delete(self, abp_scenario_id: int) -> None:
        self.abp__s.delete(
            abp__get(self.abp__s, abpScenarioRecord, abp_scenario_id, "el escenario")
        )
        self.abp__s.flush()

    def abp__occupancy_records(
        self, abp_project_id: int, abp_occupancies: Sequence[abpOccupancy]
    ) -> list[abpOccupancyRecord]:
        abp_rooms = {
            (abp_level, abp_name): abp_room_id
            for abp_room_id, abp_name, abp_level in self.abp__s.execute(
                select(abpRoomRecord.abp_id, abpRoomRecord.abp_name, abpFloorRecord.abp_level)
                .join(abpFloorRecord)
                .where(abpFloorRecord.abp_project_id == abp_project_id)
            )
        }
        abp_profiles = {
            abp_name: abp_profile_id
            for abp_name, abp_profile_id in self.abp__s.execute(
                select(abpPersonProfileRecord.abp_name, abpPersonProfileRecord.abp_id)
            )
        }
        abp_records: list[abpOccupancyRecord] = []
        for abp_occ in abp_occupancies:
            abp_room_id = abp_rooms.get((abp_occ.abp_level, abp_occ.abp_room_name))
            if abp_room_id is None:
                raise ValueError(
                    f"No existe el ambiente «{abp_occ.abp_room_name}» en el piso {abp_occ.abp_level}."
                )
            abp_profile_id = abp_profiles.get(abp_occ.abp_profile_name)
            if abp_profile_id is None:
                raise ValueError(f"No existe el perfil «{abp_occ.abp_profile_name}».")
            abp_records.append(
                abpOccupancyRecord(
                    abp_room_id=abp_room_id,
                    abp_profile_id=abp_profile_id,
                    abp_count=abp_occ.abp_count,
                )
            )
        return abp_records

    @staticmethod
    def abp__to_domain(abp_record: abpScenarioRecord) -> abpScenario:
        abp_occupancies = tuple(
            abpOccupancy(
                abp_room_name=abp_o.abp_room.abp_name,
                abp_profile_name=abp_o.abp_profile.abp_name,
                abp_count=abp_o.abp_count,
                abp_level=abp_o.abp_room.abp_floor.abp_level,
            )
            for abp_o in abp_record.abp_occupancies
        )
        return abpScenario(
            abp_name=abp_record.abp_name,
            abp_seed=abp_record.abp_seed,
            abp_occupancies=abp_occupancies,
            abp_blocked_exits=frozenset(abp_record.abp_blocked_exits),
            abp_description=abp_record.abp_description or "",
            abp_reaction_factor=abp_record.abp_reaction_factor or 1.0,
            abp_speed_factor=abp_record.abp_speed_factor or 1.0,
            abp_runs=abp_record.abp_runs or 1,
            abp_routes=tuple(abp__route_from_json(abp_r) for abp_r in abp_record.abp_routes or ()),
        )


def abp__statistics_to_json(abp_stats: abpRunStatistics) -> dict[str, Any]:
    return {
        "semillas": list(abp_stats.abp_seeds),
        "tiempos_totales_s": list(abp_stats.abp_total_times_s),
        "tiempos_90_s": list(abp_stats.abp_ninety_times_s),
        "completas": list(abp_stats.abp_completed),
        "semilla_representativa": abp_stats.abp_representative_seed,
    }


def abp__statistics_from_json(abp_data: dict[str, Any] | None) -> abpRunStatistics | None:
    if not abp_data:
        return None
    return abpRunStatistics(
        abp_seeds=tuple(int(abp_s) for abp_s in abp_data["semillas"]),
        abp_total_times_s=tuple(float(abp_t) for abp_t in abp_data["tiempos_totales_s"]),
        abp_ninety_times_s=tuple(
            None if abp_t is None else float(abp_t) for abp_t in abp_data["tiempos_90_s"]
        ),
        abp_completed=tuple(bool(abp_c) for abp_c in abp_data["completas"]),
        abp_representative_seed=int(abp_data["semilla_representativa"]),
    )


class abpSimulationRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp_add(
        self,
        abp_scenario_id: int,
        abp_result: abpSimulationResult,
        abp_observations: Sequence[abpObservation] = (),
        abp_statistics: abpRunStatistics | None = None,
        abp_fingerprint: str = "",
    ) -> int:
        abp__get(self.abp__s, abpScenarioRecord, abp_scenario_id, "el escenario")
        abp_record = abpSimulationRecord(
            abp_scenario_id=abp_scenario_id,
            abp_seed=abp_result.abp_seed,
            abp_total_time_s=abp_result.abp_total_time_s,
            abp_time_per_exit_s=dict(abp_result.abp_time_per_exit_s),
            abp_trajectories_path=abp_result.abp_trajectories_path,
            abp_statistics=None
            if abp_statistics is None
            else abp__statistics_to_json(abp_statistics),
            abp_fingerprint=abp_fingerprint,
        )
        abp_record.abp_observations.extend(
            self.abp__observation_record(abp_o) for abp_o in abp_observations
        )
        self.abp__s.add(abp_record)
        self.abp__s.flush()
        return abp_record.abp_id

    def abp_get(self, abp_simulation_id: int) -> abpSimulationSummary:
        return self.abp__summary(
            abp__get(self.abp__s, abpSimulationRecord, abp_simulation_id, "la simulación")
        )

    def abp_list_all(self, abp_scenario_id: int) -> list[tuple[int, abpSimulationSummary]]:
        abp_records = self.abp__s.scalars(
            select(abpSimulationRecord)
            .where(abpSimulationRecord.abp_scenario_id == abp_scenario_id)
            .order_by(abpSimulationRecord.abp_id)
        )
        return [(abp_r.abp_id, self.abp__summary(abp_r)) for abp_r in abp_records]

    def abp_observations(self, abp_simulation_id: int) -> list[abpObservation]:
        abp_record = abp__get(self.abp__s, abpSimulationRecord, abp_simulation_id, "la simulación")
        return [self.abp__observation_domain(abp_o) for abp_o in abp_record.abp_observations]

    @staticmethod
    def abp__summary(abp_record: abpSimulationRecord) -> abpSimulationSummary:
        return abpSimulationSummary(
            abp_seed=abp_record.abp_seed,
            abp_total_time_s=abp_record.abp_total_time_s,
            abp_time_per_exit_s=tuple(abp_record.abp_time_per_exit_s.items()),
            abp_trajectories_path=abp_record.abp_trajectories_path,
            abp_created_at=abp_record.abp_created_at,
            abp_statistics=abp__statistics_from_json(abp_record.abp_statistics),
            abp_fingerprint=abp_record.abp_fingerprint or "",
        )

    @staticmethod
    def abp__observation_record(abp_obs: abpObservation) -> abpObservationRecord:
        abp_location = (
            None
            if abp_obs.abp_location is None
            else abp_geometry_dumps(abp_point_to_geojson(abp_obs.abp_location))
        )
        return abpObservationRecord(
            abp_kind=abp_obs.abp_kind,
            abp_description=abp_obs.abp_description,
            abp_norm=abp_obs.abp_norm,
            abp_article=abp_obs.abp_article,
            abp_verified=abp_obs.abp_verified,
            abp_location=abp_location,
            abp_recommendation=abp_obs.abp_recommendation,
        )

    @staticmethod
    def abp__observation_domain(abp_record: abpObservationRecord) -> abpObservation:
        abp_location = (
            None
            if abp_record.abp_location is None
            else abp_point_from_geojson(abp_geometry_loads(abp_record.abp_location))
        )
        return abpObservation(
            abp_kind=abpObservationType(abp_record.abp_kind),
            abp_description=abp_record.abp_description,
            abp_recommendation=abp_record.abp_recommendation,
            abp_location=abp_location,
            abp_norm=abp_record.abp_norm,
            abp_article=abp_record.abp_article,
            abp_verified=abp_record.abp_verified,
        )


class abpRealDrillRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp_add(self, abp_project_id: int, abp_drill: abpRealDrill) -> int:
        abp__get(self.abp__s, abpProjectRecord, abp_project_id, "el proyecto")
        abp_record = abpRealDrillRecord(
            abp_project_id=abp_project_id,
            abp_drill_date=abp_drill.abp_drill_date,
            abp_participants=abp_drill.abp_participants,
            abp_total_time_s=abp_drill.abp_total_time_s,
            abp_time_per_exit_s=dict(abp_drill.abp_time_per_exit_s),
        )
        self.abp__s.add(abp_record)
        self.abp__s.flush()
        return abp_record.abp_id

    def abp_list_all(self, abp_project_id: int) -> list[tuple[int, abpRealDrill]]:
        abp_records = self.abp__s.scalars(
            select(abpRealDrillRecord)
            .where(abpRealDrillRecord.abp_project_id == abp_project_id)
            .order_by(abpRealDrillRecord.abp_drill_date, abpRealDrillRecord.abp_id)
        )
        return [
            (
                abp_r.abp_id,
                abpRealDrill(
                    abp_drill_date=abp_r.abp_drill_date,
                    abp_participants=abp_r.abp_participants,
                    abp_total_time_s=abp_r.abp_total_time_s,
                    abp_time_per_exit_s=tuple(abp_r.abp_time_per_exit_s.items()),
                ),
            )
            for abp_r in abp_records
        ]

    def abp_delete(self, abp_drill_id: int) -> None:
        self.abp__s.delete(abp__get(self.abp__s, abpRealDrillRecord, abp_drill_id, "el simulacro"))
        self.abp__s.flush()


class abpRuleVerificationRepository:
    def __init__(self, abp_session: Session) -> None:
        self.abp__s = abp_session

    def abp_save(self, abp_verification: abpRuleVerification) -> None:
        abp_record = self.abp__s.scalars(
            select(abpRuleVerificationRecord).where(
                abpRuleVerificationRecord.abp_rule_id == abp_verification.abp_rule_id
            )
        ).one_or_none()
        if abp_record is None:
            abp_record = abpRuleVerificationRecord(abp_rule_id=abp_verification.abp_rule_id)
            self.abp__s.add(abp_record)
        abp_record.abp_value = abp_verification.abp_value
        abp_record.abp_norm = abp_verification.abp_norm
        abp_record.abp_article = abp_verification.abp_article
        abp_record.abp_source = abp_verification.abp_source
        abp_record.abp_verified = abp_verification.abp_verified
        abp_record.abp_verified_by = abp_verification.abp_verified_by
        abp_record.abp_verified_on = abp_verification.abp_verified_on
        self.abp__s.flush()

    def abp_list_all(self) -> list[abpRuleVerification]:
        abp_records = self.abp__s.scalars(
            select(abpRuleVerificationRecord).order_by(abpRuleVerificationRecord.abp_rule_id)
        )
        return [
            abpRuleVerification(
                abp_rule_id=abp_r.abp_rule_id,
                abp_value=abp_r.abp_value,
                abp_norm=abp_r.abp_norm,
                abp_article=abp_r.abp_article,
                abp_source=abp_r.abp_source or "",
                abp_verified=bool(abp_r.abp_verified),
                abp_verified_by=abp_r.abp_verified_by or "",
                abp_verified_on=abp_r.abp_verified_on,
            )
            for abp_r in abp_records
        ]

    def abp_delete(self, abp_rule_id: str) -> None:
        abp_record = self.abp__s.scalars(
            select(abpRuleVerificationRecord).where(
                abpRuleVerificationRecord.abp_rule_id == abp_rule_id
            )
        ).one_or_none()
        if abp_record is not None:
            self.abp__s.delete(abp_record)
            self.abp__s.flush()
