from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, create_engine

from abp_rutasegura.abp_data.abp_models import abpBase

abp_config = context.config
abp_target_metadata = abpBase.metadata


def abp__configure_and_run(abp_connection: Connection) -> None:
    context.configure(
        connection=abp_connection,
        target_metadata=abp_target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def abp_run_migrations_offline() -> None:
    context.configure(
        url=abp_config.get_main_option("sqlalchemy.url"),
        target_metadata=abp_target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def abp_run_migrations_online() -> None:
    abp_connection = abp_config.attributes.get("connection")
    if abp_connection is not None:
        abp__configure_and_run(abp_connection)
        return
    abp_url = abp_config.get_main_option("sqlalchemy.url")
    if abp_url is None:
        raise RuntimeError("Falta sqlalchemy.url en alembic.ini")
    abp_engine = create_engine(abp_url)
    with abp_engine.begin() as abp_conn:
        abp__configure_and_run(abp_conn)
    abp_engine.dispose()


if context.is_offline_mode():
    abp_run_migrations_offline()
else:
    abp_run_migrations_online()
