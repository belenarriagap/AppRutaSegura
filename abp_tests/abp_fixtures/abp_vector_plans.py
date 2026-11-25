from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pymupdf

abp_DENOMINATOR = 50
abp_PT_PER_M = 72 / 0.0254 / abp_DENOMINATOR
abp_ORIGIN = (70.0, 60.0)
abp_WALL = 0.15
abp_WIDTH, abp_HEIGHT, abp_CORRIDOR_Y = 10.0, 7.0, 5.0
abp_DOOR_A, abp_DOOR_B, abp_EXIT_DOOR = (2.0, 2.9), (7.0, 7.9), (5.4, 6.6)


@dataclass(frozen=True)
class abpStyle:
    abp_walls: str = "doble"
    abp_polyline_arcs: bool = False
    abp_angle_deg: float = 0.0
    abp_stairs: bool = False
    abp_dimensions: bool = False
    abp_labels: bool = True
    abp_signs: bool = False
    abp_numbered_stairs: bool = False
    abp_tags: bool = False


abp__angle = 0.0


def abp__pt(abp_x: float, abp_y: float) -> pymupdf.Point:
    abp_c, abp_s = math.cos(math.radians(abp__angle)), math.sin(math.radians(abp__angle))
    abp_dx, abp_dy = abp_x - abp_WIDTH / 2, abp_y - abp_HEIGHT / 2
    abp_u, abp_v = (
        abp_WIDTH / 2 + abp_dx * abp_c - abp_dy * abp_s,
        abp_HEIGHT / 2 + abp_dx * abp_s + abp_dy * abp_c,
    )
    return pymupdf.Point(abp_ORIGIN[0] + abp_u * abp_PT_PER_M, abp_ORIGIN[1] + abp_v * abp_PT_PER_M)


def abp__wall(
    abp_shape: pymupdf.Shape,
    abp_x1: float,
    abp_y1: float,
    abp_x2: float,
    abp_y2: float,
    abp_kind: str,
) -> None:
    if abp_kind == "trazo":
        abp_shape.draw_line(abp__pt(abp_x1, abp_y1), abp__pt(abp_x2, abp_y2))
        return
    abp_length = math.hypot(abp_x2 - abp_x1, abp_y2 - abp_y1)
    abp_nx, abp_ny = (
        -(abp_y2 - abp_y1) / abp_length * abp_WALL / 2,
        (abp_x2 - abp_x1) / abp_length * abp_WALL / 2,
    )
    if abp_kind == "relleno":
        abp_corners = [
            (abp_x1 + abp_nx, abp_y1 + abp_ny),
            (abp_x2 + abp_nx, abp_y2 + abp_ny),
            (abp_x2 - abp_nx, abp_y2 - abp_ny),
            (abp_x1 - abp_nx, abp_y1 - abp_ny),
        ]
        abp_shape.draw_polyline([abp__pt(*abp_q) for abp_q in [*abp_corners, abp_corners[0]]])
        return
    for abp_s in (1, -1):
        abp_shape.draw_line(
            abp__pt(abp_x1 + abp_s * abp_nx, abp_y1 + abp_s * abp_ny),
            abp__pt(abp_x2 + abp_s * abp_nx, abp_y2 + abp_s * abp_ny),
        )
    for abp_x, abp_y in ((abp_x1, abp_y1), (abp_x2, abp_y2)):
        abp_shape.draw_line(
            abp__pt(abp_x + abp_nx, abp_y + abp_ny), abp__pt(abp_x - abp_nx, abp_y - abp_ny)
        )


def abp__leaf(
    abp_shape: pymupdf.Shape,
    abp_hinge: tuple[float, float],
    abp_closed: float,
    abp_opened: float,
    abp_r: float,
    *,
    abp_polyline: bool = False,
) -> None:
    abp_a0, abp_a1 = math.radians(abp_closed), math.radians(abp_opened)
    abp_k = 4 / 3 * math.tan((abp_a1 - abp_a0) / 4) * abp_r
    abp_p0 = (abp_hinge[0] + abp_r * math.cos(abp_a0), abp_hinge[1] + abp_r * math.sin(abp_a0))
    abp_p3 = (abp_hinge[0] + abp_r * math.cos(abp_a1), abp_hinge[1] + abp_r * math.sin(abp_a1))
    abp_p1 = (abp_p0[0] - abp_k * math.sin(abp_a0), abp_p0[1] + abp_k * math.cos(abp_a0))
    abp_p2 = (abp_p3[0] + abp_k * math.sin(abp_a1), abp_p3[1] - abp_k * math.cos(abp_a1))
    if abp_polyline:
        abp_steps = [abp_a0 + (abp_a1 - abp_a0) * abp_i / 12 for abp_i in range(13)]
        abp_shape.draw_polyline(
            [
                abp__pt(
                    abp_hinge[0] + abp_r * math.cos(abp_a), abp_hinge[1] + abp_r * math.sin(abp_a)
                )
                for abp_a in abp_steps
            ]
        )
    else:
        abp_shape.draw_bezier(
            abp__pt(*abp_p0), abp__pt(*abp_p1), abp__pt(*abp_p2), abp__pt(*abp_p3)
        )
    abp_shape.draw_line(abp__pt(*abp_hinge), abp__pt(*abp_p3))


def abp_write_vector_plan(
    abp_path: Path,
    *,
    abp_pages: int = 1,
    abp_scale_text: bool = True,
    abp_style: abpStyle | None = None,
) -> Path:
    global abp__angle
    abp_style = abp_style or abpStyle()
    abp__angle = abp_style.abp_angle_deg
    abp_doc = pymupdf.open()
    abp_levels = ("PRIMER NIVEL", "SEGUNDO NIVEL", "TERCER NIVEL")
    for abp_number in range(abp_pages):
        abp_page = abp_doc.new_page(width=1190.55, height=841.89)
        abp_walls = abp_doc.add_ocg("MUROS") if abp_number == 0 else abp__ocg(abp_doc, "MUROS")
        abp_furniture = (
            abp_doc.add_ocg("MOBILIARIO") if abp_number == 0 else abp__ocg(abp_doc, "MOBILIARIO")
        )
        abp_shape = abp_page.new_shape()
        abp_x_mid = abp_WIDTH / 2
        abp__wall(abp_shape, 0, 0, abp_WIDTH, 0, abp_style.abp_walls)
        abp__wall(abp_shape, 0, 0, 0, abp_EXIT_DOOR[0], abp_style.abp_walls)
        abp__wall(abp_shape, 0, abp_EXIT_DOOR[1], 0, abp_HEIGHT, abp_style.abp_walls)
        abp__wall(abp_shape, 0, abp_HEIGHT, abp_WIDTH, abp_HEIGHT, abp_style.abp_walls)
        abp__wall(abp_shape, abp_WIDTH, 0, abp_WIDTH, abp_HEIGHT, abp_style.abp_walls)
        abp__wall(abp_shape, abp_x_mid, 0, abp_x_mid, abp_CORRIDOR_Y, abp_style.abp_walls)
        abp__wall(abp_shape, 0, abp_CORRIDOR_Y, abp_DOOR_A[0], abp_CORRIDOR_Y, abp_style.abp_walls)
        abp__wall(
            abp_shape,
            abp_DOOR_A[1],
            abp_CORRIDOR_Y,
            abp_DOOR_B[0],
            abp_CORRIDOR_Y,
            abp_style.abp_walls,
        )
        abp__wall(
            abp_shape, abp_DOOR_B[1], abp_CORRIDOR_Y, abp_WIDTH, abp_CORRIDOR_Y, abp_style.abp_walls
        )
        abp__finish_walls(abp_shape, abp_style.abp_walls, abp_walls)
        abp_thin = abp_page.new_shape()
        abp_poly = abp_style.abp_polyline_arcs
        for abp_x, abp_y, abp_closed, abp_opened, abp_r in (
            (abp_DOOR_A[0], abp_CORRIDOR_Y, 0, -90, abp_DOOR_A[1] - abp_DOOR_A[0]),
            (abp_DOOR_B[0], abp_CORRIDOR_Y, 0, -90, abp_DOOR_B[1] - abp_DOOR_B[0]),
            (0, abp_EXIT_DOOR[0], 90, 0, abp_EXIT_DOOR[1] - abp_EXIT_DOOR[0]),
        ):
            abp__leaf(
                abp_thin, (abp_x, abp_y), abp_closed, abp_opened, abp_r, abp_polyline=abp_poly
            )
        if abp_style.abp_stairs:
            for abp_i in range(9):
                abp_x = 7.4 + 0.28 * abp_i
                abp_thin.draw_line(abp__pt(abp_x, 5.4), abp__pt(abp_x, 6.8))
            abp_thin.draw_line(abp__pt(7.4, 6.1), abp__pt(7.4 + 0.28 * 8, 6.1))
        if abp_style.abp_dimensions:
            for abp_x1, abp_x2, abp_y in ((0, 5, -0.5), (5, 10, -0.5)):
                abp_thin.draw_line(abp__pt(abp_x1, abp_y), abp__pt(abp_x2, abp_y))
                for abp_x in (abp_x1, abp_x2):
                    abp_thin.draw_line(abp__pt(abp_x, abp_y - 0.1), abp__pt(abp_x, abp_y + 0.1))
            abp_thin.draw_line(abp__pt(10.5, 0), abp__pt(10.5, 7))
        abp_thin.finish(color=(0.5, 0.5, 0.5), width=0.3, oc=abp_walls)
        abp_thin.commit()
        if abp_style.abp_dimensions:
            abp_page.insert_text(abp__pt(2.4, -0.55), "5.00", fontname="helv", fontsize=6)
            abp_page.insert_text(abp__pt(7.4, -0.55), "5.00", fontname="helv", fontsize=6)
            abp_page.insert_text(abp__pt(10.6, 3.5), "7.00", fontname="helv", fontsize=6)
        abp_desks = abp_page.new_shape()
        for abp_x in (1.0, 2.6):
            for abp_y in (1.0, 2.6):
                abp_desks.draw_rect(
                    pymupdf.Rect(abp__pt(abp_x, abp_y), abp__pt(abp_x + 0.8, abp_y + 0.5))
                )
                abp_desks.draw_line(
                    abp__pt(abp_x, abp_y + 0.25), abp__pt(abp_x + 0.8, abp_y + 0.25)
                )
        abp_desks.finish(color=(0.5, 0.5, 0.5), width=0.2, oc=abp_furniture)
        abp_desks.commit()
        if abp_style.abp_signs:
            abp__draw_signs(abp_page)
        if abp_style.abp_numbered_stairs:
            abp__draw_numbered_stairs(abp_page)
        if abp_style.abp_tags:
            abp__draw_tags(abp_page)
        if abp_style.abp_stairs:
            abp_page.insert_text(abp__pt(7.9, 6.0), "SUBE", fontname="helv", fontsize=5)
        if not abp_style.abp_labels:
            abp__sheet(abp_page, abp_levels[abp_number % 3], abp_scale_text)
            continue
        abp__labels(abp_page, 1.6, 1.8, "AULA 101", "24.00", "16")
        abp__labels(abp_page, 7.4, 2.4, "TALLER DE ARTE", "24.00", "8")
        abp__labels(abp_page, 6.0, 5.8, "PASILLO", "", "")
        abp_arrow = abp_page.new_shape()
        abp_arrow.draw_polyline(
            [abp__pt(7, 5.9), abp__pt(2, 5.9), abp__pt(2, 6.1), abp__pt(7, 6.1)]
        )
        abp_arrow.finish(fill=(0, 1, 0), color=(0, 0.5, 0), closePath=True)
        abp_arrow.commit()
        abp__sheet(abp_page, abp_levels[abp_number % 3], abp_scale_text)
    abp_doc.save(abp_path)
    abp_doc.close()
    return abp_path


abp_SIGN_PLACES = (
    ("extintor", 9.2, 3.0, 0),
    ("extintor", 0.6, 3.4, 90),
    ("direccion", 4.2, 4.4, 0),
    ("direccion", 5.8, 6.3, 90),
    ("prohibicion", 8.6, 1.2, 0),
)
abp_LEGEND = (
    ("extintor", "UBICACIÓN DE EXTINTOR"),
    ("direccion", "SEÑAL DIRECCIONAL DE SALIDA"),
    ("prohibicion", "PROHIBIDO CORRER"),
)


def abp__symbol(
    abp_page: pymupdf.Page, abp_kind: str, abp_cx: float, abp_cy: float, abp_turn: float
) -> None:
    abp_c, abp_s = math.cos(math.radians(abp_turn)), math.sin(math.radians(abp_turn))

    def abp_at(abp_x: float, abp_y: float) -> pymupdf.Point:
        return pymupdf.Point(
            abp_cx + abp_x * abp_c - abp_y * abp_s, abp_cy + abp_x * abp_s + abp_y * abp_c
        )

    def abp_poly(
        abp_points: list[tuple[float, float]], abp_fill: tuple[float, float, float]
    ) -> None:
        abp_shape = abp_page.new_shape()
        abp_shape.draw_polyline([abp_at(*abp_p) for abp_p in abp_points])
        abp_shape.finish(fill=abp_fill, color=abp_fill, width=0.2, closePath=True)
        abp_shape.commit()

    def abp_box(
        abp_x0: float,
        abp_y0: float,
        abp_x1: float,
        abp_y1: float,
        abp_fill: tuple[float, float, float],
    ) -> None:
        abp_poly([(abp_x0, abp_y0), (abp_x1, abp_y0), (abp_x1, abp_y1), (abp_x0, abp_y1)], abp_fill)

    def abp_word(abp_text: str, abp_y: float, abp_size: float) -> None:
        abp_width = pymupdf.get_text_length(abp_text, "hebo", abp_size)
        abp_page.insert_text(
            abp_at(-abp_width / 2, abp_y),
            abp_text,
            fontname="hebo",
            fontsize=abp_size,
            color=(1, 1, 1),
            rotate=int(-abp_turn),
        )

    if abp_kind == "extintor":
        abp_box(-10, -13, 10, 13, (0.85, 0.05, 0.05))
        abp_box(-3, -7, 4, 5, (1, 1, 1))
        abp_box(-1, -10, 1, -7, (1, 1, 1))
        abp_poly([(-2, -9), (-8, -5), (-8, 1), (-6, 1), (-6, -4), (-2, -7)], (1, 1, 1))
        abp_word("EXTINTOR", 11, 3.6)
    elif abp_kind == "direccion":
        abp_box(-10, -13, 10, 13, (0.97, 0.98, 0.7))
        abp_green = (0.1, 0.6, 0.15)
        abp_poly([(-8, -3), (0, -10), (0, -6), (8, -6), (8, 0), (0, 0), (0, 4)], abp_green)
        abp_box(-9, 6, 9, 12, abp_green)
        abp_word("SALIDA", 10.6, 4)
    else:
        abp_shape = abp_page.new_shape()
        abp_shape.draw_circle(abp_at(0, 0), 11)
        abp_shape.finish(fill=(0.9, 0.05, 0.05), color=(0.9, 0.05, 0.05))
        abp_shape.draw_circle(abp_at(0, 0), 8)
        abp_shape.finish(fill=(1, 1, 1), color=(1, 1, 1))
        abp_shape.draw_line(abp_at(-7, -7), abp_at(7, 7))
        abp_shape.finish(color=(0.9, 0.05, 0.05), width=3)
        abp_shape.commit()
        abp_box(-4, -5, 1, 5, (0, 0, 0))


def abp__draw_signs(abp_page: pymupdf.Page) -> None:
    for abp_kind, abp_x, abp_y, abp_turn in abp_SIGN_PLACES:
        abp_p = abp__pt(abp_x, abp_y)
        abp__symbol(abp_page, abp_kind, abp_p.x, abp_p.y, abp_turn)
    abp_x0, abp_y0, abp_w, abp_row = 760.0, 60.0, 250.0, 40.0
    abp_shape = abp_page.new_shape()
    abp_rows = [abp_y0, abp_y0 + 30] + [
        abp_y0 + 30 + abp_row * (abp_i + 1) for abp_i in range(len(abp_LEGEND))
    ]
    for abp_y in abp_rows:
        abp_shape.draw_line((abp_x0, abp_y), (abp_x0 + abp_w, abp_y))
    for abp_x in (abp_x0, abp_x0 + 60, abp_x0 + abp_w):
        abp_shape.draw_line(
            (abp_x, abp_rows[1] if abp_x == abp_x0 + 60 else abp_rows[0]), (abp_x, abp_rows[-1])
        )
    abp_shape.finish(color=(0, 0, 0), width=0.6)
    abp_shape.commit()
    abp_page.insert_text((abp_x0 + 80, abp_y0 + 20), "LEYENDA", fontname="helv", fontsize=14)
    for abp_i, (abp_kind, abp_text) in enumerate(abp_LEGEND):
        abp__symbol(abp_page, abp_kind, abp_x0 + 30, abp_rows[1] + abp_row * (abp_i + 0.5), 0)
        abp_page.insert_text(
            (abp_x0 + 70, abp_rows[1] + abp_row * (abp_i + 0.6)),
            abp_text,
            fontname="helv",
            fontsize=7,
        )
    abp_center = pymupdf.Point(
        abp_ORIGIN[0] + 12 * abp_PT_PER_M, abp_ORIGIN[1] + 8.5 * abp_PT_PER_M
    )
    abp_shape = abp_page.new_shape()
    abp_shape.draw_circle(abp_center, 45)
    abp_shape.finish(fill=(0.96, 0.85, 0.15), color=(0.8, 0.7, 0.1))
    abp_shape.commit()
    abp_page.insert_text(
        (abp_center.x - 28, abp_center.y), "ZONA DE REUNION", fontname="helv", fontsize=7
    )


def abp__draw_numbered_stairs(abp_page: pymupdf.Page) -> None:
    abp_shape = abp_page.new_shape()
    for abp_i in range(8):
        abp_y = 1.5 + 0.28 * abp_i
        abp_shape.draw_line(abp__pt(7.4, abp_y), abp__pt(8.6, abp_y))
        abp_shape.draw_line(abp__pt(8.72, abp_y), abp__pt(9.92, abp_y))
    abp_shape.draw_line(abp__pt(8.66, 1.3), abp__pt(8.66, 3.6))
    abp_shape.finish(color=(0.5, 0.5, 0.5), width=0.3)
    abp_shape.commit()
    for abp_i in range(8):
        abp_y = 1.5 + 0.28 * abp_i
        abp_page.insert_text(
            abp__pt(7.95, abp_y + 0.02), str(8 - abp_i), fontname="helv", fontsize=5
        )
        abp_page.insert_text(
            abp__pt(9.25, abp_y + 0.02), str(9 + abp_i), fontname="helv", fontsize=5
        )


def abp__draw_tags(abp_page: pymupdf.Page) -> None:
    for abp_x, abp_y, abp_cells in (
        (2.1, 5.35, ("P - 01", "0.90", "2.10")),
        (7.1, 5.35, ("P - 02", "0.90", "2.10")),
        (2.0, -0.4, ("VEN. 01", "1.10", "2.00", "1.50")),
    ):
        abp_page.insert_text(abp__pt(abp_x, abp_y), abp_cells[0], fontname="helv", fontsize=4)
        for abp_k, abp_text in enumerate(abp_cells[1:]):
            abp_dx = (0.45, 0.0, 0.45)[abp_k] if len(abp_cells) > 3 else (0.0, 0.45)[abp_k]
            abp_dy = (0.0, 0.14, 0.14)[abp_k] if len(abp_cells) > 3 else 0.14
            abp_page.insert_text(
                abp__pt(abp_x + abp_dx, abp_y + abp_dy), abp_text, fontname="helv", fontsize=4
            )


def abp__finish_walls(abp_shape: pymupdf.Shape, abp_kind: str, abp_layer: int) -> None:
    if abp_kind == "relleno":
        abp_shape.finish(color=None, fill=(0.25, 0.25, 0.25), oc=abp_layer)
    elif abp_kind == "trazo":
        abp_shape.finish(color=(0, 0, 0), width=abp_WALL * abp_PT_PER_M, oc=abp_layer, lineCap=2)
    else:
        abp_shape.finish(color=(0.5, 0.5, 0.5), width=0.3, oc=abp_layer)
    abp_shape.commit()


def abp_write_scanned_plan(
    abp_path: Path, *, abp_dpi: int = 150, abp_style: abpStyle | None = None
) -> Path:
    abp_source = abp_write_vector_plan(abp_path.with_suffix(".src.pdf"), abp_style=abp_style)
    abp_doc, abp_out = pymupdf.open(abp_source), pymupdf.open()
    abp_page = abp_out.new_page(width=abp_doc[0].rect.width, height=abp_doc[0].rect.height)
    abp_page.insert_image(abp_page.rect, pixmap=abp_doc[0].get_pixmap(dpi=abp_dpi))
    abp_out.save(abp_path)
    abp_doc.close()
    abp_out.close()
    return abp_path


def abp__ocg(abp_doc: pymupdf.Document, abp_name: str) -> int:
    return int(
        next(
            abp_x for abp_x, abp_info in abp_doc.get_ocgs().items() if abp_info["name"] == abp_name
        )
    )


def abp__labels(
    abp_page: pymupdf.Page,
    abp_x: float,
    abp_y: float,
    abp_name: str,
    abp_area: str,
    abp_capacity: str,
) -> None:
    abp_page.insert_text(abp__pt(abp_x, abp_y), abp_name, fontname="hebo", fontsize=8)
    abp_page.insert_text(abp__pt(abp_x, abp_y + 0.18), "NPT. +0.00", fontname="helv", fontsize=6)
    if abp_area:
        abp_text = f"AREA= {abp_area}  AFORO= {abp_capacity}"
        abp_page.insert_text(abp__pt(abp_x, abp_y + 0.36), abp_text, fontname="helv", fontsize=4)


def abp__sheet(abp_page: pymupdf.Page, abp_level: str, abp_scale_text: bool) -> None:
    abp_w, abp_h = abp_page.rect.width, abp_page.rect.height
    abp_shape = abp_page.new_shape()
    abp_shape.draw_rect(pymupdf.Rect(20, 20, abp_w - 20, abp_h - 20))
    abp_shape.draw_rect(pymupdf.Rect(abp_w - 150, 24, abp_w - 24, abp_h - 24))
    for abp_i in range(12):
        abp_shape.draw_line((abp_w - 150, 60 + 55 * abp_i), (abp_w - 24, 60 + 55 * abp_i))
        abp_shape.draw_line((abp_w - 150, 72 + 55 * abp_i), (abp_w - 24, 72 + 55 * abp_i))
    abp_shape.finish(color=(0, 0, 0), width=0.6)
    abp_shape.commit()
    abp_page.insert_text(
        (200, abp_h - 80), "MAPA DE EVACUACIÓN Y SEÑALIZACIÓN", fontname="hebi", fontsize=14
    )
    abp_page.insert_text((260, abp_h - 60), abp_level, fontname="hebi", fontsize=9)
    if abp_scale_text:
        abp_page.insert_text(
            (560, abp_h - 80), f"ESC. 1/{abp_DENOMINATOR}", fontname="helv", fontsize=7
        )
