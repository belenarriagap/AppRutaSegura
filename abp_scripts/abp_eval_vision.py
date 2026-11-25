from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

abp_ROOT = Path(__file__).resolve().parents[1]
if str(abp_ROOT) not in sys.path:
    sys.path.insert(0, str(abp_ROOT))

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpSegment
from abp_rutasegura.abp_engines.abp_vision.abp_images import (
    abp_load_plan_file,
    abp_write_png,
    abpRGBImage,
)
from abp_rutasegura.abp_engines.abp_vision.abp_metrics import abp_opening_score, abp_wall_score
from abp_rutasegura.abp_engines.abp_vision.abp_pipeline import (
    abp_detect_plan,
    abpDetectionResult,
    abpVisionParams,
)

abp_TARGET = 0.85
abp_WALL_TOL_M = 0.2


@dataclass(frozen=True)
class abpCase:
    abp_name: str
    abp_image: abpRGBImage
    abp_walls: tuple[abpSegment, ...]
    abp_openings: tuple[abpSegment, ...]
    abp_scale_m_per_px: float | None


def abp__segments(abp_raw: list[list[float]]) -> tuple[abpSegment, ...]:
    return tuple(
        abpSegment(abpPoint(abp_a, abp_b), abpPoint(abp_c, abp_d))
        for abp_a, abp_b, abp_c, abp_d in abp_raw
    )


def abp_synthetic_cases(
    abp_count: int, abp_first_seed: int, abp_furnished: bool = False
) -> Iterator[abpCase]:
    from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan

    abp_prefix = "amoblado" if abp_furnished else "sintetico"
    for abp_seed in range(abp_first_seed, abp_first_seed + abp_count):
        abp_plan = abp_generate_plan(abp_seed, abp_furnished=abp_furnished)
        yield abpCase(
            f"{abp_prefix}_{abp_seed:03d}",
            abp_plan.abp_image,
            abp_plan.abp_walls,
            abp_plan.abp_openings,
            abp_plan.abp_scale_m_per_px,
        )


def abp_dataset_cases(abp_folder: Path) -> Iterator[abpCase]:
    for abp_label in sorted(abp_folder.glob("*.json")):
        abp_data = json.loads(abp_label.read_text(encoding="utf-8"))
        abp_image_path = next(
            (
                abp_p
                for abp_p in abp_folder.glob(f"{abp_label.stem}.*")
                if abp_p.suffix.lower() != ".json"
            ),
            None,
        )
        if abp_image_path is None:
            print(f"[aviso] {abp_label.name}: no se encontró la imagen; se omite.")
            continue
        yield abpCase(
            abp_label.stem,
            abp_load_plan_file(abp_image_path, int(abp_data.get("pagina", 0))),
            abp__segments(abp_data.get("muros", [])),
            abp__segments(abp_data.get("puertas", [])) + abp__segments(abp_data.get("salidas", [])),
            abp_data.get("escala_m_por_px"),
        )


def abp_draw_overlay(abp_case: abpCase, abp_result: abpDetectionResult) -> abpRGBImage:
    abp_img = abp_case.abp_image.copy()

    def abp_line(abp_seg: abpSegment, abp_color: tuple[int, int, int], abp_width: int) -> None:
        abp_p1 = (round(abp_seg.abp_start.abp_x), round(abp_seg.abp_start.abp_y))
        abp_p2 = (round(abp_seg.abp_end.abp_x), round(abp_seg.abp_end.abp_y))
        cv2.line(abp_img, abp_p1, abp_p2, abp_color, abp_width, cv2.LINE_AA)

    for abp_seg in abp_case.abp_walls + abp_case.abp_openings:
        abp_line(abp_seg, (0, 200, 0), 5)
    for abp_wall in abp_result.abp_walls:
        abp_line(abp_wall.abp_segment, (220, 0, 0), 2)
    for abp_opening in [abp_d.abp_segment for abp_d in abp_result.abp_doors] + [
        abp_e.abp_segment for abp_e in abp_result.abp_exits
    ]:
        abp_line(abp_opening, (0, 80, 255), 3)
    return np.ascontiguousarray(abp_img, dtype=np.uint8)


def abp_main(abp_argv: list[str] | None = None) -> int:
    abp_parser = argparse.ArgumentParser(
        description="Evalúa la detección sobre planos etiquetados o sintéticos",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    abp_parser.add_argument(
        "--synthetic", type=int, default=0, help="cantidad de planos sintéticos"
    )
    abp_parser.add_argument("--first-seed", type=int, default=0)
    abp_parser.add_argument(
        "--furnished", action="store_true", help="sintéticos con mobiliario en color"
    )
    abp_parser.add_argument("--dataset", type=Path, help="carpeta con planos etiquetados")
    abp_parser.add_argument(
        "--overlays", type=Path, help="carpeta donde guardar imágenes de control"
    )
    abp_args = abp_parser.parse_args(abp_argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    abp_cases: list[abpCase] = []
    if abp_args.synthetic:
        abp_cases.extend(
            abp_synthetic_cases(abp_args.synthetic, abp_args.first_seed, abp_args.furnished)
        )
    if abp_args.dataset:
        abp_cases.extend(abp_dataset_cases(abp_args.dataset))
    if not abp_cases:
        abp_parser.error("indique --synthetic N y/o --dataset CARPETA")

    abp_rows = []
    print(f"{'plano':<22}{'muros P':>9}{'muros R':>9}{'vanos P':>9}{'vanos R':>9}")
    for abp_case in abp_cases:
        abp_result = abp_detect_plan(
            abp_case.abp_image, abpVisionParams(abp_scale_m_per_px=abp_case.abp_scale_m_per_px)
        )
        abp_tol = (
            abp_WALL_TOL_M / abp_case.abp_scale_m_per_px if abp_case.abp_scale_m_per_px else 10.0
        )
        abp_walls = abp_wall_score(
            [abp_w.abp_segment for abp_w in abp_result.abp_walls], abp_case.abp_walls, abp_tol
        )
        abp_predicted_openings = [abp_d.abp_segment for abp_d in abp_result.abp_doors] + [
            abp_e.abp_segment for abp_e in abp_result.abp_exits
        ]
        abp_openings = abp_opening_score(abp_predicted_openings, abp_case.abp_openings, abp_tol)
        abp_rows.append(
            (
                abp_walls.abp_precision,
                abp_walls.abp_recall,
                abp_openings.abp_precision,
                abp_openings.abp_recall,
            )
        )
        print(
            f"{abp_case.abp_name:<22}{abp_walls.abp_precision:>9.1%}{abp_walls.abp_recall:>9.1%}"
            f"{abp_openings.abp_precision:>9.1%}{abp_openings.abp_recall:>9.1%}"
        )
        if abp_args.overlays:
            abp_write_png(
                abp_args.overlays / f"{abp_case.abp_name}.png",
                abp_draw_overlay(abp_case, abp_result),
            )

    abp_means = np.mean(np.array(abp_rows), axis=0)
    print("-" * 58)
    print(f"{'PROMEDIO':<22}" + "".join(f"{abp_m:>9.1%}" for abp_m in abp_means))
    abp_ok = bool((abp_means >= abp_TARGET).all())
    print(f"Meta ≥ {abp_TARGET:.0%} en las cuatro métricas: {'CUMPLE' if abp_ok else 'NO CUMPLE'}")
    return 0 if abp_ok else 1


if __name__ == "__main__":
    raise SystemExit(abp_main())
