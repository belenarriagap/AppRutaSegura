from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import pymupdf

abpRGBImage = npt.NDArray[np.uint8]
abpGrayImage = npt.NDArray[np.uint8]
abpMask = npt.NDArray[np.bool_]

abp_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
abp_PDF_SUFFIX = ".pdf"
abp_PDF_DPI = 200
abp_MAX_SIDE_PX = 6000


class abpPlanFileError(ValueError):
    pass


def abp_is_supported(abp_path: Path) -> bool:
    abp_suffix = abp_path.suffix.lower()
    return abp_suffix in abp_IMAGE_SUFFIXES or abp_suffix == abp_PDF_SUFFIX


def abp_page_count(abp_path: Path) -> int:
    if abp_path.suffix.lower() == abp_PDF_SUFFIX:
        try:
            with pymupdf.open(abp_path) as abp_doc:
                return int(abp_doc.page_count)
        except (RuntimeError, ValueError) as abp_exc:
            raise abpPlanFileError(f"No se pudo abrir el PDF: {abp_exc}") from abp_exc
    if abp_path.suffix.lower() in abp_IMAGE_SUFFIXES:
        return 1
    raise abpPlanFileError(f"Formato no soportado: {abp_path.suffix or 'sin extensión'}.")


def abp_read_image(abp_path: Path) -> abpRGBImage:
    try:
        abp_data = np.fromfile(abp_path, dtype=np.uint8)
    except OSError as abp_exc:
        raise abpPlanFileError(f"No se pudo leer el archivo: {abp_exc}") from abp_exc
    abp_decoded = cv2.imdecode(abp_data, cv2.IMREAD_COLOR)
    if abp_decoded is None:
        raise abpPlanFileError("El archivo no es una imagen válida o está dañado.")
    return np.ascontiguousarray(cv2.cvtColor(abp_decoded, cv2.COLOR_BGR2RGB), dtype=np.uint8)


def abp_write_png(abp_path: Path, abp_image: abpRGBImage) -> None:
    abp_ok, abp_buffer = cv2.imencode(".png", cv2.cvtColor(abp_image, cv2.COLOR_RGB2BGR))
    if not abp_ok:
        raise abpPlanFileError("No se pudo codificar la imagen.")
    abp_path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(abp_buffer, dtype=np.uint8).tofile(abp_path)


def abp_rasterize_pdf_page(
    abp_path: Path, abp_page: int = 0, abp_dpi: int = abp_PDF_DPI
) -> abpRGBImage:
    try:
        with pymupdf.open(abp_path) as abp_doc:
            if not 0 <= abp_page < abp_doc.page_count:
                raise abpPlanFileError(
                    f"El PDF tiene {abp_doc.page_count} página(s); no existe la {abp_page + 1}."
                )
            abp_pdf_page = abp_doc[abp_page]
            abp_rect = abp_pdf_page.rect
            abp_longest_in = max(abp_rect.width, abp_rect.height) / 72.0
            abp_effective_dpi = (
                min(abp_dpi, int(abp_MAX_SIDE_PX / abp_longest_in))
                if abp_longest_in > 0
                else abp_dpi
            )
            abp_pix = abp_pdf_page.get_pixmap(
                dpi=max(abp_effective_dpi, 36), alpha=False, colorspace=pymupdf.csRGB
            )
            abp_raw = np.frombuffer(abp_pix.samples, dtype=np.uint8)
            abp_rows = abp_raw.reshape(abp_pix.height, abp_pix.stride)[
                :, : abp_pix.width * abp_pix.n
            ]
            abp_image = abp_rows.reshape(abp_pix.height, abp_pix.width, abp_pix.n)
    except abpPlanFileError:
        raise
    except (RuntimeError, ValueError) as abp_exc:
        raise abpPlanFileError(f"No se pudo leer el PDF: {abp_exc}") from abp_exc
    return np.ascontiguousarray(abp_image[:, :, :3], dtype=np.uint8)


def abp_load_plan_file(abp_path: Path, abp_page: int = 0) -> abpRGBImage:
    if not abp_path.exists():
        raise abpPlanFileError("El archivo no existe.")
    if abp_path.suffix.lower() == abp_PDF_SUFFIX:
        return abp_rasterize_pdf_page(abp_path, abp_page)
    if abp_path.suffix.lower() in abp_IMAGE_SUFFIXES:
        return abp_read_image(abp_path)
    raise abpPlanFileError(f"Formato no soportado: {abp_path.suffix or 'sin extensión'}.")
