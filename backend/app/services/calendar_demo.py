"""Opt-in temporary calendar dates for the Sprint 1 demonstration."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.schedule import ScheduleEntry

DEMO_MODE_ENV = "CALENDAR_DEMO_MODE"
DEMO_START = date(2027, 1, 11)
DEMO_END = date(2027, 5, 7)
DEMO_TIMEZONE = "America/Chicago"
DEMO_DAYS = ("MO", "WE")
DEMO_DURATION = timedelta(minutes=60)


@dataclass(frozen=True)
class CalendarDemoConfig:
    """Temporary date assumptions used only when demo mode is enabled."""

    start_date: date = DEMO_START
    end_date: date = DEMO_END
    timezone: str = DEMO_TIMEZONE
    meeting_days: tuple[str, ...] = DEMO_DAYS
    duration: timedelta = DEMO_DURATION


def demo_mode_enabled() -> bool:
    """Return whether the temporary demo-date behavior is explicitly enabled."""
    import os

    raw_value = os.getenv(DEMO_MODE_ENV)
    if raw_value is not None:
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    from app.core.config import get_settings

    return get_settings().calendar_demo_mode


def demo_config() -> CalendarDemoConfig:
    """Return validated, immutable demonstration settings."""
    config = CalendarDemoConfig()
    if config.start_date > config.end_date:
        raise ValueError("Calendar demo start date must precede its end date")
    ZoneInfo(config.timezone)
    return config


def build_demo_event(entry: ScheduleEntry) -> dict[str, object]:
    """Build one recurring event from database-owned course, room, and hour data."""
    config = demo_config()
    zone = ZoneInfo(config.timezone)
    start = datetime.combine(
        config.start_date, time(entry.time_slot.hour), tzinfo=zone
    )
    end = start + config.duration
    until = datetime.combine(
        config.end_date, time(23, 59, 59), tzinfo=zone
    ).astimezone(timezone.utc)
    return {
        "_coursecorrect_event_key": (
            f"demo-{entry.schedule_id}-{entry.id}-{config.start_date}-"
            f"{config.end_date}"
        ),
        "summary": f"{entry.course.code}: {entry.course.name}",
        "description": "CourseCorrect Sprint 1 demo schedule",
        "location": f"{entry.room.name}, {entry.room.building}",
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": config.timezone,
        },
        "end": {"dateTime": end.isoformat(), "timeZone": config.timezone},
        "recurrence": [
            "RRULE:FREQ=WEEKLY;BYDAY="
            + ",".join(config.meeting_days)
            + f";UNTIL={until.strftime('%Y%m%dT%H%M%SZ')}"
        ],
    }
