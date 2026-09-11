"""The real ``get_db`` dependency, which API tests override away."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app import db
from app.config import Settings


@pytest.fixture(autouse=True)
def _real_engine(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the module's caches at the test database and tear them down cleanly."""
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    yield
    db.get_engine().dispose()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()


def test_get_engine_is_cached() -> None:
    engine = db.get_engine()

    assert isinstance(engine, Engine)
    assert db.get_engine() is engine


def test_get_db_yields_a_working_session_and_closes_it() -> None:
    generator = db.get_db()
    session = next(generator)

    assert session.execute(text("SELECT 1")).scalar_one() == 1

    with pytest.raises(StopIteration):
        next(generator)
    assert session.get_transaction() is None
