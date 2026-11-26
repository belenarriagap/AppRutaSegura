from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np

from abp_rutasegura.abp_domain.abp_vector import abpFloatArray, abpVectorText
from abp_rutasegura.abp_engines.abp_vision.abp_pdf_vector import abp_plain

abp__LEVEL = re.compile(r"^N\s*\.?\s*P\s*\.?\s*T\b")
abp__AREA = re.compile(r"\bAREA\s*[=:]\s*(\d+(?:[.,]\d+)?)")
abp__CAPACITY = re.compile(r"\bAFORO\s*[=:]\s*(\d+)")
abp__NOT_A_NAME = re.compile(
    r"^(?:PISO|N\.?P\.?T|AREA\s*[=:]|AFORO|ESC\.|VEN\.|VEN\s*\d|PUERTA|VENTANA|\d|[A-Z]{1,3}\s*-\s*\d)"
)

abp_NAME_REACH = 18.0


@dataclass(frozen=True, slots=True)
class abpRoomLabel:
    abp_name: str
    abp_x: float
    abp_y: float
    abp_area_m2: float | None = None
    abp_capacity: int | None = None


def abp_label_anchors(abp_texts: Collection[abpVectorText]) -> abpFloatArray:
    abp_points = [
        (abp_t.abp_x, abp_t.abp_y)
        for abp_t in abp_texts
        if (
            abp__LEVEL.match(abp_plain(abp_t.abp_text))
            and any(abp_c.isdigit() for abp_c in abp_t.abp_text)
        )
        or abp__AREA.search(abp_plain(abp_t.abp_text))
        or abp__CAPACITY.search(abp_plain(abp_t.abp_text))
    ]
    return np.array(abp_points, np.float64).reshape(-1, 2)


def abp_read_room_labels(abp_texts: Sequence[abpVectorText]) -> tuple[abpRoomLabel, ...]:
    abp_used: set[int] = set()
    abp_styles: set[tuple[str, float]] = set()
    abp_out: list[abpRoomLabel] = []
    abp_orphans: list[abpRoomLabel] = []
    for abp_anchor in abp_texts:
        if not abp__LEVEL.match(abp_plain(abp_anchor.abp_text)):
            continue
        abp_rad = math.radians(abp_anchor.abp_angle_deg)
        abp_u, abp_v = (
            (math.cos(abp_rad), math.sin(abp_rad)),
            (-math.sin(abp_rad), math.cos(abp_rad)),
        )
        abp_h = abp_anchor.abp_size
        abp_above: list[tuple[float, int]] = []
        abp_area: float | None = None
        abp_capacity: int | None = None
        for abp_i, abp_t in enumerate(abp_texts):
            abp_dx, abp_dy = abp_t.abp_x - abp_anchor.abp_x, abp_t.abp_y - abp_anchor.abp_y
            abp_along, abp_down = (
                abp_dx * abp_u[0] + abp_dy * abp_u[1],
                abp_dx * abp_v[0] + abp_dy * abp_v[1],
            )
            if abs((abp_t.abp_angle_deg - abp_anchor.abp_angle_deg + 180) % 360 - 180) > 12:
                continue
            abp_text = abp_plain(abp_t.abp_text)
            if 0.4 * abp_h < abp_down < 4.0 * abp_h and abs(abp_along) < 4 * abp_h:
                abp_found = abp__AREA.search(abp_text)
                abp_area = (
                    float(abp_found[1].replace(",", "."))
                    if abp_found and abp_area is None
                    else abp_area
                )
                abp_found = abp__CAPACITY.search(abp_text)
                abp_capacity = (
                    int(abp_found[1]) if abp_found and abp_capacity is None else abp_capacity
                )
            elif (
                -4.5 * abp_h < abp_down < -0.4 * abp_h
                and abs(abp_along) < 0.5 * abp_t.abp_width + 4 * abp_h
                and abp_t.abp_size >= 1.02 * abp_h
                and abp__is_name(abp_text)
            ):
                abp_above.append((abp_down, abp_i))
        abp_lines: list[int] = []
        abp_previous = 0.0
        for abp_down, abp_i in sorted(abp_above, reverse=True):
            if abp_previous - abp_down > (2.6 if not abp_lines else 1.7) * abp_h:
                break
            abp_lines.append(abp_i)
            abp_previous = abp_down
        if not abp_lines:
            if abp_area is not None or abp_capacity is not None:
                abp_orphans.append(
                    abpRoomLabel("", abp_anchor.abp_x, abp_anchor.abp_y, abp_area, abp_capacity)
                )
            continue
        abp_used.update(abp_lines)
        abp_styles.update(
            (abp_texts[abp_i].abp_font, round(abp_texts[abp_i].abp_size, 1)) for abp_i in abp_lines
        )
        abp_name = " ".join(abp_texts[abp_i].abp_text.strip() for abp_i in reversed(abp_lines))
        abp_out.append(
            abpRoomLabel(
                abp__tidy(abp_name), abp_anchor.abp_x, abp_anchor.abp_y, abp_area, abp_capacity
            )
        )
    abp_loose = [
        abp_t
        for abp_i, abp_t in enumerate(abp_texts)
        if abp_i not in abp_used
        and abp__is_name(abp_plain(abp_t.abp_text))
        and any(
            abp_t.abp_font == abp_f and abs(abp_t.abp_size - abp_s) < 0.05 * abp_s
            for abp_f, abp_s in abp_styles
        )
    ]
    abp_names = abp__joined_lines(abp_loose)
    abp_pairs = sorted(
        (math.hypot(abp_o.abp_x - abp_q.abp_x, abp_o.abp_y - abp_q.abp_y), abp_k, abp_m)
        for abp_k, abp_o in enumerate(abp_orphans)
        for abp_m, (abp_q, abp__size) in enumerate(abp_names)
    )
    abp_taken_o: set[int] = set()
    abp_taken_n: set[int] = set()
    for abp_away, abp_k, abp_m in abp_pairs:
        if (
            abp_k in abp_taken_o
            or abp_m in abp_taken_n
            or abp_away > abp_NAME_REACH * abp_names[abp_m][1]
        ):
            continue
        abp_taken_o.add(abp_k)
        abp_taken_n.add(abp_m)
        abp_out.append(
            dataclasses.replace(abp_orphans[abp_k], abp_name=abp_names[abp_m][0].abp_name)
        )
    abp_out += [
        abp_q for abp_m, (abp_q, abp__size) in enumerate(abp_names) if abp_m not in abp_taken_n
    ]
    return tuple(abp_out)


def abp__joined_lines(abp_texts: Sequence[abpVectorText]) -> list[tuple[abpRoomLabel, float]]:
    abp_rest = sorted(abp_texts, key=lambda abp_t: abp_t.abp_y)
    abp_out: list[tuple[abpRoomLabel, float]] = []
    while abp_rest:
        abp_group = [abp_rest.pop(0)]
        for abp_t in list(abp_rest):
            abp_last = abp_group[-1]
            abp_same = (
                abp_t.abp_font == abp_last.abp_font
                and abs(abp_t.abp_size - abp_last.abp_size) < 0.1 * abp_last.abp_size
            )
            abp_same &= abs((abp_t.abp_angle_deg - abp_last.abp_angle_deg + 180) % 360 - 180) < 8
            abp_rad = math.radians(abp_last.abp_angle_deg)
            abp_dx, abp_dy = abp_t.abp_x - abp_last.abp_x, abp_t.abp_y - abp_last.abp_y
            abp_down = -abp_dx * math.sin(abp_rad) + abp_dy * math.cos(abp_rad)
            abp_along = abp_dx * math.cos(abp_rad) + abp_dy * math.sin(abp_rad)
            if (
                abp_same
                and 0.6 * abp_t.abp_size < abp_down < 2.4 * abp_t.abp_size
                and abs(abp_along) < 0.7 * max(abp_t.abp_width, abp_last.abp_width)
            ):
                abp_group.append(abp_t)
                abp_rest.remove(abp_t)
        abp_name = abp__tidy(" ".join(abp_t.abp_text.strip() for abp_t in abp_group))
        abp_first = abp_group[0]
        abp_out.append(
            (abpRoomLabel(abp_name, abp_first.abp_x, abp_first.abp_y), abp_first.abp_size)
        )
    return abp_out


def abp__is_name(abp_text: str) -> bool:
    return sum(abp_c.isalpha() for abp_c in abp_text) >= 4 and not abp__NOT_A_NAME.match(abp_text)


def abp__tidy(abp_text: str) -> str:
    abp_clean = " ".join(abp_text.split())
    return abp_clean.capitalize() if abp_clean.isupper() else abp_clean
