from __future__ import annotations

import dataclasses
import hashlib
import tempfile
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_domain.abp_enums import abpSignKind, abpStairUse, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import (
    abpExit,
    abpFloorPlan,
    abpObstacle,
    abpRoom,
    abpSafeZone,
    abpSign,
    abpStair,
)
from abp_rutasegura.abp_domain.abp_vector import abpPdfPage, abpVectorPlan
from abp_rutasegura.abp_engines.abp_cad.abp_reader import (
    abp_CAD_SUFFIXES,
    abp_convert,
    abp_list_sheets,
    abpCadFileError,
)
from abp_rutasegura.abp_engines.abp_navigation.abp_rooms import abp_detect_rooms
from abp_rutasegura.abp_engines.abp_vision.abp_auto import (
    abp_detect_auto,
    abp_sheet_scale,
    abp_stairs_in,
)
from abp_rutasegura.abp_engines.abp_vision.abp_images import (
    abp_IMAGE_SUFFIXES,
    abp_load_plan_file,
    abp_page_count,
    abp_PDF_SUFFIX,
    abpPlanFileError,
)
from abp_rutasegura.abp_engines.abp_vision.abp_inventory import abp_build_inventory, abpPlanElement
from abp_rutasegura.abp_engines.abp_vision.abp_layered import abp_detect_drawing
from abp_rutasegura.abp_engines.abp_vision.abp_obstacles import abp_shape_at
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import (
    abp_inspect_pdf,
    abp_is_furniture_layer,
    abp_is_structure_layer,
    abp_read_blocks,
    abp_read_vector,
    abp_render_page,
    abp_thicken_lines,
    abp_thumbnail,
)
from abp_rutasegura.abp_engines.abp_vision.abp_rectify import abp_rectify
from abp_rutasegura.abp_engines.abp_vision.abp_room_labels import (
    abp_label_anchors,
    abp_read_room_labels,
    abpRoomLabel,
)
from abp_rutasegura.abp_engines.abp_vision.abp_scale import abp_scale_from_reference
from abp_rutasegura.abp_engines.abp_vision.abp_scale_check import abp_scale_factor
from abp_rutasegura.abp_engines.abp_vision.abp_symbols import abp_find_signs, abpFoundSigns

abpImage = npt.NDArray[np.uint8]
abpRect = tuple[float, float, float, float]
abp_CROP_MARGIN_M = 2.0
abp_NEAR_BUILDING_M = 4.0
abp_MIN_SCALE_FIX = 0.08
abp_ZONE_REACH_M = 40.0

__all__ = [
    "abpLoadedPlan",
    "abpPdfPage",
    "abpPlanElement",
    "abpPlanImportService",
    "abpRoomLabel",
    "abpVectorPlan",
]


@dataclass(frozen=True, eq=False, slots=True)
class abpLoadedPlan:
    abp_image: abpImage
    abp_vector: abpVectorPlan | None = None
    abp_signs: tuple[abpSign, ...] = ()
    abp_zones: tuple[abpSafeZone, ...] = ()
    abp_written_scale: float | None = None

    @property
    def abp_scale_m_per_px(self) -> float | None:
        return abp_sheet_scale(self.abp_vector)


class abpPlanImportService:
    @staticmethod
    def abp_supported_suffixes() -> tuple[str, ...]:
        return (*sorted(abp_IMAGE_SUFFIXES), abp_PDF_SUFFIX, *abp_CAD_SUFFIXES)

    @staticmethod
    def abp_page_count(abp_path: Path) -> int:
        try:
            return abp_page_count(abp_path)
        except abpPlanFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_load(abp_path: Path, abp_page: int = 0) -> abpImage:
        try:
            return abp_load_plan_file(abp_path, abp_page)
        except abpPlanFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_is_cad(abp_path: Path) -> bool:
        return abp_path.suffix.lower() in abp_CAD_SUFFIXES

    @staticmethod
    def abp_cad_sheets(abp_path: Path) -> tuple[str, ...]:
        try:
            return abp_list_sheets(abp_path)
        except abpCadFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_cad_to_pdf(abp_path: Path, abp_sheets: Sequence[str] = ()) -> Path:
        try:
            abp_info = abp_path.stat()
            abp_key = f"{abp_path.resolve()}|{abp_info.st_size}|{abp_info.st_mtime_ns}|{'|'.join(abp_sheets)}"
            abp_name = hashlib.sha256(abp_key.encode("utf-8")).hexdigest()[:16]
            abp_folder = Path(tempfile.gettempdir()) / "RutaSegura" / abp_name
            abp_target = abp_folder / f"{abp_path.stem}.pdf"
            if not abp_target.exists():
                abp_folder.mkdir(parents=True, exist_ok=True)
                abp_partial = abp_folder / "parcial.pdf"
                abp_convert(abp_path, abp_partial, abp_sheets)
                abp_partial.replace(abp_target)
            return abp_target
        except abpCadFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo leer el plano de AutoCAD: {abp_exc}") from abp_exc

    @staticmethod
    def abp_is_pdf(abp_path: Path) -> bool:
        return abp_path.suffix.lower() == abp_PDF_SUFFIX

    @staticmethod
    def abp_pdf_pages(abp_path: Path) -> tuple[abpPdfPage, ...]:
        try:
            return abp_inspect_pdf(abp_path)
        except abpPlanFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_pdf_thumbnail(abp_path: Path, abp_page: int, abp_max_side: int = 220) -> abpImage:
        try:
            return abp_thumbnail(abp_path, abp_page, abp_max_side)
        except abpPlanFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_suggested_hidden_layers(abp_page: abpPdfPage) -> tuple[str, ...]:
        return tuple(
            abp_name
            for abp_name in abp_page.abp_layers
            if abp_name and not abp_is_structure_layer(abp_name)
        )

    @staticmethod
    def abp_load_pdf_page(
        abp_path: Path,
        abp_page: int,
        *,
        abp_hidden_layers: Collection[str] = (),
        abp_remove_colors: bool = False,
    ) -> abpLoadedPlan:
        try:
            abp_image = abp_render_page(
                abp_path,
                abp_page,
                abp_hidden_layers=abp_hidden_layers,
                abp_remove_colors=abp_remove_colors,
            )
            abp_vector = abp_read_vector(abp_path, abp_page)
        except abpPlanFileError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        abp_found = abpFoundSigns()
        abp_written: float | None = None
        if abp_vector is not None:
            abp_vector, abp_written = abp__checked_scale(abp_vector)
            abp_original = (
                abp_render_page(abp_path, abp_page)
                if abp_hidden_layers or abp_remove_colors
                else abp_image
            )
            abp_found = abp__with_capacities(
                abp_find_signs(abp_original, abp_vector, abp_read_blocks(abp_path, abp_page)),
                abp_vector,
            )
            abp_image = abp_thicken_lines(abp_image)
            abp_vector = abp_vector.abp_without_layers(
                [abp_n for abp_n in abp_hidden_layers if not abp_is_furniture_layer(abp_n)]
            )
        return abpLoadedPlan(
            abp_image, abp_vector, abp_found.abp_signs, abp_found.abp_zones, abp_written
        )

    @staticmethod
    def abp_suggest_crop(abp_loaded: abpLoadedPlan) -> abpRect | None:
        abp_vector, abp_scale = abp_loaded.abp_vector, abp_loaded.abp_scale_m_per_px
        if abp_vector is None or abp_scale is None:
            return None
        abp_bounds = abp_detect_drawing(
            abp_vector, abp_scale, abp_anchors_px=abp_label_anchors(abp_vector.abp_texts)
        ).abp_bounds
        if abp_bounds is None:
            return None
        abp_margin = abp_CROP_MARGIN_M / abp_scale
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]
        abp_x0, abp_y0, abp_x1, abp_y1 = abp_bounds
        abp_near = [
            (abp_p, abp_ZONE_REACH_M / abp_scale)
            for abp_z in abp_loaded.abp_zones
            for abp_p in abp_z.abp_area.abp_vertices
        ]
        abp_near += [
            (abp_s.abp_position, abp_NEAR_BUILDING_M / abp_scale) for abp_s in abp_loaded.abp_signs
        ]
        for abp_p, abp_reach in abp_near:
            if (
                abp_x0 - abp_reach <= abp_p.abp_x <= abp_x1 + abp_reach
                and abp_y0 - abp_reach <= abp_p.abp_y <= abp_y1 + abp_reach
            ):
                abp_x0, abp_y0, abp_x1, abp_y1 = (
                    min(abp_x0, abp_p.abp_x),
                    min(abp_y0, abp_p.abp_y),
                    max(abp_x1, abp_p.abp_x),
                    max(abp_y1, abp_p.abp_y),
                )
        return (
            max(0.0, abp_x0 - abp_margin),
            max(0.0, abp_y0 - abp_margin),
            min(float(abp_w), abp_x1 + abp_margin),
            min(float(abp_h), abp_y1 + abp_margin),
        )

    @staticmethod
    def abp_rotate(abp_loaded: abpLoadedPlan, abp_turns: int) -> abpLoadedPlan:
        abp_turns %= 4
        if abp_turns == 0:
            return abp_loaded
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]

        def abp_moved(abp_p: abpPoint) -> abpPoint:
            return abp_rotate_point(abp_p, abp_w, abp_h, abp_turns)

        return abpLoadedPlan(
            np.ascontiguousarray(np.rot90(abp_loaded.abp_image, -abp_turns)),
            abp_loaded.abp_vector.abp_rotated(abp_turns)
            if abp_loaded.abp_vector is not None
            else None,
            tuple(
                abp__turned_sign(abp_s, abp_moved(abp_s.abp_position), abp_turns)
                for abp_s in abp_loaded.abp_signs
            ),
            tuple(
                abpSafeZone(
                    abpPolygon(tuple(abp_moved(abp_v) for abp_v in abp_z.abp_area.abp_vertices)),
                    abp_z.abp_name,
                )
                for abp_z in abp_loaded.abp_zones
            ),
            abp_loaded.abp_written_scale,
        )

    @staticmethod
    def abp_suggested_turns(abp_loaded: abpLoadedPlan) -> int:
        if abp_loaded.abp_vector is None:
            return 0
        abp_votes = [0.0] * 4
        for abp_t in abp_loaded.abp_vector.abp_texts:
            abp_votes[round(abp_t.abp_angle_deg / 90) % 4] += len(abp_t.abp_text)
        abp_best = max(range(4), key=lambda abp_k: abp_votes[abp_k])
        return (4 - abp_best) % 4 if abp_votes[abp_best] > 1.5 * abp_votes[0] else 0

    @staticmethod
    def abp_rotate_plan(
        abp_plan: abpFloorPlan, abp_size: tuple[int, int], abp_turns: int
    ) -> abpFloorPlan:
        abp_turns %= 4
        if abp_turns == 0:
            return abp_plan
        abp_w, abp_h = abp_size

        def abp_point(abp_p: abpPoint) -> abpPoint:
            return abp_rotate_point(abp_p, abp_w, abp_h, abp_turns)

        def abp_segment(abp_x: abpSegment) -> abpSegment:
            return abpSegment(abp_point(abp_x.abp_start), abp_point(abp_x.abp_end))

        def abp_area(abp_x: abpPolygon) -> abpPolygon:
            return abpPolygon(tuple(abp_point(abp_v) for abp_v in abp_x.abp_vertices))

        abp_edit = dataclasses.replace
        return abp_edit(
            abp_plan,
            abp_walls=tuple(
                abp_edit(abp_x, abp_segment=abp_segment(abp_x.abp_segment))
                for abp_x in abp_plan.abp_walls
            ),
            abp_doors=tuple(
                abp_edit(abp_x, abp_segment=abp_segment(abp_x.abp_segment))
                for abp_x in abp_plan.abp_doors
            ),
            abp_exits=tuple(
                abp_edit(abp_x, abp_segment=abp_segment(abp_x.abp_segment))
                for abp_x in abp_plan.abp_exits
            ),
            abp_stairs=tuple(
                abp_edit(
                    abp_x,
                    abp_area=abp_area(abp_x.abp_area),
                    abp_entry=abp_point(abp_x.abp_entry) if abp_x.abp_entry else None,
                )
                for abp_x in abp_plan.abp_stairs
            ),
            abp_obstacles=tuple(
                abp_edit(abp_x, abp_area=abp_area(abp_x.abp_area))
                for abp_x in abp_plan.abp_obstacles
            ),
            abp_safe_zones=tuple(
                abp_edit(abp_x, abp_area=abp_area(abp_x.abp_area))
                for abp_x in abp_plan.abp_safe_zones
            ),
            abp_rooms=tuple(
                abp_edit(abp_x, abp_area=abp_area(abp_x.abp_area)) for abp_x in abp_plan.abp_rooms
            ),
            abp_signs=tuple(
                abp__turned_sign(abp_x, abp_point(abp_x.abp_position), abp_turns)
                for abp_x in abp_plan.abp_signs
            ),
        )

    @staticmethod
    def abp_rotate_image(abp_image: abpImage, abp_turns: int) -> abpImage:
        return np.ascontiguousarray(np.rot90(abp_image, -(abp_turns % 4)))

    @staticmethod
    def abp_crop(abp_loaded: abpLoadedPlan, abp_rect: abpRect) -> abpLoadedPlan:
        abp_h, abp_w = abp_loaded.abp_image.shape[:2]
        abp_x0, abp_x1 = sorted(
            (int(min(max(abp_rect[0], 0), abp_w)), int(min(max(abp_rect[2], 0), abp_w)))
        )
        abp_y0, abp_y1 = sorted(
            (int(min(max(abp_rect[1], 0), abp_h)), int(min(max(abp_rect[3], 0), abp_h)))
        )
        if abp_x1 - abp_x0 < 50 or abp_y1 - abp_y0 < 50:
            raise abpUserFacingError("El recorte es demasiado pequeño: abarque todo el plano.")
        abp_vector = abp_loaded.abp_vector

        def abp_inside(abp_p: abpPoint) -> bool:
            return abp_x0 <= abp_p.abp_x <= abp_x1 and abp_y0 <= abp_p.abp_y <= abp_y1

        def abp_moved(abp_p: abpPoint) -> abpPoint:
            return abpPoint(abp_p.abp_x - abp_x0, abp_p.abp_y - abp_y0)

        return abpLoadedPlan(
            np.ascontiguousarray(abp_loaded.abp_image[abp_y0:abp_y1, abp_x0:abp_x1]),
            abp_vector.abp_cropped(abp_x0, abp_y0, abp_x1, abp_y1)
            if abp_vector is not None
            else None,
            tuple(
                dataclasses.replace(abp_s, abp_position=abp_moved(abp_s.abp_position))
                for abp_s in abp_loaded.abp_signs
                if abp_inside(abp_s.abp_position)
            ),
            tuple(
                abpSafeZone(
                    abpPolygon(tuple(abp_moved(abp_v) for abp_v in abp_z.abp_area.abp_vertices)),
                    abp_z.abp_name,
                )
                for abp_z in abp_loaded.abp_zones
                if abp_inside(abp_z.abp_area.abp_centroid)
            ),
            abp_loaded.abp_written_scale,
        )

    @staticmethod
    def abp_room_labels(abp_vector: abpVectorPlan | None) -> tuple[abpRoomLabel, ...]:
        return abp_read_room_labels(abp_vector.abp_texts) if abp_vector is not None else ()

    @staticmethod
    def abp_straighten(abp_image: abpImage, abp_corners: Sequence[abpPoint]) -> abpImage:
        try:
            return abp_rectify(abp_image, abp_corners)
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_scale_from_reference(abp_p1: abpPoint, abp_p2: abpPoint, abp_meters: float) -> float:
        try:
            return abp_scale_from_reference(abp_p1, abp_p2, abp_meters)
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc

    @staticmethod
    def abp_detect(
        abp_image: abpImage,
        abp_plan: abpFloorPlan,
        *,
        abp_allow_diagonal: bool = False,
        abp_vector: abpVectorPlan | None = None,
    ) -> abpFloorPlan:
        abp_found = abp_detect_auto(
            abp_image,
            abp_scale_m_per_px=abp_plan.abp_scale_m_per_px,
            abp_vector=abp_vector,
            abp_orthogonal_only=not abp_allow_diagonal,
        )
        abp_kept = tuple(abp_o for abp_o in abp_plan.abp_obstacles if abp_o.abp_confirmed)
        return dataclasses.replace(
            abp_plan,
            abp_walls=abp_found.abp_walls,
            abp_doors=abp_found.abp_doors,
            abp_exits=abp__new_exits(abp_plan, abp_found.abp_exits),
            abp_stairs=abp_plan.abp_stairs
            or abp__for_level(abp_found.abp_stairs, abp_plan.abp_level),
            abp_obstacles=(
                *abp_kept,
                *(
                    abp_o
                    for abp_o in abp_found.abp_obstacles
                    if not abp__repeated(abp_o, abp_kept) and not abp__under_sign(abp_o, abp_plan)
                ),
            ),
        )

    @staticmethod
    def abp_analyze_stairs(
        abp_plan: abpFloorPlan, abp_vector: abpVectorPlan | None
    ) -> abpFloorPlan:
        abp_found = (
            list(abp__for_level(abp_stairs_in(abp_plan, abp_vector), abp_plan.abp_level))
            if abp_vector is not None
            else []
        )
        abp_out: list[abpStair] = []
        for abp_stair in abp_plan.abp_stairs:
            abp_mine = [
                abp_f for abp_f in abp_found if abp__overlaps(abp_f.abp_area, abp_stair.abp_area)
            ]
            abp_found = [abp_f for abp_f in abp_found if abp_f not in abp_mine]
            if abp_stair.abp_use is not abpStairUse.abp_AUTO or not abp_mine:
                abp_out.append(abp_stair)
                continue
            abp_mine.sort(
                key=lambda abp_f: (
                    abp_f.abp_use is abpStairUse.abp_SAME_FLOOR,
                    -abp_f.abp_area.abp_area,
                )
            )
            abp_out.append(
                dataclasses.replace(
                    abp_mine[0],
                    abp_name=abp_stair.abp_name,
                    abp_confirmed=abp_stair.abp_confirmed,
                    abp_leads_to=abp_stair.abp_leads_to,
                )
            )
            abp_out += [
                dataclasses.replace(abp_f, abp_confirmed=abp_stair.abp_confirmed)
                for abp_f in abp_mine[1:]
            ]
        abp_out += abp_found
        abp_named: list[abpStair] = []
        abp_used = {abp_s.abp_name for abp_s in abp_out if abp_s.abp_name}
        for abp_stair in abp_out:
            if not abp_stair.abp_name and abp_stair.abp_confirmed:
                abp_stem = (
                    "Gradas" if abp_stair.abp_use is abpStairUse.abp_SAME_FLOOR else "Escalera"
                )
                abp_name = next(
                    f"{abp_stem} {abp_c}"
                    for abp_c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    if f"{abp_stem} {abp_c}" not in abp_used
                )
                abp_used.add(abp_name)
                abp_stair = dataclasses.replace(abp_stair, abp_name=abp_name)
            abp_named.append(abp_stair)
        return dataclasses.replace(abp_plan, abp_stairs=tuple(abp_named))

    @staticmethod
    def abp_inventory(
        abp_plan: abpFloorPlan, abp_vector: abpVectorPlan | None
    ) -> tuple[abpPlanElement, ...]:
        return abp_build_inventory(abp_plan, abp_vector)

    @staticmethod
    def abp_sheet_scale(abp_vector: abpVectorPlan | None) -> float | None:
        return abp_sheet_scale(abp_vector)

    @staticmethod
    def abp_shape_at(
        abp_plan: abpFloorPlan,
        abp_point: abpPoint,
        abp_image: abpImage | None,
        abp_vector: abpVectorPlan | None,
    ) -> abpPolygon | None:
        if abp_vector is not None:
            abp_found = abp_shape_at(abp_plan, abp_point, abp_vector=abp_vector)
            if abp_found is not None:
                return abp_found
        return (
            abp_shape_at(abp_plan, abp_point, abp_image=abp_image)
            if abp_image is not None
            else None
        )

    @staticmethod
    def abp_detect_rooms(
        abp_plan: abpFloorPlan,
        abp_use: abpUseType,
        abp_name_template: str,
        *,
        abp_labels: Sequence[abpRoomLabel] = (),
    ) -> abpFloorPlan:
        try:
            abp_polygons = abp_detect_rooms(abp_plan)
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        abp_used = {abp_r.abp_name for abp_r in abp_plan.abp_rooms}
        abp_taken_centers = [abp_r.abp_area.abp_centroid for abp_r in abp_plan.abp_rooms]
        abp_rooms = list(abp_plan.abp_rooms)
        abp_number = 1
        for abp_polygon in abp_polygons:
            abp_center = abp_polygon.abp_centroid
            if (
                any(
                    abp__inside(abp_r.abp_area.abp_vertices, abp_center)
                    for abp_r in abp_plan.abp_rooms
                )
                or abp_center in abp_taken_centers
            ):
                continue
            abp_label = abp_label_inside(abp_polygon, abp_labels)
            abp_name = abp_label.abp_name if abp_label is not None else ""
            if abp_name in abp_used:
                abp_name = next(
                    f"{abp_name} ({abp_k})"
                    for abp_k in range(2, 100)
                    if f"{abp_name} ({abp_k})" not in abp_used
                )
            if not abp_name:
                while abp_name_template.format(number=abp_number) in abp_used:
                    abp_number += 1
                abp_name = abp_name_template.format(number=abp_number)
            abp_used.add(abp_name)
            abp_rooms.append(abpRoom(abp_name, abp_use, abp_polygon))
        return dataclasses.replace(abp_plan, abp_rooms=tuple(abp_rooms))


def abp__for_level(abp_stairs: Sequence[abpStair], abp_level: int) -> tuple[abpStair, ...]:
    if abp_level == 0:
        return tuple(abp_stairs)
    return tuple(
        dataclasses.replace(abp_s, abp_use=abpStairUse.abp_AUTO, abp_entry=None)
        if abp_s.abp_use is abpStairUse.abp_UP
        else abp_s
        for abp_s in abp_stairs
    )


def abp__overlaps(abp_a: abpPolygon, abp_b: abpPolygon) -> bool:
    abp_xs, abp_ys = (
        [abp_v.abp_x for abp_v in abp_a.abp_vertices],
        [abp_v.abp_y for abp_v in abp_a.abp_vertices],
    )
    abp_grid = [
        abpPoint(
            min(abp_xs) + (max(abp_xs) - min(abp_xs)) * abp_i / 8,
            min(abp_ys) + (max(abp_ys) - min(abp_ys)) * abp_j / 8,
        )
        for abp_i in range(9)
        for abp_j in range(9)
    ]
    abp_own = [abp_p for abp_p in abp_grid if abp__inside(abp_a.abp_vertices, abp_p)]
    return bool(abp_own) and sum(
        abp__inside(abp_b.abp_vertices, abp_p) for abp_p in abp_own
    ) > 0.5 * len(abp_own)


def abp_rotate_point(
    abp_p: abpPoint, abp_width: float, abp_height: float, abp_turns: int
) -> abpPoint:
    for _ in range(abp_turns % 4):
        abp_p, abp_width, abp_height = (
            abpPoint(abp_height - abp_p.abp_y, abp_p.abp_x),
            abp_height,
            abp_width,
        )
    return abp_p


def abp__turned_sign(abp_sign: abpSign, abp_position: abpPoint, abp_turns: int) -> abpSign:
    abp_angle = abp_sign.abp_rotation_deg
    if abp_sign.abp_kind is abpSignKind.abp_DIRECTION:
        abp_angle = (abp_angle + 90.0 * abp_turns) % 360.0
    return dataclasses.replace(abp_sign, abp_position=abp_position, abp_rotation_deg=abp_angle)


def abp__checked_scale(abp_vector: abpVectorPlan) -> tuple[abpVectorPlan, float | None]:
    abp_written = abp_vector.abp_scale_denominator
    if abp_written is None or abp_vector.abp_exact_scale:
        return abp_vector, None
    abp_factor = abp_scale_factor(abp_vector, 0.0254 / abp_vector.abp_dpi * abp_written)
    if abp_factor is None or abs(abp_factor - 1.0) < abp_MIN_SCALE_FIX:
        return abp_vector, None
    return dataclasses.replace(
        abp_vector, abp_scale_denominator=round(abp_written * abp_factor, 2)
    ), abp_written


def abp_label_inside(
    abp_polygon: abpPolygon, abp_labels: Sequence[abpRoomLabel]
) -> abpRoomLabel | None:
    abp_inside = [
        abp_q
        for abp_q in abp_labels
        if abp__inside(abp_polygon.abp_vertices, abpPoint(abp_q.abp_x, abp_q.abp_y))
    ]
    if not abp_inside:
        return None
    return max(
        abp_inside,
        key=lambda abp_q: (abp_q.abp_capacity is not None, abp_q.abp_area_m2 is not None),
    )


def abp__with_capacities(abp_found: abpFoundSigns, abp_vector: abpVectorPlan) -> abpFoundSigns:
    abp_labels = [
        abp_q for abp_q in abp_read_room_labels(abp_vector.abp_texts) if abp_q.abp_capacity
    ]
    if not abp_labels:
        return abp_found

    def abp_filled(abp_sign: abpSign) -> abpSign:
        if abp_sign.abp_kind is not abpSignKind.abp_CAPACITY or abp_sign.abp_text:
            return abp_sign
        abp_nearest = min(
            abp_labels,
            key=lambda abp_q: abp_sign.abp_position.abp_distance_to(
                abpPoint(abp_q.abp_x, abp_q.abp_y)
            ),
        )
        return dataclasses.replace(abp_sign, abp_text=str(abp_nearest.abp_capacity))

    return abpFoundSigns(
        tuple(abp_filled(abp_s) for abp_s in abp_found.abp_signs), abp_found.abp_zones
    )


def abp__under_sign(abp_obstacle: abpObstacle, abp_plan: abpFloorPlan) -> bool:
    abp_scale = abp_plan.abp_scale_m_per_px or 1.0
    abp_size = abp_obstacle.abp_area.abp_area * abp_scale * abp_scale
    abp_center = abp_obstacle.abp_area.abp_centroid
    return abp_size < 1.2 and any(
        abp_s.abp_position.abp_distance_to(abp_center) * abp_scale < 0.45
        or abp__inside(abp_obstacle.abp_area.abp_vertices, abp_s.abp_position)
        for abp_s in abp_plan.abp_signs
    )


def abp__repeated(abp_obstacle: abpObstacle, abp_others: Sequence[abpObstacle]) -> bool:
    abp_center = abp_obstacle.abp_area.abp_centroid
    return any(abp__inside(abp_o.abp_area.abp_vertices, abp_center) for abp_o in abp_others)


def abp__new_exits(abp_plan: abpFloorPlan, abp_proposals: Sequence[abpExit]) -> tuple[abpExit, ...]:
    abp_confirmed = [abp_e for abp_e in abp_plan.abp_exits if abp_e.abp_confirmed]
    abp_near = (1.0 / abp_plan.abp_scale_m_per_px) if abp_plan.abp_scale_m_per_px else 40.0
    abp_used = {abp_e.abp_name for abp_e in abp_confirmed}
    abp_renamed: list[abpExit] = []
    abp_number = 1
    for abp_exit_ in abp_proposals:
        abp_middle = abp_exit_.abp_segment.abp_midpoint
        if any(
            abp_middle.abp_distance_to(abp_c.abp_segment.abp_midpoint) <= abp_near
            for abp_c in abp_confirmed
        ):
            continue
        while f"Salida {abp_number}" in abp_used:
            abp_number += 1
        abp_used.add(f"Salida {abp_number}")
        abp_renamed.append(dataclasses.replace(abp_exit_, abp_name=f"Salida {abp_number}"))
    return (*abp_confirmed, *abp_renamed)


def abp__inside(abp_vertices: tuple[abpPoint, ...], abp_p: abpPoint) -> bool:
    abp_inside = False
    abp_j = len(abp_vertices) - 1
    for abp_i, abp_vi in enumerate(abp_vertices):
        abp_vj = abp_vertices[abp_j]
        if (abp_vi.abp_y > abp_p.abp_y) != (abp_vj.abp_y > abp_p.abp_y):
            abp_x_cross = (abp_vj.abp_x - abp_vi.abp_x) * (abp_p.abp_y - abp_vi.abp_y) / (
                abp_vj.abp_y - abp_vi.abp_y
            ) + abp_vi.abp_x
            if abp_p.abp_x < abp_x_cross:
                abp_inside = not abp_inside
        abp_j = abp_i
    return abp_inside
