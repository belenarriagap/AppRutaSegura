from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from abp_rutasegura.abp_data.abp_database import (
    abp_alembic_config,
    abp_plain_sqlite_engine,
    abp_upgrade_to_head,
    abpDatabase,
)
from abp_rutasegura.abp_data.abp_models import abpBase

abp_EXPECTED_TABLES = {
    "proyecto",
    "piso",
    "elemento",
    "ambiente",
    "perfil_persona",
    "escenario",
    "ocupacion",
    "simulacion",
    "observacion",
    "simulacro_real",
    "verificacion_regla",
}


def abp_test_upgrade_creates_spec_tables(tmp_path: Path) -> None:
    abp_engine = abp_plain_sqlite_engine(tmp_path / "db.sqlite")
    abp_upgrade_to_head(abp_engine)
    abp_tables = set(inspect(abp_engine).get_table_names()) - {"alembic_version"}
    assert abp_tables == abp_EXPECTED_TABLES
    abp_engine.dispose()


def abp_test_migrations_match_models(tmp_path: Path) -> None:
    abp_engine = abp_plain_sqlite_engine(tmp_path / "db.sqlite")
    abp_upgrade_to_head(abp_engine)
    with abp_engine.connect() as abp_conn:
        abp_diff = compare_metadata(MigrationContext.configure(abp_conn), abpBase.metadata)
    abp_engine.dispose()
    assert abp_diff == [], f"Los modelos cambiaron sin migración: {abp_diff}"


def abp_test_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    abp_engine = abp_plain_sqlite_engine(tmp_path / "db.sqlite")
    abp_upgrade_to_head(abp_engine)
    abp_config = abp_alembic_config()
    with abp_engine.begin() as abp_conn:
        abp_config.attributes["connection"] = abp_conn
        command.downgrade(abp_config, "base")
    assert set(inspect(abp_engine).get_table_names()) <= {"alembic_version"}
    abp_upgrade_to_head(abp_engine)
    assert set(inspect(abp_engine).get_table_names()) >= abp_EXPECTED_TABLES
    abp_engine.dispose()


def abp_test_open_is_idempotent(tmp_path: Path) -> None:
    abp_path = tmp_path / "carpeta nueva" / "rutasegura.db"
    abpDatabase.abp_open(abp_path).abp_close()
    abp_db = abpDatabase.abp_open(abp_path)
    with abp_db.abp_unit_of_work() as abp_uow:
        abp_names = [abp_p.abp_name for abp_p in abp_uow.abp_profiles.abp_list_all()]
    abp_db.abp_close()
    assert abp_names == ["adulto", "niño", "movilidad reducida"]
