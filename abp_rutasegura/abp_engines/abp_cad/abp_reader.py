from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pymupdf
from ezdxf import filemanagement, recover
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
from ezdxf.addons.drawing.frontend import UniversalFrontend
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.lldxf.const import DXFError

from abp_rutasegura.abp_engines.abp_cad.abp_pdf_backend import (
    abp_block_rows,
    abp_save_document,
    abp_write_page,
    abpPageRecorder,
    abpTextPipeline,
)

abp_CAD_SUFFIXES = (".dwg", ".dxf")
abp_TOOL = Path(__file__).parent / "abp_bin" / "abp_lector_cad.exe"
abp_TOOL_TIMEOUT_S = 900
abp_UNITS = {1.0: 6, 0.01: 5, 0.001: 4, 0.0254: 1, 0.3048: 2}
abp_DOOR_RADIUS_M = (0.55, 1.15)
abp_MODEL_PAPER_MM = 800.0
abp_MODEL_NAME = "Model"
abp_SKIPPED = ("OLE2FRAME", "IMAGE", "PDFUNDERLAY", "DWFUNDERLAY", "DGNUNDERLAY")
abp_MARGIN_MM = 2.0

abpProgress = Callable[[str], None]


class abpCadFileError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class abpCadSheet:
    abp_name: str
    abp_scale: float | None = None
    abp_blocks: tuple[Any, ...] = ()


def abp_list_sheets(abp_path: Path) -> tuple[str, ...]:
    if abp_path.suffix.lower() == ".dwg":
        abp_lines = abp__run_tool("--lista", str(abp_path))
        abp_names = [
            abp_line.split("\t", 1)[1] for abp_line in abp_lines if abp_line.startswith("lamina\t")
        ]
        return tuple(abp_names) or (abp_MODEL_NAME,)
    return abp__layout_names(abp__open_dxf(abp_path))


def abp_convert(
    abp_path: Path,
    abp_target: Path,
    abp_sheets: Sequence[str] = (),
    abp_progress: abpProgress | None = None,
) -> tuple[abpCadSheet, ...]:
    abp_say = abp_progress or (lambda abp__text: None)
    abp_pdf: Any = cast(Any, pymupdf).open()
    abp_done: list[abpCadSheet] = []
    if abp_path.suffix.lower() == ".dwg":
        with tempfile.TemporaryDirectory(prefix="rutasegura_cad_") as abp_folder:
            abp_say("Abriendo el DWG…")
            for abp_line in abp__run_tool(str(abp_path), abp_folder, *abp_sheets):
                if not abp_line.startswith("lamina\t"):
                    continue
                abp__mark, abp_file, abp_name = abp_line.split("\t")[:3]
                abp_say(f"Dibujando «{abp_name}»…")
                abp_done.append(
                    abp__draw(abp__open_dxf(Path(abp_folder) / abp_file), abp_name, abp_pdf)
                )
    else:
        abp_doc = abp__open_dxf(abp_path)
        for abp_name in abp_sheets or abp__layout_names(abp_doc):
            abp_say(f"Dibujando «{abp_name}»…")
            abp_done.append(abp__draw(abp_doc, abp_name, abp_pdf))
    if not abp_done:
        raise abpCadFileError("El dibujo no tiene ninguna lámina con contenido.")
    abp_pdf.set_toc([[1, abp_s.abp_name, abp_k + 1] for abp_k, abp_s in enumerate(abp_done)])
    abp_save_document(
        abp_pdf,
        abp_target,
        [abp_s.abp_scale for abp_s in abp_done],
        [abp_s.abp_blocks for abp_s in abp_done],
    )
    abp_pdf.close()
    return tuple(abp_done)


def abp__run_tool(*abp_args: str) -> list[str]:
    if sys.platform != "win32" or not abp_TOOL.exists():
        raise abpCadFileError(
            "Los archivos DWG solo se pueden abrir en Windows. En AutoCAD use «Guardar como» y "
            "elija DXF o PDF."
        )
    try:
        abp_result = subprocess.run(
            [str(abp_TOOL), *abp_args],
            capture_output=True,
            timeout=abp_TOOL_TIMEOUT_S,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as abp_exc:
        raise abpCadFileError(f"No se pudo leer el DWG: {abp_exc}") from abp_exc
    if abp_result.returncode != 0:
        raise abpCadFileError(
            "No se pudo leer el DWG: puede estar dañado o ser de una versión muy antigua. En "
            "AutoCAD use «Guardar como» y elija DXF."
        )
    return abp_result.stdout.decode("utf-8", "replace").splitlines()


def abp_save_as_dwg(abp_source: Path, abp_target: Path) -> bool:
    if sys.platform != "win32" or not abp_TOOL.exists():
        return False
    abp__run_tool("--dwg", str(abp_source), str(abp_target))
    return abp_target.exists()


def abp_write_sample_dxf(abp_path: Path) -> None:
    abp_doc: Any = filemanagement.new("R2018", setup=True)
    abp_doc.layers.add("MUROS")
    abp_msp = abp_doc.modelspace()
    for abp_inset in (0.0, 0.15):
        abp_a, abp_b, abp_c, abp_d = abp_inset, 6 - abp_inset, abp_inset, 4 - abp_inset
        abp_corners = [(abp_a, abp_c), (abp_b, abp_c), (abp_b, abp_d), (abp_a, abp_d)]
        abp_msp.add_lwpolyline(abp_corners, close=True, dxfattribs={"layer": "MUROS"})
    for abp_k in range(6):
        for abp_m in range(4):
            abp_msp.add_line((abp_k + 0.2, abp_m + 0.2), (abp_k + 0.7, abp_m + 0.2))
    abp_msp.add_arc((2, 0.15), 0.9, 0, 90)
    abp_doc.saveas(abp_path)


def abp__open_dxf(abp_path: Path) -> Any:
    try:
        return filemanagement.readfile(abp_path)
    except OSError as abp_exc:
        raise abpCadFileError(f"No se pudo abrir el plano: {abp_exc}") from abp_exc
    except (DXFError, ValueError, KeyError):
        pass
    try:
        abp_doc, abp__auditor = recover.readfile(abp_path)
    except (OSError, DXFError, ValueError, KeyError) as abp_exc:
        raise abpCadFileError("El archivo no es un DXF válido o está dañado.") from abp_exc
    return abp_doc


def abp__viewports(abp_layout: Any) -> list[Any]:
    return [
        abp_v
        for abp_v in abp_layout.query("VIEWPORT")
        if abp_v.dxf.get("id", 2) != 1 and abp_v.dxf.view_height > 0 and abp_v.dxf.height > 0
    ]


def abp__layout_names(abp_doc: Any) -> tuple[str, ...]:
    abp_names = [
        abp_layout.name
        for abp_layout in abp_doc.layouts
        if abp_layout.name != abp_MODEL_NAME and abp__viewports(abp_layout)
    ]
    return tuple(abp_names) or (abp_MODEL_NAME,)


def abp_unit_meters(abp_doc: Any) -> float:
    abp_radii: list[float] = []
    abp_blocks = [
        abp_doc.modelspace(),
        *(abp_b for abp_b in abp_doc.blocks if not abp_b.is_any_layout),
    ]
    for abp_block in abp_blocks:
        for abp_arc in abp_block.query("ARC"):
            abp_sweep = (abp_arc.dxf.end_angle - abp_arc.dxf.start_angle) % 360
            if 70 <= abp_sweep <= 110:
                abp_radii.append(float(abp_arc.dxf.radius))
    abp_written = abp_doc.header.get("$INSUNITS", 0)
    abp_best = max(
        abp_UNITS,
        key=lambda abp_u: (
            sum(
                abp_DOOR_RADIUS_M[0] <= abp_r * abp_u <= abp_DOOR_RADIUS_M[1] for abp_r in abp_radii
            ),
            abp_UNITS[abp_u] == abp_written,
        ),
    )
    return abp_best


def abp__draw(abp_doc: Any, abp_name: str, abp_pdf: Any) -> abpCadSheet:
    abp_layout = abp_doc.layouts.get(abp_name)
    abp_recorder = abpPageRecorder()
    abp_context = RenderContext(abp_doc)
    abp_context.set_current_layout(abp_layout)
    abp_frontend = abp__BlockFrontend(
        abp_context,
        abpTextPipeline(abp_recorder),
        config=Configuration(background_policy=BackgroundPolicy.WHITE),
    )
    abp_frontend.abp_recorder = abp_recorder
    abp_frontend.draw_layout(
        abp_layout, filter_func=lambda abp_e: abp_e.dxftype() not in abp_SKIPPED
    )
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_recorder.abp_bounds()
    abp_meters = abp_unit_meters(abp_doc)
    if abp_name == abp_MODEL_NAME:
        abp_per_unit = abp_MODEL_PAPER_MM / max(abp_x1 - abp_x0, abp_y1 - abp_y0, 1e-9)
        abp_recorder.abp_scale(abp_per_unit)
        abp_x0, abp_y0, abp_x1, abp_y1 = (
            abp_x0 * abp_per_unit,
            abp_y0 * abp_per_unit,
            abp_x1 * abp_per_unit,
            abp_y1 * abp_per_unit,
        )
    else:
        abp_views = abp__viewports(abp_layout)
        abp_main = max(abp_views, key=lambda abp_v: abp_v.dxf.width * abp_v.dxf.height)
        abp_per_unit = float(abp_main.dxf.height / abp_main.dxf.view_height)
    abp_m = abp_MARGIN_MM
    abp_bounds = (abp_x0 - abp_m, abp_y0 - abp_m, abp_x1 + abp_m, abp_y1 + abp_m)
    abp_write_page(abp_pdf, abp_recorder, abp_bounds)
    abp_scale = 1000.0 * abp_meters / abp_per_unit
    abp_good = math.isfinite(abp_scale) and abp_scale > 0
    return abpCadSheet(
        abp_name, abp_scale if abp_good else None, tuple(abp_block_rows(abp_recorder, abp_bounds))
    )


class abp__BlockFrontend(UniversalFrontend):
    abp_recorder: abpPageRecorder

    def draw_composite_entity(self, abp_entity: Any, abp_properties: Any) -> None:
        abp_first = len(self.abp_recorder.abp_items)
        super().draw_composite_entity(abp_entity, abp_properties)
        if abp_entity.dxftype() == "INSERT" and len(self.abp_recorder.abp_items) > abp_first:
            abp_angle = float(abp_entity.dxf.get("rotation", 0.0))
            if abp_entity.dxf.extrusion.z < 0:
                abp_angle = 180.0 - abp_angle
            self.abp_recorder.abp_note_block(str(abp_entity.dxf.name), abp_angle, abp_first)
