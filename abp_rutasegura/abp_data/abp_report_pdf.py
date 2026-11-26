from __future__ import annotations

import io
import os
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_domain.abp_norms import abpNormEvaluation, abpNormRule
from abp_rutasegura.abp_domain.abp_people import abpPersonProfile
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_results import (
    abpFloorClearance,
    abpObservation,
    abpRoomRoute,
    abpRunStatistics,
    abpSimulationResult,
)
from abp_rutasegura.abp_domain.abp_scenario import abpScenario

abp_FONT = "Arial"
abp_FONT_BOLD = "Arial-Bold"
abp_FONT_BOLD_ITALIC = "Arial-BoldItalic"
abp__FONT_FILES: dict[str, tuple[str, ...]] = {
    abp_FONT: ("arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    abp_FONT_BOLD: (
        "arialbd.ttf",
        "Arial_Bold.ttf",
        "LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ),
    abp_FONT_BOLD_ITALIC: (
        "arialbi.ttf",
        "Arial_Bold_Italic.ttf",
        "LiberationSans-BoldItalic.ttf",
        "DejaVuSans-BoldOblique.ttf",
    ),
}
abp_PLOT_FONTS = ["Arial", "Liberation Sans", "DejaVu Sans"]
abp_INK = colors.black
abp_MUTED = colors.HexColor("#444444")
abp_LINE = colors.black
abp_HEADER_BG = colors.HexColor("#e6e6e6")
abp_ROUTE_GREEN = "#1e8a4c"
abp_USE_LABELS = {
    "educacion": "Educación",
    "oficinas": "Oficinas",
    "comercio": "Comercio (tienda, restaurante)",
}


@dataclass(frozen=True)
class abpScenarioRow:
    abp_name: str
    abp_occupants: int
    abp_blocked_exits: tuple[str, ...]
    abp_total_time_s: float
    abp_time_90_s: float | None
    abp_evacuated: int
    abp_agents: int
    abp_completed: bool
    abp_bottlenecks: int
    abp_runs: int = 1
    abp_total_p95_s: float | None = None


@dataclass(frozen=True, eq=False)
class abpReportContent:
    abp_project: abpProject
    abp_plan: abpFloorPlan
    abp_plan_image: npt.NDArray[np.uint8] | None
    abp_scenario: abpScenario
    abp_norms: abpNormEvaluation
    abp_result: abpSimulationResult | None
    abp_congestion: tuple[abpObservation, ...]
    abp_profiles: tuple[abpPersonProfile, ...]
    abp_provisional_profiles: tuple[str, ...]
    abp_parameters: tuple[tuple[str, str], ...]
    abp_legal_disclaimer: str
    abp_app_version: str
    abp_comparison: tuple[abpScenarioRow, ...] = ()
    abp_floors: tuple[tuple[abpFloorPlan, npt.NDArray[np.uint8] | None], ...] = ()
    abp_generated_at: datetime = field(default_factory=datetime.now)
    abp_statistics: abpRunStatistics | None = None
    abp_floor_clearance: tuple[abpFloorClearance, ...] = ()

    @property
    def abp_all_floors(self) -> tuple[tuple[abpFloorPlan, npt.NDArray[np.uint8] | None], ...]:
        return self.abp_floors or ((self.abp_plan, self.abp_plan_image),)


def abp__font_folders() -> list[Path]:
    abp_folders = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
    abp_local = os.environ.get("LOCALAPPDATA")
    if abp_local:
        abp_folders.append(Path(abp_local) / "Microsoft" / "Windows" / "Fonts")
    abp_folders += [
        Path("/usr/share/fonts/truetype/msttcorefonts"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/truetype/liberation2"),
        Path(matplotlib.get_data_path()) / "fonts" / "ttf",
    ]
    return abp_folders


def abp_font_file(abp_font: str) -> Path:
    abp_folders = abp__font_folders()
    for abp_name in abp__FONT_FILES[abp_font]:
        for abp_folder in abp_folders:
            if (abp_folder / abp_name).is_file():
                return abp_folder / abp_name
    return abp_folders[-1] / abp__FONT_FILES[abp_font][-1]


def abp__register_fonts() -> None:
    abp_registered = pdfmetrics.getRegisteredFontNames()
    for abp_font in abp__FONT_FILES:
        if abp_font not in abp_registered:
            pdfmetrics.registerFont(TTFont(abp_font, str(abp_font_file(abp_font))))
    pdfmetrics.registerFontFamily(
        abp_FONT,
        normal=abp_FONT,
        bold=abp_FONT_BOLD,
        italic=abp_FONT,
        boldItalic=abp_FONT_BOLD_ITALIC,
    )


def abp_plot_style() -> AbstractContextManager[Any]:
    return matplotlib.rc_context({"font.family": "sans-serif", "font.sans-serif": abp_PLOT_FONTS})


def abp__styles() -> dict[str, ParagraphStyle]:
    abp_base = getSampleStyleSheet()
    abp_body = ParagraphStyle(
        "body",
        parent=abp_base["BodyText"],
        fontName=abp_FONT,
        fontSize=9.5,
        leading=13.5,
        textColor=abp_INK,
    )
    return {
        "body": abp_body,
        "small": ParagraphStyle("small", parent=abp_body, fontSize=8.2, leading=10.8),
        "small_bold": ParagraphStyle(
            "small_bold", parent=abp_body, fontName=abp_FONT_BOLD, fontSize=8.2, leading=10.8
        ),
        "muted": ParagraphStyle(
            "muted", parent=abp_body, fontSize=8.2, leading=10.8, textColor=abp_MUTED
        ),
        "th": ParagraphStyle(
            "th",
            parent=abp_body,
            fontName=abp_FONT_BOLD,
            fontSize=8.2,
            leading=10.5,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=abp_body,
            fontName=abp_FONT_BOLD,
            fontSize=15,
            leading=19,
            spaceBefore=10,
            spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=abp_body,
            fontName=abp_FONT_BOLD,
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "card_title": ParagraphStyle("card_title", parent=abp_body, fontSize=8, leading=10),
        "card_value": ParagraphStyle(
            "card_value", parent=abp_body, fontName=abp_FONT_BOLD, fontSize=17, leading=21
        ),
        "card_note": ParagraphStyle("card_note", parent=abp_body, fontSize=7.5, leading=9.5),
        "box": ParagraphStyle("box", parent=abp_body, fontSize=8.8, leading=12),
        "warning": ParagraphStyle(
            "warning",
            parent=abp_body,
            borderColor=abp_LINE,
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=8,
            spaceAfter=12,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=abp_body, leftIndent=12, bulletIndent=2, spaceAfter=3
        ),
    }


def abp_format_duration(abp_seconds: float) -> str:
    abp_minutes, abp_secs = divmod(round(max(0.0, abp_seconds)), 60)
    return f"{abp_minutes} min {abp_secs:02d} s" if abp_minutes else f"{abp_secs} s"


def abp__escape(abp_text: str) -> str:
    return abp_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def abp__table(
    abp_rows: Sequence[Sequence[str]],
    abp_widths: Sequence[float],
    abp_styles: dict[str, ParagraphStyle],
    *,
    abp_row_kinds: Sequence[str | None] = (),
) -> Table:
    abp_header, *abp_body = abp_rows
    abp_cells = [[Paragraph(abp__escape(abp_c), abp_styles["th"]) for abp_c in abp_header]]
    for abp_i, abp_row in enumerate(abp_body):
        abp_bold = abp_i < len(abp_row_kinds) and abp_row_kinds[abp_i] == "error"
        abp_cells.append(
            [
                Paragraph(abp__escape(abp_c), abp_styles["small_bold" if abp_bold else "small"])
                for abp_c in abp_row
            ]
        )
    abp_table = Table(abp_cells, colWidths=list(abp_widths), repeatRows=1)
    abp_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), abp_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, abp_LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    abp_table.setStyle(TableStyle(abp_commands))
    return abp_table


def abp__data_table(
    abp_pairs: Sequence[tuple[str, str]], abp_styles: dict[str, ParagraphStyle]
) -> Table:
    abp_rows = [
        [
            Paragraph(f"<b>{abp__escape(abp_k)}</b>", abp_styles["small"]),
            Paragraph(abp__escape(abp_v), abp_styles["small"]),
        ]
        for abp_k, abp_v in abp_pairs
        if abp_v
    ]
    abp_table = Table(abp_rows, colWidths=[4.6 * cm, 12.4 * cm])
    abp_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, abp_LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return abp_table


def abp__box(abp_text: str, abp_kind: str, abp_styles: dict[str, ParagraphStyle]) -> Table:
    if abp_kind == "error":
        abp_text = f"<b>{abp_text}</b>"
    abp_table = Table([[Paragraph(abp_text, abp_styles["box"])]], colWidths=[17 * cm])
    abp_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, abp_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return abp_table


def abp__cards(
    abp_cards: Sequence[tuple[str, str, str, str]], abp_styles: dict[str, ParagraphStyle]
) -> Table:
    abp_row = []
    for abp_title, abp_value, abp_note, abp__kind in abp_cards:
        abp_row.append(
            [
                Paragraph(abp__escape(abp_title), abp_styles["card_title"]),
                Paragraph(abp__escape(abp_value), abp_styles["card_value"]),
                Paragraph(abp__escape(abp_note), abp_styles["card_note"]),
            ]
        )
    abp_width = 17 * cm / len(abp_cards)
    abp_table = Table([abp_row], colWidths=[abp_width] * len(abp_cards))
    abp_commands: list[tuple[Any, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.5, abp_LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    abp_table.setStyle(TableStyle(abp_commands))
    return abp_table


def abp__figure_image(abp_fig: Figure, abp_width_cm: float) -> Image:
    abp_buffer = io.BytesIO()
    with abp_plot_style():
        abp_fig.savefig(abp_buffer, format="png")
    abp_buffer.seek(0)
    abp_w, abp_h = abp_fig.get_size_inches()
    return Image(abp_buffer, width=abp_width_cm * cm, height=abp_width_cm * cm * abp_h / abp_w)


def abp__section(
    abp_title: str, abp_first: Sequence[Flowable], abp_styles: dict[str, ParagraphStyle]
) -> Flowable:
    return KeepTogether([Paragraph(abp_title, abp_styles["h1"]), *abp_first])


def abp_plan_figure(abp_plan: abpFloorPlan, abp_routes: Sequence[abpRoomRoute]) -> Figure | None:
    abp_s = abp_plan.abp_scale_m_per_px
    if abp_s is None or not (abp_plan.abp_walls or abp_plan.abp_rooms):
        return None
    with abp_plot_style():
        return abp__plan_figure(abp_plan, abp_routes, abp_s)


def abp__plan_figure(
    abp_plan: abpFloorPlan, abp_routes: Sequence[abpRoomRoute], abp_s: float
) -> Figure:
    abp_fig = Figure(figsize=(7.5, 5.0), dpi=160)
    abp_ax = abp_fig.add_subplot()

    def abp_poly(abp_points: Sequence[abpPoint]) -> list[tuple[float, float]]:
        return [(abp_p.abp_x * abp_s, abp_p.abp_y * abp_s) for abp_p in abp_points]

    for abp_zone in abp_plan.abp_safe_zones:
        abp_ax.add_patch(
            MplPolygon(
                abp_poly(abp_zone.abp_area.abp_vertices),
                closed=True,
                fc="none",
                ec="black",
                hatch="//",
            )
        )
    for abp_stair in abp_plan.abp_stairs:
        abp_ax.add_patch(
            MplPolygon(
                abp_poly(abp_stair.abp_area.abp_vertices),
                closed=True,
                fc="none",
                ec="#555555",
                hatch="\\\\",
            )
        )
    for abp_obstacle in abp_plan.abp_obstacles:
        abp_ax.add_patch(
            MplPolygon(
                abp_poly(abp_obstacle.abp_area.abp_vertices),
                closed=True,
                fc="#e0e0e0",
                ec="#808080",
            )
        )
    for abp_wall in abp_plan.abp_walls:
        (abp_x1, abp_y1), (abp_x2, abp_y2) = abp_poly(
            (abp_wall.abp_segment.abp_start, abp_wall.abp_segment.abp_end)
        )
        abp_ax.plot(
            [abp_x1, abp_x2], [abp_y1, abp_y2], color="black", lw=2.2, solid_capstyle="butt"
        )
    for abp_door in abp_plan.abp_doors:
        (abp_x1, abp_y1), (abp_x2, abp_y2) = abp_poly(
            (abp_door.abp_segment.abp_start, abp_door.abp_segment.abp_end)
        )
        abp_ax.plot([abp_x1, abp_x2], [abp_y1, abp_y2], color="#808080", lw=0.9)
    for abp_exit_ in abp_plan.abp_exits:
        if not abp_exit_.abp_confirmed:
            continue
        (abp_x1, abp_y1), (abp_x2, abp_y2) = abp_poly(
            (abp_exit_.abp_segment.abp_start, abp_exit_.abp_segment.abp_end)
        )
        abp_ax.plot(
            [abp_x1, abp_x2], [abp_y1, abp_y2], color="black", lw=4.5, solid_capstyle="butt"
        )
        abp_ax.annotate(
            abp_exit_.abp_name,
            ((abp_x1 + abp_x2) / 2, (abp_y1 + abp_y2) / 2),
            xytext=(0, -11),
            textcoords="offset points",
            ha="center",
            fontsize=6.5,
            color="black",
            fontweight="bold",
        )
    for abp_route in abp_routes:
        if abp_route.abp_level != abp_plan.abp_level or len(abp_route.abp_path_m) < 2:
            continue
        abp_xs = [abp_p.abp_x for abp_p in abp_route.abp_path_m]
        abp_ys = [abp_p.abp_y for abp_p in abp_route.abp_path_m]
        abp_ax.plot(abp_xs, abp_ys, color=abp_ROUTE_GREEN, lw=1.6, alpha=0.9)
        abp_ax.annotate(
            "",
            xy=(abp_xs[-1], abp_ys[-1]),
            xytext=(abp_xs[-2], abp_ys[-2]),
            arrowprops={
                "arrowstyle": "-|>",
                "color": abp_ROUTE_GREEN,
                "lw": 1.6,
                "mutation_scale": 11,
            },
        )
        abp_ax.plot(abp_xs[0], abp_ys[0], "o", color=abp_ROUTE_GREEN, ms=3.5)
    for abp_room in abp_plan.abp_rooms:
        abp_c = abp_room.abp_area.abp_centroid
        abp_ax.text(
            abp_c.abp_x * abp_s,
            abp_c.abp_y * abp_s,
            abp_room.abp_name,
            ha="center",
            va="bottom",
            fontsize=6.5,
            color="black",
            bbox={"boxstyle": "square,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.8},
        )
    abp_ax.set_aspect("equal")
    abp_ax.invert_yaxis()
    abp_ax.axis("off")
    abp_fig.tight_layout()
    return abp_fig


def abp_heatmap_figure(
    abp_content: abpReportContent, abp_level: int | None = None
) -> Figure | None:
    with abp_plot_style():
        return abp__heatmap_figure(abp_content, abp_level)


def abp__heatmap_figure(abp_content: abpReportContent, abp_level: int | None) -> Figure | None:
    abp_result = abp_content.abp_result
    if abp_result is None:
        return None
    abp_floors = {
        abp_p.abp_level: (abp_p, abp_img) for abp_p, abp_img in abp_content.abp_all_floors
    }
    abp_maps = {abp_m.abp_level: abp_m for abp_m in abp_result.abp_maps()}
    if abp_level is None:
        abp_level = min(abp_floors)
    abp_plan, abp_plan_image = abp_floors.get(
        abp_level, (abp_content.abp_plan, abp_content.abp_plan_image)
    )
    abp_floor_map = (
        abp_maps.get(abp_level) if abp_result.abp_floor_maps else abp_result.abp_maps()[0]
    )
    abp_scale = abp_plan.abp_scale_m_per_px
    if abp_scale is None or abp_floor_map is None:
        return None
    abp_fig = Figure(figsize=(7.5, 5.0), dpi=150)
    abp_ax = abp_fig.add_subplot()
    if abp_plan_image is not None:
        abp_h, abp_w = abp_plan_image.shape[:2]
        abp_gray = abp_plan_image.mean(axis=2) if abp_plan_image.ndim == 3 else abp_plan_image
        abp_ax.imshow(
            abp_gray, cmap="gray", extent=(0, abp_w * abp_scale, abp_h * abp_scale, 0), alpha=0.5
        )
    abp_density = np.ma.masked_less_equal(abp_floor_map.abp_density_map, 0.0)
    abp_rows, abp_cols = abp_floor_map.abp_density_map.shape
    abp_x0, abp_y0 = abp_floor_map.abp_grid_origin_m
    abp_size = abp_floor_map.abp_cell_size_m
    abp_image = abp_ax.imshow(
        abp_density,
        cmap="Greys",
        extent=(abp_x0, abp_x0 + abp_cols * abp_size, abp_y0 + abp_rows * abp_size, abp_y0),
        alpha=0.78,
        interpolation="nearest",
    )
    for abp_rank, abp_bottleneck in enumerate(abp_result.abp_bottlenecks[:5], start=1):
        if abp_result.abp_floor_maps and abp_bottleneck.abp_level != abp_level:
            continue
        abp_ax.annotate(
            str(abp_rank),
            (abp_bottleneck.abp_location.abp_x, abp_bottleneck.abp_location.abp_y),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="white",
            bbox={"boxstyle": "circle,pad=0.25", "fc": "black", "ec": "white"},
        )
    abp_ax.set_xlabel("metros")
    abp_ax.set_ylabel("metros")
    abp_ax.set_aspect("equal")
    abp_cbar = abp_fig.colorbar(abp_image, ax=abp_ax, shrink=0.8)
    abp_cbar.set_label("Densidad acumulada (personas·s/m²)")
    abp_fig.tight_layout()
    return abp_fig


def abp_curve_figure(abp_result: abpSimulationResult) -> Figure:
    with abp_plot_style():
        return abp__curve_figure(abp_result)


def abp__curve_figure(abp_result: abpSimulationResult) -> Figure:
    abp_fig = Figure(figsize=(7.5, 3.2), dpi=150)
    abp_ax = abp_fig.add_subplot()
    abp_ax.step(
        abp_result.abp_curve_times_s,
        abp_result.abp_curve_evacuated,
        where="post",
        color="black",
        lw=1.4,
    )
    abp_ax.axhline(abp_result.abp_agents_total, color="#808080", linestyle="--", linewidth=0.8)
    for abp_fraction, abp_label in ((0.5, "50 %"), (0.9, "90 %")):
        abp_t = abp_result.abp_time_to_evacuate(abp_fraction)
        if abp_t is not None:
            abp_ax.axvline(abp_t, color="#555555", linestyle=":", linewidth=0.9)
            abp_ax.text(
                abp_t,
                abp_result.abp_agents_total * 0.04,
                f" {abp_label}",
                color="black",
                fontsize=7,
            )
    abp_ax.set_xlabel("Tiempo (s)")
    abp_ax.set_ylabel("Personas evacuadas")
    abp_ax.set_ylim(0, max(1, abp_result.abp_agents_total) * 1.05)
    abp_ax.grid(alpha=0.25)
    for abp_spine in ("top", "right"):
        abp_ax.spines[abp_spine].set_visible(False)
    abp_fig.tight_layout()
    return abp_fig


def abp_rule_state(abp_rule: abpNormRule) -> str:
    if not abp_rule.abp_verified:
        return "No verificada"
    if abp_rule.abp_verified_by and abp_rule.abp_verified_on:
        return f"Verificada por {abp_rule.abp_verified_by} el {abp_rule.abp_verified_on.strftime('%d/%m/%Y')}"
    return "Verificada"


def abp__findings(abp_content: abpReportContent) -> list[tuple[str, str]]:
    abp_out: list[tuple[str, str]] = []
    abp_result, abp_norms = abp_content.abp_result, abp_content.abp_norms
    if abp_result is not None and not abp_result.abp_completed:
        abp_left = abp_result.abp_agents_total - abp_result.abp_agents_evacuated
        abp_out.append(
            (f"Al final de la simulación quedaban {abp_left} persona(s) dentro.", "error")
        )
    abp_exceeded = [abp_c for abp_c in abp_norms.abp_capacities if abp_c.abp_exceeded]
    if abp_exceeded:
        abp_names = ", ".join(
            f"«{abp_c.abp_room_name}» ({abp_c.abp_occupants} de {abp_c.abp_capacity})"
            for abp_c in abp_exceeded[:4]
        )
        abp_out.append((f"{len(abp_exceeded)} ambiente(s) superan su aforo: {abp_names}.", "error"))
    abp_others = len(abp_norms.abp_observations) - len(abp_exceeded)
    if abp_others > 0:
        abp_out.append(
            (
                f"{abp_others} observación(es) sobre anchos, recorridos u otras reglas (sección 3).",
                "warning",
            )
        )
    if abp_content.abp_congestion:
        abp_out.append(
            (f"Mayor congestión: {abp_content.abp_congestion[0].abp_description}", "warning")
        )
    if (
        abp_result is not None
        and abp_result.abp_completed
        and not abp_exceeded
        and not abp_norms.abp_observations
    ):
        abp_out.append(
            ("Todas las personas salen y no hay incumplimientos con las reglas usadas.", "success")
        )
    abp_unverified = len(abp_norms.abp_unverified_rules)
    if abp_unverified:
        abp_out.append(
            (
                f"{abp_unverified} de {len(abp_norms.abp_rules_used)} reglas usadas aún no están verificadas "
                "con el texto oficial (anexo A).",
                "info",
            )
        )
    return abp_out


def abp__recommendations(abp_content: abpReportContent) -> list[tuple[str, str, str]]:
    abp_seen: set[str] = set()
    abp_out: list[tuple[str, str, str]] = []
    for abp_obs in abp_content.abp_norms.abp_observations:
        if abp_obs.abp_recommendation in abp_seen:
            continue
        abp_seen.add(abp_obs.abp_recommendation)
        abp_out.append(("Alta", abp_obs.abp_description, abp_obs.abp_recommendation))
    for abp_obs in abp_content.abp_congestion:
        if abp_obs.abp_recommendation in abp_seen:
            continue
        abp_seen.add(abp_obs.abp_recommendation)
        abp_out.append(("Media", abp_obs.abp_description, abp_obs.abp_recommendation))
    return abp_out


def abp_write_report(abp_path: Path, abp_content: abpReportContent) -> None:
    abp__register_fonts()
    abp_s = abp__styles()
    abp_story: list[Flowable] = []
    abp_project = abp_content.abp_project
    abp_result = abp_content.abp_result
    abp_norms = abp_content.abp_norms
    abp_stats = abp_content.abp_statistics
    abp_unverified = abp_norms.abp_unverified_rules
    abp_area = sum(abp_c.abp_area_m2 for abp_c in abp_norms.abp_capacities)
    abp_scenario = abp_content.abp_scenario

    abp_floors_text = str(len(abp_content.abp_all_floors))
    abp_story += [
        Spacer(1, 6.2 * cm),
        Paragraph("Datos del local", abp_s["h2"]),
        abp__data_table(
            [
                ("Local", abp_project.abp_name),
                (
                    "Tipo de local",
                    abp_USE_LABELS.get(abp_project.abp_use.value, abp_project.abp_use.value),
                ),
                ("Dirección", abp_project.abp_address or "No registrada"),
                ("Distrito / provincia / departamento", abp_project.abp_location),
                (
                    "Responsable",
                    ", ".join(
                        abp_p
                        for abp_p in (abp_project.abp_responsible, abp_project.abp_responsible_role)
                        if abp_p
                    ),
                ),
                ("Teléfono", abp_project.abp_phone),
                ("Correo", abp_project.abp_email),
                ("Horario de mayor concurrencia", abp_project.abp_schedule),
                ("Observaciones", abp_project.abp_notes),
            ],
            abp_s,
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Datos del estudio", abp_s["h2"]),
        abp__data_table(
            [
                ("Fecha del informe", abp_content.abp_generated_at.strftime("%d/%m/%Y %H:%M")),
                ("Pisos evaluados", abp_floors_text),
                ("Área de ambientes", f"{abp_area:.1f} m²" if abp_area else ""),
                ("Ocupantes considerados", str(abp_norms.abp_total_occupants)),
                ("Escenario", f"{abp_scenario.abp_name} (semilla {abp_scenario.abp_seed})"),
                ("Corridas de simulación", str(abp_stats.abp_runs) if abp_stats else "1"),
                ("Emergencia evaluada", "Sismo"),
                ("Programa", f"RutaSegura {abp_content.abp_app_version}, sin conexión a internet"),
            ],
            abp_s,
        ),
        Spacer(1, 0.6 * cm),
        abp__box(
            f"<b>Aclaración legal.</b> {abp__escape(abp_content.abp_legal_disclaimer)}",
            "warning",
            abp_s,
        ),
        PageBreak(),
    ]

    abp_cards: list[tuple[str, str, str, str]] = []
    if abp_result is None:
        abp_summary_first: list[Flowable] = [
            abp__box("Todavía no se ha simulado la evacuación de este local.", "info", abp_s)
        ]
    else:
        abp_congestion = len(abp_content.abp_congestion)
        abp_complete = abp_result.abp_completed and (
            abp_stats is None or abp_stats.abp_all_completed
        )
        abp_total_kind = (
            "error" if not abp_complete else ("warning" if abp_congestion else "success")
        )
        if abp_stats is not None:
            abp_cards.append(
                (
                    "Tiempo total (promedio)",
                    abp_format_duration(abp_stats.abp_total_mean_s),
                    f"{abp_stats.abp_runs} corridas · peor caso P95: {abp_format_duration(abp_stats.abp_total_p95_s)}",
                    abp_total_kind,
                )
            )
        else:
            abp_cards.append(
                (
                    "Tiempo total",
                    abp_format_duration(abp_result.abp_total_time_s),
                    f"{abp_congestion} zona(s) de congestión"
                    if abp_congestion
                    else "Sin congestión sostenida",
                    abp_total_kind,
                )
            )
        abp_ninety = abp_result.abp_time_to_evacuate(0.9)
        abp_cards.append(
            (
                "90 % evacuado",
                "—" if abp_ninety is None else abp_format_duration(abp_ninety),
                "Momento en que salió el 90 %",
                "info",
            )
        )
        abp_cards.append(
            (
                "Personas evacuadas",
                f"{abp_result.abp_agents_evacuated} de {abp_result.abp_agents_total}",
                "Salieron todas" if abp_result.abp_completed else "Quedaron personas dentro",
                "success" if abp_result.abp_completed else "error",
            )
        )
        abp_summary_first = [abp__cards(abp_cards, abp_s), Spacer(1, 0.25 * cm)]
    abp_exceeded = any(abp_c.abp_exceeded for abp_c in abp_norms.abp_capacities)
    abp_capacity_card = abp__cards(
        [
            (
                "Aforo calculado",
                f"{abp_norms.abp_total_capacity}",
                f"Ocupantes asignados: {abp_norms.abp_total_occupants}",
                "error" if abp_exceeded else "success",
            ),
            (
                "Observaciones normativas",
                str(len(abp_norms.abp_observations)),
                "Ver sección 3",
                "warning" if abp_norms.abp_observations else "success",
            ),
            (
                "Reglas verificadas",
                f"{len(abp_norms.abp_rules_used) - len(abp_unverified)} de {len(abp_norms.abp_rules_used)}",
                "Ver anexo A",
                "warning" if abp_unverified else "success",
            ),
        ],
        abp_s,
    )
    abp_lines = []
    if abp_result is not None:
        if abp_stats is not None:
            abp_lines.append(
                f"<b>Tiempo total estimado de evacuación: {abp_format_duration(abp_stats.abp_total_mean_s)}"
                f"</b> (promedio de {abp_stats.abp_runs} corridas; peor caso P95: "
                f"{abp_format_duration(abp_stats.abp_total_p95_s)}; rango {abp_format_duration(abp_stats.abp_total_min_s)} "
                f"a {abp_format_duration(abp_stats.abp_total_max_s)})."
            )
        else:
            abp_total = abp_format_duration(abp_result.abp_total_time_s)
            abp_lines.append(f"<b>Tiempo total estimado de evacuación: {abp_total}</b>.")
    abp_lines.append(
        f"Aforo calculado: {abp_norms.abp_total_capacity} personas. "
        f"Ocupantes asignados: {abp_norms.abp_total_occupants}."
    )
    abp_story.append(abp__section("1. Resumen ejecutivo", abp_summary_first, abp_s))
    abp_story += [abp_capacity_card, Spacer(1, 0.3 * cm)]
    abp_story += [Paragraph(abp_line, abp_s["body"]) for abp_line in abp_lines]
    abp_findings = abp__findings(abp_content)
    if abp_findings:
        abp_story.append(Paragraph("Hallazgos principales", abp_s["h2"]))
        for abp_text, abp_finding_kind in abp_findings:
            abp_story += [abp__box(abp__escape(abp_text), abp_finding_kind, abp_s), Spacer(1, 3)]
    if abp_unverified:
        abp_story.append(
            Paragraph(
                f"<b>Advertencia:</b> este informe usó {len(abp_unverified)} regla(s) normativa(s) "
                "con valores de referencia que todavía no fueron contrastados con el texto "
                "oficial del RNE (marcadas «no verificada»). Antes de usar estos resultados con "
                "fines formales, verifíquelas en RutaSegura (Herramientas › Reglas normativas). "
                "El detalle está en el anexo A.",
                abp_s["warning"],
            )
        )

    abp_route_rows = [["Ambiente", "Categoría", "Área (m²)", "Recorrido máx. (m)", "Sale por"]]
    abp_routes = {abp_r.abp_room_name: abp_r for abp_r in abp_norms.abp_routes}
    for abp_cap in abp_norms.abp_capacities:
        abp_route = abp_routes.get(abp_cap.abp_room_name)
        abp_route_rows.append(
            [
                abp_cap.abp_room_name,
                abp_cap.abp_category_label or abp_cap.abp_category,
                f"{abp_cap.abp_area_m2:.1f}",
                "—" if abp_route is None else f"{abp_route.abp_max_distance_m:.1f}",
                "—" if abp_route is None else abp_route.abp_target_name,
            ]
        )
    abp_first: list[Flowable] = [
        Paragraph(
            "Plano redibujado a partir del plano corregido en RutaSegura. Las flechas verdes "
            "muestran la ruta más corta de cada ambiente a su salida o zona segura; el recorrido "
            "máximo se mide desde el punto más alejado del ambiente.",
            abp_s["body"],
        )
    ]
    for abp_plan, abp__image in abp_content.abp_all_floors:
        abp_fig = abp_plan_figure(abp_plan, abp_norms.abp_routes)
        if abp_fig is None:
            continue
        abp_caption = (
            f"Piso {abp_plan.abp_level + 1}" if len(abp_content.abp_all_floors) > 1 else ""
        )
        abp_block: list[Flowable] = [abp__figure_image(abp_fig, 16.5)]
        if abp_caption:
            abp_block.insert(0, Paragraph(abp_caption, abp_s["h2"]))
        abp_first.append(KeepTogether(abp_block))
        break
    abp_story.append(abp__section("2. El local y sus rutas de evacuación", abp_first, abp_s))
    for abp_plan, abp__image in abp_content.abp_all_floors[1:]:
        abp_fig = abp_plan_figure(abp_plan, abp_norms.abp_routes)
        if abp_fig is not None:
            abp_story.append(
                KeepTogether(
                    [
                        Paragraph(f"Piso {abp_plan.abp_level + 1}", abp_s["h2"]),
                        abp__figure_image(abp_fig, 16.5),
                    ]
                )
            )
    if len(abp_route_rows) > 1:
        abp_story.append(
            abp__table(abp_route_rows, [4.2 * cm, 4.4 * cm, 2.2 * cm, 2.8 * cm, 3.4 * cm], abp_s)
        )

    abp_rows = [
        ["Ambiente", "Categoría", "Área (m²)", "m²/persona", "Aforo", "Ocupantes", "Estado"]
    ]
    abp_kinds: list[str | None] = []
    for abp_cap in abp_norms.abp_capacities:
        abp_kind: str | None
        if abp_cap.abp_capacity is None:
            abp_status, abp_kind = "Sin aforo propio", None
        elif abp_cap.abp_exceeded:
            abp_status, abp_kind = "Excede el aforo", "error"
        else:
            abp_status, abp_kind = "Correcto", None
        abp_kinds.append(abp_kind)
        abp_rows.append(
            [
                abp_cap.abp_room_name,
                abp_cap.abp_category_label or abp_cap.abp_category,
                f"{abp_cap.abp_area_m2:.1f}",
                "—" if abp_cap.abp_m2_per_person is None else f"{abp_cap.abp_m2_per_person:g}",
                "—" if abp_cap.abp_capacity is None else str(abp_cap.abp_capacity),
                str(abp_cap.abp_occupants),
                abp_status,
            ]
        )
    if len(abp_rows) == 1:
        abp_rows.append(["Sin ambientes marcados", "", "", "", "", "", ""])
    abp_capacity_table = abp__table(
        abp_rows,
        [3.4 * cm, 3.6 * cm, 1.8 * cm, 2 * cm, 1.5 * cm, 1.9 * cm, 2.8 * cm],
        abp_s,
        abp_row_kinds=abp_kinds,
    )
    abp_story.append(
        abp__section(
            "3. Aforo y verificación normativa",
            [
                Paragraph(
                    "Aforo = área del ambiente ÷ m² por persona de su categoría. Los baños, "
                    "depósitos, patios y pasillos no tienen aforo propio: sus usuarios ya se "
                    "cuentan en otros ambientes.",
                    abp_s["muted"],
                ),
                Spacer(1, 4),
                abp_capacity_table,
            ],
            abp_s,
        )
    )
    abp_story.append(Paragraph("Observaciones normativas", abp_s["h2"]))
    if not abp_norms.abp_observations:
        abp_story.append(
            Paragraph("No se encontraron incumplimientos con las reglas usadas.", abp_s["body"])
        )
    for abp_i, abp_obs in enumerate(abp_norms.abp_observations, start=1):
        abp_state = "verificada" if abp_obs.abp_verified else "<b>regla no verificada</b>"
        abp_text = (
            f"<b>{abp_i}. {abp__escape(abp_obs.abp_description)}</b><br/>"
            f"Norma: {abp__escape(abp_obs.abp_norm or '')}, {abp__escape(abp_obs.abp_article or '')} — {abp_state}<br/>"
            f"Recomendación: {abp__escape(abp_obs.abp_recommendation)}"
        )
        abp_story += [KeepTogether([abp__box(abp_text, "warning", abp_s)]), Spacer(1, 4)]

    if abp_result is None:
        abp_story.append(
            abp__section(
                "4. Simulación de la evacuación",
                [
                    Paragraph(
                        "Simule la evacuación (paso 6) para completar esta sección.", abp_s["body"]
                    )
                ],
                abp_s,
            )
        )
    else:
        abp_intro: list[Flowable] = [
            Paragraph(
                "Cada persona espera su tiempo de reacción y luego camina hacia la salida o zona "
                "segura más cercana, frenando cuando hay mucha gente alrededor.",
                abp_s["body"],
            )
        ]
        if abp_stats is not None:
            abp_stats_rows = [
                ["Indicador", "Valor"],
                [
                    "Corridas (semillas)",
                    f"{abp_stats.abp_runs} ({abp_stats.abp_seeds[0]} a {abp_stats.abp_seeds[-1]})",
                ],
                ["Tiempo total promedio", abp_format_duration(abp_stats.abp_total_mean_s)],
                ["Desviación estándar", abp_format_duration(abp_stats.abp_total_std_s)],
                ["Mejor corrida", abp_format_duration(abp_stats.abp_total_min_s)],
                ["Peor corrida", abp_format_duration(abp_stats.abp_total_max_s)],
                ["Peor caso razonable (P95)", abp_format_duration(abp_stats.abp_total_p95_s)],
                ["Corrida mostrada (mediana)", f"semilla {abp_stats.abp_representative_seed}"],
            ]
            abp_intro += [
                Paragraph("Resultados de varias corridas", abp_s["h2"]),
                abp__table(abp_stats_rows, [8 * cm, 6 * cm], abp_s),
            ]
        abp_levels = [abp_p.abp_level for abp_p, _ in abp_content.abp_all_floors]
        abp_heat_blocks: list[list[Flowable]] = []
        for abp_level in abp_levels:
            abp_heat = abp_heatmap_figure(abp_content, abp_level)
            if abp_heat is None:
                continue
            abp_title = "Mapa de calor de congestión"
            if len(abp_levels) > 1:
                abp_title += f" — Piso {abp_level + 1}"
            abp_heat_blocks.append(
                [
                    Paragraph(abp_title, abp_s["h2"]),
                    abp__figure_image(abp_heat, 15),
                    Paragraph(
                        "Las zonas más oscuras concentraron más personas en movimiento durante "
                        "más tiempo. Los números indican los cuellos de botella del ranking.",
                        abp_s["muted"],
                    ),
                ]
            )
        abp_first_heat = abp_heat_blocks[0] if abp_heat_blocks and abp_stats is None else []
        abp_story.append(
            abp__section("4. Simulación de la evacuación", [*abp_intro, *abp_first_heat], abp_s)
        )
        for abp_block in abp_heat_blocks[1:] if abp_first_heat else abp_heat_blocks:
            abp_story.append(KeepTogether(abp_block))
        abp_story.append(
            KeepTogether(
                [
                    Paragraph("Personas evacuadas a lo largo del tiempo", abp_s["h2"]),
                    abp__figure_image(abp_curve_figure(abp_result), 16),
                ]
            )
        )
        if abp_content.abp_floor_clearance:
            abp_lowest = min(abp_f.abp_level for abp_f in abp_content.abp_floor_clearance)
            abp_floor_rows = [
                ["Piso", "Personas que empezaron ahí", "Cómo salieron", "Piso vacío a los"]
            ]
            abp_floor_kinds: list[str | None] = []
            for abp_floor in sorted(
                abp_content.abp_floor_clearance, key=lambda abp_f: -abp_f.abp_level
            ):
                abp_how = (
                    "Por las salidas del primer piso"
                    if abp_floor.abp_level == abp_lowest
                    else f"{abp_floor.abp_descended} bajaron por la escalera"
                )
                abp_floor_rows.append(
                    [
                        f"Piso {abp_floor.abp_level + 1}",
                        str(abp_floor.abp_people),
                        abp_how,
                        "No se vació"
                        if abp_floor.abp_cleared_s is None
                        else abp_format_duration(abp_floor.abp_cleared_s),
                    ]
                )
                abp_floor_kinds.append("error" if abp_floor.abp_cleared_s is None else None)
            abp_story.append(
                KeepTogether(
                    [
                        Paragraph("Desalojo por piso", abp_s["h2"]),
                        Paragraph(
                            "En los pisos altos la única salida es la escalera: las personas bajan "
                            "y salen por el primer piso. El primer piso se vacía al final porque "
                            "recibe a quienes bajan.",
                            abp_s["muted"],
                        ),
                        abp__table(
                            abp_floor_rows,
                            [2.4 * cm, 4.2 * cm, 6.4 * cm, 4 * cm],
                            abp_s,
                            abp_row_kinds=abp_floor_kinds,
                        ),
                    ]
                )
            )
        if abp_result.abp_time_per_exit_s:
            abp_exit_rows = [["Salida o zona segura", "Última persona en salir"]]
            abp_exit_rows += [
                [abp_name, abp_format_duration(abp_t)]
                for abp_name, abp_t in abp_result.abp_time_per_exit_s
            ]
            abp_story.append(
                KeepTogether(
                    [
                        Paragraph("Tiempo por salida", abp_s["h2"]),
                        abp__table(abp_exit_rows, [9 * cm, 5 * cm], abp_s),
                    ]
                )
            )
        abp_ranking_title = Paragraph("Ranking de cuellos de botella", abp_s["h2"])
        if not abp_content.abp_congestion:
            abp_story.append(
                KeepTogether(
                    [
                        abp_ranking_title,
                        Paragraph("No se detectaron zonas de congestión sostenida.", abp_s["body"]),
                    ]
                )
            )
        else:
            abp_ranking = [["N.º", "Dónde y cuánto", "Recomendación"]]
            abp_ranking += [
                [str(abp_i), abp_obs.abp_description, abp_obs.abp_recommendation]
                for abp_i, abp_obs in enumerate(abp_content.abp_congestion, start=1)
            ]
            abp_story.append(
                KeepTogether(
                    [
                        abp_ranking_title,
                        abp__table(abp_ranking, [1.1 * cm, 8.4 * cm, 7.5 * cm], abp_s),
                    ]
                )
            )

    abp_section = 5
    if len(abp_content.abp_comparison) >= 2:
        abp_rows = [
            [
                "Escenario",
                "Personas",
                "Salidas bloqueadas",
                "Tiempo total",
                "Peor caso (P95)",
                "Al 90 %",
                "Evacuados",
                "Cuellos",
            ]
        ]
        abp_kinds = []
        for abp_row in abp_content.abp_comparison:
            abp_evacuated = f"{abp_row.abp_evacuated} de {abp_row.abp_agents}" + (
                "" if abp_row.abp_completed else " (incompleto)"
            )
            abp_kinds.append(None if abp_row.abp_completed else "error")
            abp_rows.append(
                [
                    abp_row.abp_name,
                    str(abp_row.abp_occupants),
                    ", ".join(abp_row.abp_blocked_exits) or "Ninguna",
                    abp_format_duration(abp_row.abp_total_time_s),
                    "—"
                    if abp_row.abp_total_p95_s is None
                    else abp_format_duration(abp_row.abp_total_p95_s),
                    "—"
                    if abp_row.abp_time_90_s is None
                    else abp_format_duration(abp_row.abp_time_90_s),
                    abp_evacuated,
                    str(abp_row.abp_bottlenecks),
                ]
            )
        abp_widths = [
            3.0 * cm,
            1.5 * cm,
            2.6 * cm,
            2.0 * cm,
            2.0 * cm,
            1.7 * cm,
            2.4 * cm,
            1.4 * cm,
        ]
        abp_story.append(
            abp__section(
                f"{abp_section}. Comparación de escenarios",
                [
                    Paragraph(
                        "Última simulación de cada escenario «qué pasa si». El tiempo total suele "
                        "depender de la persona que reacciona más tarde; el tiempo para evacuar "
                        "al 90 % muestra mejor el efecto de bloquear salidas o cambiar el aforo.",
                        abp_s["body"],
                    ),
                    abp__table(abp_rows, abp_widths, abp_s, abp_row_kinds=abp_kinds),
                ],
                abp_s,
            )
        )
        abp_section += 1

    abp_recommendations = abp__recommendations(abp_content)
    if abp_recommendations:
        abp_rec_rows = [["Prioridad", "Situación", "Qué hacer"]]
        abp_rec_rows += [
            [abp_p, abp_what, abp_how] for abp_p, abp_what, abp_how in abp_recommendations
        ]
        abp_rec_kinds = [
            "error" if abp_p == "Alta" else "warning" for abp_p, _, _ in abp_recommendations
        ]
        abp_story.append(
            abp__section(
                f"{abp_section}. Recomendaciones priorizadas",
                [
                    abp__table(
                        abp_rec_rows,
                        [2 * cm, 7.6 * cm, 7.4 * cm],
                        abp_s,
                        abp_row_kinds=abp_rec_kinds,
                    )
                ],
                abp_s,
            )
        )

    abp_rule_rows = [["Regla", "Valor usado", "Norma y artículo", "Estado"]]
    abp_rule_kinds: list[str | None] = []
    for abp_rule in abp_norms.abp_rules_used:
        abp_name = (
            f"{abp_rule.abp_label} — {abp_rule.abp_description}"
            if abp_rule.abp_label
            else abp_rule.abp_description
        )
        abp_rule_rows.append(
            [abp_name, abp_rule.abp_value_text, abp_rule.abp_citation, abp_rule_state(abp_rule)]
        )
        abp_rule_kinds.append(None if abp_rule.abp_verified else "warning")
    abp_story.append(PageBreak())
    abp_story.append(
        abp__section(
            "Anexo A. Reglas normativas usadas",
            [
                Paragraph(
                    "RutaSegura trae valores de referencia para cada regla (índices de ocupación, "
                    "anchos mínimos, distancias), pero no los da por buenos hasta que alguien los "
                    "contraste con el texto oficial vigente del RNE y la guía de cálculo de aforo "
                    "de CENEPRED. Por eso una regla aparece <b>«No verificada»</b>: el cálculo es "
                    "orientativo. Cuando un profesional revisa la norma, puede registrar el valor "
                    "y el artículo oficiales en <b>Herramientas › Reglas normativas</b>; la regla "
                    "pasa a «Verificada» con su nombre y la fecha.",
                    abp_s["body"],
                ),
                Spacer(1, 5),
                abp__table(
                    abp_rule_rows,
                    [6.4 * cm, 2.6 * cm, 3.6 * cm, 4.4 * cm],
                    abp_s,
                    abp_row_kinds=abp_rule_kinds,
                ),
            ],
            abp_s,
        )
    )

    abp_params_first: list[Flowable] = [
        Paragraph(
            f"Escenario: {abp__escape(abp_scenario.abp_name)}. Semilla: {abp_scenario.abp_seed} (con la misma "
            "semilla y los mismos datos, la simulación da el mismo resultado).",
            abp_s["body"],
        )
    ]
    if abp_scenario.abp_runs > 1 or (
        abp_scenario.abp_reaction_factor,
        abp_scenario.abp_speed_factor,
    ) != (1.0, 1.0):
        abp_params_first.append(
            Paragraph(
                f"Ajustes del escenario: {abp_scenario.abp_runs} corrida(s) con semillas consecutivas; "
                f"tiempo de reacción × {abp_scenario.abp_reaction_factor:g}; velocidad × "
                f"{abp_scenario.abp_speed_factor:g}.",
                abp_s["body"],
            )
        )
    abp_story.append(abp__section("Anexo B. Parámetros y semilla", abp_params_first, abp_s))
    abp_profile_rows = [
        ["Perfil", "Velocidad máx. (m/s)", "Reacción media (s)", "Desv. (s)", "Radio (m)"]
    ]
    for abp_p in abp_content.abp_profiles:
        abp_mark = (
            " (provisional)" if abp_p.abp_name in abp_content.abp_provisional_profiles else ""
        )
        abp_profile_rows.append(
            [
                abp_p.abp_name + abp_mark,
                f"{abp_p.abp_max_speed_mps:.2f}",
                f"{abp_p.abp_reaction_mean_s:.1f}",
                f"{abp_p.abp_reaction_std_s:.1f}",
                f"{abp_p.abp_radius_m:.2f}",
            ]
        )
    abp_story += [
        Paragraph("Perfiles de personas", abp_s["h2"]),
        abp__table(abp_profile_rows, [4.6 * cm, 3.2 * cm, 3.2 * cm, 2.2 * cm, 2.2 * cm], abp_s),
    ]
    abp_param_rows = [
        ["Parámetro del modelo", "Valor"],
        *[[abp_k, abp_v] for abp_k, abp_v in abp_content.abp_parameters],
    ]
    abp_story.append(
        KeepTogether(
            [
                Paragraph("Modelo de movimiento", abp_s["h2"]),
                abp__table(abp_param_rows, [10 * cm, 5 * cm], abp_s),
            ]
        )
    )
    if abp_content.abp_provisional_profiles:
        abp_story.append(
            Paragraph(
                "Los valores marcados como provisionales deben calibrarse con un simulacro real "
                "(Herramientas › Calibrar con un simulacro real).",
                abp_s["muted"],
            )
        )

    abp_story.append(
        abp__section(
            "Anexo C. Aclaración legal",
            [abp__box(abp__escape(abp_content.abp_legal_disclaimer), "warning", abp_s)],
            abp_s,
        )
    )

    abp__build(abp_path, abp_content, abp_story)


def abp__build(abp_path: Path, abp_content: abpReportContent, abp_story: list[Flowable]) -> None:
    abp_project = abp_content.abp_project
    abp_page_w, abp_page_h = A4
    abp_footer = abp_content.abp_legal_disclaimer
    abp_logo = abp__logo_reader(abp_project.abp_logo_path)

    def abp_cover(abp_canvas: Canvas, abp_doc: SimpleDocTemplate) -> None:
        abp_canvas.saveState()
        abp_left = 2 * cm
        abp_canvas.setFillColor(abp_INK)
        abp_canvas.setFont(abp_FONT, 10)
        abp_canvas.drawString(abp_left, abp_page_h - 1.9 * cm, "Informe técnico de apoyo")
        abp_canvas.setFont(abp_FONT_BOLD, 20)
        abp_canvas.drawString(abp_left, abp_page_h - 3.2 * cm, "Informe de evacuación ante sismo")
        abp_canvas.setFont(abp_FONT_BOLD, 13)
        abp_canvas.drawString(abp_left, abp_page_h - 4.3 * cm, abp_project.abp_name[:60])
        abp_canvas.setFont(abp_FONT, 10)
        abp_canvas.drawString(abp_left, abp_page_h - 5.0 * cm, abp_project.abp_full_address[:95])
        abp_canvas.setStrokeColor(abp_LINE)
        abp_canvas.setLineWidth(0.8)
        abp_canvas.line(
            abp_left, abp_page_h - 5.6 * cm, abp_page_w - abp_left, abp_page_h - 5.6 * cm
        )
        if abp_logo is not None:
            abp_w, abp_h = abp_logo.getSize()
            abp_box_h, abp_box_w = 2.6 * cm, 4.2 * cm
            abp_k = min(abp_box_w / abp_w, abp_box_h / abp_h)
            abp_x = abp_page_w - 1.8 * cm - abp_box_w
            abp_y = abp_page_h - 1.2 * cm - abp_box_h
            abp_canvas.drawImage(
                abp_logo,
                abp_x + (abp_box_w - abp_w * abp_k) / 2,
                abp_y + (abp_box_h - abp_h * abp_k) / 2,
                abp_w * abp_k,
                abp_h * abp_k,
                mask="auto",
            )
        abp__footer(abp_canvas, abp_doc, abp_footer)
        abp_canvas.restoreState()

    def abp_later(abp_canvas: Canvas, abp_doc: SimpleDocTemplate) -> None:
        abp_canvas.saveState()
        abp_canvas.setStrokeColor(abp_LINE)
        abp_canvas.setLineWidth(0.5)
        abp_canvas.line(
            1.8 * cm, abp_page_h - 1.3 * cm, abp_page_w - 1.8 * cm, abp_page_h - 1.3 * cm
        )
        abp_canvas.setFont(abp_FONT, 7.5)
        abp_canvas.setFillColor(abp_MUTED)
        abp_canvas.drawString(
            1.8 * cm, abp_page_h - 1.15 * cm, f"Informe de evacuación — {abp_project.abp_name}"[:90]
        )
        abp_canvas.drawRightString(
            abp_page_w - 1.8 * cm,
            abp_page_h - 1.15 * cm,
            abp_content.abp_generated_at.strftime("%d/%m/%Y"),
        )
        abp__footer(abp_canvas, abp_doc, abp_footer)
        abp_canvas.restoreState()

    abp_path.parent.mkdir(parents=True, exist_ok=True)
    abp_document = SimpleDocTemplate(
        str(abp_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.9 * cm,
        bottomMargin=2 * cm,
        title=f"Informe de evacuación — {abp_project.abp_name}",
        author="RutaSegura",
    )
    abp_document.build(abp_story, onFirstPage=abp_cover, onLaterPages=abp_later)


def abp__footer(abp_canvas: Canvas, abp_doc: SimpleDocTemplate, abp_text: str) -> None:
    abp_page_w = A4[0]
    abp_canvas.setFont(abp_FONT, 6.5)
    abp_canvas.setFillColor(abp_MUTED)
    abp_canvas.drawCentredString(abp_page_w / 2, 1.25 * cm, abp_text)
    abp_canvas.drawRightString(abp_page_w - 1.8 * cm, 0.8 * cm, f"Página {abp_doc.page}")


def abp__logo_reader(abp_path: str | None) -> ImageReader | None:
    if not abp_path or not Path(abp_path).is_file():
        return None
    try:
        abp_reader = ImageReader(abp_path)
        abp_reader.getSize()
    except (OSError, ValueError):
        return None
    return abp_reader
