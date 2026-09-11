"""Application settings.

Settings come only from here. The app refuses to start when a required secret is
missing or has been left at the placeholder value shipped in ``.env.example``.
"""

from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Placeholder values committed in ``.env.example``. Keeping a real deployment on
#: one of these would give every install the same secret, so it is a startup error.
EXAMPLE_VALUES: frozenset[str] = frozenset(
    {
        "change-me-session-secret",
        "change-me-postgres-password",
    }
)


class Settings(BaseSettings):
    """Runtime configuration, read from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn
    session_secret: SecretStr

    log_level: str = "INFO"

    # Argon2id parameters. Defaults match argon2-cffi's own defaults; tests lower
    # them so hashing does not dominate the suite runtime.
    argon2_time_cost: Annotated[int, Field(ge=1)] = 3
    argon2_memory_cost: Annotated[int, Field(ge=8)] = 65536
    argon2_parallelism: Annotated[int, Field(ge=1)] = 4

    @model_validator(mode="after")
    def _reject_example_values(self) -> Self:
        if self.session_secret.get_secret_value() in EXAMPLE_VALUES:
            msg = "session_secret is still set to its .env.example placeholder"
            raise ValueError(msg)
        if any(value in str(self.database_url) for value in EXAMPLE_VALUES):
            msg = "database_url still contains an .env.example placeholder"
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, constructed once."""
    return Settings()
