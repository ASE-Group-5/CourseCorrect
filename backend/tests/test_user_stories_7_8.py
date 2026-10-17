"""Acceptance tests for modification requests and calendar synchronization."""

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import current_user
from app.main import app
from app.models.calendar import CalendarLink
from app.models.common import RequestStatus, Role, ScheduleStatus
from app.models.course import Course, Semester
from app.models.request import ModificationRequest
from app.models.resources import Room, TimeSlot
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User


def make_schedule(db_session: Session) -> tuple[User, ScheduleEntry]:
    semester = Semester(name="Fall 2026", is_active=True)
    instructor = User(
        username="jdoe",
        email="jdoe@umkc.edu",
        full_name="Jane Doe",
        password_hash="x",
        role=Role.INSTRUCTOR,
    )
    coordinator = User(
        username="admin",
        email="admin@umkc.edu",
        full_name="Admin User",
        password_hash="x",
        role=Role.COORDINATOR,
    )
    course = Course(
        semester=semester, code="CS101", name="Intro to CS", enrollment=30
    )
    room = Room(name="Room A", building="Flarsheim", capacity=40)
    time_slot = TimeSlot(hour=9, label="9:00 AM")
    schedule = Schedule(
        semester=semester,
        status=ScheduleStatus.PUBLISHED,
        fitness=1.0,
        generation_found=1,
        generations_run=1,
    )
    db_session.add_all(
        [instructor, coordinator, course, room, time_slot, schedule]
    )
    db_session.flush()
    entry = ScheduleEntry(
        schedule=schedule,
        course=course,
        instructor=instructor,
        room=room,
        time_slot=time_slot,
    )
    db_session.add(entry)
    db_session.commit()
    return coordinator, entry


def test_protected_endpoint_requires_shared_authentication(
    client: TestClient,
) -> None:
    response = client.get("/requests/open")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_coordinator_views_open_requests(
    client: TestClient, db_session: Session
) -> None:
    coordinator, entry = make_schedule(db_session)
    request = ModificationRequest(
        entry=entry,
        requester=entry.instructor,
        assigned_to=coordinator,
        reason="Please move the class.",
        status=RequestStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(request)
    db_session.commit()
    app.dependency_overrides[current_user] = lambda: coordinator

    response = client.get("/requests/open")

    assert response.status_code == 200
    assert response.json()[0]["course_code"] == "CS101"
    assert response.json()[0]["status"] == "pending"


def test_coordinator_views_all_pending_requests(
    client: TestClient, db_session: Session
) -> None:
    coordinator, entry = make_schedule(db_session)
    other_coordinator = User(
        username="other-admin",
        email="other-admin@umkc.edu",
        full_name="Other Admin",
        password_hash="x",
        role=Role.COORDINATOR,
    )
    db_session.add(other_coordinator)
    db_session.flush()
    db_session.add_all(
        [
            ModificationRequest(
                entry=entry,
                requester=entry.instructor,
                assigned_to=coordinator,
                reason="Move the room.",
                status=RequestStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            ),
            ModificationRequest(
                entry=entry,
                requester=entry.instructor,
                assigned_to=other_coordinator,
                reason="Move the time.",
                status=RequestStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()
    app.dependency_overrides[current_user] = lambda: coordinator

    response = client.get("/requests/open")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_open_requests_returns_empty_list(
    client: TestClient, db_session: Session
) -> None:
    db_session.add(
        User(
            username="admin",
            email="admin@umkc.edu",
            full_name="Admin User",
            password_hash="x",
            role=Role.COORDINATOR,
        )
    )
    db_session.commit()
    app.dependency_overrides[current_user] = lambda: (
        db_session.query(User).filter(User.username == "admin").one()
    )
    response = client.get("/requests/open")

    assert response.status_code == 200
    assert response.json() == []


def test_non_coordinator_cannot_view_open_requests(
    client: TestClient, db_session: Session
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
    app.dependency_overrides[current_user] = lambda: instructor

    response = client.get("/requests/open")

    assert response.status_code == 403


def test_build_event_uses_explicit_schedule_date(
    db_session: Session,
) -> None:
    _coordinator, entry = make_schedule(db_session)
    from app.services.calendar import build_event

    event = build_event(entry, date(2026, 10, 20))

    assert event["summary"] == "CS101: Intro to CS"
    assert event["location"] == "Room A, Flarsheim"
    assert event["start"]["dateTime"].startswith("2026-10-20T09:00:00")


def test_push_schedule_without_schedule_date_returns_validation_error(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    from app.services.calendar_security import encrypt_refresh_token

    _coordinator, entry = make_schedule(db_session)
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "false")
    db_session.add(
        CalendarLink(
            user_id=entry.instructor_id,
            calendar_id="jane@example.com",
            refresh_token=encrypt_refresh_token("refresh-token"),
        )
    )
    db_session.commit()
    app.dependency_overrides[current_user] = lambda: entry.instructor

    response = client.post("/calendar/push")

    assert response.status_code == 422
    assert "date information is unavailable" in response.json()["detail"]


def test_push_schedule_without_calendar_returns_clear_error(
    client: TestClient, db_session: Session, monkeypatch
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
    app.dependency_overrides[current_user] = lambda: instructor

    class UnexpectedCalendarCall:
        def __init__(self, _link):
            raise AssertionError("calendar service must not be constructed")

    monkeypatch.setattr(
        "app.services.calendar.GoogleCalendarService", UnexpectedCalendarCall
    )

    response = client.post("/calendar/push")

    assert response.status_code == 404
    assert response.json()["detail"] == "No calendar found"


def test_calendar_service_does_not_report_success_without_oauth_token() -> None:
    from app.services.calendar import GoogleCalendarService

    link = CalendarLink(
        user_id=1,
        calendar_id="jane@example.com",
        refresh_token=None,
    )

    with pytest.raises(ValueError, match="refresh token"):
        GoogleCalendarService(link).push([])
