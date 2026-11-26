from __future__ import annotations

from typing import Any

from abp_rutasegura.abp_domain.abp_enums import abpSignKind, abpStairUse, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
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
from abp_rutasegura.abp_domain.abp_scenario import abpManualRoute, abpScenario


def abp__seg(abp_s: abpSegment) -> list[float]:
    return [abp_s.abp_start.abp_x, abp_s.abp_start.abp_y, abp_s.abp_end.abp_x, abp_s.abp_end.abp_y]


def abp__poly(abp_p: abpPolygon) -> list[list[float]]:
    return [[abp_v.abp_x, abp_v.abp_y] for abp_v in abp_p.abp_vertices]


def abp__to_seg(abp_raw: list[float]) -> abpSegment:
    abp_x1, abp_y1, abp_x2, abp_y2 = (float(abp_v) for abp_v in abp_raw)
    return abpSegment(abpPoint(abp_x1, abp_y1), abpPoint(abp_x2, abp_y2))


def abp__to_poly(abp_raw: list[list[float]]) -> abpPolygon:
    return abpPolygon(tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_raw))


def abp_plan_to_dict(abp_plan: abpFloorPlan) -> dict[str, Any]:
    return {
        "nivel": abp_plan.abp_level,
        "escala_m_por_px": abp_plan.abp_scale_m_per_px,
        "muros": [
            {"seg": abp__seg(abp_w.abp_segment), "confianza": abp_w.abp_confidence}
            for abp_w in abp_plan.abp_walls
        ],
        "puertas": [
            {"seg": abp__seg(abp_d.abp_segment), "confianza": abp_d.abp_confidence}
            for abp_d in abp_plan.abp_doors
        ],
        "salidas": [
            {
                "seg": abp__seg(abp_e.abp_segment),
                "nombre": abp_e.abp_name,
                "confirmada": abp_e.abp_confirmed,
            }
            for abp_e in abp_plan.abp_exits
        ],
        "escaleras": [
            {
                "area": abp__poly(abp_s.abp_area),
                "nombre": abp_s.abp_name,
                "confirmada": abp_s.abp_confirmed,
                "conecta_con": abp_s.abp_connects_to_level,
                **(
                    {"uso": abp_s.abp_use.value}
                    if abp_s.abp_use is not abpStairUse.abp_AUTO
                    else {}
                ),
                **(
                    {"entrada": [abp_s.abp_entry.abp_x, abp_s.abp_entry.abp_y]}
                    if abp_s.abp_entry is not None
                    else {}
                ),
                **({"lleva_a": abp_s.abp_leads_to} if abp_s.abp_leads_to else {}),
            }
            for abp_s in abp_plan.abp_stairs
        ],
        "obstaculos": [
            {
                "area": abp__poly(abp_o.abp_area),
                **({} if abp_o.abp_confirmed else {"confirmado": False}),
                **({"nombre": abp_o.abp_name} if abp_o.abp_name else {}),
            }
            for abp_o in abp_plan.abp_obstacles
        ],
        "zonas_seguras": [
            {"area": abp__poly(abp_z.abp_area), "nombre": abp_z.abp_name}
            for abp_z in abp_plan.abp_safe_zones
        ],
        "ambientes": [
            {
                "nombre": abp_r.abp_name,
                "uso": abp_r.abp_use.value,
                "area": abp__poly(abp_r.abp_area),
                "categoria": abp_r.abp_category,
                **({"salida": abp_r.abp_exit_name} if abp_r.abp_exit_name else {}),
            }
            for abp_r in abp_plan.abp_rooms
        ],
        "senales": [
            {
                "tipo": abp_s.abp_kind.value,
                "x": abp_s.abp_position.abp_x,
                "y": abp_s.abp_position.abp_y,
                "giro": abp_s.abp_rotation_deg,
                "texto": abp_s.abp_text,
            }
            for abp_s in abp_plan.abp_signs
        ],
    }


def abp_plan_from_dict(abp_data: dict[str, Any]) -> abpFloorPlan:
    abp_scale = abp_data.get("escala_m_por_px")
    return abpFloorPlan(
        abp_level=int(abp_data["nivel"]),
        abp_scale_m_per_px=None if abp_scale is None else float(abp_scale),
        abp_walls=tuple(
            abpWall(abp__to_seg(abp_w["seg"]), float(abp_w["confianza"]))
            for abp_w in abp_data["muros"]
        ),
        abp_doors=tuple(
            abpDoor(abp__to_seg(abp_d["seg"]), float(abp_d["confianza"]))
            for abp_d in abp_data["puertas"]
        ),
        abp_exits=tuple(
            abpExit(abp__to_seg(abp_e["seg"]), str(abp_e["nombre"]), bool(abp_e["confirmada"]))
            for abp_e in abp_data["salidas"]
        ),
        abp_stairs=tuple(
            abpStair(
                abp__to_poly(abp_s["area"]),
                abp_connects_to_level=abp_s.get("conecta_con"),
                abp_confirmed=bool(abp_s["confirmada"]),
                abp_name=str(abp_s["nombre"]),
                abp_use=abpStairUse(abp_s.get("uso", abpStairUse.abp_AUTO)),
                abp_entry=abpPoint(*abp_s["entrada"]) if abp_s.get("entrada") else None,
                abp_leads_to=str(abp_s.get("lleva_a", "")),
            )
            for abp_s in abp_data["escaleras"]
        ),
        abp_obstacles=tuple(
            abpObstacle(
                abp__to_poly(abp_o["area"]),
                bool(abp_o.get("confirmado", True)),
                str(abp_o.get("nombre", "")),
            )
            for abp_o in abp_data["obstaculos"]
        ),
        abp_safe_zones=tuple(
            abpSafeZone(abp__to_poly(abp_z["area"]), str(abp_z["nombre"]))
            for abp_z in abp_data["zonas_seguras"]
        ),
        abp_rooms=tuple(
            abpRoom(
                str(abp_r["nombre"]),
                abpUseType(abp_r["uso"]),
                abp__to_poly(abp_r["area"]),
                str(abp_r["categoria"]),
                str(abp_r.get("salida", "")),
            )
            for abp_r in abp_data["ambientes"]
        ),
        abp_signs=tuple(
            abpSign(
                abpSignKind(abp_s["tipo"]),
                abpPoint(float(abp_s["x"]), float(abp_s["y"])),
                float(abp_s["giro"]),
                str(abp_s["texto"]),
            )
            for abp_s in abp_data.get("senales", [])
        ),
    )


def abp_scenario_to_dict(abp_scenario: abpScenario) -> dict[str, Any]:
    return {
        "nombre": abp_scenario.abp_name,
        "semilla": abp_scenario.abp_seed,
        "salidas_bloqueadas": sorted(abp_scenario.abp_blocked_exits),
        "descripcion": abp_scenario.abp_description,
        "factor_reaccion": abp_scenario.abp_reaction_factor,
        "factor_velocidad": abp_scenario.abp_speed_factor,
        "corridas": abp_scenario.abp_runs,
        "ocupacion": [
            {
                "ambiente": abp_o.abp_room_name,
                "perfil": abp_o.abp_profile_name,
                "cantidad": abp_o.abp_count,
                "nivel": abp_o.abp_level,
            }
            for abp_o in abp_scenario.abp_occupancies
        ],
        **(
            {"rutas": [abp__route_to_dict(abp_r) for abp_r in abp_scenario.abp_routes]}
            if abp_scenario.abp_routes
            else {}
        ),
    }


def abp__route_to_dict(abp_route: abpManualRoute) -> dict[str, Any]:
    return {
        "origen": abp_route.abp_source,
        "nivel": abp_route.abp_level,
        "salida": abp_route.abp_exit_name,
        "puntos": [[abp_p.abp_x, abp_p.abp_y] for abp_p in abp_route.abp_waypoints],
        "escalera": abp_route.abp_from_stair,
    }


def abp_scenario_from_dict(abp_data: dict[str, Any]) -> abpScenario:
    return abpScenario(
        abp_name=str(abp_data["nombre"]),
        abp_seed=int(abp_data["semilla"]),
        abp_occupancies=tuple(
            abpOccupancy(
                str(abp_o["ambiente"]),
                str(abp_o["perfil"]),
                int(abp_o["cantidad"]),
                int(abp_o["nivel"]),
            )
            for abp_o in abp_data["ocupacion"]
        ),
        abp_blocked_exits=frozenset(str(abp_n) for abp_n in abp_data["salidas_bloqueadas"]),
        abp_description=str(abp_data.get("descripcion", "")),
        abp_reaction_factor=float(abp_data.get("factor_reaccion", 1.0)),
        abp_speed_factor=float(abp_data.get("factor_velocidad", 1.0)),
        abp_runs=int(abp_data.get("corridas", 1)),
        abp_routes=tuple(
            abpManualRoute(
                str(abp_r["origen"]),
                int(abp_r["nivel"]),
                str(abp_r.get("salida", "")),
                tuple(
                    abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_r.get("puntos", [])
                ),
                bool(abp_r.get("escalera", False)),
            )
            for abp_r in abp_data.get("rutas", [])
        ),
    )
