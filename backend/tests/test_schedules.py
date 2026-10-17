"""Tests for the schedule endpoints (acceptance criteria 4.1 and 9.1)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.common import Role, ScheduleStatus
from app.models.course import Course, Enrollment, Semester
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


def test_instructor_schedule_returns_course_code(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    semester = Semester(name="Fall 2026", is_active=True)
    instructor = User(
        username="jdoe",
        email="jdoe@umkc.edu",
        full_name="Jane Doe",
        password_hash="x",
        role=Role.INSTRUCTOR,
    )
    db_session.add_all([semester, instructor])
    db_session.flush()

    course = Course(
        semester_id=semester.id, code="CS101", name="Intro to CS", enrollment=30
    )
    room = Room(name="Room A", building="Flarsheim", capacity=40)
    time_slot = TimeSlot(hour=9, label="9:00 AM")
    db_session.add_all([course, room, time_slot])
    db_session.flush()

    schedule = Schedule(
        semester_id=semester.id,
        status=ScheduleStatus.PUBLISHED,
        fitness=1.0,
        generation_found=1,
        generations_run=1,
    )
    db_session.add(schedule)
    db_session.flush()

    entry = ScheduleEntry(
        schedule_id=schedule.id,
        course_id=course.id,
        instructor_id=instructor.id,
        room_id=room.id,
        time_slot_id=time_slot.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = client.get(
        f"/schedules/instructor/{instructor.username}",
        headers=auth_headers(instructor),
    )

    assert response.status_code == 200
    codes = [entry["course_code"] for entry in response.json()]
    assert "CS101" in codes


def test_instructor_schedule_unknown_username_returns_404(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    coordinator = make_user(db_session, "amorgan", Role.COORDINATOR)

    response = client.get(
        "/schedules/instructor/nobody", headers=auth_headers(coordinator)
    )

    assert response.status_code == 404


def test_student_schedule_returns_enrolled_course_code(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    semester = Semester(name="Fall 2026", is_active=True)
    student = User(
        username="sstudent",
        email="sstudent@umkc.edu",
        full_name="Sam Student",
        password_hash="x",
        role=Role.STUDENT,
    )
    instructor = User(
        username="jdoe",
        email="jdoe@umkc.edu",
        full_name="Jane Doe",
        password_hash="x",
        role=Role.INSTRUCTOR,
    )
    db_session.add_all([semester, student, instructor])
    db_session.flush()

    course = Course(
        semester_id=semester.id, code="CS101", name="Intro to CS", enrollment=30
    )
    room = Room(name="Room A", building="Flarsheim", capacity=40)
    time_slot = TimeSlot(hour=9, label="9:00 AM")
    db_session.add_all([course, room, time_slot])
    db_session.flush()

    schedule = Schedule(
        semester_id=semester.id,
        status=ScheduleStatus.PUBLISHED,
        fitness=1.0,
        generation_found=1,
        generations_run=1,
    )
    db_session.add(schedule)
    db_session.flush()

    entry = ScheduleEntry(
        schedule_id=schedule.id,
        course_id=course.id,
        instructor_id=instructor.id,
        room_id=room.id,
        time_slot_id=time_slot.id,
    )
    enrollment = Enrollment(student_id=student.id, course_id=course.id)
    db_session.add_all([entry, enrollment])
    db_session.commit()

    response = client.get(
        f"/schedules/student/{student.username}",
        headers=auth_headers(student),
    )

    assert response.status_code == 200
    codes = [entry["course_code"] for entry in response.json()]
    assert "CS101" in codes


def test_student_schedule_unknown_username_returns_404(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    coordinator = make_user(db_session, "amorgan", Role.COORDINATOR)

    response = client.get(
        "/schedules/student/nobody", headers=auth_headers(coordinator)
    )

    assert response.status_code == 404


def test_student_schedule_no_enrollments_returns_empty(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    student = User(
        username="sstudent",
        email="sstudent@umkc.edu",
        full_name="Sam Student",
        password_hash="x",
        role=Role.STUDENT,
    )
    db_session.add(student)
    db_session.commit()

    response = client.get(
        f"/schedules/student/{student.username}",
        headers=auth_headers(student),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_student_schedule_non_student_returns_404(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
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
    coordinator = make_user(db_session, "amorgan", Role.COORDINATOR)

    response = client.get(
        f"/schedules/student/{instructor.username}",
        headers=auth_headers(coordinator),
    )

    assert response.status_code == 404


# --- Security gate: own schedule only, coordinators may view anyone's -------


def test_schedules_require_login(client: TestClient) -> None:
    assert client.get("/schedules/instructor/jdoe").status_code == 401
    assert client.get("/schedules/student/sstudent").status_code == 401


def test_student_cannot_view_another_students_schedule(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)
    make_user(db_session, "other", Role.STUDENT)

    response = client.get(
        "/schedules/student/other", headers=auth_headers(student)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only view your own schedule"


def test_instructor_cannot_view_another_instructors_schedule(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)
    make_user(db_session, "other", Role.INSTRUCTOR)

    response = client.get(
        "/schedules/instructor/other", headers=auth_headers(instructor)
    )

    assert response.status_code == 403


def test_student_cannot_use_instructor_route(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)

    response = client.get(
        "/schedules/instructor/sstudent", headers=auth_headers(student)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed for your role"


def test_instructor_cannot_use_student_route(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)

    response = client.get(
        "/schedules/student/sstudent", headers=auth_headers(instructor)
    )

    assert response.status_code == 403


def test_coordinator_can_view_any_schedule(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    coordinator = make_user(db_session, "amorgan", Role.COORDINATOR)
    make_user(db_session, "jdoe", Role.INSTRUCTOR)
    make_user(db_session, "sstudent", Role.STUDENT)
    headers = auth_headers(coordinator)

    instructor_response = client.get(
        "/schedules/instructor/jdoe", headers=headers
    )
    student_response = client.get(
        "/schedules/student/sstudent", headers=headers
    )

    assert instructor_response.status_code == 200
    assert student_response.status_code == 200
