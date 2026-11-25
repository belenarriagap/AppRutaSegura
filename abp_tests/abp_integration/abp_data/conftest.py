from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from abp_rutasegura.abp_data.abp_database import abpDatabase


@pytest.fixture
def abp_db(tmp_path: Path) -> Iterator[abpDatabase]:
    abp_database = abpDatabase.abp_open(tmp_path / "prueba.db")
    yield abp_database
    abp_database.abp_close()
