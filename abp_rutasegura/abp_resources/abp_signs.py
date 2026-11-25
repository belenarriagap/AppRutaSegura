from __future__ import annotations

from dataclasses import dataclass

abp_GREEN, abp_RED, abp_YELLOW = "#00913f", "#d7181f", "#ffd500"
abp_WHITE, abp_BLACK, abp_BLUE = "#ffffff", "#1a1a1a", "#1b5fa7"

abpPoints = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class abpShape:
    abp_kind: str
    abp_points: abpPoints
    abp_color: str
    abp_size: float = 0.0
    abp_text: str = ""


@dataclass(frozen=True, slots=True)
class abpSignArt:
    abp_label: str
    abp_shapes: tuple[abpShape, ...]
    abp_rotates: bool = False


def abp__box(abp_w: float, abp_h: float, abp_color: str) -> abpShape:
    abp_x, abp_y = abp_w / 2, abp_h / 2
    return abpShape(
        "poly", ((-abp_x, -abp_y), (abp_x, -abp_y), (abp_x, abp_y), (-abp_x, abp_y)), abp_color
    )


def abp__arrow(abp_color: str) -> abpShape:
    return abpShape(
        "poly",
        (
            (-0.34, -0.1),
            (0.04, -0.1),
            (0.04, -0.28),
            (0.38, 0.0),
            (0.04, 0.28),
            (0.04, 0.1),
            (-0.34, 0.1),
        ),
        abp_color,
    )


def abp__runner(abp_dx: float, abp_dy: float, abp_k: float) -> tuple[abpShape, ...]:
    def abp_at(*abp_points: tuple[float, float]) -> abpPoints:
        return tuple(
            (abp_dx + abp_x * abp_k, abp_dy + abp_y * abp_k) for abp_x, abp_y in abp_points
        )

    return (
        abpShape("circle", abp_at((0.08, -0.36)), abp_WHITE, 0.09 * abp_k),
        abpShape("line", abp_at((0.05, -0.22), (-0.05, 0.08)), abp_WHITE, 0.13 * abp_k),
        abpShape(
            "line", abp_at((0.03, -0.18), (0.2, -0.06), (0.32, -0.14)), abp_WHITE, 0.07 * abp_k
        ),
        abpShape(
            "line", abp_at((0.02, -0.2), (-0.2, -0.16), (-0.26, 0.0)), abp_WHITE, 0.07 * abp_k
        ),
        abpShape("line", abp_at((-0.04, 0.08), (0.14, 0.18), (0.1, 0.42)), abp_WHITE, 0.09 * abp_k),
        abpShape(
            "line", abp_at((-0.05, 0.08), (-0.14, 0.26), (-0.36, 0.28)), abp_WHITE, 0.09 * abp_k
        ),
    )


abp_SIGNS: dict[str, abpSignArt] = {
    "salida": abpSignArt(
        "Salida",
        (
            abp__box(1.7, 0.75, abp_GREEN),
            *abp__runner(-0.52, -0.03, 0.72),
            abpShape("text", ((0.29, 0.0),), abp_WHITE, 0.19, "SALIDA"),
        ),
    ),
    "direccion": abpSignArt(
        "Dirección de salida", (abp__box(1, 1, abp_GREEN), abp__arrow(abp_WHITE)), True
    ),
    "escalera": abpSignArt(
        "Escalera de evacuación",
        (
            abp__box(1, 1, abp_GREEN),
            abpShape(
                "line",
                (
                    (-0.36, -0.2),
                    (-0.14, -0.2),
                    (-0.14, 0.02),
                    (0.08, 0.02),
                    (0.08, 0.24),
                    (0.34, 0.24),
                ),
                abp_WHITE,
                0.08,
            ),
            abpShape("line", ((0.06, -0.3), (0.3, -0.06)), abp_WHITE, 0.07),
            abpShape("poly", ((0.36, 0.02), (0.14, -0.02), (0.32, -0.2)), abp_WHITE),
        ),
    ),
    "zona_segura": abpSignArt(
        "Zona segura en caso de sismos",
        (
            abp__box(1, 1.25, abp_GREEN),
            abpShape("circle", ((0.0, -0.16),), abp_WHITE, 0.36),
            abpShape("text", ((0.0, -0.16),), abp_GREEN, 0.52, "S"),
            abpShape("text", ((0.0, 0.38),), abp_WHITE, 0.09, "ZONA SEGURA"),
            abpShape("text", ((0.0, 0.52),), abp_WHITE, 0.06, "EN CASO DE SISMOS"),
        ),
    ),
    "botiquin": abpSignArt(
        "Botiquín",
        (
            abp__box(1, 1, abp_GREEN),
            abpShape("line", ((-0.32, 0.0), (0.32, 0.0)), abp_WHITE, 0.24),
            abpShape("line", ((0.0, -0.32), (0.0, 0.32)), abp_WHITE, 0.24),
        ),
    ),
    "luz_emergencia": abpSignArt(
        "Luz de emergencia",
        (
            abp__box(1, 0.8, abp_GREEN),
            abp__box(0.9, 0.7, abp_WHITE),
            abpShape("poly", ((-0.28, 0.02), (0.28, 0.02), (0.28, 0.28), (-0.28, 0.28)), abp_GREEN),
            abpShape("circle", ((-0.2, -0.14),), abp_GREEN, 0.14),
            abpShape("circle", ((0.2, -0.14),), abp_GREEN, 0.14),
        ),
    ),
    "extintor": abpSignArt(
        "Extintor",
        (
            abp__box(1, 1, abp_RED),
            abpShape(
                "poly",
                ((-0.14, -0.12), (0.18, -0.12), (0.18, 0.38), (-0.14, 0.38)),
                abp_WHITE,
            ),
            abpShape("line", ((0.02, -0.12), (0.02, -0.3)), abp_WHITE, 0.1),
            abpShape("line", ((-0.1, -0.34), (0.22, -0.28)), abp_WHITE, 0.06),
            abpShape("line", ((0.0, -0.26), (-0.24, -0.18), (-0.28, 0.12)), abp_WHITE, 0.06),
        ),
    ),
    "alarma": abpSignArt(
        "Pulsador de alarma",
        (
            abp__box(1, 1, abp_RED),
            abpShape("circle", ((0.0, 0.0),), abp_WHITE, 0.3),
            abpShape("circle", ((0.0, 0.0),), abp_RED, 0.18),
        ),
    ),
    "hidrante": abpSignArt(
        "Gabinete contra incendio",
        (
            abp__box(1, 1, abp_RED),
            abpShape("circle", ((-0.05, -0.05),), abp_WHITE, 0.28),
            abpShape("circle", ((-0.05, -0.05),), abp_RED, 0.17),
            abpShape("circle", ((-0.05, -0.05),), abp_WHITE, 0.08),
            abpShape("line", ((0.22, -0.05), (0.28, 0.2), (0.1, 0.36)), abp_WHITE, 0.07),
        ),
    ),
    "prohibicion": abpSignArt(
        "Prohibición",
        (
            abpShape("circle", ((0.0, 0.0),), abp_RED, 0.5),
            abpShape("circle", ((0.0, 0.0),), abp_WHITE, 0.37),
            abpShape("line", ((-0.27, -0.27), (0.27, 0.27)), abp_RED, 0.12),
        ),
    ),
    "obligacion": abpSignArt(
        "Obligación",
        (
            abpShape("circle", ((0.0, 0.0),), abp_BLUE, 0.5),
            abpShape("line", ((0.0, -0.26), (0.0, 0.1)), abp_WHITE, 0.13),
            abpShape("circle", ((0.0, 0.28),), abp_WHITE, 0.08),
        ),
    ),
    "advertencia": abpSignArt(
        "Advertencia",
        (
            abpShape("poly", ((0.0, -0.5), (0.56, 0.45), (-0.56, 0.45)), abp_BLACK),
            abpShape("poly", ((0.0, -0.37), (0.45, 0.38), (-0.45, 0.38)), abp_YELLOW),
            abpShape("line", ((0.0, -0.14), (0.0, 0.14)), abp_BLACK, 0.1),
            abpShape("circle", ((0.0, 0.28),), abp_BLACK, 0.06),
        ),
    ),
    "riesgo_electrico": abpSignArt(
        "Riesgo eléctrico",
        (
            abpShape("poly", ((0.0, -0.5), (0.56, 0.45), (-0.56, 0.45)), abp_BLACK),
            abpShape("poly", ((0.0, -0.37), (0.45, 0.38), (-0.45, 0.38)), abp_YELLOW),
            abpShape(
                "poly",
                (
                    (0.06, -0.2),
                    (-0.14, 0.12),
                    (-0.01, 0.12),
                    (-0.07, 0.33),
                    (0.14, 0.03),
                    (0.02, 0.03),
                ),
                abp_BLACK,
            ),
        ),
    ),
    "aforo": abpSignArt(
        "Aforo",
        (
            abp__box(1, 1, abp_BLUE),
            abp__box(0.9, 0.9, abp_WHITE),
            abpShape("text", ((0.0, -0.24),), abp_BLUE, 0.14, "AFORO"),
            abpShape("text", ((0.0, 0.14),), abp_BLUE, 0.36, "{text}"),
        ),
    ),
    "camilla": abpSignArt(
        "Camilla rígida",
        (
            abp__box(1.0, 1.0, abp_GREEN),
            abpShape(
                "poly", ((-0.42, -0.06), (0.14, -0.06), (0.14, 0.12), (-0.42, 0.12)), abp_WHITE
            ),
            abpShape("circle", ((-0.3, -0.18),), abp_WHITE, 0.09),
            abpShape("line", ((-0.46, 0.2), (0.18, 0.2)), abp_WHITE, 0.05),
            abpShape("poly", ((0.28, -0.22), (0.36, -0.22), (0.36, 0.06), (0.28, 0.06)), abp_WHITE),
            abpShape(
                "poly", ((0.18, -0.12), (0.46, -0.12), (0.46, -0.04), (0.18, -0.04)), abp_WHITE
            ),
        ),
    ),
    "salida_emergencia": abpSignArt(
        "Salida de emergencia",
        (
            abp__box(1.0, 1.0, abp_GREEN),
            abpShape("poly", ((0.02, -0.4), (0.42, -0.4), (0.42, 0.42), (0.02, 0.42)), abp_WHITE),
            abpShape("poly", ((0.08, -0.34), (0.36, -0.34), (0.36, 0.42), (0.08, 0.42)), abp_GREEN),
            *abp__runner(-0.14, 0.02, 0.8),
        ),
    ),
    "detector_humo": abpSignArt(
        "Detector de humo",
        (
            abpShape("circle", ((0.0, 0.0),), abp_GREEN, 0.5),
            abpShape("circle", ((0.0, 0.0),), abp_WHITE, 0.42),
            abpShape("text", ((0.0, 0.0),), abp_BLUE, 0.46, "H"),
        ),
    ),
    "detector_temperatura": abpSignArt(
        "Detector de temperatura",
        (
            abpShape("circle", ((0.0, 0.0),), abp_BLACK, 0.5),
            abpShape("circle", ((0.0, 0.0),), abp_WHITE, 0.42),
            abpShape("text", ((0.0, 0.0),), abp_BLACK, 0.46, "T"),
        ),
    ),
    "luz_estroboscopica": abpSignArt(
        "Luz estroboscópica",
        (
            abp__box(0.9, 0.9, abp_RED),
            abp__box(0.78, 0.78, abp_WHITE),
            abpShape("line", ((-0.28, -0.28), (0.28, 0.28)), abp_RED, 0.07),
            abpShape("line", ((0.28, -0.28), (-0.28, 0.28)), abp_RED, 0.07),
            abpShape("circle", ((0.0, 0.0),), abp_RED, 0.14),
        ),
    ),
    "estacion_manual": abpSignArt(
        "Estación manual de alarma",
        (
            abp__box(0.9, 0.9, abp_RED),
            abp__box(0.74, 0.74, abp_WHITE),
            abpShape("circle", ((0.0, 0.0),), abp_RED, 0.2),
        ),
    ),
    "central_alarma": abpSignArt(
        "Central de alarma contra incendios",
        (
            abp__box(1.3, 0.7, abp_RED),
            abp__box(1.18, 0.58, abp_WHITE),
            abpShape("text", ((0.0, 0.0),), abp_RED, 0.24, "C-ACI"),
        ),
    ),
}
