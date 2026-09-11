"""Startup must fail on a missing secret or one left at its example value."""

import pytest
from pydantic import ValidationError

from app.config import EXAMPLE_VALUES, Settings, get_settings

VALID_URL = "postgresql+psycopg://user:pw@db:5432/tour"


def _settings(url: str = VALID_URL, secret: str = "a-real-secret") -> Settings:
    return Settings(database_url=url, session_secret=secret)


def test_valid_settings_build(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()

    assert settings.session_secret.get_secret_value() == "a-real-secret"
    assert str(settings.database_url).startswith("postgresql+psycopg://")


def test_missing_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", VALID_URL)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    assert "session_secret" in str(excinfo.value)


def test_example_session_secret_raises() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(secret="change-me-session-secret")

    assert ".env.example placeholder" in str(excinfo.value)


def test_example_password_in_database_url_raises() -> None:
    url = "postgresql+psycopg://user:change-me-postgres-password@db:5432/tour"

    with pytest.raises(ValidationError) as excinfo:
        _settings(url=url)

    assert ".env.example placeholder" in str(excinfo.value)


def test_every_example_value_is_rejected_somewhere() -> None:
    """Guards against adding a placeholder to the set without checking it."""
    assert EXAMPLE_VALUES


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("SESSION_SECRET", "a-real-secret")
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
