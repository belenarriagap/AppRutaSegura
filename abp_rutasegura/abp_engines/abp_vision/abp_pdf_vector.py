from __future__ import annotations

import itertools
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf

from abp_rutasegura.abp_domain.abp_vector import (
    abpPdfPage,
    abpPlacedBlock,
    abpVectorPlan,
    abpVectorText,
)
from abp_rutasegura.abp_engines.abp_vision.abp_images import (
    abp_MAX_SIDE_PX,
    abp_PDF_DPI,
    abpPlanFileError,
    abpRGBImage,
)

abp_CAD_BLOCKS = "bloques"
abp_CAD_PRODUCER = "RutaSegura CAD"
abp_GREEN_SHARE = 0.4
abp_MIN_VECTOR_STROKES = 25
abp_SCAN_COVERAGE = 0.5
abp_SCAN_STROKES = 400
abp_NEUTRAL_SPREAD, abp_NEUTRAL_LIGHT = 0.12, 0.85
abp_COMMON_SCALES = frozenset({20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 1000})
abp_MIN_ARC_PIECES = 5
abpArcParams = tuple[float, float, float, float, float]
abp_COLOR_SATURATION = 45

abp__ORDINALS = {
    "PRIMER": 0,
    "PRIMERA": 0,
    "1ER": 0,
    "1ERA": 0,
    "SEGUNDO": 1,
    "SEGUNDA": 1,
    "2DO": 1,
    "2DA": 1,
    "TERCER": 2,
    "TERCERA": 2,
    "3ER": 2,
    "3ERA": 2,
    "CUARTO": 3,
    "CUARTA": 3,
    "4TO": 3,
    "4TA": 3,
}
abp__SCALE = re.compile(r"\b1\s*[/:]\s*(\d{2,4})\b")
abp__LEVEL = re.compile(
    r"\b(PRIMERA?|SEGUND[OA]|TERCERA?|CUART[OA]|1ERA?|2D[OA]|3ERA?|4T[OA])\s+(?:NIVEL|PISO|PLANTA)\b"
)
abp__LEVEL_NUMBER = re.compile(r"\b(?:PISO|NIVEL|PLANTA)\s+(?:N[°º.]\s*)?([1-4])\b")
abp__TITLE = re.compile(
    r"\b(PLANO|MAPA|PLANTA|DISTRIBUCION|ARQUITECTURA|EVACUACION|SENALIZACION)\b"
)

abp_FURNITURE_WORDS = ("mueble", "mobil", "movil", "furn", "equip", "silla", "mesa")
abp_WALL_WORDS = ("muro", "wall", "tabique", "pared", "albanil")
abp_NON_STRUCTURE_WORDS = (
    "eje",
    "axis",
    "cota",
    "acot",
    "dim",
    "text",
    "senal",
    "evacua",
    "muebl",
    "mobil",
    "moviliari",
    "furn",
    "nota",
    "etiquet",
    "hatch",
    "trama",
    "achur",
    "marco",
    "formato",
    "lamina",
    "membrete",
    "extint",
    "electr",
    "lumin",
    "sanit",
    "seguridad",
    "persona",
    "arbol",
    "veget",
    "fondo",
    "titulo",
    "norte",
    "simbol",
    "leyenda",
    "viewport",
    "defpoints",
)


def abp_plain(abp_text: str) -> str:
    abp_decomposed = unicodedata.normalize("NFKD", abp_text)
    abp_letters = "".join(abp_c for abp_c in abp_decomposed if not unicodedata.combining(abp_c))
    return " ".join(abp_letters.upper().split())


def abp_is_structure_layer(abp_name: str) -> bool:
    abp_lowered = abp_plain(abp_name).lower()
    return not any(abp_word in abp_lowered for abp_word in abp_NON_STRUCTURE_WORDS)


def abp_is_wall_layer(abp_name: str) -> bool:
    abp_lowered = abp_plain(abp_name).lower()
    return any(abp_word in abp_lowered for abp_word in abp_WALL_WORDS)


def abp_is_furniture_layer(abp_name: str) -> bool:
    abp_lowered = abp_plain(abp_name).lower()
    return any(abp_word in abp_lowered for abp_word in abp_FURNITURE_WORDS)


def abp__open(abp_path: Path) -> Any:
    try:
        abp_doc = pymupdf.open(abp_path)
    except (RuntimeError, ValueError) as abp_exc:
        raise abpPlanFileError(f"No se pudo abrir el PDF: {abp_exc}") from abp_exc
    if abp_doc.needs_pass:
        abp_doc.close()
        raise abpPlanFileError(
            "El PDF tiene contraseña. Guárdelo sin contraseña e inténtelo de nuevo."
        )
    return abp_doc


def abp__page(abp_doc: Any, abp_number: int) -> Any:
    if not 0 <= abp_number < abp_doc.page_count:
        raise abpPlanFileError(
            f"El PDF tiene {abp_doc.page_count} página(s); no existe la {abp_number + 1}."
        )
    return abp_doc[abp_number]


def abp_effective_dpi(
    abp_width_pt: float, abp_height_pt: float, abp_dpi: float = abp_PDF_DPI
) -> float:
    abp_longest_in = max(abp_width_pt, abp_height_pt) / 72.0
    abp_limit = int(abp_MAX_SIDE_PX / abp_longest_in) if abp_longest_in > 0 else abp_dpi
    return float(max(min(abp_dpi, abp_limit), 36))


def abp__texts(abp_page: Any, abp_zoom: float) -> list[abpVectorText]:
    abp_matrix = abp_page.rotation_matrix
    abp_out: list[abpVectorText] = []
    for abp_block in abp_page.get_text("dict")["blocks"]:
        for abp_line in abp_block.get("lines", []):
            abp_spans = abp_line["spans"]
            abp_text = "".join(abp_s["text"] for abp_s in abp_spans).strip()
            if not abp_text:
                continue
            abp_dx, abp_dy = abp_line["dir"]
            abp_a = pymupdf.Point(0, 0) * abp_matrix
            abp_b = pymupdf.Point(abp_dx, abp_dy) * abp_matrix
            abp_angle = math.degrees(math.atan2(abp_b.y - abp_a.y, abp_b.x - abp_a.x))
            abp_x0, abp_y0, abp_x1, abp_y1 = abp_line["bbox"]
            abp_center = pymupdf.Point((abp_x0 + abp_x1) / 2, (abp_y0 + abp_y1) / 2) * abp_matrix
            abp_size = float(abp_spans[0]["size"])
            abp_c, abp_s = abs(abp_dx), abs(abp_dy)
            abp_w, abp_h = abp_x1 - abp_x0, abp_y1 - abp_y0
            abp_width = (
                ((abp_w - abp_size * abp_s) / abp_c if abp_c else abp_w)
                if abp_c >= abp_s
                else (abp_h - abp_size * abp_c) / abp_s
            )
            abp_out.append(
                abpVectorText(
                    abp_text,
                    abp_center.x * abp_zoom,
                    abp_center.y * abp_zoom,
                    max(float(abp_width), abp_size) * abp_zoom,
                    abp_size * abp_zoom,
                    round(abp_angle, 1),
                    str(abp_spans[0]["font"]),
                )
            )
    return abp_out


def abp_find_scale(abp_texts: Iterable[str]) -> int | None:
    abp_found: Counter[int] = Counter()
    for abp_text in abp_texts:
        for abp_match in abp__SCALE.finditer(abp_text):
            abp_value = int(abp_match.group(1))
            if abp_value in abp_COMMON_SCALES:
                abp_found[abp_value] += 3 if "ESC" in abp_plain(abp_text) else 1
    return abp_found.most_common(1)[0][0] if abp_found else None


def abp_find_level(abp_texts: Iterable[str]) -> int | None:
    for abp_text in abp_texts:
        abp_upper = abp_plain(abp_text)
        abp_match = abp__LEVEL.search(abp_upper)
        if abp_match:
            return abp__ORDINALS[abp_match.group(1)]
        abp_number = abp__LEVEL_NUMBER.search(abp_upper)
        if abp_number:
            return int(abp_number.group(1)) - 1
    return None


def abp_find_title(abp_texts: Iterable[abpVectorText]) -> str:
    abp_best: tuple[float, str] | None = None
    for abp_t in abp_texts:
        if (
            len(abp_t.abp_text) > 8
            and abp__TITLE.search(abp_plain(abp_t.abp_text))
            and (abp_best is None or abp_t.abp_size > abp_best[0])
        ):
            abp_best = (abp_t.abp_size, abp_t.abp_text)
    return " ".join(abp_best[1].split()) if abp_best else ""


def abp__kind(abp_title: str) -> str:
    abp_upper = abp_plain(abp_title)
    if "EVACUACION" in abp_upper or "SENALIZACION" in abp_upper:
        return "evacuacion"
    return "riesgo" if "RIESGO" in abp_upper else ""


def abp__layer_names(abp_doc: Any) -> dict[int, str]:
    return {
        int(abp_xref): str(abp_info["name"])
        for abp_xref, abp_info in (abp_doc.get_ocgs() or {}).items()
    }


def abp_inspect_pdf(abp_path: Path) -> tuple[abpPdfPage, ...]:
    with abp__open(abp_path) as abp_doc:
        abp_layers = tuple(sorted(set(abp__layer_names(abp_doc).values())))
        abp_pages = []
        for abp_number in range(abp_doc.page_count):
            abp_page = abp_doc[abp_number]
            abp_texts = abp__texts(abp_page, 1.0)
            abp_plain_texts = [abp_t.abp_text for abp_t in abp_texts]
            abp_title = abp_find_title(abp_texts)
            abp_pages.append(
                abpPdfPage(
                    abp_number=abp_number,
                    abp_width_mm=abp_page.rect.width / 72 * 25.4,
                    abp_height_mm=abp_page.rect.height / 72 * 25.4,
                    abp_is_vector=abp__is_vector(abp_page),
                    abp_title=abp_title,
                    abp_level=abp_find_level(abp_plain_texts),
                    abp_scale_denominator=abp__exact_scale(abp_doc, abp_number)
                    or abp_find_scale(abp_plain_texts),
                    abp_layers=abp_layers,
                    abp_kind=abp__kind(abp_title),
                )
            )
        return tuple(abp_pages)


def abp__exact_scale(abp_doc: Any, abp_number: int) -> float | None:
    if abp_doc.metadata.get("producer") != abp_CAD_PRODUCER:
        return None
    abp_words = (abp_doc.metadata.get("keywords") or "").split()
    abp_value = float(abp_words[abp_number]) if abp_number < len(abp_words) else 0.0
    return abp_value or None


def abp_read_blocks(abp_path: Path, abp_number: int) -> tuple[abpPlacedBlock, ...]:
    with abp__open(abp_path) as abp_doc:
        if (
            abp_doc.metadata.get("producer") != abp_CAD_PRODUCER
            or abp_CAD_BLOCKS not in abp_doc.embfile_names()
        ):
            return ()
        abp_pages = json.loads(abp_doc.embfile_get(abp_CAD_BLOCKS).decode("utf-8"))
        abp_page = abp__page(abp_doc, abp_number)
        abp_k = int(abp_effective_dpi(abp_page.rect.width, abp_page.rect.height)) / 72.0
    abp_rows = abp_pages[abp_number] if abp_number < len(abp_pages) else ()
    return tuple(
        abpPlacedBlock(abp_n, abp_x * abp_k, abp_y * abp_k, abp_w * abp_k, abp_h * abp_k, abp_a)
        for abp_n, abp_x, abp_y, abp_w, abp_h, abp_a in abp_rows
    )


def abp__is_vector(abp_page: Any) -> bool:
    abp_area = max(float(abs(abp_page.rect)), 1.0)
    abp_covered = sum(
        float(abs(abp_page.rect & abp_rect))
        for abp_info in abp_page.get_images(full=True)
        for abp_rect in abp_page.get_image_rects(abp_info[0])
    )
    abp_needed = (
        abp_SCAN_STROKES if abp_covered >= abp_SCAN_COVERAGE * abp_area else abp_MIN_VECTOR_STROKES
    )
    abp_strokes = 0
    for abp_path in abp_page.get_cdrawings():
        abp_strokes += len(abp_path["items"])
        if abp_strokes >= abp_needed:
            return True
    return False


def abp__is_symbol_fill(abp_drawing: Any) -> bool:
    abp_fill = abp_drawing.get("fill")
    if "f" not in abp_drawing["type"] or abp_fill is None:
        return False
    abp_low, abp_high = min(abp_fill), max(abp_fill)
    return bool(abp_high - abp_low > abp_NEUTRAL_SPREAD or abp_low > abp_NEUTRAL_LIGHT)


def abp__is_green_stroke(abp_drawing: Any) -> bool:
    abp_color = abp_drawing.get("color")
    if "s" not in abp_drawing["type"] or abp_color is None or len(abp_color) != 3:
        return False
    return bool(abp_color[1] - max(abp_color[0], abp_color[2]) > 0.5)


def abp_thumbnail(abp_path: Path, abp_number: int, abp_max_side: int = 220) -> abpRGBImage:
    with abp__open(abp_path) as abp_doc:
        abp_page = abp__page(abp_doc, abp_number)
        abp_zoom = abp_max_side / max(abp_page.rect.width, abp_page.rect.height)
        abp_pix = abp_page.get_pixmap(matrix=pymupdf.Matrix(abp_zoom, abp_zoom), alpha=False)
        return abp__to_array(abp_pix)


def abp__to_array(abp_pix: Any) -> abpRGBImage:
    abp_raw = np.frombuffer(abp_pix.samples, dtype=np.uint8)
    abp_rows = abp_raw.reshape(abp_pix.height, abp_pix.stride)[:, : abp_pix.width * abp_pix.n]
    abp_image = abp_rows.reshape(abp_pix.height, abp_pix.width, abp_pix.n)
    return np.ascontiguousarray(abp_image[:, :, :3], dtype=np.uint8)


def abp_render_page(
    abp_path: Path,
    abp_number: int,
    *,
    abp_hidden_layers: Collection[str] = (),
    abp_remove_colors: bool = False,
) -> abpRGBImage:
    with abp__open(abp_path) as abp_doc:
        abp_page = abp__page(abp_doc, abp_number)
        abp_off = [
            abp_x
            for abp_x, abp_name in abp__layer_names(abp_doc).items()
            if abp_name in set(abp_hidden_layers)
        ]
        if abp_off:
            abp_doc.set_layer(-1, off=abp_off)
            abp_page = abp_doc.reload_page(abp_page)
        abp_dpi = int(abp_effective_dpi(abp_page.rect.width, abp_page.rect.height))
        abp_pix = abp_page.get_pixmap(dpi=abp_dpi, alpha=False, colorspace=pymupdf.csRGB)
        abp_image = abp__to_array(abp_pix)
    return abp_without_colors(abp_image) if abp_remove_colors else abp_image


def abp_without_colors(abp_image: abpRGBImage) -> abpRGBImage:
    abp_hsv = cv2.cvtColor(abp_image, cv2.COLOR_RGB2HSV)
    abp_colored = (abp_hsv[:, :, 1] > abp_COLOR_SATURATION).astype(np.uint8)
    abp_colored = np.asarray(cv2.dilate(abp_colored, np.ones((3, 3), np.uint8)), np.uint8)
    abp_out = abp_image.copy()
    abp_out[abp_colored > 0] = 255
    return np.ascontiguousarray(abp_out, dtype=np.uint8)


def abp_thicken_lines(abp_image: abpRGBImage) -> abpRGBImage:
    return np.ascontiguousarray(cv2.erode(abp_image, np.ones((2, 2), np.uint8)), dtype=np.uint8)


def abp_read_vector(abp_path: Path, abp_number: int) -> abpVectorPlan | None:
    with abp__open(abp_path) as abp_doc:
        abp_page = abp__page(abp_doc, abp_number)
        if not abp__is_vector(abp_page):
            return None
        abp_dpi = float(int(abp_effective_dpi(abp_page.rect.width, abp_page.rect.height)))
        abp_zoom = abp_dpi / 72.0
        abp_m = abp_page.rotation_matrix
        abp_matrix = np.array([[abp_m.a, abp_m.b], [abp_m.c, abp_m.d]]) * abp_zoom
        abp_offset = np.array([abp_m.e, abp_m.f]) * abp_zoom
        abp_names: dict[str, int] = {}
        abp_segments: list[tuple[float, float, float, float]] = []
        abp_seg_layer: list[int] = []
        abp_filled: list[bool] = []
        abp_widths: list[float] = []
        abp_arcs: list[tuple[float, float, float, float, float]] = []
        abp_arc_layer: list[int] = []

        def abp_to_px(abp_points: Any) -> Any:
            return np.asarray(abp_points, np.float64).reshape(-1, 2) @ abp_matrix + abp_offset

        abp_drawings = abp_page.get_cdrawings()
        abp_green = [abp__is_green_stroke(abp_d) for abp_d in abp_drawings]
        abp_skip_green = sum(abp_green) < abp_GREEN_SHARE * len(abp_drawings)
        for abp_drawing, abp_is_green in zip(abp_drawings, abp_green, strict=True):
            abp_layer = abp_names.setdefault(str(abp_drawing.get("layer") or ""), len(abp_names))
            abp_is_filled = abp__is_symbol_fill(abp_drawing) or (abp_is_green and abp_skip_green)
            abp_stroked = "s" in abp_drawing["type"]
            abp_width = float(abp_drawing.get("width") or 0.0) * abp_zoom if abp_stroked else 0.0
            abp_run: list[Any] = []
            abp_curve: list[Any] = []

            def abp_flush(abp_curve: list[Any], abp_layer: int = abp_layer) -> None:
                if abp_curve:
                    abp_arc = abp_fit_arc(abp_to_px(np.concatenate(abp_curve)))
                    if abp_arc is not None:
                        abp_arcs.append(abp_arc)
                        abp_arc_layer.append(abp_layer)
                    abp_curve.clear()

            def abp_flush_run(
                abp_run: list[Any],
                abp_layer: int = abp_layer,
                abp_is_filled: bool = abp_is_filled,
                abp_width: float = abp_width,
            ) -> None:
                if not abp_run:
                    return
                abp_px = abp_to_px([abp_run[0][0], *(abp_b for abp__a, abp_b in abp_run)])
                abp_run.clear()
                abp_taken = np.zeros(len(abp_px) - 1, bool)
                for abp_i, abp_j, abp_arc in abp_polyline_arcs(abp_px) if not abp_is_filled else ():
                    abp_taken[abp_i:abp_j] = True
                    abp_arcs.append(abp_arc)
                    abp_arc_layer.append(abp_layer)
                for (abp_a, abp_b), abp_used in zip(
                    itertools.pairwise(abp_px), abp_taken, strict=True
                ):
                    if not abp_used and abs(abp_a[0] - abp_b[0]) + abs(abp_a[1] - abp_b[1]) > 1e-6:
                        abp_segments.append((abp_a[0], abp_a[1], abp_b[0], abp_b[1]))
                        abp_seg_layer.append(abp_layer)
                        abp_filled.append(abp_is_filled)
                        abp_widths.append(abp_width)

            for abp_item in abp_drawing["items"]:
                abp_op = abp_item[0]
                if abp_op != "l":
                    abp_flush_run(abp_run)
                if abp_op == "c":
                    abp_points = abp__bezier(np.asarray(abp_item[1:5], np.float64))
                    if abp_curve and np.abs(abp_curve[-1][-1] - abp_points[0]).max() > 0.05:
                        abp_flush(abp_curve)
                    abp_curve.append(abp_points)
                    continue
                abp_flush(abp_curve)
                if abp_op == "l":
                    abp_path_points = [abp_item[1], abp_item[2]]
                    if abp_run and abp_run[-1][1] != abp_item[1]:
                        abp_flush_run(abp_run)
                    abp_run.append((abp_item[1], abp_item[2]))
                    continue
                elif abp_op == "re":
                    abp_x0, abp_y0, abp_x1, abp_y1 = abp_item[1]
                    abp_path_points = [
                        (abp_x0, abp_y0),
                        (abp_x1, abp_y0),
                        (abp_x1, abp_y1),
                        (abp_x0, abp_y1),
                        (abp_x0, abp_y0),
                    ]
                elif abp_op == "qu":
                    abp_ul, abp_ur, abp_ll, abp_lr = abp_item[1]
                    abp_path_points = [abp_ul, abp_ur, abp_lr, abp_ll, abp_ul]
                else:
                    continue
                abp_px = abp_to_px(abp_path_points)
                for abp_a, abp_b in itertools.pairwise(abp_px):
                    if abs(abp_a[0] - abp_b[0]) + abs(abp_a[1] - abp_b[1]) > 1e-6:
                        abp_segments.append((abp_a[0], abp_a[1], abp_b[0], abp_b[1]))
                        abp_seg_layer.append(abp_layer)
                        abp_filled.append(abp_is_filled)
                        abp_widths.append(abp_width)
            abp_flush(abp_curve)
            abp_flush_run(abp_run)
        abp_texts = abp__texts(abp_page, abp_zoom)
        return abpVectorPlan(
            abp_width=abp_page.rect.width * abp_zoom,
            abp_height=abp_page.rect.height * abp_zoom,
            abp_dpi=abp_dpi,
            abp_layers=tuple(abp_names),
            abp_segments=np.array(abp_segments, np.float64).reshape(-1, 4),
            abp_segment_layer=np.array(abp_seg_layer, np.int64),
            abp_filled=np.array(abp_filled, np.bool_),
            abp_arcs=np.array(abp_arcs, np.float64).reshape(-1, 5),
            abp_arc_layer=np.array(abp_arc_layer, np.int64),
            abp_texts=tuple(abp_texts),
            abp_segment_width=np.array(abp_widths, np.float64),
            abp_scale_denominator=abp__exact_scale(abp_doc, abp_number)
            or abp_find_scale(abp_t.abp_text for abp_t in abp_texts),
            abp_exact_scale=abp__exact_scale(abp_doc, abp_number) is not None,
        )


def abp_polyline_arcs(abp_points: Any) -> list[tuple[int, int, abpArcParams]]:
    abp_p = np.asarray(abp_points, np.float64)
    if len(abp_p) < abp_MIN_ARC_PIECES + 1:
        return []
    abp_d = np.diff(abp_p, axis=0)
    abp_size = np.hypot(abp_d[:, 0], abp_d[:, 1])
    abp_angle = np.arctan2(abp_d[:, 1], abp_d[:, 0])
    abp_turn = (np.diff(abp_angle) + np.pi) % (2 * np.pi) - np.pi
    abp_out: list[tuple[int, int, abpArcParams]] = []
    abp_i = 0
    while abp_i < len(abp_turn):
        abp_j = abp_i
        while (
            abp_j < len(abp_turn)
            and math.radians(1.5) < abs(abp_turn[abp_j]) < math.radians(28)
            and abp_turn[abp_j] * abp_turn[abp_i] > 0
            and 0.5 < abp_size[abp_j + 1] / max(abp_size[abp_i], 1e-9) < 2.0
        ):
            abp_j += 1
        if abp_j - abp_i + 1 >= abp_MIN_ARC_PIECES:
            abp_arc = abp_fit_arc(abp_p[abp_i : abp_j + 2])
            if abp_arc is not None:
                abp_out.append((abp_i, abp_j + 1, abp_arc))
        abp_i = max(abp_j, abp_i + 1)
    return abp_out


def abp__bezier(abp_control: Any) -> Any:
    abp_t = np.linspace(0.0, 1.0, 5)[:, None]
    abp_p0, abp_p1, abp_p2, abp_p3 = abp_control
    return (
        (1 - abp_t) ** 3 * abp_p0
        + 3 * (1 - abp_t) ** 2 * abp_t * abp_p1
        + 3 * (1 - abp_t) * abp_t**2 * abp_p2
        + abp_t**3 * abp_p3
    )


def abp_fit_arc(abp_points: Any) -> tuple[float, float, float, float, float] | None:
    abp_p = np.asarray(abp_points, np.float64)
    abp_center = abp_p.mean(axis=0)
    abp_q = abp_p - abp_center
    abp_a = np.c_[2 * abp_q, np.ones(len(abp_q))]
    abp_solution, _, abp_rank, _ = np.linalg.lstsq(abp_a, (abp_q**2).sum(axis=1), rcond=None)
    if abp_rank < 3:
        return None
    abp_cx, abp_cy = abp_solution[0], abp_solution[1]
    abp_r2 = abp_solution[2] + abp_cx * abp_cx + abp_cy * abp_cy
    if abp_r2 <= 0:
        return None
    abp_radius = math.sqrt(abp_r2)
    abp_error = np.abs(np.hypot(abp_q[:, 0] - abp_cx, abp_q[:, 1] - abp_cy) - abp_radius).max()
    if abp_error > max(0.02 * abp_radius, 0.6):
        return None
    abp_angles = np.unwrap(np.arctan2(abp_q[:, 1] - abp_cy, abp_q[:, 0] - abp_cx))
    return (
        float(abp_cx + abp_center[0]),
        float(abp_cy + abp_center[1]),
        abp_radius,
        float(abp_angles[0]),
        float(abp_angles[-1] - abp_angles[0]),
    )
