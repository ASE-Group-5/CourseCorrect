"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api import (
    auth,
    health,
    modifications,
    scheduler,
    schedules,
    scheduling,
    semesters,
    users,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(schedules.router)
app.include_router(users.router)
app.include_router(semesters.router)
app.include_router(scheduler.router)
app.include_router(modifications.router)
app.include_router(scheduling.router)
