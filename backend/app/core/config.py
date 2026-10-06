"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache

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
    return Settings()
