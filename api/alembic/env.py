"""Alembic environment.

Lives outside ``app/`` on purpose: migration code is exercised by
``tests/migrations/`` but is not part of the 100% coverage target (plan §10.2).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from app.config import get_settings
from app.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """URL from the command line (``-x`` / programmatic) or from app settings."""
    configured = config.get_main_option("sqlalchemy.url")
    return configured or str(get_settings().database_url)


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DBAPI connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        _do_run_migrations(connectable)
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        _do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
