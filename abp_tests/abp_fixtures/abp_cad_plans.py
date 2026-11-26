from __future__ import annotations

from pathlib import Path
from typing import Any

from ezdxf import filemanagement
from ezdxf.enums import TextEntityAlignment

abp_WALLS = (
    (0, 0, 12, 0),
    (0, 8, 12, 8),
    (0, 0, 0, 8),
    (12, 0, 12, 5),
    (12, 6.4, 12, 8),
    (6, 0, 6, 5),
    (0, 5, 2, 5),
    (2.9, 5, 8, 5),
    (8.9, 5, 12, 5),
)
abp_DOORS = ((2.0, 5.0, 0.9), (8.0, 5.0, 0.9))
abp_SIGNS = (("EXTINTOR", 0.5, 4.6), ("EXTINTOR", 11.5, 7.6), ("LUZ DE EMERGENCIA", 6.0, 7.6))
abp_HALF = 0.075


def abp_write_dxf(
    abp_path: Path,
    *,
    abp_units: float = 1.0,
    abp_insunits: int = 4,
    abp_layouts: int = 1,
    abp_scale: float = 50.0,
) -> Path:
    abp_doc = filemanagement.new("R2018", setup=True)
    abp_doc.header["$INSUNITS"] = abp_insunits
    for abp_name in ("MUROS", "PUERTAS", "VENTANAS", "COLUMNAS", "TEXTOS", "SEÑALES", "LEYENDA"):
        abp_doc.layers.add(abp_name)
    abp__block(abp_doc, "EXTINTOR", 1, abp_units)
    abp__block(abp_doc, "LUZ DE EMERGENCIA", 30, abp_units)
    abp_msp = abp_doc.modelspace()
    abp__building(abp_msp, abp_units)
    abp__labels(abp_msp, abp_units)
    for abp_name, abp_x, abp_y in abp_SIGNS:
        abp_msp.add_blockref(
            abp_name, (abp_x * abp_units, abp_y * abp_units), dxfattribs={"layer": "SEÑALES"}
        )
    abp__legend(abp_msp, abp_units)
    for abp_k in range(abp_layouts):
        abp_layout = abp_doc.layouts.new(f"L-{abp_k + 1:02d}")
        abp_layout.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units="mm")
        for abp_viewport in list(abp_layout.query("VIEWPORT")):
            if abp_viewport.dxf.id != 1:
                abp_layout.delete_entity(abp_viewport)
        abp_height = 290.0
        abp_layout.add_viewport(
            center=(210, 148),
            size=(410, abp_height),
            view_center_point=(9 * abp_units, 4 * abp_units),
            view_height=abp_height / 1000 * abp_scale * abp_units,
        )
        abp_layout.add_text("MAPA DE EVACUACION - COLEGIO", height=6).set_placement((20, 10))
        abp_layout.add_text("ESC. 1/100", height=4).set_placement((200, 10))
    abp_doc.saveas(abp_path)
    return abp_path


def abp__block(abp_doc: Any, abp_name: str, abp_color: int, abp_u: float) -> None:
    abp_block = abp_doc.blocks.new(abp_name)
    abp_hatch = abp_block.add_hatch(color=abp_color)
    abp_points = [
        (-0.15 * abp_u, -0.2 * abp_u),
        (0.15 * abp_u, -0.2 * abp_u),
        (0.15 * abp_u, 0.2 * abp_u),
        (-0.15 * abp_u, 0.2 * abp_u),
    ]
    abp_hatch.paths.add_polyline_path(abp_points, is_closed=True)
    abp_block.add_lwpolyline(abp_points, close=True)


def abp__building(abp_msp: Any, abp_u: float) -> None:
    def abp_line(
        abp_x0: float, abp_y0: float, abp_x1: float, abp_y1: float, abp_layer: str
    ) -> None:
        abp_msp.add_line(
            (abp_x0 * abp_u, abp_y0 * abp_u),
            (abp_x1 * abp_u, abp_y1 * abp_u),
            dxfattribs={"layer": abp_layer},
        )

    for abp_x0, abp_y0, abp_x1, abp_y1 in abp_WALLS:
        if abp_y0 == abp_y1:
            abp_line(abp_x0, abp_y0 - abp_HALF, abp_x1, abp_y1 - abp_HALF, "MUROS")
            abp_line(abp_x0, abp_y0 + abp_HALF, abp_x1, abp_y1 + abp_HALF, "MUROS")
        else:
            abp_line(abp_x0 - abp_HALF, abp_y0, abp_x1 - abp_HALF, abp_y1, "MUROS")
            abp_line(abp_x0 + abp_HALF, abp_y0, abp_x1 + abp_HALF, abp_y1, "MUROS")
    for abp_x, abp_y, abp_w in abp_DOORS:
        abp_msp.add_arc(
            (abp_x * abp_u, abp_y * abp_u), abp_w * abp_u, 270, 360, dxfattribs={"layer": "PUERTAS"}
        )
        abp_line(abp_x, abp_y, abp_x, abp_y - abp_w, "PUERTAS")
    abp_msp.add_arc((12 * abp_u, 5 * abp_u), 1.4 * abp_u, 90, 180, dxfattribs={"layer": "PUERTAS"})
    abp_line(12, 5, 10.6, 5, "PUERTAS")
    for abp_x in (2.0, 8.0):
        for abp_dy in (-0.03, 0.03):
            abp_line(abp_x, abp_dy, abp_x + 2, abp_dy, "VENTANAS")


def abp__labels(abp_msp: Any, abp_u: float) -> None:
    def abp_text(abp_value: str, abp_x: float, abp_y: float, abp_h: float) -> None:
        abp_entity = abp_msp.add_text(
            abp_value, height=abp_h * abp_u, dxfattribs={"layer": "TEXTOS"}
        )
        abp_entity.set_placement(
            (abp_x * abp_u, abp_y * abp_u), align=TextEntityAlignment.MIDDLE_CENTER
        )

    for abp_name, abp_x, abp_y, abp_area in (
        ("AULA 1", 3.0, 2.8, "28.67"),
        ("AULA 2", 9.0, 2.8, "28.67"),
        ("PASILLO", 6.0, 6.8, ""),
    ):
        abp_text(abp_name, abp_x, abp_y, 0.25)
        abp_text("NPT. +0.15", abp_x, abp_y - 0.4, 0.18)
        if abp_area:
            abp_text(f"AREA= {abp_area}   AFORO= 19", abp_x, abp_y - 0.75, 0.15)


def abp__legend(abp_msp: Any, abp_u: float) -> None:
    abp_x0, abp_x1, abp_split, abp_top = 14.0, 18.0, 15.0, 7.0
    abp_rows = [abp_top, abp_top - 0.6, abp_top - 1.4, abp_top - 2.2]
    for abp_y in abp_rows:
        abp_msp.add_line(
            (abp_x0 * abp_u, abp_y * abp_u),
            (abp_x1 * abp_u, abp_y * abp_u),
            dxfattribs={"layer": "LEYENDA"},
        )
    for abp_x in (abp_x0, abp_x1):
        abp_msp.add_line(
            (abp_x * abp_u, abp_top * abp_u),
            (abp_x * abp_u, abp_rows[-1] * abp_u),
            dxfattribs={"layer": "LEYENDA"},
        )
    abp_msp.add_line(
        (abp_split * abp_u, abp_rows[1] * abp_u),
        (abp_split * abp_u, abp_rows[-1] * abp_u),
        dxfattribs={"layer": "LEYENDA"},
    )

    def abp_text(abp_value: str, abp_x: float, abp_y: float, abp_h: float) -> None:
        abp_entity = abp_msp.add_text(
            abp_value, height=abp_h * abp_u, dxfattribs={"layer": "LEYENDA"}
        )
        abp_entity.set_placement(
            (abp_x * abp_u, abp_y * abp_u), align=TextEntityAlignment.MIDDLE_CENTER
        )

    abp_text("LEYENDA", 16.0, abp_top - 0.3, 0.2)
    for abp_k, (abp_name, abp_label) in enumerate(
        (("EXTINTOR", "UBICACION DE EXTINTOR"), ("LUZ DE EMERGENCIA", "LUZ DE EMERGENCIA"))
    ):
        abp_y = abp_rows[1] - 0.8 * abp_k - 0.4
        abp_msp.add_blockref(
            abp_name, (14.5 * abp_u, abp_y * abp_u), dxfattribs={"layer": "LEYENDA"}
        )
        abp_text(abp_label, 16.5, abp_y, 0.1)
