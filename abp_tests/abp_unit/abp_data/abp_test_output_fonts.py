from __future__ import annotations

import sys

import pytest
from reportlab.lib.fonts import tt2ps

from abp_rutasegura.abp_data.abp_report_pdf import (
    abp__register_fonts,
    abp_FONT,
    abp_FONT_BOLD,
    abp_FONT_BOLD_ITALIC,
    abp_font_file,
)


def abp_test_every_font_has_a_file() -> None:
    for abp_font in (abp_FONT, abp_FONT_BOLD, abp_FONT_BOLD_ITALIC):
        assert abp_font_file(abp_font).is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Arial viene con Windows")
def abp_test_windows_uses_arial() -> None:
    assert abp_font_file(abp_FONT).name.lower() == "arial.ttf"
    assert abp_font_file(abp_FONT_BOLD).name.lower() == "arialbd.ttf"


def abp_test_bold_inside_paragraphs_uses_the_bold_font() -> None:
    abp__register_fonts()
    assert tt2ps(abp_FONT, 1, 0) == abp_FONT_BOLD
    assert tt2ps(abp_FONT, 1, 1) == abp_FONT_BOLD_ITALIC
