from __future__ import annotations

import math
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpDoor, abpExit, abpFloorPlan, abpRoom
from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorPlan, abpVectorText
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import (
    abp_is_furniture_layer,
    abp_is_structure_layer,
    abp_plain,
)
from abp_rutasegura.abp_engines.abp_vision.abp_room_labels import abp_read_room_labels, abpRoomLabel
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp_hatching,
    abp_merge_collinear,
    abp_point_segments_distance,
    abp_text_frames,
)

abp_DOOR_CODE = re.compile(r"^P[CV]?\s*[-.]\s*\d{1,3}$")
abp_WINDOW_CODE = re.compile(r"^(?:VEN|V|VE)\s*[-.]?\s*\d{1,3}$")
abp_NUMBER = re.compile(r"^\d{1,2}[.,]\d{2}$")
abp_TAG_REACH = 18.0
abp_DOOR_REACH_M, abp_WINDOW_REACH_M = 2.2, 2.2
abp_COLUMN_M = (0.15, 1.3)
abp_CHAIR_RADIUS_M = (0.15, 0.36)
abp_AREA_GAP = 0.3
abp_ADJUST_M = 0.13

abp_FURNITURE_WORDS = (
    ("ESCRITORIO", "Escritorio"),
    ("MESA", "Mesa"),
    ("SILLA", "Silla"),
    ("ESTANTE", "Estante"),
    ("SWITCH", "Switch"),
    ("RACK", "Rack"),
    ("PIZARRA", "Pizarra"),
    ("ECRAN", "Pantalla"),
    ("PANTALLA", "Pantalla"),
    ("COMPUTADORA", "Computadora"),
    ("ANTENA", "Antena"),
    ("LAVATORIO", "Lavatorio"),
    ("INODORO", "Inodoro"),
    ("URINARIO", "Urinario"),
    ("MOSTRADOR", "Mostrador"),
    ("COCINA", "Cocina"),
    ("REFRIGER", "Refrigeradora"),
    ("ARMARIO", "Armario"),
    ("ARCHIVADOR", "Archivador"),
    ("CAMILLA", "Camilla"),
)


@dataclass(frozen=True, slots=True)
class abpPlanElement:
    abp_kind: str
    abp_label: str
    abp_points: tuple[abpPoint, ...]
    abp_detail: str = ""


@dataclass(frozen=True, slots=True)
class abpTag:
    abp_code: str
    abp_x: float
    abp_y: float
    abp_numbers: tuple[float, ...]
    abp_window: bool

    @property
    def abp_width_m(self) -> float | None:
        if not self.abp_numbers:
            return None
        return (
            self.abp_numbers[1]
            if self.abp_window and len(self.abp_numbers) >= 3
            else self.abp_numbers[0]
        )


def abp_read_tags(abp_texts: Sequence[abpVectorText]) -> tuple[abpTag, ...]:
    abp_numbers = [abp_t for abp_t in abp_texts if abp_NUMBER.match(abp_t.abp_text.strip())]
    abp_out: list[abpTag] = []
    for abp_t in abp_texts:
        abp_code = abp_plain(abp_t.abp_text)
        abp_window = bool(abp_WINDOW_CODE.match(abp_code))
        if not abp_window and not abp_DOOR_CODE.match(abp_code):
            continue
        abp_rad = math.radians(abp_t.abp_angle_deg)
        abp_u, abp_v = (
            (math.cos(abp_rad), math.sin(abp_rad)),
            (-math.sin(abp_rad), math.cos(abp_rad)),
        )
        abp_near: list[tuple[int, float, float]] = []
        for abp_n in abp_numbers:
            abp_dx, abp_dy = abp_n.abp_x - abp_t.abp_x, abp_n.abp_y - abp_t.abp_y
            abp_along, abp_down = (
                abp_dx * abp_u[0] + abp_dy * abp_u[1],
                abp_dx * abp_v[0] + abp_dy * abp_v[1],
            )
            if (
                abs(abp_along) < abp_TAG_REACH * abp_t.abp_size / 2
                and -0.6 * abp_t.abp_size < abp_down < 3.2 * abp_t.abp_size
            ):
                abp_row = 0 if abp_down < 0.9 * abp_t.abp_size else 1
                abp_near.append(
                    (abp_row, abp_along, float(abp_n.abp_text.strip().replace(",", ".")))
                )
        abp_near.sort()
        abp_values = tuple(abp_value for abp__row, abp__along, abp_value in abp_near)
        abp_out.append(
            abpTag(" ".join(abp_code.split()), abp_t.abp_x, abp_t.abp_y, abp_values[:3], abp_window)
        )
    return tuple(abp_out)


def abp_adjust_doors(abp_plan: abpFloorPlan, abp_tags: Collection[abpTag]) -> abpFloorPlan:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None:
        return abp_plan
    abp_doors, abp_exits = list(abp_plan.abp_doors), list(abp_plan.abp_exits)
    for abp_tag in abp_tags:
        if abp_tag.abp_window or abp_tag.abp_width_m is None:
            continue
        abp_pick = abp__nearest_opening(abp_tag, abp_plan, abp_scale)
        if abp_pick is None:
            continue
        abp_group, abp_index = abp_pick
        abp_element: abpDoor | abpExit = (
            abp_doors[abp_index] if abp_group == "abp_doors" else abp_exits[abp_index]
        )
        abp_current = abp_element.abp_segment.abp_length * abp_scale
        if abs(abp_current - abp_tag.abp_width_m) > abp_ADJUST_M:
            continue
        abp_segment = abp__resized(abp_element.abp_segment, abp_tag.abp_width_m / abp_scale)
        if abp_group == "abp_doors":
            abp_doors[abp_index] = abpDoor(abp_segment, 1.0)
        else:
            abp_exits[abp_index] = abpExit(
                abp_segment, abp_exits[abp_index].abp_name, abp_exits[abp_index].abp_confirmed
            )
    return abpFloorPlan(
        abp_level=abp_plan.abp_level,
        abp_image_path=abp_plan.abp_image_path,
        abp_scale_m_per_px=abp_scale,
        abp_walls=abp_plan.abp_walls,
        abp_doors=tuple(abp_doors),
        abp_exits=tuple(abp_exits),
        abp_stairs=abp_plan.abp_stairs,
        abp_obstacles=abp_plan.abp_obstacles,
        abp_safe_zones=abp_plan.abp_safe_zones,
        abp_rooms=abp_plan.abp_rooms,
        abp_signs=abp_plan.abp_signs,
    )


def abp__resized(abp_s: abpSegment, abp_length: float) -> abpSegment:
    abp_mid, abp_half = abp_s.abp_midpoint, abp_length / 2
    abp_size = max(abp_s.abp_length, 1e-9)
    abp_ux, abp_uy = (
        (abp_s.abp_end.abp_x - abp_s.abp_start.abp_x) / abp_size,
        (abp_s.abp_end.abp_y - abp_s.abp_start.abp_y) / abp_size,
    )
    return abpSegment(
        abpPoint(abp_mid.abp_x - abp_ux * abp_half, abp_mid.abp_y - abp_uy * abp_half),
        abpPoint(abp_mid.abp_x + abp_ux * abp_half, abp_mid.abp_y + abp_uy * abp_half),
    )


def abp__nearest_opening(
    abp_tag: abpTag, abp_plan: abpFloorPlan, abp_scale: float
) -> tuple[str, int] | None:
    abp_best: tuple[float, str, int] | None = None
    for abp_group in ("abp_doors", "abp_exits"):
        for abp_index, abp_element in enumerate(getattr(abp_plan, abp_group)):
            abp_away = (
                abp_element.abp_segment.abp_midpoint.abp_distance_to(
                    abpPoint(abp_tag.abp_x, abp_tag.abp_y)
                )
                * abp_scale
            )
            if abp_away > abp_DOOR_REACH_M:
                continue
            abp_gap = abs(
                abp_element.abp_segment.abp_length * abp_scale - (abp_tag.abp_width_m or 0.0)
            )
            abp_cost = abp_away + 2.0 * abp_gap
            if abp_best is None or abp_cost < abp_best[0]:
                abp_best = (abp_cost, abp_group, abp_index)
    return (abp_best[1], abp_best[2]) if abp_best is not None else None


def abp_find_columns(abp_vector: abpVectorPlan, abp_scale: float) -> list[abpFloatArray]:
    abp_ids = [
        abp_i
        for abp_i, abp_name in enumerate(abp_vector.abp_layers)
        if not abp_is_structure_layer(abp_name)
    ]
    abp_raw = (
        abp_vector.abp_segments[
            ~abp_vector.abp_filled & ~np.isin(abp_vector.abp_segment_layer, abp_ids)
        ]
        * abp_scale
    )
    abp_raw = (
        abp_raw[~abp_text_frames(abp_raw, abp_vector.abp_texts, abp_scale)]
        if len(abp_raw)
        else abp_raw
    )
    if len(abp_raw) == 0:
        return []
    abp_lines = abp_merge_collinear(abp_raw)
    abp_short = abp_lines[
        np.hypot(abp_lines[:, 2] - abp_lines[:, 0], abp_lines[:, 3] - abp_lines[:, 1]) < 1.6
    ]
    abp_hatch = abp_short[abp_hatching(abp_short)] if len(abp_short) else abp_short
    abp_out: list[abpFloatArray] = []
    for abp_group in abp__clusters(abp_hatch, 0.12):
        if len(abp_group) < 4:
            continue
        abp_points = np.vstack([abp_group[:, :2], abp_group[:, 2:]])
        abp_box = abp__min_rect(abp_points)
        abp_w = float(np.hypot(*(abp_box[1] - abp_box[0])))
        abp_h = float(np.hypot(*(abp_box[2] - abp_box[1])))
        if abp_COLUMN_M[0] <= min(abp_w, abp_h) and max(abp_w, abp_h) <= abp_COLUMN_M[1]:
            abp_out.append(abp_box)
    return abp_out


def abp_find_chairs(
    abp_vector: abpVectorPlan, abp_scale: float, abp_plan: abpFloorPlan
) -> list[abpFloatArray]:
    abp_a = abp_vector.abp_arcs
    if len(abp_a) == 0:
        return []
    abp_ids = [
        abp_i
        for abp_i, abp_name in enumerate(abp_vector.abp_layers)
        if not abp_is_structure_layer(abp_name) and not abp_is_furniture_layer(abp_name)
    ]
    abp_r = abp_a[:, 2] * abp_scale
    abp_ok = (
        (abp_r >= abp_CHAIR_RADIUS_M[0])
        & (abp_r <= abp_CHAIR_RADIUS_M[1])
        & ~np.isin(abp_vector.abp_arc_layer, abp_ids)
    )
    abp_ok &= np.abs(abp_a[:, 4]) > math.radians(60)
    abp_out: list[abpFloatArray] = []
    abp_lo, abp_hi = abp__bounds(abp_plan, abp_scale)
    for abp_c in abp_a[abp_ok, :2] * abp_scale:
        if not ((abp_c >= abp_lo) & (abp_c <= abp_hi)).all():
            continue
        if all(float(np.hypot(*(abp_c - abp_o))) > 0.25 for abp_o in abp_out):
            abp_out.append(np.asarray(abp_c))
    return abp_out


def abp__bounds(abp_plan: abpFloorPlan, abp_scale: float) -> tuple[abpFloatArray, abpFloatArray]:
    abp_points = np.array(
        [
            (abp_p.abp_x, abp_p.abp_y)
            for abp_w in abp_plan.abp_walls
            for abp_p in (abp_w.abp_segment.abp_start, abp_w.abp_segment.abp_end)
        ]
    )
    if len(abp_points) == 0:
        return np.zeros(2), np.zeros(2)
    return abp_points.min(axis=0) * abp_scale, abp_points.max(axis=0) * abp_scale


def abp__clusters(abp_s: abpFloatArray, abp_gap: float) -> list[abpFloatArray]:
    abp_n = len(abp_s)
    abp_parent = list(range(abp_n))

    def abp_find(abp_i: int) -> int:
        while abp_parent[abp_i] != abp_i:
            abp_parent[abp_i] = abp_parent[abp_parent[abp_i]]
            abp_i = abp_parent[abp_i]
        return abp_i

    for abp_i in range(abp_n):
        abp_middle = (abp_s[abp_i, :2] + abp_s[abp_i, 2:]) / 2
        for abp_p in (abp_s[abp_i, :2], abp_middle, abp_s[abp_i, 2:]):
            for abp_j in np.flatnonzero(abp_point_segments_distance(abp_p, abp_s) <= abp_gap):
                abp_parent[abp_find(abp_i)] = abp_find(int(abp_j))
    abp_groups: dict[int, list[int]] = {}
    for abp_i in range(abp_n):
        abp_groups.setdefault(abp_find(abp_i), []).append(abp_i)
    return [abp_s[abp_members] for abp_members in abp_groups.values()]


def abp__min_rect(abp_points: abpFloatArray) -> abpFloatArray:
    import cv2

    abp_box = cv2.boxPoints(cv2.minAreaRect(abp_points.astype(np.float32)))
    return np.asarray(abp_box, np.float64)


def abp_furniture_names(
    abp_plan: abpFloorPlan, abp_texts: Collection[abpVectorText]
) -> tuple[str, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_words = [
        (abp_name, abp_t)
        for abp_t in abp_texts
        for abp_word, abp_name in abp_FURNITURE_WORDS
        if abp_word in abp_plain(abp_t.abp_text) and len(abp_t.abp_text) < 30
    ]
    abp_names: list[str] = []
    for abp_obstacle in abp_plan.abp_obstacles:
        if abp_obstacle.abp_name:
            abp_names.append(abp_obstacle.abp_name)
            continue
        abp_center = abp_obstacle.abp_area.abp_centroid
        abp_reach = (
            max(abp_center.abp_distance_to(abp_v) for abp_v in abp_obstacle.abp_area.abp_vertices)
            + 0.9 / abp_scale
        )
        abp_near = [
            (abp_center.abp_distance_to(abpPoint(abp_t.abp_x, abp_t.abp_y)), abp_name)
            for abp_name, abp_t in abp_words
            if abp_center.abp_distance_to(abpPoint(abp_t.abp_x, abp_t.abp_y)) <= abp_reach
            and abp_name not in ("Silla", "Computadora")
        ]
        abp_names.append(min(abp_near)[1] if abp_near else "")
    abp_areas = [
        abp_o.abp_area.abp_area * abp_scale * abp_scale for abp_o in abp_plan.abp_obstacles
    ]
    for abp_i, abp_name in enumerate(abp_names):
        if abp_name:
            continue
        abp_same = [
            abp_names[abp_j]
            for abp_j, abp_a in enumerate(abp_areas)
            if abp_names[abp_j]
            and abs(abp_a - abp_areas[abp_i]) < 0.15 * max(abp_a, abp_areas[abp_i])
        ]
        abp_names[abp_i] = abp_same[0] if abp_same else ""
    return tuple(abp_names)


def abp_build_inventory(
    abp_plan: abpFloorPlan, abp_vector: abpVectorPlan | None = None
) -> tuple[abpPlanElement, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px
    abp_texts = abp_vector.abp_texts if abp_vector is not None else ()
    abp_tags = abp_read_tags(abp_texts)
    abp_out: list[abpPlanElement] = []
    for abp_i, abp_wall in enumerate(abp_plan.abp_walls, start=1):
        abp_length = f"{abp_wall.abp_segment.abp_length * abp_scale:.2f} m" if abp_scale else ""
        abp_out.append(
            abpPlanElement("muro", f"Muro {abp_i}", abp__ends(abp_wall.abp_segment), abp_length)
        )
    abp_used: dict[tuple[str, int], abpTag] = {}
    if abp_scale:
        for abp_tag in abp_tags:
            abp_pick = (
                abp__nearest_opening(abp_tag, abp_plan, abp_scale)
                if not abp_tag.abp_window
                else None
            )
            if abp_pick is not None:
                abp_used.setdefault(abp_pick, abp_tag)
    for abp_group, abp_kind, abp_name in (
        ("abp_doors", "puerta", "Puerta"),
        ("abp_exits", "salida", "Salida"),
    ):
        for abp_i, abp_element in enumerate(getattr(abp_plan, abp_group)):
            abp_own = abp_used.get((abp_group, abp_i))
            abp_width = abp_element.abp_segment.abp_length * abp_scale if abp_scale else 0.0
            abp_label = abp_own.abp_code if abp_own is not None else f"{abp_name} {abp_i + 1}"
            if abp_kind == "salida":
                abp_label = (
                    f"{abp_element.abp_name} ({abp_own.abp_code})"
                    if abp_own is not None
                    else abp_element.abp_name
                )
            abp_out.append(
                abpPlanElement(
                    abp_kind,
                    abp_label,
                    abp__ends(abp_element.abp_segment),
                    abp__door_detail(abp_width, abp_own),
                )
            )
    if abp_scale:
        abp_out += abp__missing_doors(abp_plan, abp_tags, abp_used, abp_scale)
    if abp_scale and abp_vector is not None:
        abp_out += abp__windows(abp_plan, abp_tags, abp_scale)
        for abp_i, abp_box in enumerate(abp_find_columns(abp_vector, abp_scale), start=1):
            abp_side = (
                float(np.hypot(*(abp_box[1] - abp_box[0]))),
                float(np.hypot(*(abp_box[2] - abp_box[1]))),
            )
            abp_detail = f"{max(abp_side):.2f} × {min(abp_side):.2f} m"
            abp_out.append(
                abpPlanElement(
                    "columna", f"Columna {abp_i}", abp__corners(abp_box / abp_scale), abp_detail
                )
            )
        for abp_i, abp_c in enumerate(abp_find_chairs(abp_vector, abp_scale, abp_plan), start=1):
            abp_circle = tuple(
                abpPoint(
                    float(abp_c[0] + 0.22 * math.cos(abp_t)) / abp_scale,
                    float(abp_c[1] + 0.22 * math.sin(abp_t)) / abp_scale,
                )
                for abp_t in np.linspace(0, 2 * math.pi, 12, endpoint=False)
            )
            abp_out.append(abpPlanElement("silla", f"Silla {abp_i}", abp_circle))
    for abp_i, abp_stair in enumerate(abp_plan.abp_stairs, start=1):
        abp_area = f"{abp_plan.abp_area_m2(abp_stair.abp_area):.1f} m²" if abp_scale else ""
        abp_out.append(
            abpPlanElement(
                "escalera",
                abp_stair.abp_name or f"Escalera {abp_i}",
                abp_stair.abp_area.abp_vertices,
                abp_area,
            )
        )
    for abp_i, (abp_obstacle, abp_name) in enumerate(
        zip(abp_plan.abp_obstacles, abp_furniture_names(abp_plan, abp_texts), strict=True), start=1
    ):
        abp_area = f"{abp_plan.abp_area_m2(abp_obstacle.abp_area):.2f} m²" if abp_scale else ""
        abp_out.append(
            abpPlanElement(
                "obstaculo",
                abp_name or f"Obstáculo {abp_i}",
                abp_obstacle.abp_area.abp_vertices,
                abp_area,
            )
        )
    for abp_sign in abp_plan.abp_signs:
        abp_out.append(
            abpPlanElement(
                "senal", abp_sign.abp_kind.value, (abp_sign.abp_position,), abp_sign.abp_text
            )
        )
    for abp_zone in abp_plan.abp_safe_zones:
        abp_out.append(
            abpPlanElement(
                "zona_segura", abp_zone.abp_name or "Zona segura", abp_zone.abp_area.abp_vertices
            )
        )
    abp_labels = abp_read_room_labels(tuple(abp_texts))
    if abp_plan.abp_rooms:
        for abp_room in abp_plan.abp_rooms:
            abp_detail = abp__room_detail(abp_plan, abp_room, abp_labels) if abp_scale else ""
            abp_out.append(
                abpPlanElement(
                    "ambiente", abp_room.abp_name, abp_room.abp_area.abp_vertices, abp_detail
                )
            )
    else:
        for abp_q in abp_labels:
            abp_parts = [
                f"{abp_q.abp_area_m2:.2f} m²" if abp_q.abp_area_m2 else "",
                f"aforo {abp_q.abp_capacity}" if abp_q.abp_capacity else "",
            ]
            abp_detail = " · ".join(abp_p for abp_p in abp_parts if abp_p)
            abp_out.append(
                abpPlanElement(
                    "ambiente", abp_q.abp_name, (abpPoint(abp_q.abp_x, abp_q.abp_y),), abp_detail
                )
            )
    return tuple(abp_out)


def abp__missing_doors(
    abp_plan: abpFloorPlan,
    abp_tags: Collection[abpTag],
    abp_used: dict[tuple[str, int], abpTag],
    abp_scale: float,
) -> list[abpPlanElement]:
    abp_found = {id(abp_tag) for abp_tag in abp_used.values()}
    abp_lo, abp_hi = abp__bounds(abp_plan, abp_scale)
    abp_out: list[abpPlanElement] = []
    for abp_tag in abp_tags:
        abp_p = np.array([abp_tag.abp_x, abp_tag.abp_y]) * abp_scale
        if abp_tag.abp_window or id(abp_tag) in abp_found or abp_tag.abp_width_m is None:
            continue
        if not ((abp_p >= abp_lo - 0.5) & (abp_p <= abp_hi + 0.5)).all():
            continue
        abp_written = " × ".join(f"{abp_v:.2f}" for abp_v in abp_tag.abp_numbers)
        abp_detail = f"{abp_written} m en el plano · sin vano detectado: dibújela"
        abp_out.append(
            abpPlanElement(
                "puerta", abp_tag.abp_code, (abpPoint(abp_tag.abp_x, abp_tag.abp_y),), abp_detail
            )
        )
    return abp_out


def abp__windows(
    abp_plan: abpFloorPlan, abp_tags: Collection[abpTag], abp_scale: float
) -> list[abpPlanElement]:
    abp_walls = np.array(
        [
            (
                abp_w.abp_segment.abp_start.abp_x,
                abp_w.abp_segment.abp_start.abp_y,
                abp_w.abp_segment.abp_end.abp_x,
                abp_w.abp_segment.abp_end.abp_y,
            )
            for abp_w in abp_plan.abp_walls
        ]
    ).reshape(-1, 4)
    abp_out: list[abpPlanElement] = []
    if len(abp_walls) == 0:
        return abp_out
    for abp_tag in abp_tags:
        if not abp_tag.abp_window:
            continue
        abp_p = np.array([abp_tag.abp_x, abp_tag.abp_y])
        abp_away = abp_point_segments_distance(abp_p, abp_walls)
        abp_j = int(np.argmin(abp_away))
        if abp_away[abp_j] * abp_scale > abp_WINDOW_REACH_M:
            continue
        abp_a, abp_b = abp_walls[abp_j, :2], abp_walls[abp_j, 2:]
        abp_size = max(float(np.hypot(*(abp_b - abp_a))), 1e-9)
        abp_u = (abp_b - abp_a) / abp_size
        abp_half = min((abp_tag.abp_width_m or 1.0) / abp_scale, abp_size) / 2
        abp_t = float(np.clip((abp_p - abp_a) @ abp_u, abp_half, abp_size - abp_half))
        abp_ends = (abp_a + abp_u * (abp_t - abp_half), abp_a + abp_u * (abp_t + abp_half))
        abp_detail = " × ".join(
            f"{abp_v:.2f}" for abp_v in abp_tag.abp_numbers[1:] or abp_tag.abp_numbers
        )
        abp_out.append(
            abpPlanElement(
                "ventana",
                abp_tag.abp_code,
                tuple(abpPoint(float(abp_q[0]), float(abp_q[1])) for abp_q in abp_ends),
                f"{abp_detail} m" if abp_detail else "",
            )
        )
    return abp_out


def abp__door_detail(abp_width: float, abp_tag: abpTag | None) -> str:
    abp_found = f"{abp_width:.2f} m" if abp_width else ""
    if abp_tag is None or abp_tag.abp_width_m is None:
        return abp_found
    abp_written = " × ".join(f"{abp_v:.2f}" for abp_v in abp_tag.abp_numbers)
    abp_same = (
        "coincide" if abs(abp_width - abp_tag.abp_width_m) <= 0.05 else f"detectado {abp_found}"
    )
    return f"{abp_written} m en el plano · {abp_same}"


def abp__room_detail(
    abp_plan: abpFloorPlan, abp_room: abpRoom, abp_labels: Collection[abpRoomLabel]
) -> str:
    abp_measured = abp_plan.abp_area_m2(abp_room.abp_area)
    abp_written = [
        abp_q.abp_area_m2
        for abp_q in abp_labels
        if abp_q.abp_area_m2 and abp_q.abp_name == abp_room.abp_name
    ]
    if abp_written and all(
        abs(abp_w - abp_measured) > abp_AREA_GAP * abp_measured for abp_w in abp_written
    ):
        return f"{abp_measured:.1f} m² · el plano dice {abp_written[0]:.2f} m²: verifique"
    return f"{abp_measured:.1f} m²"


def abp__ends(abp_s: abpSegment) -> tuple[abpPoint, ...]:
    return abp_s.abp_start, abp_s.abp_end


def abp__corners(abp_box: abpFloatArray) -> tuple[abpPoint, ...]:
    return tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_box)
