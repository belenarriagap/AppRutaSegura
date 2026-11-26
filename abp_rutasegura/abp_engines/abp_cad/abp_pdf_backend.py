from __future__ import annotations

import itertools
import json
import math
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pymupdf
from ezdxf.addons.drawing.backend import Backend, BkPath2d, BkPoints2d, ImageData
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing.pipeline import RenderPipeline2d, prepare_string_for_rendering
from ezdxf.addons.drawing.properties import BackendProperties, Properties
from ezdxf.math import Matrix44, Vec2
from ezdxf.path import Command

from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_CAD_BLOCKS, abp_CAD_PRODUCER

abp_MM_TO_PT = 72.0 / 25.4
abp_CAP_HEIGHT = 0.718
abp_MAX_LINEWIDTH_MM = 2.0
abp_MIN_LINEWIDTH_MM = 0.02
abp_FRAME_SHARE = 0.85

abp_XY = tuple[float, float]
abpOrder = tuple[str, tuple[float, ...]]
abpOrders = tuple[abpOrder, ...]


@dataclass(frozen=True, slots=True)
class abp__Item:
    abp_layer: str
    abp_color: str
    abp_width: float = 0.0
    abp_filled: bool = False
    abp_paths: tuple[abpOrders, ...] = ()
    abp_text: str = ""
    abp_frame: tuple[abp_XY, abp_XY, abp_XY] = ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))


@dataclass(frozen=True, slots=True)
class abpBlockPlace:
    abp_name: str
    abp_center: abp_XY
    abp_size: abp_XY
    abp_angle: float

    def abp_scaled(self, abp_k: float) -> abpBlockPlace:
        return abpBlockPlace(
            self.abp_name,
            (self.abp_center[0] * abp_k, self.abp_center[1] * abp_k),
            (self.abp_size[0] * abp_k, self.abp_size[1] * abp_k),
            self.abp_angle,
        )


class abpPageRecorder(Backend):
    def __init__(self) -> None:
        super().__init__()
        self.abp_items: list[abp__Item] = []
        self.abp_blocks: list[abpBlockPlace] = []

    def set_background(self, abp_color: str) -> None:
        pass

    def draw_point(self, abp_pos: Vec2, abp_properties: BackendProperties) -> None:
        pass

    def draw_line(self, abp_start: Vec2, abp_end: Vec2, abp_properties: BackendProperties) -> None:
        self.abp__stroke(
            ((("m", (abp_start.x, abp_start.y)), ("l", (abp_end.x, abp_end.y))),), abp_properties
        )

    def draw_solid_lines(
        self, abp_lines: Iterable[tuple[Vec2, Vec2]], abp_properties: BackendProperties
    ) -> None:
        abp_paths: tuple[abpOrders, ...] = tuple(
            (("m", (abp_a.x, abp_a.y)), ("l", (abp_b.x, abp_b.y))) for abp_a, abp_b in abp_lines
        )
        if abp_paths:
            self.abp__stroke(abp_paths, abp_properties)

    def draw_path(self, abp_path: BkPath2d, abp_properties: BackendProperties) -> None:
        abp_orders = abp__orders(abp_path)
        if len(abp_orders) > 1:
            self.abp__stroke((abp_orders,), abp_properties)

    def draw_filled_paths(
        self, abp_paths: Iterable[BkPath2d], abp_properties: BackendProperties
    ) -> None:
        abp_found = tuple(
            abp_o for abp_o in (abp__orders(abp_p) for abp_p in abp_paths) if len(abp_o) > 2
        )
        if abp_found:
            self.abp_items.append(
                abp__Item(abp_properties.layer, abp_properties.color, 0.0, True, abp_found)
            )

    def draw_filled_polygon(
        self, abp_points: BkPoints2d, abp_properties: BackendProperties
    ) -> None:
        abp_vertices = abp_points.vertices()
        if len(abp_vertices) > 2:
            abp_orders: abpOrders = tuple(
                ("l" if abp_k else "m", (abp_v.x, abp_v.y))
                for abp_k, abp_v in enumerate(abp_vertices)
            )
            self.abp_items.append(
                abp__Item(abp_properties.layer, abp_properties.color, 0.0, True, (abp_orders,))
            )

    def draw_image(self, abp_image_data: ImageData, abp_properties: BackendProperties) -> None:
        pass

    def abp_note_block(self, abp_name: str, abp_angle: float, abp_first: int) -> None:
        abp_c, abp_s = math.cos(math.radians(abp_angle)), math.sin(math.radians(abp_angle))
        abp_points = [
            (abp_x, abp_y)
            for abp_item in self.abp_items[abp_first:]
            for abp_path in abp_item.abp_paths
            for abp__order, abp_v in abp_path
            for abp_x, abp_y in zip(abp_v[0::2], abp_v[1::2], strict=True)
        ]
        if not abp_points:
            return
        abp_us = [abp_x * abp_c + abp_y * abp_s for abp_x, abp_y in abp_points]
        abp_vs = [-abp_x * abp_s + abp_y * abp_c for abp_x, abp_y in abp_points]
        abp_u, abp_v = (min(abp_us) + max(abp_us)) / 2, (min(abp_vs) + max(abp_vs)) / 2
        abp_size = (max(abp_us) - min(abp_us), max(abp_vs) - min(abp_vs))
        self.abp_blocks.append(
            abpBlockPlace(
                abp_name,
                (abp_u * abp_c - abp_v * abp_s, abp_u * abp_s + abp_v * abp_c),
                abp_size,
                abp_angle,
            )
        )

    def clear(self) -> None:
        self.abp_items.clear()

    def configure(self, abp_config: Configuration) -> None:
        pass

    def abp_add_text(
        self,
        abp_text: str,
        abp_frame: tuple[abp_XY, abp_XY, abp_XY],
        abp_properties: BackendProperties,
    ) -> None:
        self.abp_items.append(
            abp__Item(
                abp_properties.layer, abp_properties.color, 0.0, True, (), abp_text, abp_frame
            )
        )

    def abp_bounds(self) -> tuple[float, float, float, float]:
        abp_values = [
            abp_v
            for abp_item in self.abp_items
            for abp_path in abp_item.abp_paths
            for abp__o, abp_v in abp_path
        ]
        abp_xs = [abp_x for abp_v in abp_values for abp_x in abp_v[0::2]]
        abp_ys = [abp_y for abp_v in abp_values for abp_y in abp_v[1::2]]
        if not abp_xs or not self.abp__framed(min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)):
            abp_corners = [
                abp_p
                for abp_item in self.abp_items
                if abp_item.abp_text
                for abp_p in abp_item.abp_frame
            ]
            abp_xs += [abp_p[0] for abp_p in abp_corners]
            abp_ys += [abp_p[1] for abp_p in abp_corners]
        return (
            (min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)) if abp_xs else (0.0, 0.0, 1.0, 1.0)
        )

    def abp__framed(self, abp_x0: float, abp_y0: float, abp_x1: float, abp_y1: float) -> bool:
        abp_wide = abp_tall = False
        for abp_item in self.abp_items:
            if abp_item.abp_filled:
                continue
            for abp_path in abp_item.abp_paths:
                for (abp__a, abp_p), (abp__b, abp_q) in itertools.pairwise(abp_path):
                    abp_wide = abp_wide or abs(abp_q[-2] - abp_p[-2]) > abp_FRAME_SHARE * (
                        abp_x1 - abp_x0
                    )
                    abp_tall = abp_tall or abs(abp_q[-1] - abp_p[-1]) > abp_FRAME_SHARE * (
                        abp_y1 - abp_y0
                    )
        return abp_wide and abp_tall

    def abp_scale(self, abp_factor: float) -> None:
        self.abp_items = [
            replace(
                abp_item,
                abp_paths=tuple(
                    tuple(
                        (abp_o, tuple(abp_v * abp_factor for abp_v in abp_values))
                        for abp_o, abp_values in abp_path
                    )
                    for abp_path in abp_item.abp_paths
                ),
                abp_frame=(
                    (abp_item.abp_frame[0][0] * abp_factor, abp_item.abp_frame[0][1] * abp_factor),
                    (abp_item.abp_frame[1][0] * abp_factor, abp_item.abp_frame[1][1] * abp_factor),
                    (abp_item.abp_frame[2][0] * abp_factor, abp_item.abp_frame[2][1] * abp_factor),
                ),
            )
            for abp_item in self.abp_items
        ]
        self.abp_blocks = [abp_b.abp_scaled(abp_factor) for abp_b in self.abp_blocks]

    def abp__stroke(self, abp_paths: tuple[abpOrders, ...], abp_p: BackendProperties) -> None:
        abp_width = min(max(abp_p.lineweight, abp_MIN_LINEWIDTH_MM), abp_MAX_LINEWIDTH_MM)
        self.abp_items.append(abp__Item(abp_p.layer, abp_p.color, abp_width, False, abp_paths))


class abpTextPipeline(RenderPipeline2d):
    def __init__(self, abp_recorder: abpPageRecorder) -> None:
        super().__init__(abp_recorder)
        self.abp__recorder = abp_recorder

    def draw_text(
        self,
        abp_text: str,
        abp_transform: Matrix44,
        abp_properties: Properties,
        abp_cap_height: float,
        abp_dxftype: str = "TEXT",
    ) -> None:
        if not abp_text.strip():
            return
        abp_clean = prepare_string_for_rendering(abp_text, abp_dxftype)
        abp_face = (
            abp_properties.font if abp_properties.font is not None else self.default_font_face
        )
        try:
            abp_width = self.text_engine.get_text_line_width(
                abp__unaccented(abp_clean), abp_face, abp_cap_height
            )
        except (RuntimeError, ValueError):
            abp_width = 0.7 * abp_cap_height * len(abp_clean)
        abp_local = [(0.0, 0.0, 0.0), (abp_width, 0.0, 0.0), (0.0, abp_cap_height, 0.0)]
        abp_corners = [Vec2(abp_v) for abp_v in abp_transform.transform_vertices(abp_local)]
        if self.clipping_portal.is_active:
            if self.clipping_portal.clip_point((abp_corners[0] + abp_corners[1]) * 0.5) is None:
                return
            abp_stages = self.clipping_portal._stages
            for abp_stage in abp_stages[::-1]:
                if abp_stage.transform:
                    abp_corners = list(abp_stage.transform.fast_2d_transform(abp_corners))
        abp_a, abp_b, abp_c = ((abp_v.x, abp_v.y) for abp_v in abp_corners)
        self.abp__recorder.abp_add_text(
            abp_clean, (abp_a, abp_b, abp_c), self.get_backend_properties(abp_properties)
        )


def abp__unaccented(abp_text: str) -> str:
    abp_decomposed = unicodedata.normalize("NFKD", abp_text)
    return "".join(abp_c for abp_c in abp_decomposed if not unicodedata.combining(abp_c))


def abp__orders(abp_path: BkPath2d) -> abpOrders:
    if len(abp_path) == 0:
        return ()
    abp_current = abp_path.start
    abp_out: list[abpOrder] = [("m", (abp_current.x, abp_current.y))]
    abp_commands: Any = abp_path.commands()
    for abp_command in abp_commands:
        abp_end = abp_command.end
        if abp_command.type == Command.MOVE_TO:
            abp_out.append(("m", (abp_end.x, abp_end.y)))
        elif abp_command.type == Command.LINE_TO:
            abp_out.append(("l", (abp_end.x, abp_end.y)))
        else:
            if abp_command.type == Command.CURVE3_TO:
                abp_c1 = abp_current + (abp_command.ctrl - abp_current) * (2 / 3)
                abp_c2 = abp_end + (abp_command.ctrl - abp_end) * (2 / 3)
            else:
                abp_c1, abp_c2 = abp_command.ctrl1, abp_command.ctrl2
            abp_out.append(("c", (abp_c1.x, abp_c1.y, abp_c2.x, abp_c2.y, abp_end.x, abp_end.y)))
        abp_current = abp_end
    return tuple(abp_out)


def abp_write_page(
    abp_doc: Any, abp_recorder: abpPageRecorder, abp_bounds: tuple[float, float, float, float]
) -> None:
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_bounds
    abp_page = abp_doc.new_page(
        width=(abp_x1 - abp_x0) * abp_MM_TO_PT, height=(abp_y1 - abp_y0) * abp_MM_TO_PT
    )
    abp_page.insert_font(fontname="helv")
    abp_groups = abp__layers(
        abp_doc, abp_page, [abp_i.abp_layer for abp_i in abp_recorder.abp_items]
    )
    abp_shift = f"{-abp_x0 * abp_MM_TO_PT:.4f} {-abp_y0 * abp_MM_TO_PT:.4f}"
    abp_out: list[str] = [f"{abp_MM_TO_PT:.6f} 0 0 {abp_MM_TO_PT:.6f} {abp_shift} cm 1 J 1 j"]
    abp_layer: str | None = None
    for abp_item in abp_recorder.abp_items:
        if abp_item.abp_layer != abp_layer:
            if abp_layer is not None:
                abp_out.append("EMC")
            abp_layer = abp_item.abp_layer
            abp_out.append(f"/OC /{abp_groups[abp_layer]} BDC")
        abp_out.append(abp__text(abp_item) if abp_item.abp_text else abp__drawing(abp_item))
    if abp_layer is not None:
        abp_out.append("EMC")
    abp_xref = abp_doc.get_new_xref()
    abp_doc.update_object(abp_xref, "<<>>")
    abp_doc.update_stream(abp_xref, "\n".join(abp_out).encode("latin-1", "replace"), compress=True)
    abp_page.set_contents(abp_xref)


def abp__layers(abp_doc: Any, abp_page: Any, abp_names: Sequence[str]) -> dict[str, str]:
    abp_existing = {abp_v["name"]: abp_k for abp_k, abp_v in (abp_doc.get_ocgs() or {}).items()}
    abp_kind, abp_value = abp_doc.xref_get_key(abp_page.xref, "Resources")
    abp_target, abp_prefix = abp_page.xref, "Resources/"
    if abp_kind == "xref":
        abp_target, abp_prefix = int(abp_value.split()[0]), ""
    abp_out: dict[str, str] = {}
    for abp_k, abp_name in enumerate(dict.fromkeys(abp_names)):
        abp_ocg = abp_existing.get(abp_name) or abp_doc.add_ocg(abp_name, on=True)
        abp_out[abp_name] = f"MC{abp_k}"
        abp_doc.xref_set_key(abp_target, f"{abp_prefix}Properties/MC{abp_k}", f"{abp_ocg} 0 R")
    return abp_out


def abp__color(abp_value: str) -> str:
    abp_r, abp_g, abp_b = (int(abp_value[abp_k : abp_k + 2], 16) / 255 for abp_k in (1, 3, 5))
    return f"{abp_r:.3f} {abp_g:.3f} {abp_b:.3f}"


def abp__drawing(abp_item: abp__Item) -> str:
    abp_color = abp__color(abp_item.abp_color)
    abp_paint = (
        f"{abp_color} rg" if abp_item.abp_filled else f"{abp_color} RG {abp_item.abp_width:.3f} w"
    )
    abp_body = " ".join(
        " ".join(f"{abp_v:.4f}" for abp_v in abp_values) + " " + abp_order
        for abp_path in abp_item.abp_paths
        for abp_order, abp_values in abp_path
    )
    return f"{abp_paint} {abp_body} {'f*' if abp_item.abp_filled else 'S'}"


def abp__text(abp_item: abp__Item) -> str:
    (abp_ax, abp_ay), (abp_bx, abp_by), (abp_cx, abp_cy) = abp_item.abp_frame
    abp_width, abp_height = (
        math.hypot(abp_bx - abp_ax, abp_by - abp_ay),
        math.hypot(abp_cx - abp_ax, abp_cy - abp_ay),
    )
    if abp_width < 1e-6 or abp_height < 1e-6:
        return ""
    abp_size = abp_height / abp_CAP_HEIGHT
    abp_stretch = abp_width / (
        pymupdf.get_text_length(abp_item.abp_text, "helv", abp_size) or abp_width
    )
    abp_ux, abp_uy = (
        (abp_bx - abp_ax) / abp_width * abp_stretch,
        (abp_by - abp_ay) / abp_width * abp_stretch,
    )
    abp_vx, abp_vy = (abp_cx - abp_ax) / abp_height, (abp_cy - abp_ay) / abp_height
    abp_letters = abp_item.abp_text.encode("cp1252", "replace")
    abp_escaped = "".join(
        chr(abp_c) if 32 <= abp_c < 127 and chr(abp_c) not in "()\\" else f"\\{abp_c:03o}"
        for abp_c in abp_letters
    )
    return (
        f"BT {abp__color(abp_item.abp_color)} rg /helv {abp_size:.4f} Tf "
        f"{abp_ux:.5f} {abp_uy:.5f} {abp_vx:.5f} {abp_vy:.5f} {abp_ax:.4f} {abp_ay:.4f} Tm ({abp_escaped}) Tj ET"
    )


def abp_block_rows(
    abp_recorder: abpPageRecorder, abp_bounds: tuple[float, float, float, float]
) -> list[list[Any]]:
    abp_x0, abp__y0, abp__x1, abp_y1 = abp_bounds
    return [
        [
            abp_b.abp_name,
            round((abp_b.abp_center[0] - abp_x0) * abp_MM_TO_PT, 2),
            round((abp_y1 - abp_b.abp_center[1]) * abp_MM_TO_PT, 2),
            round(abp_b.abp_size[0] * abp_MM_TO_PT, 2),
            round(abp_b.abp_size[1] * abp_MM_TO_PT, 2),
            round(-abp_b.abp_angle % 360, 2),
        ]
        for abp_b in abp_recorder.abp_blocks
    ]


def abp_save_document(
    abp_doc: Any,
    abp_path: Path,
    abp_scales: Sequence[float | None],
    abp_blocks: Sequence[Sequence[Sequence[Any]]] = (),
) -> None:
    abp_words = " ".join(f"{abp_s:.4f}" if abp_s else "0" for abp_s in abp_scales)
    abp_doc.set_metadata({"producer": abp_CAD_PRODUCER, "keywords": abp_words})
    if abp_blocks:
        abp_data = json.dumps(abp_blocks, ensure_ascii=False).encode("utf-8")
        abp_doc.embfile_add(abp_CAD_BLOCKS, abp_data, filename=f"{abp_CAD_BLOCKS}.json")
    abp_doc.save(abp_path, garbage=1, deflate=True)
