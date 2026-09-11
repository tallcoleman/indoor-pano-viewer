"""Shared fixtures: a real Postgres 18, per-test rollback, and an HTTP client.

Never SQLite: ``citext``, native enums and ``uuidv7()`` do not exist there.
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db
from app.main import create_app

ALEMBIC_INI = "alembic.ini"


def alembic_config(url: str) -> Config:
    """An Alembic config pointed at ``url``."""
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """URL of a Postgres 18 server: ``TEST_DATABASE_URL`` or a container."""
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        yield configured
        return

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:18", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Engine against a schema migrated once for the whole session."""
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    """An outer transaction that is always rolled back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def db_session(connection: Connection) -> Iterator[Session]:
    """A session nested in the outer transaction via SAVEPOINT."""
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Settings that are valid but cheap: Argon2 at its minimum cost."""
    return Settings(
        database_url=database_url,
        session_secret="test-session-secret",
        argon2_time_cost=1,
        argon2_memory_cost=8,
        argon2_parallelism=1,
    )


@pytest.fixture
def app(db_session: Session) -> Iterator[FastAPI]:
    """The application, with the DB dependency bound to the rolled-back session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """httpx client talking to the ASGI app in-process; no network."""
    with TestClient(app) as client:
        yield client
