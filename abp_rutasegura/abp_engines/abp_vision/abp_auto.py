from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpDoor,
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpStair,
    abpWall,
)
from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_filters import abp_suppress_light_fills
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage
from abp_rutasegura.abp_engines.abp_vision.abp_inventory import (
    abp_adjust_doors,
    abp_find_columns,
    abp_furniture_names,
    abp_read_tags,
)
from abp_rutasegura.abp_engines.abp_vision.abp_layered import abp_detect_drawing
from abp_rutasegura.abp_engines.abp_vision.abp_obstacles import abp_detect_obstacles
from abp_rutasegura.abp_engines.abp_vision.abp_openings import abp_classify, abp_complete_openings
from abp_rutasegura.abp_engines.abp_vision.abp_pipeline import (
    abp_detect_plan,
    abpDetectionResult,
    abpVisionParams,
)
from abp_rutasegura.abp_engines.abp_vision.abp_preprocess import abp_binarize, abp_to_gray
from abp_rutasegura.abp_engines.abp_vision.abp_quality import abp_assess
from abp_rutasegura.abp_engines.abp_vision.abp_room_labels import abp_label_anchors
from abp_rutasegura.abp_engines.abp_vision.abp_stairs import abp_find_stairs, abpFoundStair
from abp_rutasegura.abp_engines.abp_vision.abp_vector_plan import (
    abp_detect_vector_plan,
    abp_door_arcs,
    abp_merge_collinear,
    abp_plan_lines,
    abp_point_segments_distance,
    abp_scale_from_dimensions,
)
from abp_rutasegura.abp_engines.abp_vision.abp_vectorize import abp_vectorize

abp_STROKE_PX = 3.0
abp_BETTER, abp_MUCH_BETTER = 1.05, 2.0
abp_REPEATED, abp_DANGLING = 0.15, 0.3
abp_MIN_ROOMS = 1
abp_FREE_COLUMN_M = 0.5
abp_THIN_RATIO = 0.6
abp_DOOR_M = (0.7, 2.6)
abp__Run = tuple[int, int]


@dataclass(frozen=True, slots=True)
class abpAutoDetection:
    abp_walls: tuple[abpWall, ...] = ()
    abp_doors: tuple[abpDoor, ...] = ()
    abp_exits: tuple[abpExit, ...] = ()
    abp_stairs: tuple[abpStair, ...] = ()
    abp_obstacles: tuple[abpObstacle, ...] = ()
    abp_method: str = "imagen"


def abp_sheet_scale(abp_vector: abpVectorPlan | None) -> float | None:
    if abp_vector is None:
        return None
    if abp_vector.abp_scale_m_per_px is not None:
        return abp_vector.abp_scale_m_per_px
    abp_denominator = abp_scale_from_dimensions(abp_vector)
    return 0.0254 / abp_vector.abp_dpi * abp_denominator if abp_denominator is not None else None


def abp_detect_auto(
    abp_image: abpRGBImage,
    *,
    abp_scale_m_per_px: float | None,
    abp_vector: abpVectorPlan | None = None,
    abp_orthogonal_only: bool = True,
) -> abpAutoDetection:
    abp_scale = abp_scale_m_per_px or abp_sheet_scale(abp_vector)
    if abp_vector is not None and abp_scale is not None:
        abp_found = abp_detect_drawing(
            abp_vector, abp_scale, abp_anchors_px=abp_label_anchors(abp_vector.abp_texts)
        )
        abp_openings: list[abpDoor | abpExit] = [*abp_found.abp_doors, *abp_found.abp_exits]
        abp_quality = abp_assess(
            [abp_w.abp_segment for abp_w in abp_found.abp_walls],
            [abp_o.abp_segment for abp_o in abp_openings],
            abp_scale,
        )
        if abp_quality.abp_rooms >= abp_MIN_ROOMS or len(abp_found.abp_walls) >= 4:
            abp_wall_lines = (
                abp__array([abp_w.abp_segment for abp_w in abp_found.abp_walls]) * abp_scale
            )
            abp_lines = abp_plan_lines(abp_vector, abp_scale, abp_wall_lines)
            abp_stairs = tuple(
                abp_to_stair(abp_s, abp_scale)
                for abp_s in abp_find_stairs(
                    abp_lines, abp_wall_lines, abp_vector.abp_texts, abp_scale
                )
            )
            return abp__with_obstacles(
                abpAutoDetection(
                    abp_found.abp_walls,
                    abp_found.abp_doors,
                    abp_found.abp_exits,
                    abp_stairs,
                    (),
                    "trazos",
                ),
                abp_image,
                abp_vector,
                abp_scale,
            )
    return abp__from_image(abp_image, abp_scale, abp_orthogonal_only)


def abp_to_stair(
    abp_found: abpFoundStair, abp_scale: float, *, abp_confirmed: bool = False
) -> abpStair:
    abp_entry = None
    if abp_found.abp_entry is not None:
        abp_entry = abpPoint(
            float(abp_found.abp_entry[0]) / abp_scale, float(abp_found.abp_entry[1]) / abp_scale
        )
    return abpStair(
        abp__polygon(abp_found.abp_area / abp_scale),
        abp_confirmed=abp_confirmed,
        abp_use=abp_found.abp_use,
        abp_entry=abp_entry,
    )


def abp_stairs_in(abp_plan: abpFloorPlan, abp_vector: abpVectorPlan) -> tuple[abpStair, ...]:
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None or not abp_plan.abp_walls:
        return ()
    abp_walls = abp__array([abp_w.abp_segment for abp_w in abp_plan.abp_walls]) * abp_scale
    abp_lines = abp_plan_lines(abp_vector, abp_scale, abp_walls)
    return tuple(
        abp_to_stair(abp_s, abp_scale)
        for abp_s in abp_find_stairs(abp_lines, abp_walls, abp_vector.abp_texts, abp_scale)
    )


def abp__from_image(
    abp_image: abpRGBImage, abp_scale: float | None, abp_orthogonal_only: bool
) -> abpAutoDetection:
    abp_params = abpVisionParams(
        abp_scale_m_per_px=abp_scale, abp_orthogonal_only=abp_orthogonal_only
    )
    abp_raster = abp_detect_plan(abp_image, abp_params)
    if abp_scale is None:
        return abpAutoDetection(abp_raster.abp_walls, abp_raster.abp_doors, abp_raster.abp_exits)
    abp_traces = abp_vectorize(abp_image)
    abp_vector = abp_detect_vector_plan(abp_traces, abp_scale, abp_stroke_px=abp_STROKE_PX)
    abp_raster_walls, abp_sliding = abp__thin_doors(abp_image, abp_raster, abp_scale)
    abp_options: dict[str, tuple[tuple[abpWall, ...], tuple[abpDoor | abpExit, ...]]] = {
        "imagen": (abp_raster_walls, (*abp_raster.abp_doors, *abp_raster.abp_exits, *abp_sliding)),
        "imagen_trazos": (abp_vector.abp_walls, (*abp_vector.abp_doors, *abp_vector.abp_exits)),
    }
    abp_quality = {
        abp_name: abp_assess(
            [abp_w.abp_segment for abp_w in abp_walls],
            [abp_o.abp_segment for abp_o in abp_openings],
            abp_scale,
        )
        for abp_name, (abp_walls, abp_openings) in abp_options.items()
    }
    abp_by_image, abp_by_traces = abp_quality["imagen"], abp_quality["imagen_trazos"]
    abp_doubtful = (
        abp_by_image.abp_rooms == 0
        or abp_by_image.abp_repeated > abp_REPEATED
        or abp_by_image.abp_dangling > abp_DANGLING
    )
    abp_better = (
        abp_by_traces.abp_score
        > (abp_BETTER if abp_doubtful else abp_MUCH_BETTER) * abp_by_image.abp_score
    )
    abp_method = "imagen_trazos" if abp_better else "imagen"
    abp_walls, abp_openings = abp_options[abp_method]
    abp_lines = abp_merge_collinear(
        abp_traces.abp_segments * abp_scale,
        abp_offset=max(0.015, 1.3 * abp_STROKE_PX * abp_scale),
        abp_gap=0.05,
    )
    abp_wall_lines = abp__array([abp_w.abp_segment for abp_w in abp_walls]) * abp_scale
    abp_known = [
        (abp_o, abp__confidence(abp_x))
        for abp_o, abp_x in zip(
            abp__array([abp_x.abp_segment for abp_x in abp_openings]), abp_openings, strict=True
        )
    ]
    abp_known = [(abp_o * abp_scale, abp_c) for abp_o, abp_c in abp_known]
    abp_arcs = abp_door_arcs(abp_traces, abp_scale, ())
    abp_known += abp_complete_openings(
        abp_wall_lines, [abp_o for abp_o, abp__c in abp_known], abp_lines, abp_arcs
    )
    abp_doors: list[abpDoor] = []
    abp_exits: list[abpExit] = []
    abp_suspects = [abp_i for abp_i, abp_o in enumerate(abp_openings) if isinstance(abp_o, abpExit)]
    for abp_opening in abp_classify(abp_wall_lines, abp_known, abp_suspects):
        abp_segment = abp__segment(abp_opening.abp_segment / abp_scale)
        if abp_opening.abp_outside:
            abp_exits.append(
                abpExit(abp_segment, abp_name=f"Salida {len(abp_exits) + 1}", abp_confirmed=False)
            )
        else:
            abp_doors.append(abpDoor(abp_segment, abp_opening.abp_confidence))
    abp_stairs = tuple(
        abp_to_stair(abp_x, abp_scale) for abp_x in abp_find_stairs(abp_lines, abp_wall_lines)
    )
    abp_detection = abpAutoDetection(
        abp_walls, tuple(abp_doors), tuple(abp_exits), abp_stairs, (), abp_method
    )
    return abp__with_obstacles(abp_detection, abp_image, None, abp_scale)


def abp__thin_doors(
    abp_image: abpRGBImage, abp_raster: abpDetectionResult, abp_scale: float
) -> tuple[tuple[abpWall, ...], tuple[abpDoor, ...]]:
    abp_binary = abp_binarize(abp_suppress_light_fills(abp_image, abp_to_gray(abp_image)))
    abp_depth = cv2.distanceTransform(abp_binary.astype(np.uint8), cv2.DIST_L2, 3)
    abp_reach = max(2, round(abp_raster.abp_wall_thickness_px))
    abp_thick = cv2.dilate(abp_depth, np.ones((2 * abp_reach + 1, 2 * abp_reach + 1), np.uint8))
    abp_walls: list[abpWall] = []
    abp_doors: list[abpDoor] = []
    for abp_wall in abp_raster.abp_walls:
        abp_s = abp_wall.abp_segment
        abp_n = max(4, int(abp_s.abp_length))
        abp_t = np.linspace(0.0, 1.0, abp_n)
        abp_xs = np.clip(
            (abp_s.abp_start.abp_x + abp_t * (abp_s.abp_end.abp_x - abp_s.abp_start.abp_x)).astype(
                int
            ),
            0,
            abp_thick.shape[1] - 1,
        )
        abp_ys = np.clip(
            (abp_s.abp_start.abp_y + abp_t * (abp_s.abp_end.abp_y - abp_s.abp_start.abp_y)).astype(
                int
            ),
            0,
            abp_thick.shape[0] - 1,
        )
        abp_values = abp_thick[abp_ys, abp_xs]
        abp_thin = abp_values < abp_THIN_RATIO * float(np.percentile(abp_values, 75))
        abp_pieces, abp_gaps = abp__runs(abp_thin, abp_s.abp_length / abp_n * abp_scale)
        if not abp_gaps:
            abp_walls.append(abp_wall)
            continue
        abp_walls.extend(
            abpWall(abp__part(abp_s, abp_a / abp_n, abp_b / abp_n), abp_wall.abp_confidence)
            for abp_a, abp_b in abp_pieces
            if abp_b - abp_a > 2
        )
        abp_doors.extend(
            abpDoor(abp__part(abp_s, abp_a / abp_n, abp_b / abp_n), 0.6)
            for abp_a, abp_b in abp_gaps
        )
    return tuple(abp_walls), tuple(abp_doors)


def abp__runs(
    abp_thin: npt.NDArray[np.bool_], abp_step_m: float
) -> tuple[list[abp__Run], list[abp__Run]]:
    abp_edges = np.flatnonzero(np.diff(abp_thin.astype(np.int8), prepend=0, append=0))
    abp_gaps = [
        (int(abp_a), int(abp_b))
        for abp_a, abp_b in zip(abp_edges[::2], abp_edges[1::2], strict=True)
        if abp_DOOR_M[0] <= (abp_b - abp_a) * abp_step_m <= abp_DOOR_M[1]
    ]
    abp_pieces: list[abp__Run] = []
    abp_previous = 0
    for abp_a, abp_b in abp_gaps:
        abp_pieces.append((abp_previous, abp_a))
        abp_previous = abp_b
    abp_pieces.append((abp_previous, len(abp_thin)))
    return abp_pieces, abp_gaps


def abp__part(abp_s: abpSegment, abp_a: float, abp_b: float) -> abpSegment:
    def abp_at(abp_t: float) -> abpPoint:
        return abpPoint(
            abp_s.abp_start.abp_x + abp_t * (abp_s.abp_end.abp_x - abp_s.abp_start.abp_x),
            abp_s.abp_start.abp_y + abp_t * (abp_s.abp_end.abp_y - abp_s.abp_start.abp_y),
        )

    return abpSegment(abp_at(abp_a), abp_at(abp_b))


def abp__with_obstacles(
    abp_detection: abpAutoDetection,
    abp_image: abpRGBImage,
    abp_vector: abpVectorPlan | None,
    abp_scale: float,
) -> abpAutoDetection:
    abp_plan = abpFloorPlan(
        abp_scale_m_per_px=abp_scale,
        abp_walls=abp_detection.abp_walls,
        abp_doors=abp_detection.abp_doors,
        abp_exits=abp_detection.abp_exits,
        abp_stairs=abp_detection.abp_stairs,
    )
    if abp_vector is not None:
        abp_plan = abp_adjust_doors(abp_plan, abp_read_tags(abp_vector.abp_texts))
    abp_shapes = abp_detect_obstacles(
        abp_plan, abp_image=abp_image if abp_vector is None else None, abp_vector=abp_vector
    )
    abp_obstacles = [abpObstacle(abp_s, abp_confirmed=False) for abp_s in abp_shapes]
    if abp_vector is not None:
        abp_obstacles += abp__free_columns(abp_plan, abp_vector, abp_scale)
        abp_plan = dataclasses.replace(abp_plan, abp_obstacles=tuple(abp_obstacles))
        abp_names = abp_furniture_names(abp_plan, abp_vector.abp_texts)
        abp_obstacles = [
            dataclasses.replace(abp_o, abp_name=abp_n)
            for abp_o, abp_n in zip(abp_obstacles, abp_names, strict=True)
        ]
    return abpAutoDetection(
        abp_detection.abp_walls,
        abp_plan.abp_doors,
        abp_plan.abp_exits,
        abp_plan.abp_stairs,
        tuple(abp_obstacles),
        abp_detection.abp_method,
    )


def abp__free_columns(
    abp_plan: abpFloorPlan, abp_vector: abpVectorPlan, abp_scale: float
) -> list[abpObstacle]:
    abp_walls = abp__array([abp_w.abp_segment for abp_w in abp_plan.abp_walls]) * abp_scale
    abp_out: list[abpObstacle] = []
    for abp_box in abp_find_columns(abp_vector, abp_scale):
        abp_center = abp_box.mean(axis=0)
        if float(abp_point_segments_distance(abp_center, abp_walls).min()) > abp_FREE_COLUMN_M:
            abp_out.append(
                abpObstacle(
                    abp__polygon(abp_box / abp_scale), abp_confirmed=False, abp_name="Columna"
                )
            )
    return abp_out


def abp__confidence(abp_opening: abpDoor | abpExit) -> float:
    return abp_opening.abp_confidence if isinstance(abp_opening, abpDoor) else 0.7


def abp__array(abp_segments: Sequence[abpSegment]) -> abpFloatArray:
    abp_rows = [
        (abp_s.abp_start.abp_x, abp_s.abp_start.abp_y, abp_s.abp_end.abp_x, abp_s.abp_end.abp_y)
        for abp_s in abp_segments
    ]
    return np.array(abp_rows, np.float64).reshape(-1, 4)


def abp__polygon(abp_points: abpFloatArray) -> abpPolygon:
    return abpPolygon(tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_points))


def abp__segment(abp_s: abpFloatArray) -> abpSegment:
    return abpSegment(
        abpPoint(float(abp_s[0]), float(abp_s[1])), abpPoint(float(abp_s[2]), float(abp_s[3]))
    )
