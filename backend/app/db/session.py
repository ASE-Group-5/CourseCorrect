"""Database engine and session management."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
_connect_args = (
    {"check_same_thread": False}
    if _settings.sqlalchemy_url.startswith("sqlite")
    else {}
)

# pool_pre_ping avoids errors when Neon has suspended an idle compute.
engine = create_engine(
    _settings.sqlalchemy_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
