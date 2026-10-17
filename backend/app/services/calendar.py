"""Calendar synchronization service."""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.calendar import CalendarEventSync, CalendarLink
from app.models.schedule import ScheduleEntry
from app.services.calendar_security import decrypt_refresh_token

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def build_event(
    entry: ScheduleEntry,
    event_date: date,
) -> dict[str, Any]:
    """Build a Google Calendar event from a schedule entry."""

    start = datetime.combine(
        event_date,
        datetime.min.time(),
    ).replace(hour=entry.time_slot.hour)

    end = start + timedelta(hours=1)

    return {
        "summary": f"{entry.course.code}: {entry.course.name}",
        "description": (f"CourseCorrect schedule for {entry.course.code}"),
        "location": f"{entry.room.name}, {entry.room.building}",
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "UTC",
        },
    }


class GoogleCalendarService:
    """Push events to Google Calendar using stored OAuth credentials."""

    def __init__(self, link: CalendarLink) -> None:
        self.link = link

    def _get_credentials(self) -> Any:
        """Construct Google credentials using the OAuth client settings."""

        if not self.link.refresh_token:
            raise ValueError("Calendar link is missing an OAuth refresh token")

        try:
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise RuntimeError(
                "Google Calendar dependencies are not installed"
            ) from exc

        settings = get_settings()

        refresh_token = decrypt_refresh_token(self.link.refresh_token)

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=GOOGLE_CALENDAR_SCOPES,
        )

        return credentials

    def push(self, events: list[dict[str, Any]]) -> int:
        """Create events and return the number created."""

        if not self.link.refresh_token:
            raise ValueError("Calendar link is missing an OAuth refresh token")

        return sum(self.insert_event(event) is not None for event in events)

    def validate_credentials(self) -> None:
        """Refresh Google credentials without creating calendar events."""

        try:
            from google.auth.exceptions import RefreshError
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise RuntimeError(
                "Google Calendar dependencies are not installed"
            ) from exc

        credentials = self._get_credentials()

        try:
            credentials.refresh(Request())

        except RefreshError as exc:
            raise ValueError(
                "Google Calendar authorization was revoked"
            ) from exc

    def insert_event(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert one Google Calendar event."""

        _validate_event(event)

        try:
            from google.auth.exceptions import RefreshError
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Calendar dependencies are not installed"
            ) from exc

        credentials = self._get_credentials()

        try:
            credentials.refresh(Request())

            calendar = build(
                "calendar",
                "v3",
                credentials=credentials,
            )

            return (
                calendar.events()
                .insert(
                    calendarId=self.link.calendar_id,
                    body=event,
                )
                .execute()
            )

        except RefreshError as exc:
            raise ValueError(
                "Google Calendar authorization was revoked"
            ) from exc


def push_events(
    db: Session,
    link: CalendarLink,
    events: list[dict[str, Any]],
    service_factory: Callable[
        [CalendarLink], GoogleCalendarService
    ] = GoogleCalendarService,
) -> int:
    """Insert events once and persist Google event IDs."""

    service = service_factory(link)

    created = 0

    for source_event in events:
        event = dict(source_event)

        event_key = event.pop(
            "_coursecorrect_event_key",
            None,
        )

        if not event_key:
            raise ValueError("Calendar events require a stable event key")

        existing = (
            db.query(CalendarEventSync)
            .filter(
                CalendarEventSync.calendar_link_id == link.id,
                CalendarEventSync.event_key == event_key,
            )
            .first()
        )

        if existing is not None:
            continue

        google_event = service.insert_event(event)

        db.add(
            CalendarEventSync(
                calendar_link_id=link.id,
                event_key=event_key,
                google_event_id=google_event["id"],
            )
        )

        db.commit()
        created += 1

    return created


CalendarServiceFactory = Callable[[CalendarLink], GoogleCalendarService]


def _validate_event(event: dict[str, Any]) -> None:
    """Reject incomplete calendar event payloads."""

    for field in ("start", "end"):
        value = event.get(field)

        if not isinstance(value, dict):
            raise ValueError(f"Calendar event is missing {field} time")

        if not value.get("dateTime") or not value.get("timeZone"):
            raise ValueError(
                f"Calendar event {field} requires dateTime and timeZone"
            )
