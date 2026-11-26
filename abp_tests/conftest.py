from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def abp_services(tmp_path: Path) -> Iterator[object]:
    from abp_rutasegura.abp_application.abp_services import abpAppServices

    abp_app_services = abpAppServices.abp_open(tmp_path / "datos" / "rutasegura.db")
    yield abp_app_services
    abp_app_services.abp_close()
