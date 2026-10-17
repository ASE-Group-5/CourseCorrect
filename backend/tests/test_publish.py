"""Tests for listing and publishing schedules."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.common import RequestStatus, Role, ScheduleStatus
from app.models.course import Course, Semester
from app.models.request import ModificationRequest
from app.models.resources import Room, TimeSlot
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User

AuthHeaders = Callable[[User], dict[str, str]]


def make_user(db_session: Session, username: str, role: Role) -> User:
    user = User(
        username=username,
        email=f"{username}@umkc.edu",
        full_name=username.title(),
        password_hash="x",
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


class World:
    """A semester with one course, one room and one slot, ready to schedule."""

    def __init__(self, db_session: Session, name: str = "Fall 2026") -> None:
        self.db = db_session
        self.semester = Semester(name=name, is_active=name == "Fall 2026")
        self.instructor = make_user(
            db_session, f"prof{name[-4:]}", Role.INSTRUCTOR
        )
        db_session.add(self.semester)
        db_session.flush()
        self.course = Course(
            semester_id=self.semester.id,
            code="CS101",
            name="Intro",
            enrollment=30,
        )
        self.room = Room(name=f"Room {name}", building="Flarsheim", capacity=40)
        self.slot = TimeSlot(hour=9 + len(name) % 5, label=f"slot {name}")
        db_session.add_all([self.course, self.room, self.slot])
        db_session.commit()

    def schedule(
        self, status: ScheduleStatus, conflicts: int = 0
    ) -> tuple[Schedule, ScheduleEntry]:
        schedule = Schedule(
            semester_id=self.semester.id,
            status=status,
            fitness=1.0,
            generation_found=1,
            generations_run=1,
            report={
                "soft_violations": [],
                "hard_violations": [{"message": "clash"}] * conflicts,
            },
        )
        self.db.add(schedule)
        self.db.flush()
        entry = ScheduleEntry(
            schedule_id=schedule.id,
            course_id=self.course.id,
            instructor_id=self.instructor.id,
            room_id=self.room.id,
            time_slot_id=self.slot.id,
        )
        self.db.add(entry)
        self.db.commit()
        return schedule, entry


@pytest.fixture()
def coordinator(db_session: Session) -> User:
    return make_user(db_session, "amorgan", Role.COORDINATOR)


@pytest.fixture()
def headers(coordinator: User, auth_headers: AuthHeaders) -> dict[str, str]:
    return auth_headers(coordinator)


@pytest.mark.parametrize("role", [Role.STUDENT, Role.INSTRUCTOR])
@pytest.mark.parametrize(
    "method, path", [("GET", "/schedules"), ("POST", "/schedules/1/publish")]
)
def test_only_coordinators_list_and_publish(
    client: TestClient,
    db_session: Session,
    auth_headers: AuthHeaders,
    role: Role,
    method: str,
    path: str,
) -> None:
    user = make_user(db_session, "someone", role)

    response = client.request(method, path, headers=auth_headers(user))

    assert response.status_code == 403


def test_list_schedules_for_active_semester_newest_first(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    world = World(db_session)
    published, _ = world.schedule(ScheduleStatus.PUBLISHED)
    draft, _ = world.schedule(ScheduleStatus.DRAFT, conflicts=2)
    World(db_session, "Spring 2027").schedule(ScheduleStatus.DRAFT)

    response = client.get("/schedules", headers=headers)

    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == [draft.id, published.id]
    assert rows[0]["status"] == "draft"
    assert rows[0]["conflicts"] == 2
    assert rows[0]["classes"] == 1


def test_publish_replaces_published_schedule(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    world = World(db_session)
    old, _ = world.schedule(ScheduleStatus.PUBLISHED)
    new, _ = world.schedule(ScheduleStatus.DRAFT)

    response = client.post(f"/schedules/{new.id}/publish", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "schedule_id": new.id,
        "unpublished": [old.id],
        "declined": 0,
    }
    db_session.refresh(old)
    db_session.refresh(new)
    assert old.status == ScheduleStatus.DRAFT
    assert new.status == ScheduleStatus.PUBLISHED


def test_publish_declines_pending_requests_on_replaced_schedule(
    client: TestClient,
    db_session: Session,
    coordinator: User,
    headers: dict[str, str],
) -> None:
    world = World(db_session)
    old, old_entry = world.schedule(ScheduleStatus.PUBLISHED)
    new, _ = world.schedule(ScheduleStatus.DRAFT)
    pending = ModificationRequest(
        schedule_entry_id=old_entry.id,
        requester_id=world.instructor.id,
        reason="Move me",
    )
    accepted = ModificationRequest(
        schedule_entry_id=old_entry.id,
        requester_id=world.instructor.id,
        reason="Done already",
        status=RequestStatus.ACCEPTED,
    )
    db_session.add_all([pending, accepted])
    db_session.commit()

    response = client.post(f"/schedules/{new.id}/publish", headers=headers)

    assert response.json()["declined"] == 1
    db_session.refresh(pending)
    db_session.refresh(accepted)
    assert pending.status == RequestStatus.DECLINED
    assert pending.reviewed_by_id == coordinator.id
    assert pending.resolved_at is not None
    assert f"#{new.id}" in pending.reviewer_comment
    assert accepted.status == RequestStatus.ACCEPTED


def test_publish_leaves_other_semesters_alone(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    other, _ = World(db_session, "Spring 2027").schedule(
        ScheduleStatus.PUBLISHED
    )
    draft, _ = World(db_session).schedule(ScheduleStatus.DRAFT)

    client.post(f"/schedules/{draft.id}/publish", headers=headers)

    db_session.refresh(other)
    assert other.status == ScheduleStatus.PUBLISHED


def test_publish_already_published_changes_nothing(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    published, _ = World(db_session).schedule(ScheduleStatus.PUBLISHED)

    response = client.post(
        f"/schedules/{published.id}/publish", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["unpublished"] == []


def test_publish_refuses_schedule_with_conflicts(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    world = World(db_session)
    old, _ = world.schedule(ScheduleStatus.PUBLISHED)
    clashing, _ = world.schedule(ScheduleStatus.DRAFT, conflicts=1)

    response = client.post(f"/schedules/{clashing.id}/publish", headers=headers)

    assert response.status_code == 409
    db_session.refresh(old)
    assert old.status == ScheduleStatus.PUBLISHED


def test_publish_unknown_schedule_returns_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/schedules/999/publish", headers=headers)

    assert response.status_code == 404


def test_published_schedule_is_what_instructors_see(
    client: TestClient,
    db_session: Session,
    headers: dict[str, str],
    auth_headers: AuthHeaders,
) -> None:
    world = World(db_session)
    world.schedule(ScheduleStatus.PUBLISHED)
    new, entry = world.schedule(ScheduleStatus.DRAFT)
    later_slot = TimeSlot(hour=15, label="3PM")
    db_session.add(later_slot)
    db_session.flush()
    entry.time_slot_id = later_slot.id
    db_session.commit()

    client.post(f"/schedules/{new.id}/publish", headers=headers)
    response = client.get(
        f"/schedules/instructor/{world.instructor.username}",
        headers=auth_headers(world.instructor),
    )

    assert [row["time_slot_label"] for row in response.json()] == ["3PM"]


def test_schedule_entries_lists_classes(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    world = World(db_session)
    draft, _ = world.schedule(ScheduleStatus.DRAFT)

    response = client.get(f"/schedules/{draft.id}/entries", headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "course_code": "CS101",
            "course_name": "Intro",
            "time_slot_label": world.slot.label,
            "room_name": world.room.name,
            "room_building": "Flarsheim",
            "instructor_name": world.instructor.full_name,
        }
    ]


def test_schedule_entries_coordinators_only(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    world = World(db_session)
    draft, _ = world.schedule(ScheduleStatus.DRAFT)

    response = client.get(
        f"/schedules/{draft.id}/entries",
        headers=auth_headers(world.instructor),
    )

    assert response.status_code == 403


def test_schedule_entries_unknown_schedule_returns_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/schedules/999/entries", headers=headers)

    assert response.status_code == 404
