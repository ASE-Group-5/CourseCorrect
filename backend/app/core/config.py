"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_url(url: str) -> str:
    """Makes a plain `postgresql://` URL use the psycopg2 driver explicitly."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    """Backend configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CourseCorrect API"
    database_url: str = "sqlite:///./dev.db"
    database_url_direct: str | None = None

    # Login tokens (stories 1-2). No defaults: these must be set in `.env`
    # (`python scripts/dev.py setup` adds them) or, on Render, as environment
    # variables. The secret signs every token, so it must be long and private.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str
    access_token_expire_minutes: int = Field(gt=0)

    @property
    def sqlalchemy_url(self) -> str:
        """URL used by the running application (pooled)."""
        return _normalize_url(self.database_url)

    @property
    def migration_url(self) -> str:
        """URL used by Alembic (direct, falls back to the app URL)."""
        return _normalize_url(self.database_url_direct or self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]  # Fields come from `.env`.
