from __future__ import annotations

import functools
import itertools
import math
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from abp_rutasegura import abp_resources
from abp_rutasegura.abp_domain.abp_enums import abpSignKind
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon
from abp_rutasegura.abp_domain.abp_plan import abpSafeZone, abpSign
from abp_rutasegura.abp_domain.abp_vector import abpPlacedBlock, abpVectorPlan, abpVectorText
from abp_rutasegura.abp_engines.abp_vision.abp_images import abpRGBImage
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_plain

abpMask = npt.NDArray[np.uint8]
abpBox = tuple[float, float, float, float]
abpGrayF = npt.NDArray[np.float32]

abp_KEYWORDS: tuple[tuple[abpSignKind, tuple[str, ...]], ...] = (
    (abpSignKind.abp_SAFE_ZONE, ("ZONA SEGURA", "EN CASO DE SISMO")),
    (abpSignKind.abp_SMOKE_DETECTOR, ("DETECTOR DE HUMO",)),
    (abpSignKind.abp_HEAT_DETECTOR, ("DETECTOR DE TEMPERATURA", "DETECTOR TERMICO")),
    (abpSignKind.abp_STROBE, ("ESTROBOSCOP", "SIRENA")),
    (abpSignKind.abp_MANUAL_STATION, ("ESTACION MANUAL",)),
    (abpSignKind.abp_ALARM_PANEL, ("CENTRAL DE ALARMA", "C-ACI", "PANEL CONTRA")),
    (abpSignKind.abp_STRETCHER, ("CAMILLA",)),
    (abpSignKind.abp_FIRST_AID, ("BOTIQUIN", "PRIMEROS", "AUXILIOS")),
    (abpSignKind.abp_EMERGENCY_LIGHT, ("ILUMINACION", "LUZ DE EMERGENCIA", "LUCES DE EMERGENCIA")),
    (abpSignKind.abp_HYDRANT, ("HIDRANTE", "GABINETE CONTRA", "MANGUERA")),
    (abpSignKind.abp_EXTINGUISHER, ("EXTINTOR",)),
    (abpSignKind.abp_ALARM, ("ALARMA", "PULSADOR")),
    (abpSignKind.abp_ELECTRIC_RISK, ("ELECTRIC", "TABLERO")),
    (abpSignKind.abp_CAPACITY, ("AFORO", "CAPACIDAD MAXIMA")),
    (abpSignKind.abp_STAIRS, ("ESCALERA DE EVACUACION", "SENAL DE ESCALERA", "ESCALERA DESC")),
    (abpSignKind.abp_EMERGENCY_EXIT, ("SALIDA A UTILIZAR", "SALIDA DE EMERGENCIA")),
    (abpSignKind.abp_PROHIBITION, ("PROHIBIDO", "NO TOCAR", "NO FUMAR", "NO CORRER")),
    (abpSignKind.abp_MANDATORY, ("OBLIGATORIO", "USO DE MASCARILLA")),
    (abpSignKind.abp_WARNING, ("PELIGRO", "CUIDADO", "RIESGO", "ATENCION")),
    (abpSignKind.abp_DIRECTION, ("DIRECCIONAL", "DIRECCION DE SALIDA", "FLECHA")),
    (abpSignKind.abp_EXIT, ("SALIDA",)),
)
abp_BLOCK_WORDS: tuple[tuple[abpSignKind, tuple[str, ...]], ...] = (
    (abpSignKind.abp_EMERGENCY_EXIT, ("SALIDA EN CASO", "SALIDA EMERG", "SALIDA DE EMERG")),
    (abpSignKind.abp_STAIRS, ("ESCALERA SAL", "ESCALERA DE EVAC", "SENAL ESCALERA")),
    (abpSignKind.abp_EXTINGUISHER, ("EXTINT",)),
    (abpSignKind.abp_FIRST_AID, ("BOTIQ", "PRIMEROS AUX")),
    (abpSignKind.abp_STRETCHER, ("CAMILLA",)),
    (abpSignKind.abp_SMOKE_DETECTOR, ("DETECTOR DE HUMO", "HUMO")),
    (abpSignKind.abp_ALARM_PANEL, ("PANEL CONTRA", "CENTRAL DE ALARMA")),
    (abpSignKind.abp_ALARM, ("PULSADOR", "ALARMA")),
    (
        abpSignKind.abp_EMERGENCY_LIGHT,
        ("LUZ DE EMERG", "LUCES DE EMERG", "SENA EMERG", "ILUMINACION"),
    ),
    (abpSignKind.abp_ELECTRIC_RISK, ("PELIGRO ELEC", "RIESGO ELEC")),
    (abpSignKind.abp_CAPACITY, ("AFORO",)),
    (abpSignKind.abp_SAFE_ZONE, ("ZONA SEGURA",)),
    (abpSignKind.abp_DIRECTION, ("FLECHA SALIDA", "SALIDA DIREC", "DIRECCIONAL")),
    (abpSignKind.abp_EXIT, ("ETIQUETA DE SALIDA", "SENAL DE SALIDA", "SALIDA")),
)
abp_TEMPLATE_PX = 40
abp_SMALL_SCALE = 0.55
abp_SCALES = (0.65, 0.8, 0.95, 1.1, 1.3, 1.55, 1.8)
abp_FACTOR_STEP = 0.12
abp_MIN_FACTOR_VOTES = 3
abp_MIN_MATCH = 0.5
abp_SURE_MATCH, abp_SURE_HUE_GAP = 0.6, 0.2
abp_MAX_PER_BLOB = 9
abp_COVER_BONUS = 0.3
abp_AREA_BONUS = 0.15
abp_MAX_OVERLAP = 0.3
abp_THIN_INK = 0.3
abp_MIN_FILL = 0.35
abp_MAX_HUE_GAP = 0.45
abp_ROUTE_GREEN = (0, 255, 0)


@dataclass(frozen=True, eq=False, slots=True)
class abpSymbolTemplate:
    abp_kind: abpSignKind
    abp_label: str
    abp_image: abpRGBImage

    def abp_resized(self, abp_factor: float) -> abpSymbolTemplate:
        if abs(abp_factor - 1.0) < 0.06:
            return self
        abp_h, abp_w = self.abp_image.shape[:2]
        abp_size = (max(4, round(abp_w * abp_factor)), max(4, round(abp_h * abp_factor)))
        abp_image = cv2.resize(self.abp_image, abp_size, interpolation=cv2.INTER_AREA)
        return abpSymbolTemplate(self.abp_kind, self.abp_label, np.asarray(abp_image, np.uint8))


@dataclass(frozen=True, eq=False, slots=True)
class abp__Match:
    abp_x: float
    abp_y: float
    abp_template: abpSymbolTemplate
    abp_score: float
    abp_turn: int
    abp_scale: float


@dataclass(frozen=True, slots=True)
class abpFoundSigns:
    abp_signs: tuple[abpSign, ...] = ()
    abp_zones: tuple[abpSafeZone, ...] = ()


def abp_kind_of(abp_text: str) -> abpSignKind | None:
    abp_clean = abp_plain(abp_text)
    for abp_kind, abp_words in abp_KEYWORDS:
        if any(abp_word in abp_clean for abp_word in abp_words):
            return abp_kind
    return None


def abp_legend_boxes(abp_vector: abpVectorPlan) -> tuple[abpBox, ...]:
    abp_titles = [
        abp_t for abp_t in abp_vector.abp_texts if abp_plain(abp_t.abp_text).startswith("LEYENDA")
    ]
    abp_found = (abp__legend_box(abp_vector, abp_t) for abp_t in abp_titles)
    return tuple(dict.fromkeys(abp_box for abp_box in abp_found if abp_box is not None))


def abp__legend_box(abp_vector: abpVectorPlan, abp_title: abpVectorText) -> abpBox | None:
    abp_s = abp_vector.abp_segments
    abp_horizontal = np.abs(abp_s[:, 1] - abp_s[:, 3]) < 1.0
    abp_length = np.abs(abp_s[:, 2] - abp_s[:, 0])
    abp_left, abp_right = np.minimum(abp_s[:, 0], abp_s[:, 2]), np.maximum(abp_s[:, 0], abp_s[:, 2])
    abp_over = (
        abp_horizontal
        & (abp_left < abp_title.abp_x)
        & (abp_right > abp_title.abp_x)
        & (abp_length > 1.02 * abp_title.abp_width)
    )
    abp_over &= abp_length < 0.5 * abp_vector.abp_width
    abp_y = abp_s[:, 1]
    abp_above = (
        abp_over & (abp_y < abp_title.abp_y) & (abp_y > abp_title.abp_y - 6 * abp_title.abp_size)
    )
    if not abp_above.any():
        return None
    abp_top = int(np.argmax(np.where(abp_above, abp_y, -np.inf)))
    abp_x0, abp_x1, abp_y0 = (
        float(abp_left[abp_top]),
        float(abp_right[abp_top]),
        float(abp_y[abp_top]),
    )
    abp_similar = (
        abp_over
        & (np.abs(abp_left - abp_x0) < 6)
        & (np.abs(abp_right - abp_x1) < 6)
        & (abp_y >= abp_y0)
    )
    abp_end = abp_y0
    for abp_row in np.unique(np.round(abp_y[abp_similar])):
        if abp_row - abp_end > 14 * abp_title.abp_size:
            break
        abp_end = float(abp_row)
    return (abp_x0, abp_y0, abp_x1, abp_end) if abp_end > abp_y0 + 4 * abp_title.abp_size else None


def abp_read_legend(
    abp_vector: abpVectorPlan, abp_image: abpRGBImage
) -> tuple[abpSymbolTemplate, ...]:
    return tuple(
        abp_t
        for abp_box in abp_legend_boxes(abp_vector)
        for abp_t in abp__read_table(abp_vector, abp_image, abp_box)
    )


def abp__read_table(
    abp_vector: abpVectorPlan, abp_image: abpRGBImage, abp_box: abpBox
) -> list[abpSymbolTemplate]:
    abp_x0, abp_y0, abp_x1, abp_y1 = abp_box
    abp_s = abp_vector.abp_segments
    abp_left, abp_right = np.minimum(abp_s[:, 0], abp_s[:, 2]), np.maximum(abp_s[:, 0], abp_s[:, 2])
    abp_lines = (
        (np.abs(abp_s[:, 1] - abp_s[:, 3]) < 1.0)
        & (np.abs(abp_left - abp_x0) < 6)
        & (np.abs(abp_right - abp_x1) < 6)
    )
    abp_inside = abp_lines & (abp_s[:, 1] >= abp_y0 - 1) & (abp_s[:, 1] <= abp_y1 + 1)
    abp_rows = np.unique(np.round(abp_s[abp_inside, 1]))
    abp_vertical = (
        (np.abs(abp_s[:, 0] - abp_s[:, 2]) < 1.0)
        & (abp_s[:, 0] > abp_x0 + 8)
        & (abp_s[:, 0] < abp_x1 - 8)
    )
    abp_spans = np.abs(abp_s[:, 3] - abp_s[:, 1])
    abp_vertical &= (abp_spans > 12) & (np.minimum(abp_s[:, 1], abp_s[:, 3]) >= abp_y0 - 2)
    for abp_end in (abp_s[:, 1], abp_s[:, 3]):
        abp_away = (
            np.abs(abp_end[:, None] - abp_rows[None, :]).min(axis=1) if len(abp_rows) else abp_spans
        )
        abp_vertical &= abp_away < 5
    abp_cuts = [abp_x0, abp_x1]
    if abp_vertical.any():
        abp_xs = np.unique(np.round(abp_s[abp_vertical, 0]))
        abp_weight = [
            float(abp_spans[abp_vertical & (np.round(abp_s[:, 0]) == abp_x)].sum())
            for abp_x in abp_xs
        ]
        abp_cuts += [
            float(abp_x)
            for abp_x, abp_w in zip(abp_xs, abp_weight, strict=True)
            if abp_w > 0.5 * (abp_y1 - abp_y0)
        ]
    else:
        abp_cuts.append(abp_x0 + 0.25 * (abp_x1 - abp_x0))
    abp_cuts = abp__merged(sorted(abp_cuts), 6.0)
    abp_out: list[abpSymbolTemplate] = []
    for abp_top, abp_bottom in itertools.pairwise(abp_rows):
        if abp_bottom - abp_top < 12:
            continue
        abp_row = [
            abp_t
            for abp_t in abp_vector.abp_texts
            if abp_top < abp_t.abp_y < abp_bottom and abp_x0 < abp_t.abp_x < abp_x1
        ]
        abp_columns = [
            (
                abp_a,
                abp_b,
                sorted(
                    (abp_t for abp_t in abp_row if abp_a < abp_t.abp_x < abp_b),
                    key=lambda abp_t: abp_t.abp_y,
                ),
            )
            for abp_a, abp_b in itertools.pairwise(abp_cuts)
        ]
        abp_index = max(
            range(len(abp_columns)),
            key=lambda abp_k: sum(len(abp_t.abp_text) for abp_t in abp_columns[abp_k][2]),
        )
        abp_label = " ".join(abp_t.abp_text.strip() for abp_t in abp_columns[abp_index][2])
        abp_kind = abp_kind_of(abp_label)
        if abp_kind is None or any(
            abp_w in abp_plain(abp_label) for abp_w in ("RUTA", "REUNION", "LEYENDA")
        ):
            continue
        for abp_a, abp_b, abp__words in abp_columns[:abp_index]:
            abp_cell = abp_image[
                int(abp_top) + 3 : int(abp_bottom) - 2, int(abp_a) + 3 : int(abp_b) - 2
            ]
            abp_symbol = abp__trim(abp_cell)
            if abp_symbol is not None:
                abp_out.append(abpSymbolTemplate(abp_kind, abp__label(abp_label), abp_symbol))
    return abp_out


def abp__label(abp_text: str) -> str:
    return " ".join(abp_text.split()).capitalize()


def abp__merged(abp_values: list[float], abp_gap: float) -> list[float]:
    abp_out: list[float] = []
    for abp_v in abp_values:
        if not abp_out or abp_v - abp_out[-1] > abp_gap:
            abp_out.append(abp_v)
    return abp_out


def abp__trim(abp_cell: abpRGBImage) -> abpRGBImage | None:
    abp_ink = (abp_cell.min(axis=2) < 235).astype(np.uint8)
    abp_rows, abp_cols = np.nonzero(abp_ink)
    if len(abp_rows) < 30:
        return None
    abp_part = abp_cell[abp_rows.min() : abp_rows.max() + 1, abp_cols.min() : abp_cols.max() + 1]
    return abp_part if min(abp_part.shape[:2]) >= 10 else None


@functools.lru_cache(maxsize=1)
def abp_catalog() -> tuple[abpSymbolTemplate, ...]:
    abp_out: list[abpSymbolTemplate] = []
    with np.load(
        Path(abp_resources.__file__).parent / "abp_symbols" / "abp_simbolos.npz"
    ) as abp_data:
        for abp_k, (abp_kind, abp_name) in enumerate(
            zip(abp_data["tipo"], abp_data["nombre"], strict=True)
        ):
            abp_image = np.ascontiguousarray(abp_data[f"dibujo_{abp_k}"], np.uint8)
            abp_out.append(abpSymbolTemplate(abpSignKind(str(abp_kind)), str(abp_name), abp_image))
    return tuple(abp_out)


def abp_find_signs(
    abp_image: abpRGBImage,
    abp_vector: abpVectorPlan | None,
    abp_blocks: Sequence[abpPlacedBlock] = (),
) -> abpFoundSigns:
    if abp_vector is None:
        return abpFoundSigns()
    abp_legends = abp_legend_boxes(abp_vector)
    abp_templates = abp_read_legend(abp_vector, abp_image)
    abp_own = bool(abp_templates)
    if not abp_own:
        abp_templates = abp_catalog()
    abp_size = abp__typical_size(abp_templates, abp_vector)
    abp_factor = abp__plan_factor(abp_image, abp_templates, abp_size, abp_legends)
    if abp_factor is None and not abp_own:
        abp_keyed = any(abp_kind_of(abp_t.abp_text) is not None for abp_t in abp_vector.abp_texts)
        if not abp_keyed:
            return abpFoundSigns((), tuple(abp__meeting_zones(abp_image, abp_vector.abp_texts)))
    abp_factor = abp_factor or 1.0
    abp_templates = tuple(abp_t.abp_resized(abp_factor) for abp_t in abp_templates)
    abp_size *= abp_factor
    if abp_own:
        abp_known_kinds = {abp_t.abp_kind for abp_t in abp_templates}
        abp_templates += tuple(
            abp_t.abp_resized(
                abp_size / math.sqrt(abp_t.abp_image.shape[0] * abp_t.abp_image.shape[1])
            )
            for abp_t in abp_catalog()
            if abp_t.abp_kind not in abp_known_kinds
        )
    abp_signs: list[abpSign] = []
    abp_in_plan = [
        abp_t
        for abp_t in abp_vector.abp_texts
        if not any(abp__in_box((abp_t.abp_x, abp_t.abp_y), abp_b, 4) for abp_b in abp_legends)
    ]
    abp_zones = abp__meeting_zones(abp_image, abp_in_plan)
    abp_known = abp__from_blocks(abp_image, abp_vector, abp_blocks, abp_legends, abp_templates)
    for abp_blob in abp__blobs(abp_image, abp_size):
        if any(abp__in_box(abp_blob.abp_center, abp_box, 4) for abp_box in abp_legends):
            continue
        if any(
            abp__in_box(abp_blob.abp_center, abp_z, 6)
            for abp_z in (abp__bounds(abp_zone.abp_area) for abp_zone in abp_zones)
        ):
            continue
        abp_signs.extend(
            abp__identify(
                abp_image,
                abp_blob,
                abp_templates,
                abp_vector.abp_texts,
                abp_size,
                abp_sure=not abp_own,
            )
        )
    if abp_known:
        abp_spots = [
            abp_b
            for abp_b in abp_blocks
            if any(abp__at(abp_b, abp_k.abp_position) for abp_k in abp_known)
        ]
        abp_signs = [
            abp_s
            for abp_s in abp_signs
            if not any(
                abp__covers(abp_b, abp_s.abp_position, 0.2 * abp_size) for abp_b in abp_spots
            )
        ]
    abp_signs = [*abp_known, *abp__unique(abp_signs, abp_size)]
    abp_signs += abp__split_signs(abp_in_plan, abp_signs, abp_image, abp_templates, abp_size)
    return abpFoundSigns(tuple(abp_signs), tuple(abp_zones))


@dataclass(frozen=True, eq=False, slots=True)
class abp__Blob:
    abp_center: tuple[float, float]
    abp_size: tuple[float, float]
    abp_angle: float
    abp_corners: npt.NDArray[np.float32]


def abp__typical_size(
    abp_templates: Sequence[abpSymbolTemplate], abp_vector: abpVectorPlan
) -> float:
    if abp_templates:
        abp_sides = [
            math.sqrt(abp_t.abp_image.shape[0] * abp_t.abp_image.shape[1])
            for abp_t in abp_templates
        ]
        return float(np.median(abp_sides))
    abp_heights = [
        abp_t.abp_size for abp_t in abp_vector.abp_texts if abp_kind_of(abp_t.abp_text) is not None
    ]
    return float(np.median(abp_heights)) * 5 if abp_heights else 50.0


def abp__plan_factor(
    abp_image: abpRGBImage,
    abp_templates: Sequence[abpSymbolTemplate],
    abp_size: float,
    abp_legends: Sequence[abpBox],
) -> float | None:
    abp_votes: dict[int, float] = {}
    abp_counts: dict[int, int] = {}
    abp_looks = [
        (
            abp_t.abp_image.shape[1],
            abp_t.abp_image.shape[0],
            abp__hues(abp__small(abp_t.abp_image)),
            abp__small(abp_t.abp_image),
        )
        for abp_t in abp_templates
    ]
    for abp_blob in abp__blobs(abp_image, 0.45 * abp_size):
        if any(abp__in_box(abp_blob.abp_center, abp_box, 4) for abp_box in abp_legends):
            continue
        abp_patch, abp__back = abp__upright(abp_image, abp_blob, 0.0)
        if min(abp_patch.shape[:2]) < 6:
            continue
        abp_hues = abp__hues(abp__small(abp_patch))
        for abp_w, abp_h, abp_colors, abp_image_of in abp_looks:
            abp_gap = float(np.abs(abp_hues - abp_colors).sum())
            abp_ratio = max(abp_blob.abp_size) / max(min(abp_blob.abp_size), 1.0)
            if (
                abp_gap > 0.3
                or abs(math.log(abp_ratio * min(abp_w, abp_h) / max(abp_w, abp_h))) > 0.15
            ):
                continue
            abp_score = abp__likeness(abp_patch, abp_image_of)
            if abp_score < 0.55:
                continue
            abp_scale = math.log(
                math.sqrt(abp_blob.abp_size[0] * abp_blob.abp_size[1] / (abp_w * abp_h))
            )
            abp_key = round(abp_scale / abp_FACTOR_STEP)
            abp_votes[abp_key] = abp_votes.get(abp_key, 0.0) + abp_score
            abp_counts[abp_key] = abp_counts.get(abp_key, 0) + 1
    if not abp_votes:
        return None

    def abp_total(abp_key: int) -> float:
        return sum(
            abp_votes.get(abp_key + abp_d, 0.0) * (1.0 if abp_d == 0 else 0.6)
            for abp_d in (-1, 0, 1)
        )

    abp_best = max(abp_votes, key=abp_total)
    return (
        math.exp(abp_best * abp_FACTOR_STEP)
        if abp_counts[abp_best] >= abp_MIN_FACTOR_VOTES
        else None
    )


def abp__likeness(abp_patch: abpRGBImage, abp_template: abpRGBImage) -> float:
    abp_best = 0.0
    abp_wide = abp_patch.shape[1] >= abp_patch.shape[0]
    for abp_turn in range(4):
        abp_turned = np.ascontiguousarray(np.rot90(abp_template, abp_turn))
        abp_square = abs(abp_turned.shape[1] - abp_turned.shape[0]) < 0.12 * max(
            abp_turned.shape[:2]
        )
        if not abp_square and (abp_turned.shape[1] >= abp_turned.shape[0]) != abp_wide:
            continue
        abp_size = (abp_turned.shape[1], abp_turned.shape[0])
        abp_sample = cv2.resize(abp_patch, abp_size, interpolation=cv2.INTER_AREA)
        abp_best = max(
            abp_best, float(cv2.matchTemplate(abp_sample, abp_turned, cv2.TM_CCOEFF_NORMED).max())
        )
    return abp_best


def abp__color_mask(abp_image: abpRGBImage) -> abpMask:
    abp_high, abp_low = (
        abp_image.max(axis=2).astype(np.int16),
        abp_image.min(axis=2).astype(np.int16),
    )
    abp_colored = (abp_high - abp_low) >= 28
    abp_pure = np.abs(abp_image.astype(np.int16) - np.array(abp_ROUTE_GREEN)).max(axis=2) <= 12
    return np.asarray(abp_colored & ~abp_pure, np.uint8)


def abp__blobs(abp_image: abpRGBImage, abp_size: float) -> list[abp__Blob]:
    abp_mask = abp__color_mask(abp_image)
    abp_joined = cv2.morphologyEx(abp_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    abp_contours, _ = cv2.findContours(abp_joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    abp_out: list[abp__Blob] = []
    for abp_contour in abp_contours:
        (abp_cx, abp_cy), (abp_w, abp_h), abp_angle = cv2.minAreaRect(abp_contour)
        abp_short, abp_long_side = min(abp_w, abp_h), max(abp_w, abp_h)
        if (
            abp_short < 0.3 * abp_size
            or abp_long_side > 6 * abp_size
            or abp_long_side > 5.5 * abp_short
        ):
            continue
        abp_corners = np.asarray(
            cv2.boxPoints(((abp_cx, abp_cy), (abp_w, abp_h), abp_angle)), np.float32
        )
        abp_out.append(
            abp__Blob(
                (float(abp_cx), float(abp_cy)),
                (float(abp_w), float(abp_h)),
                float(abp_angle),
                abp_corners,
            )
        )
    return abp_out


def abp__identify(
    abp_image: abpRGBImage,
    abp_blob: abp__Blob,
    abp_templates: Sequence[abpSymbolTemplate],
    abp_texts: Collection[abpVectorText],
    abp_size: float,
    *,
    abp_sure: bool = False,
) -> list[abpSign]:
    abp_patch, abp_to_page = abp__upright(abp_image, abp_blob, abp_pad=0.15 * abp_size)
    abp_needed, abp_hue_gap = (
        (abp_SURE_MATCH, abp_SURE_HUE_GAP) if abp_sure else (abp_MIN_MATCH, abp_MAX_HUE_GAP)
    )
    abp_matches = abp__match_templates(abp_patch, abp_templates, abp_needed, abp_hue_gap)
    abp_inside = [
        abp_t for abp_t in abp_texts if abp__inside_patch(abp_t, abp_blob, 0.12 * abp_size)
    ]
    abp_by_text = abp_kind_of(
        " ".join(abp_t.abp_text for abp_t in sorted(abp_inside, key=lambda abp_t: -abp_t.abp_size))
    )
    abp_single = max(abp_blob.abp_size) < 1.9 * abp_size
    if not abp_matches:
        if float(abp__color_mask(abp_patch).mean()) < abp_MIN_FILL:
            return []
        abp_kind = abp_by_text or (abp__by_color(abp_patch) if abp_single else None)
        return (
            [] if abp_kind is None else [abp__sign(abp_kind, abp_blob.abp_center, "", abp_inside)]
        )
    abp_out: list[abpSign] = []
    for abp_m in abp_matches:
        abp_center = abp_to_page(abp_m.abp_x, abp_m.abp_y)
        abp_kind = (
            abp_by_text if abp_single and abp_by_text is not None else abp_m.abp_template.abp_kind
        )
        if (
            abp_kind is abpSignKind.abp_EXIT
            and abp_m.abp_template.abp_kind is abpSignKind.abp_DIRECTION
        ):
            abp_kind = abpSignKind.abp_DIRECTION
        abp_near = [
            abp_t
            for abp_t in abp_inside
            if math.dist((abp_t.abp_x, abp_t.abp_y), abp_center) < abp_size
        ]
        abp_sign = abp__sign(abp_kind, abp_center, abp_m.abp_template.abp_label, abp_near)
        if (
            abp_kind is abpSignKind.abp_DIRECTION
            and abp_m.abp_template.abp_kind is abpSignKind.abp_DIRECTION
        ):
            abp_drawn = abp__drawn_arrow(abp_patch) if abp_single else None
            abp_angle = (
                abp__arrow_angle(abp_patch, abp_m) if abp_drawn is None else abp_drawn
            ) + abp_blob.abp_angle
            abp_sign = abpSign(abp_kind, abp_sign.abp_position, round(abp_angle / 5) * 5.0 % 360)
        elif abp_kind is abpSignKind.abp_EXIT:
            abp_hidden = abp__hidden_arrow(abp_patch, (abp_m.abp_x, abp_m.abp_y), abp_size)
            if abp_hidden is not None:
                abp_angle = abp_hidden + abp_blob.abp_angle
                abp_sign = abpSign(
                    abpSignKind.abp_DIRECTION,
                    abp_sign.abp_position,
                    round(abp_angle / 5) * 5.0 % 360,
                )
        abp_out.append(abp_sign)
        if abp_single:
            break
    return abp_out


def abp__sign(
    abp_kind: abpSignKind,
    abp_center: tuple[float, float],
    abp_label: str,
    abp_texts: Sequence[abpVectorText],
) -> abpSign:
    abp_text = abp_label if abp_kind in abp_GENERIC else ""
    if abp_kind is abpSignKind.abp_CAPACITY:
        abp_numbers = [
            abp_t.abp_text.strip() for abp_t in abp_texts if abp_t.abp_text.strip().isdigit()
        ]
        abp_text = abp_numbers[0] if abp_numbers else ""
    return abpSign(abp_kind, abpPoint(*abp_center), 0.0, abp_text)


abp_SPLIT_KINDS = frozenset(
    {
        abpSignKind.abp_EXIT,
        abpSignKind.abp_SAFE_ZONE,
        abpSignKind.abp_FIRST_AID,
        abpSignKind.abp_EXTINGUISHER,
        abpSignKind.abp_ELECTRIC_RISK,
    }
)
abp_GENERIC = frozenset(
    {abpSignKind.abp_PROHIBITION, abpSignKind.abp_MANDATORY, abpSignKind.abp_WARNING}
)


def abp__upright(
    abp_image: abpRGBImage, abp_blob: abp__Blob, abp_pad: float
) -> tuple[abpRGBImage, Callable[[float, float], tuple[float, float]]]:
    abp_w, abp_h = abp_blob.abp_size[0] + 2 * abp_pad, abp_blob.abp_size[1] + 2 * abp_pad
    abp_matrix = cv2.getRotationMatrix2D(abp_blob.abp_center, abp_blob.abp_angle, 1.0)
    abp_matrix[0, 2] += abp_w / 2 - abp_blob.abp_center[0]
    abp_matrix[1, 2] += abp_h / 2 - abp_blob.abp_center[1]
    abp_patch = cv2.warpAffine(
        abp_image,
        abp_matrix,
        (max(1, int(abp_w)), max(1, int(abp_h))),
        flags=cv2.INTER_LINEAR,
        borderValue=(255, 255, 255),
    )
    abp_back = cv2.invertAffineTransform(abp_matrix)

    def abp_to_page(abp_x: float, abp_y: float) -> tuple[float, float]:
        abp_px, abp_py = abp_back @ np.array([abp_x, abp_y, 1.0])
        return float(abp_px), float(abp_py)

    return np.asarray(abp_patch, np.uint8), abp_to_page


def abp__match_templates(
    abp_patch: abpRGBImage,
    abp_templates: Sequence[abpSymbolTemplate],
    abp_needed: float = abp_MIN_MATCH,
    abp_hue_gap: float = 0.45,
) -> list[abp__Match]:
    abp_found: list[abp__Match] = []
    abp_half = abp__small(abp_patch)
    abp_inked = np.asarray(cv2.integral(abp__color_mask(abp_half)))
    abp_whole = abp__hues(abp_half)
    abp_areas = [abp_t.abp_image.shape[0] * abp_t.abp_image.shape[1] / 4 for abp_t in abp_templates]
    abp_usual = 0.9 * float(np.median(abp_areas)) if abp_areas else 1.0
    for abp_template in abp_templates:
        abp_base = abp__small(abp_template.abp_image)
        abp_ink = float(abp__color_mask(abp_template.abp_image).mean())
        abp_colors = abp__hues(abp_base)
        abp_main = int(np.argmax(abp_colors[:4]))
        if abp_colors[abp_main] > 0.1 and abp_whole[abp_main] < 0.1 * abp_colors[abp_main]:
            continue
        for abp_turn in range(4):
            abp_turned = np.ascontiguousarray(np.rot90(abp_base, abp_turn))
            abp_small = (
                (abp_SMALL_SCALE,) if abp_template.abp_kind is abpSignKind.abp_CAPACITY else ()
            )
            for abp_scale in (*abp_small, *abp_SCALES):
                abp_w, abp_h = (
                    int(abp_turned.shape[1] * abp_scale),
                    int(abp_turned.shape[0] * abp_scale),
                )
                if abp_w < 6 or abp_h < 6 or abp_w > abp_half.shape[1] or abp_h > abp_half.shape[0]:
                    continue
                abp_probe = cv2.resize(abp_turned, (abp_w, abp_h), interpolation=cv2.INTER_AREA)
                abp_response = cv2.matchTemplate(abp_half, abp_probe, cv2.TM_CCOEFF_NORMED)
                abp__low, abp_score, abp__where, (abp_x, abp_y) = cv2.minMaxLoc(abp_response)
                if abp_score < (abp_needed if abp_ink > abp_THIN_INK else abp_needed + 0.25):
                    continue
                if (
                    np.abs(
                        abp__hues(abp_half[abp_y : abp_y + abp_h, abp_x : abp_x + abp_w])
                        - abp_colors
                    ).sum()
                    > abp_hue_gap
                ):
                    continue
                if abp__ink(abp_inked, abp_x, abp_y, abp_w, abp_h) < 0.6 * abp_ink:
                    continue
                abp_cover = min((abp_w * abp_h) / (abp_half.shape[0] * abp_half.shape[1]), 1.0)
                abp_center = (2.0 * (abp_x + abp_w / 2), 2.0 * (abp_y + abp_h / 2))
                abp_whole_sign = min(1.0, abp_w * abp_h / abp_usual)
                abp_value = (
                    float(abp_score) + abp_COVER_BONUS * abp_cover + abp_AREA_BONUS * abp_whole_sign
                )
                abp_found.append(
                    abp__Match(*abp_center, abp_template, abp_value, abp_turn, abp_scale)
                )
    abp_found.sort(key=lambda abp_f: -abp_f.abp_score)
    abp_out: list[abp__Match] = []
    for abp_f in abp_found:
        if not any(abp__overlap(abp_f, abp_o) > abp_MAX_OVERLAP for abp_o in abp_out):
            abp_out.append(abp_f)
    return abp_out[:abp_MAX_PER_BLOB]


def abp__ink(
    abp_integral: npt.NDArray[np.generic], abp_x: int, abp_y: int, abp_w: int, abp_h: int
) -> float:
    abp_i = abp_integral
    abp_total = (
        int(abp_i[abp_y + abp_h, abp_x + abp_w])
        - int(abp_i[abp_y, abp_x + abp_w])
        - int(abp_i[abp_y + abp_h, abp_x])
        + int(abp_i[abp_y, abp_x])
    )
    return abp_total / max(abp_w * abp_h, 1)


def abp__overlap(abp_a: abp__Match, abp_b: abp__Match) -> float:
    def abp_box(abp_m: abp__Match) -> abpBox:
        abp_h, abp_w = abp_m.abp_template.abp_image.shape[:2]
        if abp_m.abp_turn % 2:
            abp_w, abp_h = abp_h, abp_w
        abp_w, abp_h = abp_w * abp_m.abp_scale, abp_h * abp_m.abp_scale
        return (
            abp_m.abp_x - abp_w / 2,
            abp_m.abp_y - abp_h / 2,
            abp_m.abp_x + abp_w / 2,
            abp_m.abp_y + abp_h / 2,
        )

    abp_p, abp_q = abp_box(abp_a), abp_box(abp_b)
    abp_w, abp_h = (
        min(abp_p[2], abp_q[2]) - max(abp_p[0], abp_q[0]),
        min(abp_p[3], abp_q[3]) - max(abp_p[1], abp_q[1]),
    )
    if abp_w <= 0 or abp_h <= 0:
        return 0.0
    abp_areas = [(abp_r[2] - abp_r[0]) * (abp_r[3] - abp_r[1]) for abp_r in (abp_p, abp_q)]
    return float(abp_w * abp_h / max(min(abp_areas), 1e-9))


def abp__from_blocks(
    abp_image: abpRGBImage,
    abp_vector: abpVectorPlan,
    abp_blocks: Sequence[abpPlacedBlock],
    abp_legends: Sequence[abpBox],
    abp_templates: Sequence[abpSymbolTemplate],
) -> list[abpSign]:
    abp_meaning: dict[str, tuple[abpSignKind, str]] = {}
    for abp_block in abp_blocks:
        for abp_box in abp_legends:
            if abp__in_box((abp_block.abp_x, abp_block.abp_y), abp_box, 0):
                abp_row = abp__legend_row(abp_vector, abp_box, abp_block)
                abp_kind = abp_kind_of(abp_row)
                if abp_kind is not None and "RUTA" not in abp_plain(abp_row):
                    abp_meaning.setdefault(abp_block.abp_name, (abp_kind, abp__label(abp_row)))
    for abp_block in abp_blocks:
        abp_named = abp__kind_of_block(abp_block.abp_name)
        if abp_named is not None:
            abp_meaning.setdefault(abp_block.abp_name, (abp_named, ""))
    abp_sizes = [
        math.sqrt(abp_b.abp_width * abp_b.abp_height)
        for abp_b in abp_blocks
        if abp_b.abp_name in abp_meaning
    ]
    abp_typical = float(np.median(abp_sizes)) if abp_sizes else 0.0
    for abp_name in {abp_b.abp_name for abp_b in abp_blocks if abp_b.abp_name not in abp_meaning}:
        abp_same = [abp_b for abp_b in abp_blocks if abp_b.abp_name == abp_name]
        if not all(
            0.6 * abp_typical < min(abp_b.abp_width, abp_b.abp_height)
            and abp_b.abp_width < 6 * abp_typical
            for abp_b in abp_same
        ):
            continue
        abp_written = {abp__written(abp_image, abp_b, abp_vector.abp_texts) for abp_b in abp_same}
        if len(abp_written) == 1 and None not in abp_written:
            abp_meaning[abp_name] = (next(abp_k for abp_k in abp_written if abp_k is not None), "")
    abp_out: list[abpSign] = []
    abp_arrows = [abp_t for abp_t in abp_templates if abp_t.abp_kind is abpSignKind.abp_DIRECTION]
    for abp_block in abp_blocks:
        if abp_block.abp_name not in abp_meaning or any(
            abp__in_box((abp_block.abp_x, abp_block.abp_y), abp_b, 4) for abp_b in abp_legends
        ):
            continue
        if (
            abp_block.abp_x > 0.97 * abp_vector.abp_width
            or abp_block.abp_x < 0.01 * abp_vector.abp_width
        ):
            continue
        abp_kind, abp_label = abp_meaning[abp_block.abp_name]
        abp_place = abpPoint(abp_block.abp_x, abp_block.abp_y)
        if any(
            abp_o.abp_kind is abp_kind
            and abp_o.abp_position.abp_distance_to(abp_place) < 0.4 * abp_block.abp_width
            for abp_o in abp_out
        ):
            continue
        abp_angle = 0.0
        if abp_kind is abpSignKind.abp_DIRECTION and abp_arrows:
            abp_angle = abp__block_arrow(abp_image, abp_block, abp_arrows)
        abp_out.append(
            abpSign(abp_kind, abp_place, abp_angle, abp_label if abp_kind in abp_GENERIC else "")
        )
    return abp_out


def abp__at(abp_block: abpPlacedBlock, abp_p: abpPoint) -> bool:
    return abs(abp_block.abp_x - abp_p.abp_x) < 0.5 and abs(abp_block.abp_y - abp_p.abp_y) < 0.5


def abp__covers(abp_block: abpPlacedBlock, abp_p: abpPoint, abp_pad: float) -> bool:
    abp_c, abp_s = (
        math.cos(math.radians(abp_block.abp_angle_deg)),
        math.sin(math.radians(abp_block.abp_angle_deg)),
    )
    abp_dx, abp_dy = abp_p.abp_x - abp_block.abp_x, abp_p.abp_y - abp_block.abp_y
    abp_u, abp_v = abp_dx * abp_c + abp_dy * abp_s, -abp_dx * abp_s + abp_dy * abp_c
    return (
        abs(abp_u) <= abp_block.abp_width / 2 + abp_pad
        and abs(abp_v) <= abp_block.abp_height / 2 + abp_pad
    )


def abp__kind_of_block(abp_name: str) -> abpSignKind | None:
    abp_clean = abp_plain(abp_name.replace(".", " ").replace("_", " ").replace("-", " "))
    for abp_kind, abp_words in abp_BLOCK_WORDS:
        if any(abp_word in abp_clean for abp_word in abp_words):
            return abp_kind
    return None


def abp__written(
    abp_image: abpRGBImage, abp_block: abpPlacedBlock, abp_texts: Collection[abpVectorText]
) -> abpSignKind | None:
    abp_corners = np.zeros((4, 2), np.float32)
    abp_blob = abp__Blob(
        (abp_block.abp_x, abp_block.abp_y),
        (abp_block.abp_width, abp_block.abp_height),
        abp_block.abp_angle_deg,
        abp_corners,
    )
    abp_inside = [abp_t for abp_t in abp_texts if abp__inside_patch(abp_t, abp_blob, 0.0)]
    abp_kind = abp_kind_of(" ".join(abp_t.abp_text for abp_t in abp_inside))
    if abp_kind is None:
        return None
    abp_patch, abp__back = abp__upright(abp_image, abp_blob, 0.0)
    return abp_kind if abp_patch.size and float(abp__color_mask(abp_patch).mean()) > 0.6 else None


def abp__legend_row(abp_vector: abpVectorPlan, abp_box: abpBox, abp_block: abpPlacedBlock) -> str:
    abp_s = abp_vector.abp_segments
    abp_left, abp_right = np.minimum(abp_s[:, 0], abp_s[:, 2]), np.maximum(abp_s[:, 0], abp_s[:, 2])
    abp_lines = (
        (np.abs(abp_s[:, 1] - abp_s[:, 3]) < 1.0)
        & (abp_left < abp_block.abp_x)
        & (abp_right > abp_block.abp_x)
    )
    abp_lines &= (abp_right - abp_left) > 0.5 * (abp_box[2] - abp_box[0])
    abp_ys = abp_s[abp_lines, 1]
    abp_top = (
        float(abp_ys[abp_ys < abp_block.abp_y].max())
        if (abp_ys < abp_block.abp_y).any()
        else abp_box[1]
    )
    abp_bottom = (
        float(abp_ys[abp_ys > abp_block.abp_y].min())
        if (abp_ys > abp_block.abp_y).any()
        else abp_box[3]
    )
    abp_words = [
        abp_t
        for abp_t in abp_vector.abp_texts
        if abp_top < abp_t.abp_y < abp_bottom
        and abp_block.abp_x + 0.3 * abp_block.abp_width < abp_t.abp_x < abp_box[2]
        and len(abp_t.abp_text) > 2
    ]
    return " ".join(
        abp_t.abp_text.strip() for abp_t in sorted(abp_words, key=lambda abp_t: abp_t.abp_y)
    )


def abp__block_arrow(
    abp_image: abpRGBImage, abp_block: abpPlacedBlock, abp_arrows: Sequence[abpSymbolTemplate]
) -> float:
    abp_corners = np.zeros((4, 2), np.float32)
    abp_blob = abp__Blob(
        (abp_block.abp_x, abp_block.abp_y),
        (abp_block.abp_width, abp_block.abp_height),
        abp_block.abp_angle_deg,
        abp_corners,
    )
    abp_patch, abp__back = abp__upright(
        abp_image, abp_blob, 0.1 * min(abp_block.abp_width, abp_block.abp_height)
    )
    abp_drawn = abp__drawn_arrow(abp_patch)
    if abp_drawn is not None:
        return round((abp_drawn + abp_block.abp_angle_deg) / 5) * 5.0 % 360
    abp_matches = abp__match_templates(abp_patch, abp_arrows, 0.3)
    if not abp_matches:
        return round(abp_block.abp_angle_deg / 5) * 5.0 % 360
    return (
        round((abp__arrow_angle(abp_patch, abp_matches[0]) + abp_block.abp_angle_deg) / 5)
        * 5.0
        % 360
    )


def abp__hues(abp_image: abpRGBImage) -> npt.NDArray[np.float64]:
    abp_hsv = cv2.cvtColor(np.ascontiguousarray(abp_image), cv2.COLOR_RGB2HSV)
    abp_hue, abp_saturation, abp_value = abp_hsv[:, :, 0], abp_hsv[:, :, 1], abp_hsv[:, :, 2]
    abp_strong = (abp_saturation > 60) & (abp_value > 60)
    abp_parts = (
        abp_strong & ((abp_hue < 10) | (abp_hue > 170)),
        abp_strong & (abp_hue >= 15) & (abp_hue < 37),
        abp_strong & (abp_hue >= 40) & (abp_hue < 88),
        abp_strong & (abp_hue >= 95) & (abp_hue < 135),
        abp_value < 70,
    )
    return np.array([float(abp_p.mean()) for abp_p in abp_parts])


def abp__arrow_angle(abp_patch: abpRGBImage, abp_match: abp__Match) -> float:
    abp_template = abp_match.abp_template.abp_image
    abp_h, abp_w = abp_template.shape[:2]
    abp_side = min(abp_h, abp_w)
    abp_along_y = abp_h > abp_w
    abp_top, abp_bottom = abp_template[:abp_side, :abp_side], abp_template[-abp_side:, -abp_side:]
    abp_first = abp__arrow_mass(abp_top) >= abp__arrow_mass(abp_bottom)
    abp_square = abp_top if abp_first else abp_bottom
    abp_shift = (max(abp_h, abp_w) - abp_side) / 2 * (-1 if abp_first else 1)
    abp_dx, abp_dy = (0.0, abp_shift) if abp_along_y else (abp_shift, 0.0)
    for _ in range(abp_match.abp_turn):
        abp_dx, abp_dy = abp_dy, -abp_dx
    abp_cx, abp_cy = (
        abp_match.abp_x + abp_dx * abp_match.abp_scale,
        abp_match.abp_y + abp_dy * abp_match.abp_scale,
    )
    abp_size = max(6, round(abp_side * abp_match.abp_scale))
    abp_reach = 0.5 * abp_size + 0.25 * abp_size
    abp_x0, abp_y0 = max(0, int(abp_cx - abp_reach)), max(0, int(abp_cy - abp_reach))
    abp_region = abp_patch[abp_y0 : int(abp_cy + abp_reach), abp_x0 : int(abp_cx + abp_reach)]
    abp_base = abp__mass_angle(abp_square)
    if min(abp_region.shape[:2]) < abp_size:
        return abp_base - 90.0 * abp_match.abp_turn
    abp_probe = np.asarray(
        cv2.resize(abp_square, (abp_size, abp_size), interpolation=cv2.INTER_AREA), np.uint8
    )
    abp_where = abp__greenness(abp_region)
    abp_scores = [
        float(
            cv2.matchTemplate(
                abp_where,
                abp__greenness(np.ascontiguousarray(np.rot90(abp_probe, abp_k))),
                cv2.TM_CCOEFF_NORMED,
            ).max()
        )
        for abp_k in range(4)
    ]
    return abp_base - 90.0 * int(np.argmax(abp_scores))


def abp__hidden_arrow(
    abp_patch: abpRGBImage, abp_center: tuple[float, float], abp_size: float
) -> float | None:
    abp_r = int(0.75 * abp_size)
    abp_x, abp_y = int(abp_center[0]), int(abp_center[1])
    abp_area = np.ascontiguousarray(
        abp_patch[max(0, abp_y - abp_r) : abp_y + abp_r, max(0, abp_x - abp_r) : abp_x + abp_r]
    )
    if min(abp_area.shape[:2]) < 12:
        return None
    abp_pale = (abp_area.min(axis=2) > 170) & (abp_area[:, :, 2] < 235) & (abp_area[:, :, 1] > 235)
    abp_solid = abp__arrow_mask(abp_area)
    abp_share = float(abp_solid.sum()) / max(float(abp_pale.sum()), 1.0)
    if float(abp_pale.mean()) < 0.15 or not 0.1 < abp_share < 0.9:
        return None
    return abp__drawn_arrow(abp_area)


def abp__drawn_arrow(abp_patch: abpRGBImage) -> float | None:
    abp_rows, abp_cols = np.nonzero(abp__arrow_mask(abp_patch))
    if len(abp_rows) < 20:
        return None
    abp_w, abp_h = int(np.ptp(abp_cols)) + 1, int(np.ptp(abp_rows)) + 1
    if not 0.2 * min(abp_patch.shape[:2]) < max(abp_w, abp_h) or max(abp_w, abp_h) > 2.2 * min(
        abp_w, abp_h
    ):
        return None
    if len(abp_rows) > 0.75 * abp_w * abp_h:
        return None
    abp_dx = (float(abp_cols.mean()) - (abp_cols.min() + abp_cols.max()) / 2) / abp_w
    abp_dy = (float(abp_rows.mean()) - (abp_rows.min() + abp_rows.max()) / 2) / abp_h
    if max(abs(abp_dx), abs(abp_dy)) < 0.04 or abs(abs(abp_dx) - abs(abp_dy)) < 0.03:
        return None
    return round(math.degrees(math.atan2(abp_dy, abp_dx)) / 90) * 90.0


def abp__greenness(abp_image: abpRGBImage) -> abpGrayF:
    abp_x = abp_image.astype(np.float64)
    abp_pure = np.abs(abp_x - np.array(abp_ROUTE_GREEN)).max(axis=2) <= 12
    abp_green = abp_x[:, :, 1] - np.maximum(abp_x[:, :, 0], abp_x[:, :, 2])
    abp_green[abp_pure] = 0.0
    return np.asarray(np.clip(abp_green, 0.0, 255.0), np.float32)


def abp__arrow_mask(abp_square: abpRGBImage) -> npt.NDArray[np.bool_]:
    abp_x = abp_square.astype(np.int16)
    abp_green = (abp_x[:, :, 1] - np.maximum(abp_x[:, :, 0], abp_x[:, :, 2])) > 45
    abp_count, abp_labels, abp_stats, _ = cv2.connectedComponentsWithStats(
        abp_green.astype(np.uint8)
    )
    if abp_count <= 1:
        return np.zeros(abp_green.shape, np.bool_)
    abp_box = np.maximum(abp_stats[1:, cv2.CC_STAT_WIDTH] * abp_stats[1:, cv2.CC_STAT_HEIGHT], 1)
    abp_score = abp_stats[1:, cv2.CC_STAT_AREA] / abp_box * np.sqrt(abp_stats[1:, cv2.CC_STAT_AREA])
    return np.asarray(abp_labels == int(np.argmax(abp_score)) + 1, np.bool_)


def abp__arrow_mass(abp_square: abpRGBImage) -> float:
    return float(abp__arrow_mask(abp_square).sum())


def abp__mass_angle(abp_square: abpRGBImage) -> float:
    abp_rows, abp_cols = np.nonzero(abp__arrow_mask(abp_square))
    if len(abp_rows) < 4:
        return 180.0
    abp_dx = float(abp_cols.mean()) - (abp_cols.min() + abp_cols.max()) / 2
    abp_dy = float(abp_rows.mean()) - (abp_rows.min() + abp_rows.max()) / 2
    return round(math.degrees(math.atan2(abp_dy, abp_dx)) / 90) * 90.0


def abp__small(abp_image: abpRGBImage) -> abpRGBImage:
    abp_h, abp_w = abp_image.shape[:2]
    abp_size = (max(1, abp_w // 2), max(1, abp_h // 2))
    return np.asarray(cv2.resize(abp_image, abp_size, interpolation=cv2.INTER_AREA), np.uint8)


def abp__by_color(abp_patch: abpRGBImage) -> abpSignKind | None:
    abp_red, abp_yellow, abp_green, abp_blue, abp_black = abp__hues(abp_patch).tolist()
    if abp_blue > 0.25:
        return abpSignKind.abp_MANDATORY
    if abp_red > 0.5:
        return abpSignKind.abp_EXTINGUISHER
    if abp_yellow > 0.35 and abp_black > 0.05:
        return abpSignKind.abp_WARNING
    if abp_red > 0.12 and abp_black > 0.08:
        return abpSignKind.abp_PROHIBITION
    return abpSignKind.abp_EXIT if abp_green > 0.6 else None


def abp__meeting_zones(
    abp_image: abpRGBImage, abp_texts: Sequence[abpVectorText]
) -> list[abpSafeZone]:
    abp_out: list[abpSafeZone] = []
    for abp_t in abp_texts:
        if "REUNION" not in abp_plain(abp_t.abp_text):
            continue
        abp_r = int(14 * abp_t.abp_size)
        abp_x0, abp_y0 = max(0, int(abp_t.abp_x) - abp_r), max(0, int(abp_t.abp_y) - abp_r)
        abp_patch = abp_image[abp_y0 : int(abp_t.abp_y) + abp_r, abp_x0 : int(abp_t.abp_x) + abp_r]
        if abp_patch.size == 0:
            continue
        abp_hsv = cv2.cvtColor(np.ascontiguousarray(abp_patch), cv2.COLOR_RGB2HSV)
        abp_yellow = (abp_hsv[:, :, 1] > 110) & (abp_hsv[:, :, 0] > 18) & (abp_hsv[:, :, 0] < 34)
        abp_joined = cv2.morphologyEx(
            abp_yellow.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8)
        )
        abp_contours, _ = cv2.findContours(abp_joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for abp_contour in abp_contours:
            (abp_cx, abp_cy), abp_radius = cv2.minEnclosingCircle(abp_contour)
            abp_round_enough = (
                cv2.contourArea(abp_contour) > 0.6 * math.pi * abp_radius * abp_radius
            )
            abp_near = (
                math.dist((abp_cx + abp_x0, abp_cy + abp_y0), (abp_t.abp_x, abp_t.abp_y))
                < abp_radius
            )
            if abp_round_enough and abp_near and abp_radius > 2 * abp_t.abp_size:
                abp_circle = tuple(
                    abpPoint(
                        abp_cx + abp_x0 + abp_radius * math.cos(abp_a),
                        abp_cy + abp_y0 + abp_radius * math.sin(abp_a),
                    )
                    for abp_a in np.linspace(0, 2 * math.pi, 16, endpoint=False)
                )
                abp_out.append(abpSafeZone(abpPolygon(abp_circle)))
                break
    if not abp_out:
        abp_out = abp__plain_circles(abp_image, abp_texts)
    abp_out.sort(
        key=lambda abp_z: (
            round(abp_z.abp_area.abp_centroid.abp_x),
            abp_z.abp_area.abp_centroid.abp_y,
        )
    )
    return [
        abpSafeZone(
            abp_z.abp_area, "Zona de reunión" if len(abp_out) == 1 else f"Zona de reunión {abp_k}"
        )
        for abp_k, abp_z in enumerate(abp_out, start=1)
    ]


def abp__plain_circles(
    abp_image: abpRGBImage, abp_texts: Sequence[abpVectorText]
) -> list[abpSafeZone]:
    if len(abp_texts) > 5:
        return []
    abp_hsv = cv2.cvtColor(np.ascontiguousarray(abp_image), cv2.COLOR_RGB2HSV)
    abp_yellow = (abp_hsv[:, :, 1] > 110) & (abp_hsv[:, :, 0] > 18) & (abp_hsv[:, :, 0] < 34)
    abp_least = 0.04 * min(abp_image.shape[:2])
    abp_kernel = np.ones((31, 31), np.uint8)
    abp_joined = cv2.morphologyEx(abp_yellow.astype(np.uint8), cv2.MORPH_CLOSE, abp_kernel)
    abp_contours, _ = cv2.findContours(abp_joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    abp_out: list[abpSafeZone] = []
    for abp_contour in abp_contours:
        (abp_cx, abp_cy), abp_radius = cv2.minEnclosingCircle(abp_contour)
        if (
            abp_radius > abp_least
            and cv2.contourArea(abp_contour) > 0.75 * math.pi * abp_radius * abp_radius
        ):
            abp_circle = tuple(
                abpPoint(
                    abp_cx + abp_radius * math.cos(abp_a), abp_cy + abp_radius * math.sin(abp_a)
                )
                for abp_a in np.linspace(0, 2 * math.pi, 16, endpoint=False)
            )
            abp_out.append(abpSafeZone(abpPolygon(abp_circle)))
    return abp_out


def abp__in_box(abp_p: tuple[float, float], abp_box: abpBox, abp_pad: float) -> bool:
    return (
        abp_box[0] - abp_pad <= abp_p[0] <= abp_box[2] + abp_pad
        and abp_box[1] - abp_pad <= abp_p[1] <= abp_box[3] + abp_pad
    )


def abp__bounds(abp_polygon: abpPolygon) -> abpBox:
    abp_xs, abp_ys = (
        [abp_v.abp_x for abp_v in abp_polygon.abp_vertices],
        [abp_v.abp_y for abp_v in abp_polygon.abp_vertices],
    )
    return min(abp_xs), min(abp_ys), max(abp_xs), max(abp_ys)


def abp__inside_patch(abp_t: abpVectorText, abp_blob: abp__Blob, abp_pad: float) -> bool:
    abp_c, abp_s = (
        math.cos(math.radians(abp_blob.abp_angle)),
        math.sin(math.radians(abp_blob.abp_angle)),
    )
    abp_dx, abp_dy = abp_t.abp_x - abp_blob.abp_center[0], abp_t.abp_y - abp_blob.abp_center[1]
    abp_u, abp_v = abp_dx * abp_c + abp_dy * abp_s, -abp_dx * abp_s + abp_dy * abp_c
    return (
        abs(abp_u) <= abp_blob.abp_size[0] / 2 + abp_pad
        and abs(abp_v) <= abp_blob.abp_size[1] / 2 + abp_pad
    )


def abp__unique(abp_signs: Sequence[abpSign], abp_size: float) -> list[abpSign]:
    abp_out: list[abpSign] = []
    for abp_sign in abp_signs:
        abp_apart = 0.55 * abp_size if abp_sign.abp_kind in abp_GENERIC else 1.1 * abp_size
        if all(
            abp_o.abp_kind is not abp_sign.abp_kind
            or abp_o.abp_position.abp_distance_to(abp_sign.abp_position) > abp_apart
            for abp_o in abp_out
        ):
            abp_out.append(abp_sign)
    abp_owners = {
        abpSignKind.abp_EXIT: abpSignKind.abp_DIRECTION,
        abpSignKind.abp_WARNING: abpSignKind.abp_ELECTRIC_RISK,
    }
    return [
        abp_o
        for abp_o in abp_out
        if abp_o.abp_kind not in abp_owners
        or all(
            abp_o.abp_position.abp_distance_to(abp_a.abp_position) > 1.1 * abp_size
            for abp_a in abp_out
            if abp_a.abp_kind is abp_owners[abp_o.abp_kind]
        )
    ]


def abp__split_signs(
    abp_texts: Collection[abpVectorText],
    abp_signs: Sequence[abpSign],
    abp_image: abpRGBImage,
    abp_templates: Sequence[abpSymbolTemplate],
    abp_size: float,
) -> list[abpSign]:
    abp_arrows = [abp_t for abp_t in abp_templates if abp_t.abp_kind is abpSignKind.abp_DIRECTION]
    abp_out: list[abpSign] = []
    for abp_t in abp_texts:
        abp_kind = abp_kind_of(abp_t.abp_text) if len(abp_t.abp_text) < 24 else None
        if abp_kind not in abp_SPLIT_KINDS or (
            abp_kind is abpSignKind.abp_EXIT and abp_plain(abp_t.abp_text) != "SALIDA"
        ):
            continue
        abp_place = abpPoint(abp_t.abp_x, abp_t.abp_y)
        if any(
            abp_s.abp_position.abp_distance_to(abp_place) < 1.3 * abp_size
            and (abp_s.abp_kind is abp_kind or abp_kind is abpSignKind.abp_EXIT)
            for abp_s in (*abp_signs, *abp_out)
        ):
            continue
        abp_r = max(4, int(0.5 * abp_t.abp_width))
        abp_patch = abp_image[
            max(0, int(abp_t.abp_y) - abp_r) : int(abp_t.abp_y) + abp_r,
            max(0, int(abp_t.abp_x) - abp_r) : int(abp_t.abp_x) + abp_r,
        ]
        if (
            not abp_patch.size
            or float(abp__color_mask(np.ascontiguousarray(abp_patch)).mean()) <= 0.2
        ):
            continue
        if abp_kind is not abpSignKind.abp_EXIT:
            abp_out.append(abpSign(abp_kind, abp_place))
        elif abp_arrows and abp_t.abp_width < 1.05 * min(abp_arrows[0].abp_image.shape[:2]):
            abp_out.append(abp__split_direction(abp_image, abp_t, abp_arrows, abp_size))
        else:
            abp_out.append(abpSign(abpSignKind.abp_EXIT, abp_place))
    return abp_out


def abp__split_direction(
    abp_image: abpRGBImage,
    abp_t: abpVectorText,
    abp_arrows: Sequence[abpSymbolTemplate],
    abp_size: float,
) -> abpSign:
    abp_blob = abp__Blob(
        (abp_t.abp_x, abp_t.abp_y),
        (2.6 * abp_size, 2.6 * abp_size),
        abp_t.abp_angle_deg,
        np.zeros((4, 2), np.float32),
    )
    abp_patch, abp_to_page = abp__upright(abp_image, abp_blob, 0.0)
    abp_matches = abp__match_templates(abp_patch, abp_arrows, 0.3)
    if not abp_matches:
        return abpSign(abpSignKind.abp_DIRECTION, abpPoint(abp_t.abp_x, abp_t.abp_y), 0.0)
    abp_m = abp_matches[0]
    abp_angle = abp__arrow_angle(abp_patch, abp_m) + abp_t.abp_angle_deg
    return abpSign(
        abpSignKind.abp_DIRECTION,
        abpPoint(*abp_to_page(abp_m.abp_x, abp_m.abp_y)),
        round(abp_angle / 5) * 5.0 % 360,
    )
