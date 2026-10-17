"""Personal calendar synchronization endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import instructor_only
from app.db.session import get_db
from app.models.calendar import CalendarLink
from app.models.common import ScheduleStatus
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User
from app.services.calendar import push_events
from app.services.calendar_demo import build_demo_event, demo_mode_enabled
from app.services.calendar_security import decrypt_refresh_token

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/push")
def push_schedule_to_calendar(
    user: User = Depends(instructor_only), db: Session = Depends(get_db)
) -> dict[str, int | str]:
    """Push the current instructor schedule to their linked calendar."""
    link = (
        db.query(CalendarLink).filter(CalendarLink.user_id == user.id).first()
    )
    if link is None or not link.refresh_token:
        raise HTTPException(status_code=404, detail="No calendar found")
    try:
        decrypt_refresh_token(link.refresh_token)
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=404, detail="No calendar found") from None

    schedule = (
        db.query(Schedule)
        .join(Schedule.semester)
        .filter(
            Schedule.status == ScheduleStatus.PUBLISHED,
            Schedule.semester.has(is_active=True),
        )
        .first()
    )
    entries = (
        []
        if schedule is None
        else (
            db.query(ScheduleEntry)
            .filter(
                ScheduleEntry.schedule_id == schedule.id,
                ScheduleEntry.instructor_id == user.id,
            )
            .all()
        )
    )
    if not entries:
        raise HTTPException(
            status_code=422,
            detail="No generated schedule entries are available",
        )
    if not demo_mode_enabled():
        raise HTTPException(
            status_code=422,
            detail=(
                "Schedule date information is unavailable; calendar sync "
                "requires a real date or recurrence value"
            ),
        )
    try:
        events_created = push_events(
            db, link, [build_demo_event(entry) for entry in entries]
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Google Calendar synchronization failed",
        ) from exc
    return {"events_created": events_created}
