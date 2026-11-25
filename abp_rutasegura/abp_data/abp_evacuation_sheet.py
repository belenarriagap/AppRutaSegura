from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import numpy.typing as npt
from matplotlib import get_data_path
from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A1, A2, A3, A4, landscape, portrait
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from abp_rutasegura.abp_data.abp_report_pdf import abp__register_fonts, abp_FONT, abp_FONT_BOLD
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan, abpSign
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS, abpSignArt

abp_SHEET_SIZES = {"A4": A4, "A3": A3, "A2": A2, "A1": A1}
abp_SHEET_FACTOR = {"A4": 0.74, "A3": 1.0, "A2": 1.3, "A1": 1.7}
abp_SCALES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000)
abp_FONT_ITALIC = "DejaVuSans-BoldOblique"

abp_INK = colors.HexColor("#111111")
abp_GRAY = colors.HexColor("#8f979c")
abp_LIGHT = colors.HexColor("#c9ced1")
abp_ROUTE = colors.HexColor("#16e03a")
abp_ROUTE_EDGE = colors.HexColor("#0a7d22")
abp_NOTE_GREEN = colors.HexColor("#0a7d22")
abp_RED = colors.HexColor("#d7181f")
abp_MEETING = colors.HexColor("#f6e300")

abpImage = npt.NDArray[np.uint8]
abpPt = tuple[float, float]


@dataclass(frozen=True)
class abpSheetOptions:
    abp_paper: str = "A3"
    abp_scale: int | None = None
    abp_title: str = "MAPA DE EVACUACIÓN Y SEÑALIZACIÓN"
    abp_code: str = "ES"
    abp_specialist: str = ""
    abp_drafter: str = ""
    abp_sector: str = ""
    abp_north_deg: float = 0.0
    abp_flow: float = 1.3
    abp_speed: float = 0.6
    abp_people_source: str = "aforo"
    abp_underlay: str = "original"
    abp_follow_furniture: bool = True
    abp_propose_signs: bool = True
    abp_orientation: str = "auto"
    abp_tables: str = "auto"
    abp_identify: str = "ambiente"
    abp_note: str = ""
    abp_made_on: date = field(default_factory=date.today)


@dataclass(frozen=True)
class abpRoomNote:
    abp_room_name: str
    abp_level: int
    abp_people: int
    abp_door_width_m: float
    abp_distance_m: float
    abp_time_s: float
    abp_route_id: str
    abp_exit_name: str


@dataclass(frozen=True)
class abpRouteSummary:
    abp_route_id: str
    abp_exit_name: str
    abp_people: int
    abp_distance_m: float
    abp_time_s: float
    abp_room_name: str = ""


@dataclass(frozen=True)
class abpZoneSummary:
    abp_number: int
    abp_name: str
    abp_radius_m: float
    abp_people: int
    abp_distance_m: float
    abp_time_s: float
    abp_route_ids: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class abpSheetFloor:
    abp_plan: abpFloorPlan
    abp_network: abpEvacuationNetwork
    abp_notes: tuple[abpRoomNote, ...]
    abp_signs: tuple[abpSign, ...]
    abp_image: abpImage | None = None


@dataclass(frozen=True, eq=False)
class abpSheetContent:
    abp_project: abpProject
    abp_floors: tuple[abpSheetFloor, ...]
    abp_routes: tuple[abpRouteSummary, ...]
    abp_options: abpSheetOptions
    abp_level_names: tuple[str, ...] = ()
    abp_zones: tuple[abpZoneSummary, ...] = ()
    abp_simulated_s: float | None = None
    abp_app_version: str = ""


def abp__fonts() -> None:
    abp__register_fonts()
    if abp_FONT_ITALIC not in pdfmetrics.getRegisteredFontNames():
        abp_folder = Path(get_data_path()) / "fonts" / "ttf"
        pdfmetrics.registerFont(TTFont(abp_FONT_ITALIC, str(abp_folder / f"{abp_FONT_ITALIC}.ttf")))


@dataclass(frozen=True)
class abp__View:
    abp_k: float
    abp_x0: float
    abp_y0: float
    abp_min_x: float
    abp_max_y: float

    def abp_p(self, abp_point: abpPoint) -> abpPt:
        return self.abp_x0 + (abp_point.abp_x - self.abp_min_x) * self.abp_k, self.abp_y0 + (
            self.abp_max_y - abp_point.abp_y
        ) * self.abp_k


@dataclass(frozen=True)
class abp__Box:
    abp_x: float
    abp_y: float
    abp_w: float
    abp_h: float


def abp_format_time(abp_seconds: float) -> str:
    abp_total = round(abp_seconds)
    abp_minutes, abp_rest = divmod(abp_total, 60)
    return f"{abp_minutes} min {abp_rest:02d} seg" if abp_minutes else f"{abp_rest} seg"


def abp_plan_bounds_m(abp_floor: abpSheetFloor) -> tuple[float, float, float, float]:
    abp_plan = abp_floor.abp_plan
    abp_s = abp_plan.abp_scale_m_per_px or 1.0
    abp_points: list[abpPoint] = []
    for abp_seg in (
        [abp_w.abp_segment for abp_w in abp_plan.abp_walls]
        + [abp_d.abp_segment for abp_d in abp_plan.abp_doors]
        + [abp_e.abp_segment for abp_e in abp_plan.abp_exits]
    ):
        abp_points += [abp_seg.abp_start, abp_seg.abp_end]
    for abp_poly in (
        [abp_r.abp_area for abp_r in abp_plan.abp_rooms]
        + [abp_z.abp_area for abp_z in abp_plan.abp_safe_zones]
        + [abp_st.abp_area for abp_st in abp_plan.abp_stairs]
    ):
        abp_points += list(abp_poly.abp_vertices)
    abp_points += [abp_sign.abp_position for abp_sign in abp_floor.abp_signs]
    abp_xs = [abp_p.abp_x * abp_s for abp_p in abp_points] + [
        abp_p.abp_x for abp_b in abp_floor.abp_network.abp_branches for abp_p in abp_b.abp_points_m
    ]
    abp_ys = [abp_p.abp_y * abp_s for abp_p in abp_points] + [
        abp_p.abp_y for abp_b in abp_floor.abp_network.abp_branches for abp_p in abp_b.abp_points_m
    ]
    if not abp_xs:
        return 0.0, 0.0, 10.0, 10.0
    return min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)


def abp__building_bounds_m(abp_plan: abpFloorPlan) -> tuple[float, float, float, float]:
    abp_s = abp_plan.abp_scale_m_per_px or 1.0
    abp_segments = [abp_w.abp_segment for abp_w in abp_plan.abp_walls] or [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]
    abp_points = [
        abp_p for abp_seg in abp_segments for abp_p in (abp_seg.abp_start, abp_seg.abp_end)
    ]
    abp_points += [abp_v for abp_r in abp_plan.abp_rooms for abp_v in abp_r.abp_area.abp_vertices]
    if not abp_points:
        return 0.0, 0.0, 10.0, 10.0
    abp_xs, abp_ys = (
        [abp_p.abp_x * abp_s for abp_p in abp_points],
        [abp_p.abp_y * abp_s for abp_p in abp_points],
    )
    return min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)


def abp_best_scale(
    abp_width_m: float, abp_height_m: float, abp_width_pt: float, abp_height_pt: float
) -> int:
    for abp_denominator in abp_SCALES:
        abp_k = 1000.0 * mm / abp_denominator
        if abp_width_m * abp_k <= abp_width_pt and abp_height_m * abp_k <= abp_height_pt:
            return abp_denominator
    return abp_SCALES[-1]


def abp__wrap(abp_text: str, abp_font: str, abp_size: float, abp_width: float) -> list[str]:
    abp_lines: list[str] = []
    abp_line = ""
    for abp_word in abp_text.split():
        abp_candidate = f"{abp_line} {abp_word}".strip()
        if abp_line and pdfmetrics.stringWidth(abp_candidate, abp_font, abp_size) > abp_width:
            abp_lines.append(abp_line)
            abp_line = abp_word
        else:
            abp_line = abp_candidate
    return [*abp_lines, abp_line] if abp_line else abp_lines


def abp__fit(
    abp_text: str, abp_font: str, abp_size: float, abp_width: float, abp_smallest: float = 4.0
) -> float:
    while (
        abp_size > abp_smallest and pdfmetrics.stringWidth(abp_text, abp_font, abp_size) > abp_width
    ):
        abp_size -= 0.25
    return abp_size


def abp__shorten(abp_text: str, abp_font: str, abp_size: float, abp_width: float) -> str:
    if pdfmetrics.stringWidth(abp_text, abp_font, abp_size) <= abp_width:
        return abp_text
    while abp_text and pdfmetrics.stringWidth(abp_text + "…", abp_font, abp_size) > abp_width:
        abp_text = abp_text[:-1]
    return abp_text.rstrip() + "…"


def abp__poly_path(
    abp_c: Canvas, abp_points: Sequence[abpPt], *, abp_fill: int, abp_stroke: int
) -> None:
    abp_path = abp_c.beginPath()
    abp_path.moveTo(*abp_points[0])
    for abp_p in abp_points[1:]:
        abp_path.lineTo(*abp_p)
    abp_path.close()
    abp_c.drawPath(abp_path, stroke=abp_stroke, fill=abp_fill)


def abp_draw_sign(
    abp_c: Canvas,
    abp_art: abpSignArt,
    abp_x: float,
    abp_y: float,
    abp_size: float,
    abp_rotation: float,
    abp_text: str,
) -> None:
    abp_c.saveState()
    abp_c.translate(abp_x, abp_y)
    abp_c.rotate(-abp_rotation if abp_art.abp_rotates else 0.0)
    for abp_shape in abp_art.abp_shapes:
        abp_color = colors.HexColor(abp_shape.abp_color)
        abp_c.setFillColor(abp_color)
        abp_c.setStrokeColor(abp_color)
        abp_points = [
            (abp_px * abp_size, -abp_py * abp_size) for abp_px, abp_py in abp_shape.abp_points
        ]
        if abp_shape.abp_kind == "poly":
            abp__poly_path(abp_c, abp_points, abp_fill=1, abp_stroke=0)
        elif abp_shape.abp_kind == "circle":
            abp_c.circle(
                abp_points[0][0], abp_points[0][1], abp_shape.abp_size * abp_size, stroke=0, fill=1
            )
        elif abp_shape.abp_kind == "line":
            abp_c.setLineWidth(abp_shape.abp_size * abp_size)
            abp_c.setLineCap(1)
            abp_c.setLineJoin(1)
            abp_path = abp_c.beginPath()
            abp_path.moveTo(*abp_points[0])
            for abp_p in abp_points[1:]:
                abp_path.lineTo(*abp_p)
            abp_c.drawPath(abp_path, stroke=1, fill=0)
        else:
            abp_content = abp_shape.abp_text.format(text=abp_text)
            abp_height = abp_shape.abp_size * abp_size / 0.73
            abp_c.setFont(abp_FONT_BOLD, abp_height)
            abp_c.drawCentredString(
                abp_points[0][0], abp_points[0][1] - 0.365 * abp_height, abp_content
            )
    abp_c.restoreState()


def abp__draw_underlay(
    abp_c: Canvas, abp_floor: abpSheetFloor, abp_view: abp__View, abp_box: abp__Box
) -> bool:
    abp_image, abp_scale = abp_floor.abp_image, abp_floor.abp_plan.abp_scale_m_per_px
    if abp_image is None or abp_scale is None:
        return False
    abp_x0, abp_y0, abp_x1, abp_y1 = abp__building_bounds_m(abp_floor.abp_plan)
    abp_pad = 0.6
    abp_h, abp_w = abp_image.shape[:2]
    abp_left, abp_top = (
        max(0, int((abp_x0 - abp_pad) / abp_scale)),
        max(0, int((abp_y0 - abp_pad) / abp_scale)),
    )
    abp_right, abp_bottom = (
        min(abp_w, int((abp_x1 + abp_pad) / abp_scale) + 1),
        min(abp_h, int((abp_y1 + abp_pad) / abp_scale) + 1),
    )
    if abp_right - abp_left < 10 or abp_bottom - abp_top < 10:
        return False
    abp_part = abp_image[abp_top:abp_bottom, abp_left:abp_right].astype(np.float64)
    abp_gray = abp_part if abp_part.ndim == 2 else abp_part.mean(axis=2)
    abp_faded = (255.0 - (255.0 - abp_gray) * 0.65).astype(np.uint8)
    abp_a, abp_b = (
        abp_view.abp_p(abpPoint(abp_left * abp_scale, abp_bottom * abp_scale)),
        abp_view.abp_p(abpPoint(abp_right * abp_scale, abp_top * abp_scale)),
    )
    abp_c.saveState()
    abp_clip = abp_c.beginPath()
    abp_clip.rect(abp_box.abp_x, abp_box.abp_y, abp_box.abp_w, abp_box.abp_h)
    abp_c.clipPath(abp_clip, stroke=0, fill=0)
    abp_reader = ImageReader(PilImage.fromarray(abp_faded))
    abp_c.drawImage(abp_reader, abp_a[0], abp_a[1], abp_b[0] - abp_a[0], abp_b[1] - abp_a[1])
    abp_c.restoreState()
    return True


def abp__draw_clean_plan(
    abp_c: Canvas, abp_plan: abpFloorPlan, abp_view: abp__View, abp_named: Collection[str]
) -> None:
    abp_s = abp_plan.abp_scale_m_per_px or 1.0

    def abp_at(abp_p: abpPoint) -> abpPt:
        return abp_view.abp_p(abpPoint(abp_p.abp_x * abp_s, abp_p.abp_y * abp_s))

    abp_c.setLineCap(2)
    for abp_width, abp_color in ((0.17, abp_GRAY), (0.12, colors.white)):
        abp_c.setStrokeColor(abp_color)
        abp_c.setLineWidth(max(abp_width * abp_view.abp_k, 1.4 if abp_width > 0.15 else 0.7))
        for abp_wall in abp_plan.abp_walls:
            abp_a, abp_b = (
                abp_at(abp_wall.abp_segment.abp_start),
                abp_at(abp_wall.abp_segment.abp_end),
            )
            abp_c.line(*abp_a, *abp_b)
    abp_c.setLineCap(0)
    abp_c.setStrokeColor(abp_GRAY)
    abp_c.setLineWidth(0.5)
    for abp_seg in [abp_d.abp_segment for abp_d in abp_plan.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_plan.abp_exits
    ]:
        abp__draw_door(abp_c, abp_seg, abp_at)
    for abp_obstacle in abp_plan.abp_obstacles:
        abp_c.setFillColor(colors.HexColor("#eef0f1"))
        abp__poly_path(
            abp_c,
            [abp_at(abp_v) for abp_v in abp_obstacle.abp_area.abp_vertices],
            abp_fill=1,
            abp_stroke=1,
        )
    for abp_stair in abp_plan.abp_stairs:
        abp__draw_stair(abp_c, abp_stair.abp_area, abp_at, abp_view.abp_k)
    abp_c.setFillColor(abp_GRAY)
    for abp_room in abp_plan.abp_rooms:
        if abp_room.abp_name in abp_named:
            continue
        abp_x, abp_y = abp_at(abp_room.abp_area.abp_centroid)
        abp_c.setFont(abp_FONT, 6)
        abp_c.drawCentredString(abp_x, abp_y + 3, abp_room.abp_name.upper())


def abp__draw_door(abp_c: Canvas, abp_seg: abpSegment, abp_at: Callable[[abpPoint], abpPt]) -> None:
    abp_a, abp_b = abp_at(abp_seg.abp_start), abp_at(abp_seg.abp_end)
    abp_length = math.dist(abp_a, abp_b)
    if abp_length < 1:
        return
    abp_angle = math.degrees(math.atan2(abp_b[1] - abp_a[1], abp_b[0] - abp_a[0]))
    abp_c.saveState()
    abp_c.translate(*abp_a)
    abp_c.rotate(abp_angle)
    abp_c.setStrokeColor(colors.white)
    abp_c.setLineWidth(3.2)
    abp_c.line(0, 0, abp_length, 0)
    abp_c.setStrokeColor(abp_GRAY)
    abp_c.setLineWidth(0.6)
    abp_c.line(0, 0, 0, abp_length)
    abp_path = abp_c.beginPath()
    abp_path.arc(-abp_length, -abp_length, abp_length, abp_length, 0, 90)
    abp_c.drawPath(abp_path, stroke=1, fill=0)
    abp_c.restoreState()


def abp__draw_stair(
    abp_c: Canvas, abp_area: abpPolygon, abp_at: Callable[[abpPoint], abpPt], abp_k: float
) -> None:
    abp_points = [abp_at(abp_v) for abp_v in abp_area.abp_vertices]
    abp_c.setStrokeColor(abp_GRAY)
    abp_c.setLineWidth(0.5)
    abp__poly_path(abp_c, abp_points, abp_fill=0, abp_stroke=1)
    if len(abp_points) != 4:
        return
    abp_a, abp_b, abp_d = abp_points[0], abp_points[1], abp_points[3]
    if math.dist(abp_a, abp_b) < math.dist(abp_a, abp_d):
        abp_b, abp_d = abp_d, abp_b
    abp_steps = max(2, round(math.dist(abp_a, abp_b) / (0.28 * abp_k)))
    for abp_i in range(1, abp_steps):
        abp_t = abp_i / abp_steps
        abp_x, abp_y = (
            abp_a[0] + (abp_b[0] - abp_a[0]) * abp_t,
            abp_a[1] + (abp_b[1] - abp_a[1]) * abp_t,
        )
        abp_c.line(abp_x, abp_y, abp_x + abp_d[0] - abp_a[0], abp_y + abp_d[1] - abp_a[1])


def abp__arrow_unit(abp_c: Canvas, abp_a: abpPt, abp_b: abpPt, abp_width: float) -> None:
    abp_length = math.dist(abp_a, abp_b)
    if abp_length < 0.5:
        return
    abp_ux, abp_uy = (abp_b[0] - abp_a[0]) / abp_length, (abp_b[1] - abp_a[1]) / abp_length
    abp_head = min(abp_width * 1.9, abp_length * 0.7)
    abp_half, abp_wing = abp_width / 2, abp_width * 1.15

    def abp_at(abp_along: float, abp_across: float) -> abpPt:
        return abp_a[0] + abp_ux * abp_along - abp_uy * abp_across, abp_a[
            1
        ] + abp_uy * abp_along + abp_ux * abp_across

    abp_neck = abp_length - abp_head
    abp__poly_path(
        abp_c,
        [
            abp_at(0, abp_half),
            abp_at(abp_neck, abp_half),
            abp_at(abp_neck, abp_wing),
            abp_at(abp_length, 0),
            abp_at(abp_neck, -abp_wing),
            abp_at(abp_neck, -abp_half),
            abp_at(0, -abp_half),
        ],
        abp_fill=1,
        abp_stroke=1,
    )


def abp_draw_route(
    abp_c: Canvas, abp_points: Sequence[abpPt], abp_width: float, abp_every: float
) -> None:
    abp_c.setFillColor(abp_ROUTE)
    abp_c.setStrokeColor(abp_ROUTE_EDGE)
    abp_c.setLineWidth(max(0.25, abp_width * 0.06))
    abp_c.setLineJoin(0)
    for abp_a, abp_b in itertools.pairwise(abp_points):
        abp_length = math.dist(abp_a, abp_b)
        abp_n = max(1, round(abp_length / abp_every))
        for abp_i in range(abp_n):
            abp_p = (
                abp_a[0] + (abp_b[0] - abp_a[0]) * abp_i / abp_n,
                abp_a[1] + (abp_b[1] - abp_a[1]) * abp_i / abp_n,
            )
            abp_q = (
                abp_a[0] + (abp_b[0] - abp_a[0]) * (abp_i + 1) / abp_n,
                abp_a[1] + (abp_b[1] - abp_a[1]) * (abp_i + 1) / abp_n,
            )
            abp__arrow_unit(abp_c, abp_p, abp_q, abp_width)


def abp__route_badge(
    abp_c: Canvas, abp_x: float, abp_y: float, abp_text: str, abp_size: float
) -> None:
    abp_c.setStrokeColor(abp_RED)
    abp_c.setFillColor(colors.white)
    abp_c.setLineWidth(abp_size * 0.12)
    abp_c.circle(abp_x, abp_y, abp_size, stroke=1, fill=1)
    abp_c.setFillColor(abp_RED)
    abp_c.setFont(abp_FONT_BOLD, abp_size * 1.0)
    abp_c.drawCentredString(abp_x, abp_y - abp_size * 0.36, abp_text)


def abp__draw_meeting(
    abp_c: Canvas, abp_plan: abpFloorPlan, abp_view: abp__View, abp_u: float
) -> list[abp__Box]:
    abp_s = abp_plan.abp_scale_m_per_px or 1.0
    abp_boxes: list[abp__Box] = []
    for abp_zone in abp_plan.abp_safe_zones:
        abp_points = [
            abp_view.abp_p(abpPoint(abp_v.abp_x * abp_s, abp_v.abp_y * abp_s))
            for abp_v in abp_zone.abp_area.abp_vertices
        ]
        abp_xs, abp_ys = [abp_p[0] for abp_p in abp_points], [abp_p[1] for abp_p in abp_points]
        abp_cx, abp_cy = (min(abp_xs) + max(abp_xs)) / 2, (min(abp_ys) + max(abp_ys)) / 2
        abp_rx, abp_ry = (max(abp_xs) - min(abp_xs)) / 2, (max(abp_ys) - min(abp_ys)) / 2
        abp_c.saveState()
        abp_path = abp_c.beginPath()
        abp_path.ellipse(abp_cx - abp_rx, abp_cy - abp_ry, 2 * abp_rx, 2 * abp_ry)
        abp_c.setFillColor(
            colors.Color(abp_MEETING.red, abp_MEETING.green, abp_MEETING.blue, alpha=0.35)
        )
        abp_c.setStrokeColor(colors.HexColor("#b9a800"))
        abp_c.setLineWidth(1.0)
        abp_c.drawPath(abp_path, stroke=1, fill=1)
        abp_clip = abp_c.beginPath()
        abp_clip.ellipse(abp_cx - abp_rx, abp_cy - abp_ry, 2 * abp_rx, 2 * abp_ry)
        abp_c.clipPath(abp_clip, stroke=0, fill=0)
        abp_c.setStrokeColor(abp_MEETING)
        abp_c.setLineWidth(1.6 * abp_u)
        abp_x = abp_cx - abp_rx - 2 * abp_ry
        while abp_x < abp_cx + abp_rx:
            abp_c.line(abp_x, abp_cy - abp_ry, abp_x + 2 * abp_ry, abp_cy + abp_ry)
            abp_x += 5 * abp_u
        abp_c.restoreState()
        abp_lines = abp__wrap(
            (abp_zone.abp_name or "Zona de reunión").upper(), abp_FONT_BOLD, 8 * abp_u, 2 * abp_rx
        )
        abp_c.setFillColor(abp_INK)
        abp_c.setFont(abp_FONT_BOLD, 8 * abp_u)
        for abp_i, abp_line in enumerate(abp_lines):
            abp_c.drawCentredString(
                abp_cx, abp_cy + (len(abp_lines) / 2 - abp_i - 0.75) * 9 * abp_u, abp_line
            )
        abp_boxes.append(abp__Box(abp_cx - abp_rx, abp_cy - abp_ry, 2 * abp_rx, 2 * abp_ry))
    return abp_boxes


def abp__continues(
    abp_c: Canvas, abp_end: abpPt, abp_direction: abpPt, abp_width: float, abp_u: float
) -> None:
    abp_ux, abp_uy = abp_direction
    abp_x, abp_y = abp_end[0] + abp_ux * 3 * abp_u, abp_end[1] + abp_uy * 3 * abp_u
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.8 * abp_u)
    for abp_shift in (0.0, 2.4 * abp_u):
        abp_path = abp_c.beginPath()
        abp_px, abp_py = abp_x + abp_ux * abp_shift, abp_y + abp_uy * abp_shift
        abp_path.moveTo(abp_px - abp_uy * abp_width * 1.6, abp_py + abp_ux * abp_width * 1.6)
        abp_path.curveTo(
            abp_px + abp_ux * abp_width,
            abp_py + abp_uy * abp_width,
            abp_px - abp_ux * abp_width,
            abp_py - abp_uy * abp_width,
            abp_px + abp_uy * abp_width * 1.6,
            abp_py - abp_ux * abp_width * 1.6,
        )
        abp_c.drawPath(abp_path, stroke=1, fill=0)


class abp__Placer:
    def __init__(self, abp_area: abp__Box, abp_cell: float) -> None:
        self.abp__area, self.abp__cell = abp_area, abp_cell
        self.abp__used = np.zeros(
            (math.ceil(abp_area.abp_h / abp_cell) + 1, math.ceil(abp_area.abp_w / abp_cell) + 1)
        )

    def abp__span(self, abp_box: abp__Box) -> tuple[slice, slice]:
        abp_rows, abp_cols = self.abp__used.shape
        abp_x0 = int((abp_box.abp_x - self.abp__area.abp_x) // self.abp__cell)
        abp_y0 = int((abp_box.abp_y - self.abp__area.abp_y) // self.abp__cell)
        abp_x1 = int((abp_box.abp_x + abp_box.abp_w - self.abp__area.abp_x) // self.abp__cell) + 1
        abp_y1 = int((abp_box.abp_y + abp_box.abp_h - self.abp__area.abp_y) // self.abp__cell) + 1
        return (
            slice(min(max(abp_y0, 0), abp_rows), min(max(abp_y1, 0), abp_rows)),
            slice(min(max(abp_x0, 0), abp_cols), min(max(abp_x1, 0), abp_cols)),
        )

    def abp_block(self, abp_box: abp__Box, abp_weight: float = 1.0) -> None:
        abp_rows, abp_cols = self.abp__span(abp_box)
        self.abp__used[abp_rows, abp_cols] = np.maximum(
            self.abp__used[abp_rows, abp_cols], abp_weight
        )

    def abp_block_line(self, abp_a: abpPt, abp_b: abpPt, abp_half: float) -> None:
        abp_n = max(1, math.ceil(math.dist(abp_a, abp_b) / self.abp__cell))
        for abp_i in range(abp_n + 1):
            abp_x, abp_y = (
                abp_a[0] + (abp_b[0] - abp_a[0]) * abp_i / abp_n,
                abp_a[1] + (abp_b[1] - abp_a[1]) * abp_i / abp_n,
            )
            self.abp_block(abp__Box(abp_x - abp_half, abp_y - abp_half, 2 * abp_half, 2 * abp_half))

    def abp_cost(self, abp_box: abp__Box) -> float:
        abp_rows, abp_cols = self.abp__span(abp_box)
        abp_part = self.abp__used[abp_rows, abp_cols]
        abp_outside = abp_box.abp_x < self.abp__area.abp_x or abp_box.abp_y < self.abp__area.abp_y
        abp_outside |= abp_box.abp_x + abp_box.abp_w > self.abp__area.abp_x + self.abp__area.abp_w
        abp_outside |= abp_box.abp_y + abp_box.abp_h > self.abp__area.abp_y + self.abp__area.abp_h
        return float(abp_part.sum()) + (1e3 if abp_outside else 0.0)

    def abp_best(self, abp_candidates: Sequence[tuple[float, abp__Box]]) -> abp__Box:
        abp_chosen = min(abp_candidates, key=lambda abp_x: (self.abp_cost(abp_x[1]), abp_x[0]))[1]
        self.abp_block(abp_chosen)
        return abp_chosen


def abp__inside(abp_polygon: Sequence[abpPt], abp_p: abpPt) -> bool:
    abp_out = False
    for (abp_x1, abp_y1), (abp_x2, abp_y2) in zip(
        abp_polygon, [*abp_polygon[1:], abp_polygon[0]], strict=True
    ):
        if (abp_y1 > abp_p[1]) != (abp_y2 > abp_p[1]) and abp_p[0] < (abp_x2 - abp_x1) * (
            abp_p[1] - abp_y1
        ) / (abp_y2 - abp_y1) + abp_x1:
            abp_out = not abp_out
    return abp_out


def abp__note_lines(abp_note: abpRoomNote, abp_meeting: bool) -> list[str]:
    abp_goal = "hasta círculo de reunión" if abp_meeting else "hasta la salida"
    return [
        f"Aforo de {abp_note.abp_people:02d} personas",
        f"{abp_note.abp_distance_m:.2f} ml {abp_goal}",
        f"{abp_note.abp_time_s:.2f} seg para salir",
    ]


def abp__note_box(
    abp_polygon: Sequence[abpPt], abp_lines: Sequence[str], abp_placer: abp__Placer, abp_u: float
) -> tuple[abp__Box, float]:
    abp_xs, abp_ys = [abp_p[0] for abp_p in abp_polygon], [abp_p[1] for abp_p in abp_polygon]
    abp_cx, abp_cy = (min(abp_xs) + max(abp_xs)) / 2, (min(abp_ys) + max(abp_ys)) / 2
    abp_best: tuple[float, float, abp__Box, float] | None = None
    for abp_size in (7.2 * abp_u, 6.4 * abp_u, 5.7 * abp_u, 5.0 * abp_u):
        abp_width = (
            max(pdfmetrics.stringWidth(abp_t, abp_FONT_BOLD, abp_size) for abp_t in abp_lines)
            + 4 * abp_u
        )
        abp_height = abp_size * 1.22 * len(abp_lines) + 2 * abp_u
        abp_step = max(3.0, abp_size * 0.6)
        for abp_x in np.arange(min(abp_xs), max(abp_xs) - abp_width + abp_step, abp_step):
            for abp_y in np.arange(min(abp_ys), max(abp_ys) - abp_height + abp_step, abp_step):
                abp_box = abp__Box(float(abp_x), float(abp_y), abp_width, abp_height)
                abp_corners = [
                    (abp_box.abp_x + abp_dx * abp_box.abp_w, abp_box.abp_y + abp_dy * abp_box.abp_h)
                    for abp_dx in (0.02, 0.98)
                    for abp_dy in (0.02, 0.98)
                ]
                if not all(abp__inside(abp_polygon, abp_q) for abp_q in abp_corners):
                    continue
                abp_away = math.dist(
                    (abp_box.abp_x + abp_box.abp_w / 2, abp_box.abp_y + abp_box.abp_h / 2),
                    (abp_cx, abp_cy),
                )
                abp_option = (abp_placer.abp_cost(abp_box), abp_away, abp_box, abp_size)
                if abp_best is None or abp_option[:2] < abp_best[:2]:
                    abp_best = abp_option
        if abp_best is not None and abp_best[0] == 0:
            break
    if abp_best is None:
        abp_size = 4.2 * abp_u
        abp_width = (
            max(pdfmetrics.stringWidth(abp_t, abp_FONT_BOLD, abp_size) for abp_t in abp_lines)
            + 4 * abp_u
        )
        abp_height = abp_size * 1.22 * len(abp_lines) + 2 * abp_u
        abp_options = []
        for abp_dx in np.arange(-1.2, 1.21, 0.2):
            for abp_dy in np.arange(-3.6, 3.61, 0.3):
                abp_box = abp__Box(
                    abp_cx - abp_width / 2 + float(abp_dx) * abp_width,
                    abp_cy - abp_height / 2 + float(abp_dy) * abp_height,
                    abp_width,
                    abp_height,
                )
                abp_away = math.hypot(float(abp_dx) * abp_width, float(abp_dy) * abp_height)
                abp_options.append((abp_placer.abp_cost(abp_box), abp_away, abp_box, abp_size))
        abp_best = min(abp_options, key=lambda abp_o: abp_o[:2])
    abp_placer.abp_block(abp_best[2])
    return abp_best[2], abp_best[3]


def abp__draw_notes(
    abp_c: Canvas,
    abp_floor: abpSheetFloor,
    abp_view: abp__View,
    abp_placer: abp__Placer,
    abp_u: float,
    *,
    abp_with_name: bool,
) -> None:
    abp_s = abp_floor.abp_plan.abp_scale_m_per_px or 1.0
    abp_rooms = {abp_r.abp_name: abp_r for abp_r in abp_floor.abp_plan.abp_rooms}
    for abp_note in abp_floor.abp_notes:
        abp_room = abp_rooms.get(abp_note.abp_room_name)
        if abp_room is None:
            continue
        abp_polygon = [
            abp_view.abp_p(abpPoint(abp_v.abp_x * abp_s, abp_v.abp_y * abp_s))
            for abp_v in abp_room.abp_area.abp_vertices
        ]
        abp_lines = abp__note_lines(abp_note, bool(abp_floor.abp_network.abp_meeting_links))
        if abp_with_name:
            abp_lines.insert(0, abp_note.abp_room_name.upper())
        abp_box, abp_size = abp__note_box(abp_polygon, abp_lines, abp_placer, abp_u)
        abp_c.setFillColor(colors.Color(1, 1, 1, alpha=0.78))
        abp_c.roundRect(
            abp_box.abp_x,
            abp_box.abp_y,
            abp_box.abp_w,
            abp_box.abp_h,
            1.5 * abp_u,
            stroke=0,
            fill=1,
        )
        abp_c.setFont(abp_FONT_BOLD, abp_size)
        for abp_i, abp_text in enumerate(abp_lines):
            abp_c.setFillColor(abp_INK if abp_with_name and abp_i == 0 else abp_NOTE_GREEN)
            abp_c.drawString(
                abp_box.abp_x + 2 * abp_u,
                abp_box.abp_y + abp_box.abp_h - abp_size * (1.05 + 1.22 * abp_i),
                abp_text,
            )


def abp__cell(
    abp_c: Canvas,
    abp_box: abp__Box,
    abp_label: str,
    abp_value: str,
    abp_u: float,
    abp_big: float = 7.0,
) -> None:
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.6)
    abp_c.rect(abp_box.abp_x, abp_box.abp_y, abp_box.abp_w, abp_box.abp_h, stroke=1, fill=0)
    abp_c.setFillColor(colors.HexColor("#555555"))
    abp_c.setFont(abp_FONT, 4.2 * abp_u)
    abp_c.drawString(
        abp_box.abp_x + 1.5 * abp_u, abp_box.abp_y + abp_box.abp_h - 5.2 * abp_u, abp_label
    )
    if not abp_value:
        return
    abp_size = abp_big * abp_u
    abp_lines = abp__wrap(abp_value, abp_FONT_BOLD, abp_size, abp_box.abp_w - 5 * abp_u)
    abp_room = abp_box.abp_h - 7 * abp_u
    while len(abp_lines) * abp_size * 1.18 > abp_room and abp_size > 4:
        abp_size -= 0.3
        abp_lines = abp__wrap(abp_value, abp_FONT_BOLD, abp_size, abp_box.abp_w - 5 * abp_u)
    abp_c.setFillColor(abp_INK)
    abp_top = abp_box.abp_y + abp_room / 2 + len(abp_lines) * abp_size * 1.18 / 2 + 1 * abp_u
    for abp_i, abp_line in enumerate(abp_lines):
        abp_c.setFont(
            abp_FONT_BOLD, abp__fit(abp_line, abp_FONT_BOLD, abp_size, abp_box.abp_w - 4 * abp_u)
        )
        abp_c.drawCentredString(
            abp_box.abp_x + abp_box.abp_w / 2, abp_top - abp_size * (0.95 + 1.18 * abp_i), abp_line
        )


def abp__north(abp_c: Canvas, abp_x: float, abp_y: float, abp_r: float, abp_angle: float) -> None:
    abp_c.saveState()
    abp_c.translate(abp_x, abp_y)
    abp_c.rotate(-abp_angle)
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.8)
    abp_c.circle(0, 0, abp_r * 0.72, stroke=1, fill=0)
    abp_c.setFillColor(abp_INK)
    abp__poly_path(
        abp_c,
        [(0, abp_r), (abp_r * 0.3, -abp_r * 0.55), (0, -abp_r * 0.3)],
        abp_fill=1,
        abp_stroke=1,
    )
    abp_c.setFillColor(colors.white)
    abp__poly_path(
        abp_c,
        [(0, abp_r), (-abp_r * 0.3, -abp_r * 0.55), (0, -abp_r * 0.3)],
        abp_fill=1,
        abp_stroke=1,
    )
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT_BOLD, abp_r * 0.5)
    abp_c.drawCentredString(0, abp_r * 1.12, "N")
    abp_c.restoreState()


def abp__title_block(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_box: abp__Box,
    abp_number: int,
    abp_scale: int,
    abp_u: float,
) -> None:
    abp_project, abp_opts = abp_content.abp_project, abp_content.abp_options
    abp_y = abp_box.abp_y + abp_box.abp_h

    def abp_take(abp_height: float) -> abp__Box:
        nonlocal abp_y
        abp_y -= abp_height
        return abp__Box(abp_box.abp_x, abp_y, abp_box.abp_w, abp_height)

    abp_unit = abp_box.abp_h / 100.0
    abp_logo = abp_take(13 * abp_unit)
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.6)
    abp_c.rect(abp_logo.abp_x, abp_logo.abp_y, abp_logo.abp_w, abp_logo.abp_h, stroke=1, fill=0)
    abp_name_space = 0.34 * abp_logo.abp_h
    if abp_project.abp_logo_path and Path(abp_project.abp_logo_path).is_file():
        abp_c.drawImage(
            ImageReader(abp_project.abp_logo_path),
            abp_logo.abp_x + 2 * abp_u,
            abp_logo.abp_y + abp_name_space,
            abp_logo.abp_w - 4 * abp_u,
            abp_logo.abp_h - abp_name_space - 2 * abp_u,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        abp_name_space = abp_logo.abp_h
    abp_size = 8.5 * abp_u
    abp_lines = abp__wrap(
        abp_project.abp_name.upper(), abp_FONT_BOLD, abp_size, abp_logo.abp_w - 4 * abp_u
    )
    while len(abp_lines) * abp_size * 1.2 > abp_name_space - 2 * abp_u and abp_size > 4:
        abp_size -= 0.4
        abp_lines = abp__wrap(
            abp_project.abp_name.upper(), abp_FONT_BOLD, abp_size, abp_logo.abp_w - 4 * abp_u
        )
    abp_c.setFillColor(abp_INK)
    abp_top = abp_logo.abp_y + abp_name_space / 2 + len(abp_lines) * abp_size * 0.6
    for abp_i, abp_line in enumerate(abp_lines):
        abp_c.setFont(abp_FONT_BOLD, abp_size)
        abp_c.drawCentredString(
            abp_logo.abp_x + abp_logo.abp_w / 2, abp_top - abp_size * (0.95 + 1.2 * abp_i), abp_line
        )
    for abp_label, abp_value in (
        ("REGIÓN:", abp_project.abp_department),
        ("PROVINCIA:", abp_project.abp_province),
        ("DISTRITO:", abp_project.abp_district),
    ):
        abp__cell(abp_c, abp_take(5.2 * abp_unit), abp_label, abp_value.upper(), abp_u)
    abp__cell(
        abp_c,
        abp_take(6.4 * abp_unit),
        "DIRECCIÓN / SECTOR:",
        abp__join(abp_project.abp_address, abp_opts.abp_sector),
        abp_u,
        6.0,
    )
    abp_north = abp_take(13.5 * abp_unit)
    abp_c.rect(abp_north.abp_x, abp_north.abp_y, abp_north.abp_w, abp_north.abp_h, stroke=1, fill=0)
    abp_c.setFillColor(colors.HexColor("#555555"))
    abp_c.setFont(abp_FONT, 4.2 * abp_u)
    abp_c.drawString(
        abp_north.abp_x + 1.5 * abp_u,
        abp_north.abp_y + abp_north.abp_h - 5.2 * abp_u,
        "ORIENTACIÓN:",
    )
    abp_radius = min(abp_north.abp_w, abp_north.abp_h) * 0.3
    abp__north(
        abp_c,
        abp_north.abp_x + abp_north.abp_w / 2,
        abp_north.abp_y + abp_north.abp_h * 0.43,
        abp_radius,
        abp_opts.abp_north_deg,
    )
    abp_level = (
        abp_content.abp_level_names[abp_number - 1]
        if abp_number <= len(abp_content.abp_level_names)
        else ""
    )
    abp__cell(abp_c, abp_take(8 * abp_unit), "PROYECTO:", abp_project.abp_name, abp_u, 6.5)
    abp__cell(abp_c, abp_take(9 * abp_unit), "PLANO:", abp_opts.abp_title, abp_u, 6.5)
    abp__cell(abp_c, abp_take(5.2 * abp_unit), "NIVEL:", abp_level, abp_u)
    abp__cell(abp_c, abp_take(6.2 * abp_unit), "ESPECIALISTA:", abp_opts.abp_specialist, abp_u, 6.0)
    abp__cell(abp_c, abp_take(5.2 * abp_unit), "DIBUJO:", abp_opts.abp_drafter, abp_u, 6.0)
    abp__cell(
        abp_c, abp_take(5 * abp_unit), "FECHA:", abp_opts.abp_made_on.strftime("%d/%m/%Y"), abp_u
    )
    abp__cell(abp_c, abp_take(5 * abp_unit), "ESCALA:", f"1/{abp_scale}", abp_u)
    abp_last = abp__Box(abp_box.abp_x, abp_box.abp_y, abp_box.abp_w, abp_y - abp_box.abp_y)
    abp__cell(abp_c, abp_last, "LÁMINA:", f"{abp_opts.abp_code}-{abp_number:02d}", abp_u, 15)


def abp__join(*abp_parts: str) -> str:
    return " – ".join(abp_p.strip() for abp_p in abp_parts if abp_p and abp_p.strip())


def abp__legend(
    abp_c: Canvas,
    abp_floor: abpSheetFloor,
    abp_x: float,
    abp_top: float,
    abp_w: float,
    abp_u: float,
    abp_columns: int = 1,
    abp_limit: float | None = None,
) -> float:
    abp_rows: list[str] = [
        abp_k
        for abp_k in abp_SIGNS
        if any(abp_s.abp_kind == abp_k for abp_s in abp_floor.abp_signs)
    ]
    abp_rows += ["ruta", "id"]
    if abp_floor.abp_plan.abp_safe_zones:
        abp_rows.append("reunion")
    abp_row, abp_title_h = 7.0 * mm * abp_u, 5.0 * mm * abp_u
    if abp_columns == 1 and len(abp_rows) > 12:
        abp_row = 5.2 * mm * abp_u
    abp_lines = math.ceil(len(abp_rows) / abp_columns)
    if abp_limit is not None:
        abp_row = min(abp_row, (abp_limit - 2 * abp_title_h) / max(abp_lines, 1))
    abp_total = abp_title_h * 2 + abp_row * abp_lines
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.7)
    abp_c.setFillColor(colors.white)
    abp_c.rect(abp_x, abp_top - abp_total, abp_w, abp_total, stroke=1, fill=1)
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT_BOLD, 8 * abp_u)
    abp_c.drawCentredString(abp_x + abp_w / 2, abp_top - abp_title_h * 0.7, "LEYENDA")
    abp_c.line(abp_x, abp_top - abp_title_h, abp_x + abp_w, abp_top - abp_title_h)
    abp_col_w = abp_w / abp_columns
    for abp_col in range(abp_columns):
        abp_left = abp_x + abp_col * abp_col_w
        abp_split = abp_left + 0.27 * abp_col_w
        abp_c.setFillColor(abp_INK)
        abp_c.setFont(abp_FONT_BOLD, 5 * abp_u)
        abp_c.drawCentredString((abp_left + abp_split) / 2, abp_top - abp_title_h * 1.65, "SÍMBOLO")
        abp_c.drawCentredString(
            (abp_split + abp_left + abp_col_w) / 2, abp_top - abp_title_h * 1.65, "DESCRIPCIÓN"
        )
        abp_c.setStrokeColor(abp_INK)
        abp_c.setLineWidth(0.5)
        abp_c.line(abp_split, abp_top - abp_title_h, abp_split, abp_top - abp_total)
        if abp_col:
            abp_c.line(abp_left, abp_top - abp_title_h, abp_left, abp_top - abp_total)
        abp_y = abp_top - 2 * abp_title_h
        for abp_key in abp_rows[abp_col * abp_lines : (abp_col + 1) * abp_lines]:
            abp__legend_row(abp_c, abp_key, abp_left, abp_split, abp_y, abp_col_w, abp_row, abp_u)
            abp_y -= abp_row
    return abp_total


def abp__legend_row(
    abp_c: Canvas,
    abp_key: str,
    abp_x: float,
    abp_split: float,
    abp_y: float,
    abp_w: float,
    abp_row: float,
    abp_u: float,
) -> None:
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.5)
    abp_c.line(abp_x, abp_y, abp_x + abp_w, abp_y)
    abp_cx, abp_cy = (abp_x + abp_split) / 2, abp_y - abp_row / 2
    if abp_key in abp_SIGNS:
        abp_art = abp_SIGNS[abp_key]
        abp_reach = max(
            abs(abp_v)
            for abp_shape in abp_art.abp_shapes
            for abp_p in abp_shape.abp_points
            for abp_v in abp_p
        )
        abp_draw_sign(abp_c, abp_art, abp_cx, abp_cy, 0.4 * abp_row / max(abp_reach, 0.5), 0.0, "N")
        abp_label = abp_art.abp_label
    elif abp_key == "ruta":
        abp_draw_route(
            abp_c,
            [(abp_x + 0.05 * abp_w, abp_cy), (abp_split - 0.03 * abp_w, abp_cy)],
            abp_row * 0.24,
            abp_row * 1.6,
        )
        abp_label = "Ruta de evacuación"
    elif abp_key == "id":
        abp__route_badge(abp_c, abp_cx, abp_cy, "R1", abp_row * 0.34)
        abp_label = "Identificación de ruta"
    else:
        abp_c.setFillColor(abp_MEETING)
        abp_c.setStrokeColor(colors.HexColor("#b9a800"))
        abp_c.circle(abp_cx, abp_cy, abp_row * 0.38, stroke=1, fill=1)
        abp_label = "Zona de reunión"
    abp_size = min(5.6 * abp_u, 0.42 * abp_row)
    abp_lines = abp__wrap(
        abp_label.upper(), abp_FONT, abp_size, abp_x + abp_w - abp_split - 3 * abp_u
    )
    abp_c.setFillColor(abp_INK)
    for abp_i, abp_line in enumerate(abp_lines):
        abp_c.setFont(
            abp_FONT, abp__fit(abp_line, abp_FONT, abp_size, abp_x + abp_w - abp_split - 3 * abp_u)
        )
        abp_c.drawCentredString(
            (abp_split + abp_x + abp_w) / 2,
            abp_cy + abp_size * (0.6 * len(abp_lines) - 0.95 - 1.2 * abp_i) + 0.1 * abp_size,
            abp_line,
        )


def abp__times_table(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_x: float,
    abp_top: float,
    abp_w: float,
    abp_u: float,
) -> float:
    if not abp_floor.abp_notes:
        return 0.0
    abp_row = 4.6 * mm * abp_u
    abp_columns = (
        ("AMBIENTE", 0.44),
        ("N", 0.12),
        ("A (m)", 0.14),
        ("D (m)", 0.15),
        ("T (seg)", 0.15),
    )
    abp_notes = sorted(abp_floor.abp_notes, key=lambda abp_n: -abp_n.abp_time_s)
    abp_shown = abp_notes[:14]
    abp_total = abp_row * (len(abp_shown) + 2)
    abp_c.setFillColor(colors.white)
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.6)
    abp_c.rect(abp_x, abp_top - abp_total, abp_w, abp_total, stroke=1, fill=1)
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT_BOLD, 5.6 * abp_u)
    abp_c.drawCentredString(abp_x + abp_w / 2, abp_top - abp_row * 0.7, "TIEMPOS DE EVACUACIÓN")
    abp_y = abp_top - abp_row
    for abp_index in range(-1, len(abp_shown)):
        abp_c.setLineWidth(0.35)
        abp_c.line(abp_x, abp_y, abp_x + abp_w, abp_y)
        abp_left = abp_x
        abp_note = abp_shown[abp_index] if abp_index >= 0 else None
        for abp_k, (abp_head, abp_share) in enumerate(abp_columns):
            abp_width = abp_share * abp_w
            abp_text = abp_head
            if abp_note is not None:
                abp_text = (
                    f"{abp_note.abp_route_id}  {abp_note.abp_room_name}",
                    str(abp_note.abp_people),
                    f"{abp_note.abp_door_width_m:.2f}",
                    f"{abp_note.abp_distance_m:.2f}",
                    f"{abp_note.abp_time_s:.2f}",
                )[abp_k]
            abp_font = abp_FONT_BOLD if abp_note is None or abp_index == 0 else abp_FONT
            abp_c.setFillColor(abp_RED if abp_note is not None and abp_index == 0 else abp_INK)
            abp_size = abp__fit(abp_text, abp_font, 4.9 * abp_u, abp_width - 2 * abp_u, 3.9 * abp_u)
            abp_text = abp__shorten(abp_text, abp_font, abp_size, abp_width - 2 * abp_u)
            abp_c.setFont(abp_font, abp_size)
            if abp_k == 0 and abp_note is not None:
                abp_c.drawString(abp_left + 1 * abp_u, abp_y - abp_row * 0.68, abp_text)
            else:
                abp_c.drawCentredString(abp_left + abp_width / 2, abp_y - abp_row * 0.68, abp_text)
            abp_left += abp_width
            if abp_k < len(abp_columns) - 1:
                abp_c.line(abp_left, abp_y, abp_left, abp_y - abp_row)
        abp_y -= abp_row
    return abp_total


def abp__route_table(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_x: float,
    abp_top: float,
    abp_w: float,
    abp_u: float,
    abp_columns: int = 2,
    abp_row_h: float | None = None,
) -> float:
    abp_mine = {abp_n.abp_route_id for abp_n in abp_floor.abp_notes}
    abp_routes = [abp_r for abp_r in abp_content.abp_routes if abp_r.abp_route_id in abp_mine]
    if not abp_routes:
        return 0.0
    abp_row = abp_row_h or 7.0 * mm * abp_u
    abp_rows = math.ceil(len(abp_routes) / abp_columns)
    abp_col_w = abp_w / abp_columns
    abp_c.setLineWidth(0.5)
    for abp_index, abp_route in enumerate(abp_routes):
        abp_col, abp_line = abp_index // abp_rows, abp_index % abp_rows
        abp_left, abp_y = abp_x + abp_col * abp_col_w, abp_top - (abp_line + 1) * abp_row
        abp_c.setStrokeColor(abp_GRAY)
        abp_c.setFillColor(colors.white)
        abp_c.rect(abp_left, abp_y, abp_col_w - 1.5 * abp_u, abp_row, stroke=1, fill=1)
        abp__route_badge(
            abp_c,
            abp_left + 0.14 * abp_col_w,
            abp_y + abp_row / 2,
            abp_route.abp_route_id,
            abp_row * 0.36,
        )
        abp_c.setFillColor(abp_INK)
        abp_text = f"=   {abp_format_time(abp_route.abp_time_s)}"
        abp_size = abp__fit(abp_text, abp_FONT_BOLD, 7.5 * abp_u, 0.6 * abp_col_w)
        abp_c.setFont(abp_FONT_BOLD, abp_size)
        abp_c.drawString(
            abp_left + 0.3 * abp_col_w, abp_y + abp_row / 2 - 0.35 * abp_size, abp_text
        )
    return abp_rows * abp_row


def abp__zone_table(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_x: float,
    abp_top: float,
    abp_w: float,
    abp_u: float,
) -> float:
    abp_row = 6.0 * mm * abp_u
    abp_heads = (("ZONA DE REUNIÓN", 0.4), ("RADIO", 0.18), ("N.º PERSONAS", 0.22), ("RUTAS", 0.2))
    abp_total = abp_row * (len(abp_content.abp_zones) + 2)
    abp_c.setStrokeColor(abp_INK)
    abp_c.setFillColor(colors.white)
    abp_c.setLineWidth(0.6)
    abp_c.rect(abp_x, abp_top - abp_total, abp_w, abp_total, stroke=1, fill=1)
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT_BOLD, 7 * abp_u)
    abp_c.drawCentredString(abp_x + abp_w / 2, abp_top - abp_row * 0.68, "ZONAS DE REUNIÓN")
    abp_y = abp_top - abp_row
    for abp_index in range(-1, len(abp_content.abp_zones)):
        abp_c.line(abp_x, abp_y, abp_x + abp_w, abp_y)
        abp_left = abp_x
        for abp_k, (abp_head, abp_share) in enumerate(abp_heads):
            abp_text = abp_head
            if abp_index >= 0:
                abp_z = abp_content.abp_zones[abp_index]
                abp_ids = ", ".join(abp_z.abp_route_ids) or "–"
                abp_text = (
                    f"{abp_z.abp_number}. {abp_z.abp_name}",
                    f"{abp_z.abp_radius_m:.2f} m",
                    str(abp_z.abp_people),
                    abp_ids,
                )[abp_k]
            abp_width = abp_share * abp_w
            abp_font = abp_FONT_BOLD if abp_index < 0 else abp_FONT
            abp_size = abp__fit(abp_text, abp_font, 5.2 * abp_u, abp_width - 2 * abp_u, 3.4 * abp_u)
            abp_c.setFont(abp_font, abp_size)
            abp_text = abp__shorten(abp_text, abp_font, abp_size, abp_width - 2 * abp_u)
            abp_c.drawCentredString(abp_left + abp_width / 2, abp_y - abp_row * 0.65, abp_text)
            abp_left += abp_width
            if abp_k < len(abp_heads) - 1:
                abp_c.line(abp_left, abp_y, abp_left, abp_y - abp_row)
        abp_y -= abp_row
    return abp_total


def abp__bottom_tables(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_band: abp__Box,
    abp_u: float,
) -> None:
    abp_gap = 5 * mm * abp_u
    abp_by_room = abp_content.abp_options.abp_identify == "ambiente"
    abp_routes = [
        abp_r
        for abp_r in abp_content.abp_routes
        if abp_r.abp_route_id in {abp_n.abp_route_id for abp_n in abp_floor.abp_notes}
    ]
    abp_columns = 2 if len(abp_routes) <= 14 else 3
    abp_route_w = 0.3 * abp_band.abp_w if abp_by_room and abp_routes else 0.0
    if abp_route_w:
        abp_rows = math.ceil(len(abp_routes) / abp_columns)
        abp_row = min(8.0 * mm * abp_u, abp_band.abp_h / max(abp_rows, 1))
        abp__route_table(
            abp_c,
            abp_content,
            abp_floor,
            abp_band.abp_x,
            abp_band.abp_y + abp_band.abp_h,
            abp_route_w,
            abp_u,
            abp_columns=abp_columns,
            abp_row_h=abp_row,
        )
    abp_x = abp_band.abp_x + abp_route_w + (abp_gap if abp_route_w else 0.0)
    abp_rest = abp_band.abp_x + abp_band.abp_w - abp_x - 2 * abp_gap
    abp_legend_w, abp_side_w = 0.58 * abp_rest, 0.42 * abp_rest
    abp__legend(
        abp_c,
        abp_floor,
        abp_x,
        abp_band.abp_y + abp_band.abp_h,
        abp_legend_w,
        abp_u,
        abp_columns=2,
        abp_limit=abp_band.abp_h,
    )
    abp_x += abp_legend_w + abp_gap
    abp_y = abp_band.abp_y + abp_band.abp_h
    if abp_content.abp_zones:
        abp_y -= (
            abp__zone_table(abp_c, abp_content, abp_x, abp_y, abp_side_w, abp_u) + 2 * mm * abp_u
        )
    if not abp_by_room:
        abp_y -= (
            abp__times_table(abp_c, abp_content, abp_floor, abp_x, abp_y, abp_side_w, abp_u)
            + 2 * mm * abp_u
        )
    abp__side_notes(abp_c, abp_content, abp_floor, abp_x, abp_y, abp_side_w, abp_u)


def abp__side_notes(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_x: float,
    abp_top: float,
    abp_w: float,
    abp_u: float,
) -> float:
    abp_opts = abp_content.abp_options
    abp_y = abp_top
    for abp_route in abp_content.abp_routes if abp_opts.abp_identify == "salida" else ():
        abp_h = 10.0 * mm * abp_u
        abp_c.setFillColor(colors.white)
        abp_c.setStrokeColor(abp_INK)
        abp_c.setLineWidth(0.8)
        abp_c.rect(abp_x, abp_y - abp_h, abp_w, abp_h, stroke=1, fill=1)
        abp__route_badge(
            abp_c, abp_x + 0.1 * abp_w, abp_y - abp_h / 2, abp_route.abp_route_id, abp_h * 0.34
        )
        abp_c.setFillColor(abp_RED)
        abp_c.setFont(abp_FONT_BOLD, 8.5 * abp_u)
        abp_text = f"= {abp_format_time(abp_route.abp_time_s)}"
        abp_c.drawString(abp_x + 0.22 * abp_w, abp_y - abp_h / 2 + 1.5 * abp_u, abp_text)
        abp_c.setFillColor(abp_INK)
        abp_c.setFont(abp_FONT, 4.6 * abp_u)
        abp_detail = f"{abp_route.abp_exit_name}: {abp_route.abp_people} personas · {abp_route.abp_distance_m:.2f} ml (crítica)"
        abp_c.setFont(abp_FONT, abp__fit(abp_detail, abp_FONT, 4.8 * abp_u, 0.76 * abp_w))
        abp_c.drawString(abp_x + 0.22 * abp_w, abp_y - abp_h / 2 - 7.5 * abp_u, abp_detail)
        abp_y -= abp_h + 1.5 * abp_u
    abp_notes = [
        f"T = N / (A·K) + D / V   con K = {abp_opts.abp_flow:g} pers/(m·s) y V = {abp_opts.abp_speed:g} m/s "
        "(valores por verificar).",
        "N: personas · A: ancho de la puerta · D: recorrido desde el punto más alejado.",
    ]
    if abp_content.abp_simulated_s is not None:
        abp_notes.append(
            f"Tiempo total simulado con RutaSegura: {abp_format_time(abp_content.abp_simulated_s)} (sismo)."
        )
    if abp_opts.abp_note.strip():
        abp_notes.append(f"NOTA: {abp_opts.abp_note.strip()}")
    abp_size = 5.2 * abp_u
    abp_y -= 2 * mm * abp_u
    abp_c.setFillColor(abp_INK)
    for abp_paragraph in abp_notes:
        for abp_line in abp__wrap(abp_paragraph, abp_FONT, abp_size, abp_w):
            abp_y -= abp_size * 1.25
            abp_c.setFont(abp_FONT, abp_size)
            abp_c.drawString(abp_x, abp_y, abp_line)
        abp_y -= abp_size * 0.5
    return abp_top - abp_y


def abp__draw_page(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_number: int,
    abp_page: abpPt,
    abp_u: float,
) -> None:
    abp_page_w, abp_page_h = abp_page
    abp_opts = abp_content.abp_options
    abp_margin = 7 * mm * abp_u
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.5)
    abp_c.rect(
        abp_margin,
        abp_margin,
        abp_page_w - 2 * abp_margin,
        abp_page_h - 2 * abp_margin,
        stroke=1,
        fill=0,
    )
    abp_inset = abp_margin + 2.2 * mm * abp_u
    abp_c.setLineWidth(1.4)
    abp_c.rect(
        abp_inset,
        abp_inset,
        abp_page_w - 2 * abp_inset,
        abp_page_h - 2 * abp_inset,
        stroke=1,
        fill=0,
    )
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_plan_bounds_m(abp_floor)
    abp_pad = 1.6
    abp_width_m, abp_height_m = abp_x1 - abp_x0 + 2 * abp_pad, abp_y1 - abp_y0 + 2 * abp_pad
    abp_frame = abp__best_frame(abp_page, abp_u, abp_opts, abp_width_m, abp_height_m)
    abp_block, abp_area = abp_frame.abp_block, abp_frame.abp_area
    abp_scale = abp_opts.abp_scale or abp_best_scale(
        abp_width_m, abp_height_m, abp_area.abp_w, abp_area.abp_h
    )
    abp_k = 1000.0 * mm / abp_scale
    abp_view = abp__View(
        abp_k,
        abp_area.abp_x + (abp_area.abp_w - abp_width_m * abp_k) / 2 + abp_pad * abp_k,
        abp_area.abp_y + (abp_area.abp_h - abp_height_m * abp_k) / 2 + abp_pad * abp_k,
        abp_x0,
        abp_y1,
    )
    abp_c.saveState()
    abp_clip = abp_c.beginPath()
    abp_clip.rect(abp_area.abp_x, abp_area.abp_y, abp_area.abp_w, abp_area.abp_h)
    abp_c.clipPath(abp_clip, stroke=0, fill=0)
    abp_drawn = abp_opts.abp_underlay == "original" and abp__draw_underlay(
        abp_c, abp_floor, abp_view, abp_area
    )
    if not abp_drawn:
        abp__draw_clean_plan(
            abp_c,
            abp_floor.abp_plan,
            abp_view,
            {abp_n.abp_room_name for abp_n in abp_floor.abp_notes},
        )
    abp_placer = abp__Placer(abp_area, 3.0 * abp_u)
    abp_meeting_boxes = abp__draw_meeting(abp_c, abp_floor.abp_plan, abp_view, abp_u)
    for abp_box in abp_meeting_boxes:
        abp_placer.abp_block(abp_box)
    abp__draw_routes(abp_c, abp_content, abp_floor, abp_view, abp_placer, abp_u)
    abp__draw_signs(abp_c, abp_floor, abp_view, abp_placer, abp_u)
    abp__draw_notes(abp_c, abp_floor, abp_view, abp_placer, abp_u, abp_with_name=not abp_drawn)
    if abp_floor.abp_network.abp_meeting_links:
        for abp_zone, abp_box in zip(abp_content.abp_zones, abp_meeting_boxes, strict=False):
            abp__meeting_summary(
                abp_c,
                abp_zone,
                abp_box,
                abp_placer,
                abp_u,
                abp_numbered=len(abp_content.abp_zones) > 1,
            )
    abp_c.restoreState()

    abp__page_title(
        abp_c, abp_content, abp_number, abp_scale, abp_area, abp_frame.abp_title_y, abp_u
    )
    abp__title_block(abp_c, abp_content, abp_floor, abp_block, abp_number, abp_scale, abp_u)
    if abp_frame.abp_band is not None:
        abp__bottom_tables(abp_c, abp_content, abp_floor, abp_frame.abp_band, abp_u)
        return
    abp_y = abp_block.abp_y + abp_block.abp_h
    abp_y -= (
        abp__legend(abp_c, abp_floor, abp_frame.abp_side_x, abp_y, abp_frame.abp_side_w, abp_u)
        + 3 * mm * abp_u
    )
    abp_y -= (
        abp__times_table(
            abp_c, abp_content, abp_floor, abp_frame.abp_side_x, abp_y, abp_frame.abp_side_w, abp_u
        )
        + 3 * mm * abp_u
    )
    if abp_content.abp_options.abp_identify == "ambiente":
        abp_y -= (
            abp__route_table(
                abp_c,
                abp_content,
                abp_floor,
                abp_frame.abp_side_x,
                abp_y,
                abp_frame.abp_side_w,
                abp_u,
            )
            + 3 * mm * abp_u
        )
    if len(abp_content.abp_zones) > 1:
        abp_y -= (
            abp__zone_table(
                abp_c, abp_content, abp_frame.abp_side_x, abp_y, abp_frame.abp_side_w, abp_u
            )
            + 3 * mm * abp_u
        )
    abp__side_notes(
        abp_c, abp_content, abp_floor, abp_frame.abp_side_x, abp_y, abp_frame.abp_side_w, abp_u
    )


@dataclass(frozen=True)
class abp__Frame:
    abp_area: abp__Box
    abp_block: abp__Box
    abp_title_y: float
    abp_side_x: float = 0.0
    abp_side_w: float = 0.0
    abp_band: abp__Box | None = None


def abp__frame(abp_page: abpPt, abp_u: float, abp_bottom: bool) -> abp__Frame:
    abp_page_w, abp_page_h = abp_page
    abp_inset = 7 * mm * abp_u + 2.2 * mm * abp_u
    abp_tb_w = 43 * mm * abp_u
    abp_block = abp__Box(
        abp_page_w - abp_inset - abp_tb_w - 2 * mm * abp_u,
        abp_inset + 2 * mm * abp_u,
        abp_tb_w,
        abp_page_h - 2 * abp_inset - 4 * mm * abp_u,
    )
    abp_strip = 17 * mm * abp_u
    if not abp_bottom:
        abp_side_w = 62 * mm * abp_u
        abp_side_x = abp_block.abp_x - abp_side_w - 4 * mm * abp_u
        abp_area = abp__Box(
            abp_inset + 3 * mm * abp_u,
            abp_inset + abp_strip,
            abp_side_x - abp_inset - 6 * mm * abp_u,
            abp_page_h - 2 * abp_inset - abp_strip - 3 * mm * abp_u,
        )
        return abp__Frame(abp_area, abp_block, abp_inset + abp_strip * 0.55, abp_side_x, abp_side_w)
    abp_band_h = min(72 * mm * abp_u, 0.32 * abp_page_h)
    abp_band = abp__Box(
        abp_inset + 3 * mm * abp_u,
        abp_inset + 3 * mm * abp_u,
        abp_block.abp_x - abp_inset - 7 * mm * abp_u,
        abp_band_h,
    )
    abp_title_y = abp_band.abp_y + abp_band.abp_h + abp_strip * 0.55
    abp_area = abp__Box(
        abp_band.abp_x,
        abp_band.abp_y + abp_band.abp_h + abp_strip,
        abp_band.abp_w,
        abp_page_h - abp_inset - 3 * mm * abp_u - (abp_band.abp_y + abp_band.abp_h + abp_strip),
    )
    return abp__Frame(abp_area, abp_block, abp_title_y, abp_band=abp_band)


def abp__best_frame(
    abp_page: abpPt,
    abp_u: float,
    abp_opts: abpSheetOptions,
    abp_width_m: float,
    abp_height_m: float,
) -> abp__Frame:
    abp_options = {"costado": [False], "abajo": [True]}.get(abp_opts.abp_tables, [False, True])
    if abp_opts.abp_tables == "auto" and abp_page[1] > abp_page[0]:
        abp_options = [True]
    abp_frames = [abp__frame(abp_page, abp_u, abp_bottom) for abp_bottom in abp_options]
    return min(
        abp_frames,
        key=lambda abp_f: abp_best_scale(
            abp_width_m, abp_height_m, abp_f.abp_area.abp_w, abp_f.abp_area.abp_h
        ),
    )


def abp__page_size(abp_content: abpSheetContent) -> abpPt:
    abp_opts = abp_content.abp_options
    abp_size = abp_SHEET_SIZES[abp_opts.abp_paper]
    abp_wide, abp_tall = landscape(abp_size), portrait(abp_size)
    if abp_opts.abp_orientation != "auto":
        return abp_tall if abp_opts.abp_orientation == "vertical" else abp_wide
    abp_u = abp_SHEET_FACTOR[abp_opts.abp_paper]
    abp_score = {}
    for abp_page in (abp_wide, abp_tall):
        abp_total = 0
        for abp_floor in abp_content.abp_floors:
            abp_x0, abp_y0, abp_x1, abp_y1 = abp_plan_bounds_m(abp_floor)
            abp_w, abp_h = abp_x1 - abp_x0 + 3.2, abp_y1 - abp_y0 + 3.2
            abp_f = abp__best_frame(abp_page, abp_u, abp_opts, abp_w, abp_h)
            abp_total += abp_best_scale(abp_w, abp_h, abp_f.abp_area.abp_w, abp_f.abp_area.abp_h)
        abp_score[abp_page] = abp_total
    return abp_tall if abp_score[abp_tall] < abp_score[abp_wide] else abp_wide


def abp__page_title(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_number: int,
    abp_scale: int,
    abp_area: abp__Box,
    abp_y: float,
    abp_u: float,
) -> None:
    abp_level = (
        abp_content.abp_level_names[abp_number - 1]
        if abp_number <= len(abp_content.abp_level_names)
        else ""
    )
    abp_title = abp__join(
        abp_content.abp_options.abp_title, abp_content.abp_project.abp_name.upper()
    )
    abp_size = abp__fit(abp_title, abp_FONT_ITALIC, 12 * abp_u, abp_area.abp_w * 0.78)
    abp_width = pdfmetrics.stringWidth(abp_title, abp_FONT_ITALIC, abp_size)
    abp_x = abp_area.abp_x + (abp_area.abp_w - abp_width) / 2
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT_ITALIC, abp_size)
    abp_c.drawString(abp_x, abp_y, abp_title)
    abp_c.setStrokeColor(abp_INK)
    abp_c.setLineWidth(0.9)
    abp_c.line(
        abp_x - 6 * abp_u, abp_y - 3 * abp_u, abp_x + abp_width + 34 * abp_u, abp_y - 3 * abp_u
    )
    abp_c.setLineWidth(0.4)
    abp_c.line(
        abp_x - 6 * abp_u, abp_y - 4.8 * abp_u, abp_x + abp_width + 34 * abp_u, abp_y - 4.8 * abp_u
    )
    abp_c.setFont(abp_FONT_BOLD, 6 * abp_u)
    abp_c.drawString(abp_x + abp_width + 5 * abp_u, abp_y - 0.5 * abp_u, f"ESC. 1/{abp_scale}")
    if abp_level:
        abp_c.setFont(abp_FONT_ITALIC, 8 * abp_u)
        abp_c.drawCentredString(
            abp_area.abp_x + abp_area.abp_w / 2, abp_y - 14 * abp_u, abp_level.upper()
        )


def abp__draw_routes(
    abp_c: Canvas,
    abp_content: abpSheetContent,
    abp_floor: abpSheetFloor,
    abp_view: abp__View,
    abp_placer: abp__Placer,
    abp_u: float,
) -> None:
    abp_width = min(max(0.2 * abp_view.abp_k, 3.2 * abp_u), 8.0 * abp_u)
    abp_every = max(2.1 * abp_view.abp_k, 26 * abp_u)
    abp_links: dict[str, list[list[abpPt]]] = {}
    for abp_name, abp_outside_m in abp_floor.abp_network.abp_meeting_links:
        abp_links.setdefault(abp_name, []).append(
            [abp_view.abp_p(abp_p) for abp_p in abp_outside_m]
        )
    abp_by_room = abp_content.abp_options.abp_identify == "ambiente"
    abp_ids = (
        {}
        if abp_by_room
        else {abp_r.abp_exit_name: abp_r.abp_route_id for abp_r in abp_content.abp_routes}
    )
    abp_linked = set(abp_links)
    abp_badges: list[tuple[abpPt, str]] = (
        abp__room_badges(abp_floor, abp_view, abp_u) if abp_by_room else []
    )
    for abp_branch in sorted(abp_floor.abp_network.abp_branches, key=lambda abp_b: abp_b.abp_trunk):
        abp_points = [abp_view.abp_p(abp_p) for abp_p in abp_branch.abp_points_m]
        abp_draw_route(abp_c, abp_points, abp_width, abp_every)
        for abp_a, abp_b in itertools.pairwise(abp_points):
            abp_placer.abp_block_line(abp_a, abp_b, abp_width * 1.3)
        abp_name = abp_branch.abp_target_name
        if not abp_name:
            continue
        if abp_name in abp_links:
            for abp_outside in abp_links.pop(abp_name):
                abp_draw_route(abp_c, abp_outside, abp_width, abp_every)
                for abp_a, abp_b in itertools.pairwise(abp_outside):
                    abp_placer.abp_block_line(abp_a, abp_b, abp_width * 1.3)
        elif abp_name in abp_linked:
            pass
        elif any(abp_e.abp_name == abp_name for abp_e in abp_floor.abp_plan.abp_exits):
            (abp_ax, abp_ay), (abp_bx, abp_by) = abp_points[-2], abp_points[-1]
            abp_length = math.dist((abp_ax, abp_ay), (abp_bx, abp_by)) or 1.0
            abp_ux, abp_uy = (abp_bx - abp_ax) / abp_length, (abp_by - abp_ay) / abp_length
            abp_end = (
                abp_bx + abp_ux * 1.3 * abp_view.abp_k,
                abp_by + abp_uy * 1.3 * abp_view.abp_k,
            )
            abp_draw_route(abp_c, [abp_points[-1], abp_end], abp_width, abp_every)
            abp__continues(abp_c, abp_end, (abp_ux, abp_uy), abp_width, abp_u)
            abp_placer.abp_block_line(abp_points[-1], abp_end, abp_width * 1.3)
        if abp_name in abp_ids:
            (abp_ax, abp_ay), (abp_bx, abp_by) = abp_points[-2], abp_points[-1]
            abp_length = math.dist((abp_ax, abp_ay), (abp_bx, abp_by)) or 1.0
            abp_side = (-(abp_by - abp_ay) / abp_length, (abp_bx - abp_ax) / abp_length)
            abp_badges.append(
                (
                    (abp_bx - abp_side[0] * 14 * abp_u, abp_by - abp_side[1] * 14 * abp_u),
                    abp_ids[abp_name],
                )
            )
    if not abp_by_room:
        abp_badges = [
            (abp_spot, abp_text)
            for abp_text, abp_spot in {abp_t: abp_s for abp_s, abp_t in abp_badges}.items()
        ]
    for (abp_x, abp_y), abp_text in abp_badges:
        abp_size = 5.6 * abp_u
        abp_around = [
            (
                abs(abp_dx) + abs(abp_dy),
                abp__Box(
                    abp_x + abp_dx - abp_size, abp_y + abp_dy - abp_size, 2 * abp_size, 2 * abp_size
                ),
            )
            for abp_dx in np.arange(-24 * abp_u, 25 * abp_u, 6 * abp_u)
            for abp_dy in np.arange(-24 * abp_u, 25 * abp_u, 6 * abp_u)
        ]
        abp_spot = abp_placer.abp_best([(float(abp_d), abp_b) for abp_d, abp_b in abp_around])
        abp__route_badge(
            abp_c, abp_spot.abp_x + abp_size, abp_spot.abp_y + abp_size, abp_text, abp_size
        )


def abp__room_badges(
    abp_floor: abpSheetFloor, abp_view: abp__View, abp_u: float
) -> list[tuple[abpPt, str]]:
    abp_ids = {abp_n.abp_room_name: abp_n.abp_route_id for abp_n in abp_floor.abp_notes}
    abp_s = abp_floor.abp_plan.abp_scale_m_per_px or 1.0
    abp_doors = [
        abpPoint(abp_x.abp_midpoint.abp_x * abp_s, abp_x.abp_midpoint.abp_y * abp_s)
        for abp_x in [abp_d.abp_segment for abp_d in abp_floor.abp_plan.abp_doors]
        + [abp_e.abp_segment for abp_e in abp_floor.abp_plan.abp_exits]
    ]
    abp_out: list[tuple[abpPt, str]] = []
    for abp_escape in abp_floor.abp_network.abp_escapes:
        abp_text = abp_ids.get(abp_escape.abp_room_name)
        if abp_text is None or not abp_escape.abp_path_m:
            continue
        abp_spots = [abp_escape.abp_path_m[0]]
        abp_spots += [
            abp_p
            for abp_p in abp_escape.abp_path_m
            if any(abp_p.abp_distance_to(abp_d) < 0.05 for abp_d in abp_doors)
        ][:1]
        for abp_p in abp_spots:
            abp_x, abp_y = abp_view.abp_p(abp_p)
            abp_out.append(((abp_x + 9 * abp_u, abp_y + 9 * abp_u), abp_text))
    return abp_out


def abp__draw_signs(
    abp_c: Canvas,
    abp_floor: abpSheetFloor,
    abp_view: abp__View,
    abp_placer: abp__Placer,
    abp_u: float,
) -> None:
    abp_s = abp_floor.abp_plan.abp_scale_m_per_px or 1.0
    abp_size = min(max(0.55 * abp_view.abp_k, 8.5 * abp_u), 15 * abp_u)
    for abp_sign in abp_floor.abp_signs:
        abp_x, abp_y = abp_view.abp_p(
            abpPoint(abp_sign.abp_position.abp_x * abp_s, abp_sign.abp_position.abp_y * abp_s)
        )
        abp_art = abp_SIGNS[abp_sign.abp_kind]
        abp_draw_sign(
            abp_c, abp_art, abp_x, abp_y, abp_size, abp_sign.abp_rotation_deg, abp_sign.abp_text
        )
        abp_placer.abp_block(
            abp__Box(abp_x - abp_size * 0.6, abp_y - abp_size * 0.6, abp_size * 1.2, abp_size * 1.2)
        )


def abp__meeting_summary(
    abp_c: Canvas,
    abp_summary: abpZoneSummary,
    abp_zone: abp__Box,
    abp_placer: abp__Placer,
    abp_u: float,
    *,
    abp_numbered: bool,
) -> None:
    if abp_numbered:
        abp_c.setFillColor(colors.HexColor("#ff7f00"))
        abp_c.setFont(abp_FONT_BOLD, 24 * abp_u)
        abp_c.drawString(
            abp_zone.abp_x - 2 * abp_u,
            abp_zone.abp_y + abp_zone.abp_h - 6 * abp_u,
            str(abp_summary.abp_number),
        )
        abp_placer.abp_block(
            abp__Box(
                abp_zone.abp_x - 4 * abp_u,
                abp_zone.abp_y + abp_zone.abp_h - 10 * abp_u,
                22 * abp_u,
                26 * abp_u,
            )
        )
    if not abp_summary.abp_people:
        return
    abp_lines = [
        f"Aforo de {abp_summary.abp_people} personas",
        f"{abp_summary.abp_distance_m:.2f} ml – ruta más crítica",
        f"{abp_summary.abp_time_s:.2f} seg máx. para evacuar",
    ]
    abp_size = 7.2 * abp_u
    abp_width = (
        max(pdfmetrics.stringWidth(abp_t, abp_FONT_BOLD, abp_size) for abp_t in abp_lines)
        + 4 * abp_u
    )
    abp_height = abp_size * 1.22 * 3 + 2 * abp_u
    abp_cx = abp_zone.abp_x + abp_zone.abp_w / 2 - abp_width / 2
    abp_candidates = [
        (0.0, abp__Box(abp_cx, abp_zone.abp_y - abp_height - 2 * abp_u, abp_width, abp_height)),
        (1.0, abp__Box(abp_cx, abp_zone.abp_y + abp_zone.abp_h + 2 * abp_u, abp_width, abp_height)),
        (
            2.0,
            abp__Box(
                abp_zone.abp_x + abp_zone.abp_w + 2 * abp_u,
                abp_zone.abp_y + abp_zone.abp_h / 2 - abp_height / 2,
                abp_width,
                abp_height,
            ),
        ),
        (
            3.0,
            abp__Box(
                abp_zone.abp_x - abp_width - 2 * abp_u,
                abp_zone.abp_y + abp_zone.abp_h / 2 - abp_height / 2,
                abp_width,
                abp_height,
            ),
        ),
    ]
    abp_box = abp_placer.abp_best(abp_candidates)
    abp_c.setFillColor(colors.Color(1, 1, 1, alpha=0.78))
    abp_c.roundRect(
        abp_box.abp_x, abp_box.abp_y, abp_box.abp_w, abp_box.abp_h, 1.5 * abp_u, stroke=0, fill=1
    )
    abp_c.setFillColor(abp_NOTE_GREEN)
    abp_c.setFont(abp_FONT_BOLD, abp_size)
    for abp_i, abp_text in enumerate(abp_lines):
        abp_c.drawString(
            abp_box.abp_x + 2 * abp_u,
            abp_box.abp_y + abp_box.abp_h - abp_size * (1.05 + 1.22 * abp_i),
            abp_text,
        )


def abp_write_evacuation_sheet(abp_path: Path, abp_content: abpSheetContent) -> None:
    abp__fonts()
    abp_paper = abp_content.abp_options.abp_paper
    abp_page = abp__page_size(abp_content)
    abp_path.parent.mkdir(parents=True, exist_ok=True)
    abp_c = Canvas(str(abp_path), pagesize=abp_page)
    abp_c.setTitle(f"{abp_content.abp_options.abp_title} – {abp_content.abp_project.abp_name}")
    abp_c.setAuthor(
        abp_content.abp_options.abp_specialist or abp_content.abp_project.abp_responsible
    )
    abp_c.setCreator(f"RutaSegura {abp_content.abp_app_version}".strip())
    for abp_number, abp_floor in enumerate(abp_content.abp_floors, start=1):
        abp__draw_page(
            abp_c, abp_content, abp_floor, abp_number, abp_page, abp_SHEET_FACTOR[abp_paper]
        )
        abp_c.showPage()
    abp_c.save()
