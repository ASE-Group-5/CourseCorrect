"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api import (
    auth,
    calendar_oauth,
    health,
    modifications,
    scheduler,
    schedules,
    scheduling,
    semesters,
    users,
)
from app.api import calendar as calendar_api
from app.api import requests as requests_api
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
app.include_router(requests_api.router)
app.include_router(calendar_api.router)
app.include_router(calendar_oauth.router)
