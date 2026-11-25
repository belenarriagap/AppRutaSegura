from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from abp_rutasegura.abp_data.abp_evacuation_sheet import abp_draw_sign
from abp_rutasegura.abp_data.abp_report_pdf import abp__register_fonts, abp_FONT, abp_FONT_BOLD
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork, abpRoomRoute
from abp_rutasegura.abp_resources.abp_signs import abp_SIGNS

abp_PAPER_SIZES = {"A3": landscape(A3), "A4": landscape(A4)}

abp_INK = colors.HexColor("#263238")
abp_WALL = colors.HexColor("#263238")
abp_ROOM_FILL = colors.HexColor("#f5f7f8")
abp_ROOM_TEXT = colors.HexColor("#455a64")
abp_OBSTACLE_FILL = colors.HexColor("#dfe3e6")
abp_SAFE_GREEN = colors.HexColor("#1e8a4c")
abp_SAFE_FILL = colors.HexColor("#d7efe0")
abp_STAIR_FILL = colors.HexColor("#ece3f3")
abp_STAIR_LINE = colors.HexColor("#6a3d8f")
abp_HERE_RED = colors.HexColor("#d32f2f")
abp_BAND = colors.HexColor("#0d3346")
abp_BAND_ACCENT = colors.HexColor("#0e7490")
abp_PANEL_FILL = colors.HexColor("#f3f6f8")
abp_MUTED = colors.HexColor("#5a6b75")


@dataclass(frozen=True)
class abpMapOptions:
    abp_paper: str = "A3"
    abp_you_are_here: tuple[tuple[int, str], ...] = ()
    abp_responsible: str = ""
    abp_phones: tuple[tuple[str, str], ...] = ()
    abp_meeting_point: str = ""
    abp_instructions: tuple[str, ...] = ()
    abp_disclaimer: str = ""


@dataclass(frozen=True)
class abpMapFloor:
    abp_plan: abpFloorPlan
    abp_routes: tuple[abpRoomRoute, ...] = ()
    abp_network: abpEvacuationNetwork | None = None


@dataclass(frozen=True)
class abpMapContent:
    abp_project: abpProject
    abp_floors: tuple[abpMapFloor, ...]
    abp_options: abpMapOptions = field(default_factory=abpMapOptions)
    abp_made_on: date = field(default_factory=date.today)
    abp_app_version: str = ""


@dataclass(frozen=True)
class abp__Frame:
    abp_scale: float
    abp_x0: float
    abp_y0: float
    abp_min_x: float
    abp_max_y: float

    def abp_p(self, abp_point: abpPoint) -> tuple[float, float]:
        return self.abp_x0 + (abp_point.abp_x - self.abp_min_x) * self.abp_scale, self.abp_y0 + (
            self.abp_max_y - abp_point.abp_y
        ) * self.abp_scale


def abp__bounds(abp_plan: abpFloorPlan) -> tuple[float, float, float, float]:
    abp_s = abp_plan.abp_scale_m_per_px or 1.0
    abp_xs: list[float] = []
    abp_ys: list[float] = []
    for abp_seg in (
        [abp_w.abp_segment for abp_w in abp_plan.abp_walls]
        + [abp_d.abp_segment for abp_d in abp_plan.abp_doors]
        + [abp_e.abp_segment for abp_e in abp_plan.abp_exits]
    ):
        abp_xs += [abp_seg.abp_start.abp_x * abp_s, abp_seg.abp_end.abp_x * abp_s]
        abp_ys += [abp_seg.abp_start.abp_y * abp_s, abp_seg.abp_end.abp_y * abp_s]
    for abp_poly in (
        [abp_r.abp_area for abp_r in abp_plan.abp_rooms]
        + [abp_z.abp_area for abp_z in abp_plan.abp_safe_zones]
        + [abp_st.abp_area for abp_st in abp_plan.abp_stairs]
    ):
        abp_xs += [abp_v.abp_x * abp_s for abp_v in abp_poly.abp_vertices]
        abp_ys += [abp_v.abp_y * abp_s for abp_v in abp_poly.abp_vertices]
    if not abp_xs:
        return 0.0, 0.0, 10.0, 10.0
    return min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)


def abp__m(abp_point: abpPoint, abp_scale: float) -> abpPoint:
    return abpPoint(abp_point.abp_x * abp_scale, abp_point.abp_y * abp_scale)


def abp__seg_m(abp_seg: abpSegment, abp_scale: float) -> abpSegment:
    return abpSegment(abp__m(abp_seg.abp_start, abp_scale), abp__m(abp_seg.abp_end, abp_scale))


def abp__poly_m(abp_poly: abpPolygon, abp_scale: float) -> abpPolygon:
    return abpPolygon(tuple(abp__m(abp_v, abp_scale) for abp_v in abp_poly.abp_vertices))


def abp__polygon(
    abp_c: Canvas, abp_frame: abp__Frame, abp_poly: abpPolygon, *, abp_fill: bool, abp_stroke: bool
) -> None:
    abp_path = abp_c.beginPath()
    abp_first, *abp_rest = abp_poly.abp_vertices
    abp_path.moveTo(*abp_frame.abp_p(abp_first))
    for abp_v in abp_rest:
        abp_path.lineTo(*abp_frame.abp_p(abp_v))
    abp_path.close()
    abp_c.drawPath(abp_path, stroke=int(abp_stroke), fill=int(abp_fill))


def abp__hatch(
    abp_c: Canvas,
    abp_frame: abp__Frame,
    abp_poly: abpPolygon,
    abp_color: colors.Color,
    abp_step: float,
) -> None:
    abp_c.saveState()
    abp_clip = abp_c.beginPath()
    abp_first, *abp_rest = abp_poly.abp_vertices
    abp_clip.moveTo(*abp_frame.abp_p(abp_first))
    for abp_v in abp_rest:
        abp_clip.lineTo(*abp_frame.abp_p(abp_v))
    abp_clip.close()
    abp_c.clipPath(abp_clip, stroke=0, fill=0)
    abp_xs = [abp_frame.abp_p(abp_v)[0] for abp_v in abp_poly.abp_vertices]
    abp_ys = [abp_frame.abp_p(abp_v)[1] for abp_v in abp_poly.abp_vertices]
    abp_c.setStrokeColor(abp_color)
    abp_c.setLineWidth(0.6)
    abp_span = (max(abp_xs) - min(abp_xs)) + (max(abp_ys) - min(abp_ys))
    abp_x = min(abp_xs) - (max(abp_ys) - min(abp_ys))
    while abp_x < min(abp_xs) + abp_span:
        abp_c.line(abp_x, min(abp_ys), abp_x + (max(abp_ys) - min(abp_ys)), max(abp_ys))
        abp_x += abp_step
    abp_c.restoreState()


def abp__arrow(
    abp_c: Canvas,
    abp_points: Sequence[tuple[float, float]],
    abp_width: float,
    abp_color: colors.Color,
    *,
    abp_chevron_every: float = 0.0,
    abp_start_dot: bool = False,
) -> None:
    if len(abp_points) < 2:
        return
    abp_head = abp_width * 3.6
    (abp_ax, abp_ay), (abp_bx, abp_by) = abp_points[-2], abp_points[-1]
    abp_angle = math.atan2(abp_by - abp_ay, abp_bx - abp_ax)
    abp_end = (
        abp_bx - abp_head * 0.8 * math.cos(abp_angle),
        abp_by - abp_head * 0.8 * math.sin(abp_angle),
    )
    abp_c.setStrokeColor(abp_color)
    abp_c.setLineWidth(abp_width)
    abp_c.setLineCap(1)
    abp_c.setLineJoin(1)
    abp_path = abp_c.beginPath()
    abp_path.moveTo(*abp_points[0])
    for abp_p in abp_points[1:-1]:
        abp_path.lineTo(*abp_p)
    abp_path.lineTo(*abp_end)
    abp_c.drawPath(abp_path, stroke=1, fill=0)
    abp_c.setFillColor(abp_color)
    abp__triangle(abp_c, abp_bx, abp_by, abp_angle, abp_head)
    if abp_start_dot:
        abp_c.circle(abp_points[0][0], abp_points[0][1], abp_width * 1.3, stroke=0, fill=1)
    if abp_chevron_every > 0:
        abp_c.setFillColor(colors.white)
        abp_total = sum(math.dist(abp_a, abp_b) for abp_a, abp_b in itertools.pairwise(abp_points))
        abp_target = abp_chevron_every
        abp_walked = 0.0
        for abp_a, abp_b in itertools.pairwise(abp_points):
            abp_length = math.dist(abp_a, abp_b)
            while (
                abp_length > 0
                and abp_target <= abp_walked + abp_length
                and abp_target < abp_total - 2.5 * abp_head
            ):
                abp_t = (abp_target - abp_walked) / abp_length
                abp_x, abp_y = (
                    abp_a[0] + abp_t * (abp_b[0] - abp_a[0]),
                    abp_a[1] + abp_t * (abp_b[1] - abp_a[1]),
                )
                abp__triangle(
                    abp_c,
                    abp_x
                    + abp_width
                    * 0.35
                    * math.cos(math.atan2(abp_b[1] - abp_a[1], abp_b[0] - abp_a[0])),
                    abp_y
                    + abp_width
                    * 0.35
                    * math.sin(math.atan2(abp_b[1] - abp_a[1], abp_b[0] - abp_a[0])),
                    math.atan2(abp_b[1] - abp_a[1], abp_b[0] - abp_a[0]),
                    abp_width * 0.9,
                )
                abp_target += abp_chevron_every
            abp_walked += abp_length


def abp__triangle(
    abp_c: Canvas, abp_x: float, abp_y: float, abp_angle: float, abp_size: float
) -> None:
    abp_tip = abp_c.beginPath()
    abp_tip.moveTo(abp_x, abp_y)
    for abp_side in (-1, 1):
        abp_wing = abp_angle + math.pi + abp_side * math.radians(28)
        abp_tip.lineTo(abp_x + abp_size * math.cos(abp_wing), abp_y + abp_size * math.sin(abp_wing))
    abp_tip.close()
    abp_c.drawPath(abp_tip, stroke=0, fill=1)


def abp__sign(
    abp_c: Canvas, abp_x: float, abp_y: float, abp_text: str, abp_size: float, abp_angle_deg: float
) -> None:
    abp_c.saveState()
    abp_c.setFont(abp_FONT_BOLD, abp_size)
    abp_text_w = abp_c.stringWidth(abp_text, abp_FONT_BOLD, abp_size)
    abp_w, abp_h = abp_text_w + abp_size * 3.4, abp_size * 2.0
    abp_c.translate(abp_x, abp_y)
    abp_c.setFillColor(abp_SAFE_GREEN)
    abp_c.setStrokeColor(colors.white)
    abp_c.setLineWidth(1)
    abp_c.roundRect(-abp_w / 2, -abp_h / 2, abp_w, abp_h, abp_size * 0.35, stroke=1, fill=1)
    abp_c.setFillColor(colors.white)
    abp_c.drawString(-abp_w / 2 + abp_size * 0.6, -abp_size * 0.36, abp_text)
    abp_c.translate(abp_w / 2 - abp_size * 1.3, 0)
    abp_c.rotate(abp_angle_deg)
    abp_c.setStrokeColor(colors.white)
    abp_c.setLineWidth(abp_size * 0.22)
    abp_c.line(-abp_size * 0.55, 0, abp_size * 0.45, 0)
    abp_arrow = abp_c.beginPath()
    abp_arrow.moveTo(abp_size * 0.7, 0)
    abp_arrow.lineTo(abp_size * 0.2, abp_size * 0.45)
    abp_arrow.lineTo(abp_size * 0.2, -abp_size * 0.45)
    abp_arrow.close()
    abp_c.drawPath(abp_arrow, stroke=0, fill=1)
    abp_c.restoreState()


def abp__wrap(
    abp_c: Canvas, abp_text: str, abp_font: str, abp_size: float, abp_width: float
) -> list[str]:
    abp_words, abp_lines, abp_line = abp_text.split(), [], ""
    for abp_word in abp_words:
        abp_candidate = f"{abp_line} {abp_word}".strip()
        if abp_c.stringWidth(abp_candidate, abp_font, abp_size) <= abp_width:
            abp_line = abp_candidate
        else:
            if abp_line:
                abp_lines.append(abp_line)
            abp_line = abp_word
    if abp_line:
        abp_lines.append(abp_line)
    return abp_lines


def abp__outward(
    abp_exit_seg: abpSegment, abp_routes: Sequence[abpRoomRoute], abp_center: abpPoint
) -> tuple[float, float]:
    abp_dx, abp_dy = (
        abp_exit_seg.abp_end.abp_x - abp_exit_seg.abp_start.abp_x,
        abp_exit_seg.abp_end.abp_y - abp_exit_seg.abp_start.abp_y,
    )
    abp_length = math.hypot(abp_dx, abp_dy) or 1.0
    abp_nx, abp_ny = -abp_dy / abp_length, abp_dx / abp_length
    abp_mid = abp_exit_seg.abp_midpoint
    abp_reference = None
    for abp_route in abp_routes:
        if (
            len(abp_route.abp_path_m) >= 2
            and abp_route.abp_path_m[-1].abp_distance_to(abp_mid) < 1.5
        ):
            abp_a, abp_b = abp_route.abp_path_m[-2], abp_route.abp_path_m[-1]
            abp_reference = (abp_b.abp_x - abp_a.abp_x, abp_b.abp_y - abp_a.abp_y)
            break
    if abp_reference is None:
        abp_reference = (abp_mid.abp_x - abp_center.abp_x, abp_mid.abp_y - abp_center.abp_y)
    if abp_nx * abp_reference[0] + abp_ny * abp_reference[1] < 0:
        abp_nx, abp_ny = -abp_nx, -abp_ny
    return abp_nx, abp_ny


def abp__draw_floor(
    abp_c: Canvas,
    abp_content: abpMapContent,
    abp_floor: abpMapFloor,
    abp_page_w: float,
    abp_page_h: float,
) -> None:
    abp_plan = abp_floor.abp_plan
    abp_opts = abp_content.abp_options
    abp_s = abp_plan.abp_scale_m_per_px or 1.0
    abp_big = abp_page_w > 1000
    abp_unit = 1.25 if abp_big else 1.0

    abp_band_h = 26 * mm * abp_unit
    abp_c.setFillColor(abp_BAND)
    abp_c.rect(0, abp_page_h - abp_band_h, abp_page_w, abp_band_h, stroke=0, fill=1)
    abp_c.setFillColor(abp_SAFE_GREEN)
    abp_c.rect(0, abp_page_h - abp_band_h - 2.2 * mm, abp_page_w, 2.2 * mm, stroke=0, fill=1)
    abp_c.setFillColor(colors.white)
    abp_c.setFont(abp_FONT_BOLD, 26 * abp_unit)
    abp_c.drawString(14 * mm, abp_page_h - 14 * mm * abp_unit, "PLANO DE EVACUACIÓN")
    abp_c.setFont(abp_FONT, 12 * abp_unit)
    abp_c.drawString(14 * mm, abp_page_h - 21.5 * mm * abp_unit, "En caso de sismo")
    abp_floor_name = f"Piso {abp_plan.abp_level + 1}" if len(abp_content.abp_floors) > 1 else ""
    abp_c.setFont(abp_FONT_BOLD, 15 * abp_unit)
    abp_c.drawRightString(
        abp_page_w - 14 * mm, abp_page_h - 13 * mm * abp_unit, abp_content.abp_project.abp_name
    )
    abp_c.setFont(abp_FONT, 11 * abp_unit)
    abp_subtitle = " · ".join(
        abp_x for abp_x in (abp_content.abp_project.abp_full_address, abp_floor_name) if abp_x
    )
    if abp_subtitle:
        abp_c.drawRightString(abp_page_w - 14 * mm, abp_page_h - 20.5 * mm * abp_unit, abp_subtitle)

    abp_margin = 12 * mm
    abp_panel_w = (95 if abp_big else 78) * mm
    abp_footer_h = 12 * mm
    abp_map_x0, abp_map_y0 = abp_margin, abp_margin + abp_footer_h
    abp_map_w = abp_page_w - abp_panel_w - 3 * abp_margin
    abp_map_h = abp_page_h - abp_band_h - 2.2 * mm - abp_map_y0 - abp_margin

    abp_min_x, abp_min_y, abp_max_x, abp_max_y = abp__bounds(abp_plan)
    abp_pad = 2.2
    abp_width_m, abp_height_m = (
        abp_max_x - abp_min_x + 2 * abp_pad,
        abp_max_y - abp_min_y + 2 * abp_pad,
    )
    abp_k = min(abp_map_w / abp_width_m, abp_map_h / abp_height_m)
    abp_ox = abp_map_x0 + (abp_map_w - abp_width_m * abp_k) / 2 + abp_pad * abp_k
    abp_oy = abp_map_y0 + (abp_map_h - abp_height_m * abp_k) / 2 + abp_pad * abp_k
    abp_frame = abp__Frame(abp_k, abp_ox, abp_oy, abp_min_x, abp_max_y)

    abp_c.setStrokeColor(colors.HexColor("#c5cdd3"))
    abp_c.setLineWidth(0.6)
    abp_c.roundRect(abp_map_x0, abp_map_y0, abp_map_w, abp_map_h, 3 * mm, stroke=1, fill=0)

    abp_c.setFillColor(abp_ROOM_FILL)
    abp_c.setStrokeColor(abp_ROOM_FILL)
    for abp_room in abp_plan.abp_rooms:
        abp__polygon(
            abp_c, abp_frame, abp__poly_m(abp_room.abp_area, abp_s), abp_fill=True, abp_stroke=False
        )
    for abp_zone in abp_plan.abp_safe_zones:
        abp_poly = abp__poly_m(abp_zone.abp_area, abp_s)
        abp_c.setFillColor(abp_SAFE_FILL)
        abp_c.setStrokeColor(abp_SAFE_GREEN)
        abp_c.setLineWidth(1.4)
        abp__polygon(abp_c, abp_frame, abp_poly, abp_fill=True, abp_stroke=True)
        abp__hatch(abp_c, abp_frame, abp_poly, colors.HexColor("#9fd3b2"), 7 * abp_unit)
    for abp_stair in abp_plan.abp_stairs:
        abp_poly = abp__poly_m(abp_stair.abp_area, abp_s)
        abp_c.setFillColor(abp_STAIR_FILL)
        abp_c.setStrokeColor(abp_STAIR_LINE)
        abp_c.setLineWidth(1)
        abp__polygon(abp_c, abp_frame, abp_poly, abp_fill=True, abp_stroke=True)
        abp__hatch(abp_c, abp_frame, abp_poly, colors.HexColor("#c3a8d8"), 4 * abp_unit)
    abp_c.setFillColor(abp_OBSTACLE_FILL)
    abp_c.setStrokeColor(colors.HexColor("#b0bac0"))
    abp_c.setLineWidth(0.5)
    for abp_obstacle in abp_plan.abp_obstacles:
        abp__polygon(
            abp_c,
            abp_frame,
            abp__poly_m(abp_obstacle.abp_area, abp_s),
            abp_fill=True,
            abp_stroke=True,
        )
    abp_wall_w = min(5.0, max(2.2, 0.22 * abp_k))
    abp_c.setStrokeColor(abp_WALL)
    abp_c.setLineWidth(abp_wall_w)
    abp_c.setLineCap(2)
    for abp_wall in abp_plan.abp_walls:
        abp_seg = abp__seg_m(abp_wall.abp_segment, abp_s)
        abp_c.line(*abp_frame.abp_p(abp_seg.abp_start), *abp_frame.abp_p(abp_seg.abp_end))
    for abp_door in abp_plan.abp_doors:
        abp_seg = abp__seg_m(abp_door.abp_segment, abp_s)
        abp_c.setStrokeColor(colors.white)
        abp_c.setLineWidth(abp_wall_w + 0.6)
        abp_c.setLineCap(0)
        abp_c.line(*abp_frame.abp_p(abp_seg.abp_start), *abp_frame.abp_p(abp_seg.abp_end))
        abp_c.setStrokeColor(colors.HexColor("#8d6e63"))
        abp_c.setLineWidth(0.8)
        abp_c.line(*abp_frame.abp_p(abp_seg.abp_start), *abp_frame.abp_p(abp_seg.abp_end))
    abp_center = abpPoint((abp_min_x + abp_max_x) / 2, (abp_min_y + abp_max_y) / 2)
    abp_exits = [abp_e for abp_e in abp_plan.abp_exits if abp_e.abp_confirmed]
    for abp_exit_ in abp_exits:
        abp_seg = abp__seg_m(abp_exit_.abp_segment, abp_s)
        abp_c.setStrokeColor(abp_SAFE_GREEN)
        abp_c.setLineWidth(abp_wall_w + 1.4)
        abp_c.setLineCap(0)
        abp_c.line(*abp_frame.abp_p(abp_seg.abp_start), *abp_frame.abp_p(abp_seg.abp_end))

    abp_route_w = min(4.5, max(2.2, 0.16 * abp_k)) * (1.1 if abp_big else 1.0)
    abp_network = abp_floor.abp_network
    for abp_branch in abp_network.abp_branches if abp_network is not None else ():
        abp__arrow(
            abp_c,
            [abp_frame.abp_p(abp_p) for abp_p in abp_branch.abp_points_m],
            abp_route_w,
            abp_SAFE_GREEN,
            abp_chevron_every=2.2 * abp_k,
            abp_start_dot=not abp_branch.abp_trunk,
        )
    for abp__name, abp_link in abp_network.abp_meeting_links if abp_network is not None else ():
        abp__arrow(
            abp_c,
            [abp_frame.abp_p(abp_p) for abp_p in abp_link],
            abp_route_w,
            abp_SAFE_GREEN,
            abp_chevron_every=2.2 * abp_k,
        )
    for abp_route in abp_floor.abp_routes if abp_network is None else ():
        if len(abp_route.abp_path_m) >= 2:
            abp__arrow(
                abp_c,
                [abp_frame.abp_p(abp_p) for abp_p in abp_route.abp_path_m],
                abp_route_w,
                abp_SAFE_GREEN,
                abp_chevron_every=3.0 * abp_k,
                abp_start_dot=True,
            )

    abp_c.setFillColor(abp_ROOM_TEXT)
    abp_label_size = (8.5 if abp_big else 7) * abp_unit
    for abp_room in abp_plan.abp_rooms:
        abp_cx, abp_cy = abp_frame.abp_p(abp__poly_m(abp_room.abp_area, abp_s).abp_centroid)
        abp_text = abp_room.abp_name.upper()
        abp_tw = abp_c.stringWidth(abp_text, abp_FONT_BOLD, abp_label_size)
        abp_ty = abp_cy + abp_label_size * 1.2
        abp_c.saveState()
        abp_c.setFillColor(colors.white)
        abp_c.setFillAlpha(0.85)
        abp_c.roundRect(
            abp_tw / -2 + abp_cx - 2.5,
            abp_ty - abp_label_size * 0.35,
            abp_tw + 5,
            abp_label_size * 1.35,
            2,
            0,
            1,
        )
        abp_c.restoreState()
        abp_c.setFillColor(abp_ROOM_TEXT)
        abp_c.setFont(abp_FONT_BOLD, abp_label_size)
        abp_c.drawCentredString(abp_cx, abp_ty, abp_text)
    for abp_stair in abp_plan.abp_stairs:
        abp_cx, abp_cy = abp_frame.abp_p(abp__poly_m(abp_stair.abp_area, abp_s).abp_centroid)
        abp_c.setFillColor(abp_STAIR_LINE)
        abp_c.setFont(abp_FONT_BOLD, abp_label_size)
        abp_c.drawCentredString(
            abp_cx, abp_cy - abp_label_size / 3, (abp_stair.abp_name or "ESCALERA").upper()
        )
    for abp_zone in abp_plan.abp_safe_zones:
        abp_cx, abp_cy = abp_frame.abp_p(abp__poly_m(abp_zone.abp_area, abp_s).abp_centroid)
        abp_c.setFillColor(abp_SAFE_GREEN)
        abp_c.setFont(abp_FONT_BOLD, abp_label_size * 1.15)
        abp_c.drawCentredString(abp_cx, abp_cy + abp_label_size * 0.2, "ZONA SEGURA")
        if abp_zone.abp_name:
            abp_c.setFont(abp_FONT, abp_label_size)
            abp_c.drawCentredString(abp_cx, abp_cy - abp_label_size * 1.1, abp_zone.abp_name)

    abp_sign_size = (9 if abp_big else 7.5) * abp_unit
    for abp_exit_ in abp_exits:
        abp_seg = abp__seg_m(abp_exit_.abp_segment, abp_s)
        abp_nx, abp_ny = abp__outward(abp_seg, abp_floor.abp_routes, abp_center)
        abp_mid = abp_seg.abp_midpoint
        abp_anchor = abpPoint(abp_mid.abp_x + abp_nx * 1.1, abp_mid.abp_y + abp_ny * 1.1)
        abp_px, abp_py = abp_frame.abp_p(abp_anchor)
        abp_angle = math.degrees(math.atan2(-abp_ny, abp_nx))
        abp__sign(abp_c, abp_px, abp_py, "SALIDA", abp_sign_size, abp_angle)
        abp_c.setFillColor(abp_INK)
        abp_c.setFont(abp_FONT, abp_sign_size * 0.8)
        abp_c.drawCentredString(abp_px, abp_py - abp_sign_size * 1.9, abp_exit_.abp_name)

    for abp_sign in abp_plan.abp_signs:
        abp_sx, abp_sy = abp_frame.abp_p(abp__m(abp_sign.abp_position, abp_s))
        abp_size = min(max(0.55 * abp_k, 11 * abp_unit), 20 * abp_unit)
        abp_draw_sign(
            abp_c,
            abp_SIGNS[abp_sign.abp_kind],
            abp_sx,
            abp_sy,
            abp_size,
            abp_sign.abp_rotation_deg,
            abp_sign.abp_text,
        )

    abp_here = dict(abp_opts.abp_you_are_here).get(abp_plan.abp_level)
    if abp_here:
        abp_here_room = next(
            (abp_r for abp_r in abp_plan.abp_rooms if abp_r.abp_name == abp_here), None
        )
        if abp_here_room is not None:
            abp_hx, abp_hy = abp_frame.abp_p(
                abp__poly_m(abp_here_room.abp_area, abp_s).abp_centroid
            )
            abp_hy -= abp_label_size * 1.2
            abp_radius = 5.5 * abp_unit
            abp_c.setFillColor(abp_HERE_RED)
            abp_c.setStrokeColor(colors.white)
            abp_c.setLineWidth(1.5)
            abp_c.circle(abp_hx, abp_hy, abp_radius, stroke=1, fill=1)
            abp_c.setFont(abp_FONT_BOLD, abp_label_size)
            abp_text = "USTED ESTÁ AQUÍ"
            abp_tw = abp_c.stringWidth(abp_text, abp_FONT_BOLD, abp_label_size)
            abp_c.setFillColor(colors.white)
            abp_c.roundRect(
                abp_hx - abp_tw / 2 - 3,
                abp_hy - abp_radius - abp_label_size * 1.9,
                abp_tw + 6,
                abp_label_size * 1.45,
                2,
                stroke=0,
                fill=1,
            )
            abp_c.setFillColor(abp_HERE_RED)
            abp_c.drawCentredString(abp_hx, abp_hy - abp_radius - abp_label_size * 1.45, abp_text)

    abp_bar_m = abp__nice_length(abp_map_w / abp_k / 5)
    abp_bx, abp_by = abp_map_x0 + 6 * mm, abp_map_y0 + 6 * mm
    abp_c.setStrokeColor(abp_INK)
    abp_c.setFillColor(abp_INK)
    abp_c.setLineWidth(1)
    for abp_i in range(4):
        abp_x = abp_bx + abp_i * abp_bar_m * abp_k / 4
        abp_c.setFillColor(abp_INK if abp_i % 2 == 0 else colors.white)
        abp_c.rect(abp_x, abp_by, abp_bar_m * abp_k / 4, 2.2 * mm, stroke=1, fill=1)
    abp_c.setFillColor(abp_INK)
    abp_c.setFont(abp_FONT, 7.5 * abp_unit)
    abp_c.drawString(abp_bx, abp_by + 3.6 * mm, "0")
    abp_c.drawRightString(abp_bx + abp_bar_m * abp_k + 2, abp_by + 3.6 * mm, f"{abp_bar_m:g} m")

    abp__draw_panel(
        abp_c,
        abp_content,
        abp_page_w - abp_margin - abp_panel_w,
        abp_map_y0,
        abp_panel_w,
        abp_map_h,
        abp_unit,
    )

    abp_c.setFillColor(abp_MUTED)
    abp_c.setFont(abp_FONT, 7 * abp_unit)
    abp_footer = abp_opts.abp_disclaimer or ""
    abp_made_on = abp_content.abp_made_on.strftime("%d/%m/%Y")
    abp_made = f"Elaborado el {abp_made_on} con RutaSegura {abp_content.abp_app_version}".strip()
    if abp_opts.abp_responsible:
        abp_made += f" · Responsable: {abp_opts.abp_responsible}"
    abp_c.drawString(abp_margin, abp_margin + 2 * mm, abp_made)
    if abp_footer:
        abp_lines = abp__wrap(
            abp_c, abp_footer, abp_FONT, 7 * abp_unit, abp_page_w / 2 - abp_margin
        )
        abp_line_h = 8.5 * abp_unit
        for abp_i, abp_line in enumerate(abp_lines):
            abp_c.drawRightString(
                abp_page_w - abp_margin,
                abp_margin + 2 * mm + (len(abp_lines) - 1 - abp_i) * abp_line_h,
                abp_line,
            )


def abp__nice_length(abp_target: float) -> float:
    for abp_value in (1, 2, 5, 10, 20, 25, 50, 100):
        if abp_value >= abp_target:
            return float(abp_value)
    return 100.0


def abp__draw_panel(
    abp_c: Canvas,
    abp_content: abpMapContent,
    abp_x: float,
    abp_y: float,
    abp_w: float,
    abp_h: float,
    abp_unit: float,
) -> None:
    abp_opts = abp_content.abp_options
    abp_c.setFillColor(abp_PANEL_FILL)
    abp_c.setStrokeColor(colors.HexColor("#d5dee4"))
    abp_c.setLineWidth(0.6)
    abp_c.roundRect(abp_x, abp_y, abp_w, abp_h, 3 * mm, stroke=1, fill=1)
    abp_pad = 5 * mm
    abp_cursor = abp_y + abp_h - abp_pad
    abp_inner = abp_w - 2 * abp_pad

    def abp_title(abp_text: str) -> None:
        nonlocal abp_cursor
        abp_c.setFillColor(abp_BAND)
        abp_c.setFont(abp_FONT_BOLD, 10.5 * abp_unit)
        abp_c.drawString(abp_x + abp_pad, abp_cursor - 10 * abp_unit, abp_text)
        abp_c.setStrokeColor(abp_BAND_ACCENT)
        abp_c.setLineWidth(1.2)
        abp_c.line(
            abp_x + abp_pad,
            abp_cursor - 13 * abp_unit,
            abp_x + abp_pad + abp_inner,
            abp_cursor - 13 * abp_unit,
        )
        abp_cursor -= 20 * abp_unit

    def abp_text_line(
        abp_text: str,
        abp_size: float = 8.5,
        abp_bold: bool = False,
        abp_color: colors.Color = abp_INK,
    ) -> None:
        nonlocal abp_cursor
        abp_font = abp_FONT_BOLD if abp_bold else abp_FONT
        abp_c.setFillColor(abp_color)
        abp_c.setFont(abp_font, abp_size * abp_unit)
        for abp_line in abp__wrap(abp_c, abp_text, abp_font, abp_size * abp_unit, abp_inner):
            abp_c.drawString(abp_x + abp_pad, abp_cursor - abp_size * abp_unit, abp_line)
            abp_cursor -= abp_size * abp_unit * 1.35

    abp_title("LEYENDA")
    abp_sw = 11 * mm
    abp_items: list[tuple[str, str]] = [
        ("ruta", "Ruta de evacuación"),
        ("salida", "Salida"),
        ("zona", "Zona segura en caso de sismo"),
        ("escalera", "Escalera"),
        ("aqui", "Usted está aquí"),
        ("muro", "Muro"),
        ("puerta", "Puerta"),
    ]
    for abp_kind, abp_label in abp_items:
        abp_cy = abp_cursor - 5 * abp_unit
        abp_sx = abp_x + abp_pad
        if abp_kind == "ruta":
            abp__arrow(abp_c, [(abp_sx, abp_cy), (abp_sx + abp_sw, abp_cy)], 2.4, abp_SAFE_GREEN)
        elif abp_kind == "salida":
            abp__sign(abp_c, abp_sx + abp_sw / 2, abp_cy, "S", 6 * abp_unit, 0)
        elif abp_kind == "zona":
            abp_c.setFillColor(abp_SAFE_FILL)
            abp_c.setStrokeColor(abp_SAFE_GREEN)
            abp_c.setLineWidth(1)
            abp_c.rect(abp_sx, abp_cy - 3.2 * abp_unit, abp_sw, 6.4 * abp_unit, stroke=1, fill=1)
        elif abp_kind == "escalera":
            abp_c.setFillColor(abp_STAIR_FILL)
            abp_c.setStrokeColor(abp_STAIR_LINE)
            abp_c.rect(abp_sx, abp_cy - 3.2 * abp_unit, abp_sw, 6.4 * abp_unit, stroke=1, fill=1)
        elif abp_kind == "aqui":
            abp_c.setFillColor(abp_HERE_RED)
            abp_c.circle(abp_sx + abp_sw / 2, abp_cy, 3.6 * abp_unit, stroke=0, fill=1)
        elif abp_kind == "muro":
            abp_c.setStrokeColor(abp_WALL)
            abp_c.setLineWidth(2.6)
            abp_c.line(abp_sx, abp_cy, abp_sx + abp_sw, abp_cy)
        else:
            abp_c.setStrokeColor(abp_WALL)
            abp_c.setLineWidth(2.6)
            abp_c.line(abp_sx, abp_cy, abp_sx + abp_sw * 0.3, abp_cy)
            abp_c.line(abp_sx + abp_sw * 0.7, abp_cy, abp_sx + abp_sw, abp_cy)
            abp_c.setStrokeColor(colors.HexColor("#8d6e63"))
            abp_c.setLineWidth(0.8)
            abp_c.line(abp_sx + abp_sw * 0.3, abp_cy, abp_sx + abp_sw * 0.7, abp_cy)
        abp_c.setFillColor(abp_INK)
        abp_c.setFont(abp_FONT, 8.5 * abp_unit)
        abp_c.drawString(abp_sx + abp_sw + 3 * mm, abp_cy - 3 * abp_unit, abp_label)
        abp_cursor -= 12 * abp_unit
    abp_cursor -= 4 * abp_unit

    if abp_opts.abp_instructions:
        abp_title("EN CASO DE SISMO")
        for abp_i, abp_step in enumerate(abp_opts.abp_instructions, start=1):
            abp_text_line(f"{abp_i}. {abp_step}", 8.3)
            abp_cursor -= 2 * abp_unit
        abp_cursor -= 3 * abp_unit

    if abp_opts.abp_meeting_point:
        abp_title("PUNTO DE REUNIÓN")
        abp_text_line(abp_opts.abp_meeting_point, 8.5, abp_bold=True, abp_color=abp_SAFE_GREEN)
        abp_cursor -= 4 * abp_unit

    if abp_opts.abp_phones:
        abp_title("TELÉFONOS DE EMERGENCIA")
        for abp_service, abp_number in abp_opts.abp_phones:
            abp_c.setFillColor(abp_INK)
            abp_c.setFont(abp_FONT, 8.8 * abp_unit)
            abp_c.drawString(abp_x + abp_pad, abp_cursor - 9 * abp_unit, abp_service)
            abp_c.setFont(abp_FONT_BOLD, 10 * abp_unit)
            abp_c.setFillColor(abp_HERE_RED)
            abp_c.drawRightString(
                abp_x + abp_pad + abp_inner, abp_cursor - 9 * abp_unit, abp_number
            )
            abp_cursor -= 13 * abp_unit
        abp_cursor -= 4 * abp_unit


def abp_write_evacuation_map(abp_path: Path, abp_content: abpMapContent) -> None:
    abp__register_fonts()
    abp_page_w, abp_page_h = abp_PAPER_SIZES.get(
        abp_content.abp_options.abp_paper, abp_PAPER_SIZES["A3"]
    )
    abp_path.parent.mkdir(parents=True, exist_ok=True)
    abp_c = Canvas(str(abp_path), pagesize=(abp_page_w, abp_page_h))
    abp_c.setTitle(f"Plano de evacuación - {abp_content.abp_project.abp_name}")
    abp_c.setAuthor("RutaSegura")
    for abp_floor in abp_content.abp_floors:
        abp__draw_floor(abp_c, abp_content, abp_floor, abp_page_w, abp_page_h)
        abp_c.showPage()
    abp_c.save()
