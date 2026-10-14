"""Tests for the instructor schedule endpoint (acceptance criterion 4.1)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.common import Role, ScheduleStatus
from app.models.course import Course, Enrollment, Semester
from app.models.resources import Room, TimeSlot
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User


def test_instructor_schedule_returns_course_code(
    client: TestClient, db_session: Session
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

    response = client.get(f"/schedules/instructor/{instructor.username}")

    assert response.status_code == 200
    codes = [entry["course_code"] for entry in response.json()]
    assert "CS101" in codes


def test_instructor_schedule_unknown_username_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/schedules/instructor/nobody")

    assert response.status_code == 404


def test_student_schedule_returns_enrolled_course_code(
    client: TestClient, db_session: Session
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

    response = client.get(f"/schedules/student/{student.username}")

    assert response.status_code == 200
    codes = [entry["course_code"] for entry in response.json()]
    assert "CS101" in codes


def test_student_schedule_unknown_username_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/schedules/student/nobody")

    assert response.status_code == 404


def test_student_schedule_no_enrollments_returns_empty(
    client: TestClient, db_session: Session
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

    response = client.get(f"/schedules/student/{student.username}")

    assert response.status_code == 200
    assert response.json() == []


def test_student_schedule_non_student_returns_404(
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

    response = client.get(f"/schedules/student/{instructor.username}")

    assert response.status_code == 404
