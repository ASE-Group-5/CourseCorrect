"""Tests for the opt-in Sprint 1 calendar date assumptions."""

from datetime import date

from fastapi.testclient import TestClient

from app.api import calendar as calendar_api
from app.api.deps import get_current_user
from app.main import app
from app.models.calendar import CalendarLink
from app.models.common import Role
from app.models.user import User
from app.services.calendar_demo import (
    DEMO_END,
    DEMO_START,
    DEMO_TIMEZONE,
    build_demo_event,
    demo_mode_enabled,
)
from app.services.calendar_security import encrypt_refresh_token
from tests.test_user_stories_7_8 import make_schedule


def test_demo_mode_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "false")
    assert demo_mode_enabled() is False


def test_demo_mode_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "true")
    assert demo_mode_enabled() is True
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "off")
    assert demo_mode_enabled() is False


def test_demo_event_uses_boundaries_timezone_and_database_fields(db_session) -> None:
    _coordinator, entry = make_schedule(db_session)
    event = build_demo_event(entry)

    assert DEMO_START == date(2027, 1, 11)
    assert DEMO_END == date(2027, 5, 7)
    assert event["summary"] == "CS101: Intro to CS"
    assert event["location"] == "Room A, Flarsheim"
    assert event["start"] == {
        "dateTime": "2027-01-11T09:00:00-06:00",
        "timeZone": DEMO_TIMEZONE,
    }
    assert event["end"] == {
        "dateTime": "2027-01-11T10:00:00-06:00",
        "timeZone": DEMO_TIMEZONE,
    }
    assert event["recurrence"] == [
        "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20270508T045959Z"
    ]


def test_enabled_push_uses_only_authenticated_instructor_entries(
    client: TestClient, db_session, monkeypatch
) -> None:
    _coordinator, entry = make_schedule(db_session)
    db_session.add(
        CalendarLink(
            user_id=entry.instructor_id,
            calendar_id="primary",
            refresh_token=encrypt_refresh_token("refresh-token"),
        )
    )
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: entry.instructor
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "1")
    captured = {}

    def fake_push(_db, _link, events):
        captured["events"] = events
        return len(events)

    monkeypatch.setattr(calendar_api, "push_events", fake_push)
    response = client.post("/calendar/push")

    assert response.status_code == 200
    assert response.json() == {"events_created": 1}
    assert captured["events"][0]["_coursecorrect_event_key"].startswith("demo-")


def test_google_failure_does_not_report_success(
    client: TestClient, db_session, monkeypatch
) -> None:
    _coordinator, entry = make_schedule(db_session)
    db_session.add(
        CalendarLink(
            user_id=entry.instructor_id,
            calendar_id="primary",
            refresh_token=encrypt_refresh_token("refresh-token"),
        )
    )
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: entry.instructor
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "true")

    def fail_push(*_args):
        raise RuntimeError("Google Calendar unavailable")

    monkeypatch.setattr(calendar_api, "push_events", fail_push)
    response = client.post("/calendar/push")

    assert response.status_code == 502
    assert response.json()["detail"] == "Google Calendar unavailable"


def test_no_calendar_still_wins_when_demo_mode_is_enabled(
    client: TestClient, db_session, monkeypatch
) -> None:
    instructor = User(
        username="jdoe",
        email="jdoe@umkc.edu",
        full_name="Jane Doe",
        password_hash="x",
        role=Role.INSTRUCTOR,
    )
    db_session.add(instructor)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: instructor
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "true")

    response = client.post("/calendar/push")

    assert response.status_code == 404
    assert response.json()["detail"] == "No calendar found"
