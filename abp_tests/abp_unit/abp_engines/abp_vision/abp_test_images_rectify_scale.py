from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest

from abp_rutasegura.abp_domain.abp_geometry import abpPoint
from abp_rutasegura.abp_engines.abp_vision.abp_images import (
    abp_is_supported,
    abp_load_plan_file,
    abp_page_count,
    abp_rasterize_pdf_page,
    abp_read_image,
    abp_write_png,
    abpPlanFileError,
)
from abp_rutasegura.abp_engines.abp_vision.abp_rectify import abp_order_corners, abp_rectify
from abp_rutasegura.abp_engines.abp_vision.abp_scale import abp_scale_from_reference


def abp__sample_image() -> np.ndarray:
    abp_img = np.full((60, 80, 3), 255, dtype=np.uint8)
    abp_img[10:20, 10:70] = (200, 30, 30)
    return abp_img


class abpTestImages:
    def abp_test_png_round_trip_with_non_ascii_path(self, tmp_path: Path) -> None:
        abp_path = tmp_path / "Ingeniería" / "plano ñandú.png"
        abp_image = abp__sample_image()
        abp_write_png(abp_path, abp_image)
        assert np.array_equal(abp_read_image(abp_path), abp_image)
        assert abp_page_count(abp_path) == 1
        assert np.array_equal(abp_load_plan_file(abp_path), abp_image)

    def abp_test_jpg_is_loaded_as_rgb(self, tmp_path: Path) -> None:
        abp_path = tmp_path / "plano.jpg"
        abp_ok, abp_buf = cv2.imencode(".jpg", cv2.cvtColor(abp__sample_image(), cv2.COLOR_RGB2BGR))
        assert abp_ok
        abp_buf.tofile(abp_path)
        abp_image = abp_read_image(abp_path)
        assert abp_image.shape == (60, 80, 3)
        assert abp_image[15, 40, 0] > 150
        assert abp_image[15, 40, 2] < 100

    def abp_test_pdf_pages_are_rasterized(self, tmp_path: Path) -> None:
        abp_path = tmp_path / "planos.pdf"
        with pymupdf.open() as abp_doc:
            for _ in range(2):
                abp_page = abp_doc.new_page(width=288, height=144)
                abp_page.draw_rect(pymupdf.Rect(36, 36, 252, 108), color=(0, 0, 0), fill=(0, 0, 0))
            abp_doc.save(abp_path)
        assert abp_page_count(abp_path) == 2
        abp_image = abp_rasterize_pdf_page(abp_path, abp_page=1, abp_dpi=100)
        assert abp_image.shape == (200, 400, 3)
        assert abp_image[100, 200].max() < 50
        assert abp_image[5, 5].min() > 200
        with pytest.raises(abpPlanFileError, match="no existe la 3"):
            abp_rasterize_pdf_page(abp_path, abp_page=2)

    def abp_test_unsupported_and_broken_files(self, tmp_path: Path) -> None:
        abp_dwg = tmp_path / "plano.dwg"
        abp_dwg.write_bytes(b"x")
        assert not abp_is_supported(abp_dwg)
        assert abp_is_supported(tmp_path / "a.PDF")
        with pytest.raises(abpPlanFileError, match="no soportado"):
            abp_load_plan_file(abp_dwg)
        abp_broken = tmp_path / "roto.png"
        abp_broken.write_bytes(b"no es una imagen")
        with pytest.raises(abpPlanFileError, match="dañado"):
            abp_load_plan_file(abp_broken)
        with pytest.raises(abpPlanFileError, match="no existe"):
            abp_load_plan_file(tmp_path / "falta.png")


class abpTestRectify:
    def abp_test_order_corners_any_input_order(self) -> None:
        abp_corners = [abpPoint(100, 90), abpPoint(5, 10), abpPoint(110, 5), abpPoint(0, 100)]
        abp_ordered = abp_order_corners(abp_corners)
        assert abp_ordered.tolist() == [[5, 10], [110, 5], [100, 90], [0, 100]]

    def abp_test_invalid_corners(self) -> None:
        with pytest.raises(ValueError, match="4 esquinas"):
            abp_order_corners([abpPoint(0, 0), abpPoint(1, 1)])
        with pytest.raises(ValueError, match="pequeña"):
            abp_order_corners([abpPoint(0, 0), abpPoint(5, 0), abpPoint(5, 5), abpPoint(0, 5)])

    def abp_test_rectify_restores_a_warped_rectangle(self) -> None:
        abp_src = np.full((100, 200, 3), 255, np.uint8)
        abp_src[:, :10] = 0
        abp_quad = np.array([[40, 30], [260, 50], [250, 170], [30, 150]], np.float32)
        abp_rect = np.array([[0, 0], [199, 0], [199, 99], [0, 99]], np.float32)
        abp_matrix = cv2.getPerspectiveTransform(abp_rect, abp_quad)
        abp_warped = np.asarray(
            cv2.warpPerspective(abp_src, abp_matrix, (300, 200), borderValue=(128, 128, 128)),
            dtype=np.uint8,
        )
        abp_result = abp_rectify(
            abp_warped, [abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_quad]
        )
        assert abs(abp_result.shape[1] - 220) < 5
        assert abs(abp_result.shape[0] - 120) < 5
        assert abp_result[:, :5].mean() < 80
        assert abp_result[:, -20:].mean() > 200


class abpTestScale:
    def abp_test_scale_from_two_points(self) -> None:
        assert abp_scale_from_reference(abpPoint(0, 0), abpPoint(300, 400), 10.0) == pytest.approx(
            0.02
        )

    def abp_test_invalid_reference(self) -> None:
        with pytest.raises(ValueError, match="mayor que cero"):
            abp_scale_from_reference(abpPoint(0, 0), abpPoint(10, 0), 0)
        with pytest.raises(ValueError, match="demasiado cerca"):
            abp_scale_from_reference(abpPoint(0, 0), abpPoint(0.5, 0), 1.0)
