"""Health-check endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check (does not touch the database)."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness check that verifies the database connection."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=503, detail="Database unavailable"
        ) from exc
    return {"status": "ok", "database": "connected"}
