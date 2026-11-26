from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from abp_rutasegura.abp_data.abp_default_profiles import abp_load_default_profiles
from abp_rutasegura.abp_data.abp_repositories import (
    abpFloorRepository,
    abpProfileRepository,
    abpProjectRepository,
    abpRealDrillRepository,
    abpRuleVerificationRepository,
    abpScenarioRepository,
    abpSimulationRepository,
)

abp_APP_DIR_NAME = "RutaSegura"
abp_DB_FILE_NAME = "rutasegura.db"
abp_MIGRATIONS_DIR = Path(__file__).parent / "abp_migrations"


class abpEngineFactory(Protocol):
    def __call__(self, abp_path: Path) -> Engine: ...


def abp__enable_foreign_keys(abp_dbapi_connection: Any, abp__record: Any) -> None:
    abp_cursor = abp_dbapi_connection.cursor()
    abp_cursor.execute("PRAGMA foreign_keys=ON")
    abp_cursor.close()


def abp_plain_sqlite_engine(abp_path: Path) -> Engine:
    abp_engine = create_engine(URL.create("sqlite", database=str(abp_path)))
    event.listen(abp_engine, "connect", abp__enable_foreign_keys)
    return abp_engine


def abp_default_database_path() -> Path:
    if sys.platform == "win32":
        abp_base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        abp_base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return abp_base / abp_APP_DIR_NAME / abp_DB_FILE_NAME


def abp_alembic_config() -> Config:
    abp_config = Config()
    abp_config.set_main_option("script_location", str(abp_MIGRATIONS_DIR).replace("%", "%%"))
    abp_versions = str(abp_MIGRATIONS_DIR / "abp_versions").replace("%", "%%")
    abp_config.set_main_option("path_separator", "os")
    abp_config.set_main_option("version_locations", abp_versions)
    return abp_config


def abp_upgrade_to_head(abp_engine: Engine) -> None:
    abp_config = abp_alembic_config()
    with abp_engine.begin() as abp_connection:
        abp_config.attributes["connection"] = abp_connection
        command.upgrade(abp_config, "head")


class abpUnitOfWork:
    def __init__(self, abp_session: Session) -> None:
        self.abp_session = abp_session
        self.abp_projects = abpProjectRepository(abp_session)
        self.abp_floors = abpFloorRepository(abp_session)
        self.abp_profiles = abpProfileRepository(abp_session)
        self.abp_scenarios = abpScenarioRepository(abp_session)
        self.abp_simulations = abpSimulationRepository(abp_session)
        self.abp_drills = abpRealDrillRepository(abp_session)
        self.abp_rule_verifications = abpRuleVerificationRepository(abp_session)


class abpDatabase:
    def __init__(self, abp_engine: Engine) -> None:
        self.abp_engine = abp_engine
        self.abp__sessions = sessionmaker(abp_engine, expire_on_commit=False)

    @classmethod
    def abp_open(
        cls,
        abp_path: Path,
        *,
        abp_engine_factory: abpEngineFactory = abp_plain_sqlite_engine,
        abp_migrate: bool = True,
        abp_seed_defaults: bool = True,
    ) -> abpDatabase:
        abp_path.parent.mkdir(parents=True, exist_ok=True)
        abp_engine = abp_engine_factory(abp_path)
        if abp_migrate:
            abp_upgrade_to_head(abp_engine)
        abp_database = cls(abp_engine)
        if abp_seed_defaults:
            with abp_database.abp_unit_of_work() as abp_uow:
                abp_uow.abp_profiles.abp_ensure(
                    abp_d.abp_profile for abp_d in abp_load_default_profiles()
                )
        return abp_database

    @contextmanager
    def abp_session(self) -> Iterator[Session]:
        with self.abp__sessions.begin() as abp_session:
            yield abp_session

    @contextmanager
    def abp_unit_of_work(self) -> Iterator[abpUnitOfWork]:
        with self.abp_session() as abp_session:
            yield abpUnitOfWork(abp_session)

    def abp_close(self) -> None:
        self.abp_engine.dispose()
