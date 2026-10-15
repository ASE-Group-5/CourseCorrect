"""Tests for coordinator user management (users and semesters endpoints)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.common import CoursePreference, Role, ScheduleStatus
from app.models.course import Course, CourseInstructor, Enrollment, Semester
from app.models.resources import Room, TimeSlot
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User

AuthHeaders = Callable[[User], dict[str, str]]
PASSWORD = "Password123!"
PASSWORD_HASH = hash_password(PASSWORD)  # bcrypt is slow: hash once.


def make_user(
    db_session: Session,
    username: str,
    role: Role,
    coordinator_id: int | None = None,
) -> User:
    user = User(
        username=username,
        email=f"{username}@umkc.edu",
        full_name=username.title(),
        password_hash=PASSWORD_HASH,
        role=role,
        coordinator_id=coordinator_id,
    )
    db_session.add(user)
    db_session.commit()
    return user


def make_semester(
    db_session: Session, name: str, codes: list[str]
) -> tuple[Semester, list[Course]]:
    semester = Semester(name=name, is_active=True)
    db_session.add(semester)
    db_session.flush()
    courses = [
        Course(semester_id=semester.id, code=code, name=code, enrollment=30)
        for code in codes
    ]
    db_session.add_all(courses)
    db_session.commit()
    return semester, courses


@pytest.fixture()
def coordinator(db_session: Session) -> User:
    return make_user(db_session, "amorgan", Role.COORDINATOR)


@pytest.fixture()
def headers(coordinator: User, auth_headers: AuthHeaders) -> dict[str, str]:
    return auth_headers(coordinator)


def can_log_in(client: TestClient, username: str, password: str) -> bool:
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    return response.status_code == 200


# --- Only coordinators ------------------------------------------------------


@pytest.mark.parametrize("role", [Role.STUDENT, Role.INSTRUCTOR])
@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/users"),
        ("POST", "/users"),
        ("PATCH", "/users/1"),
        ("PUT", "/users/1/password"),
        ("PUT", "/users/1/enrollments"),
        ("GET", "/semesters"),
    ],
)
def test_only_coordinators_manage_users(
    client: TestClient,
    db_session: Session,
    auth_headers: AuthHeaders,
    role: Role,
    method: str,
    path: str,
) -> None:
    user = make_user(db_session, "someone", role)

    response = client.request(method, path, headers=auth_headers(user), json={})

    assert response.status_code == 403


# --- Listing ----------------------------------------------------------------


def test_list_users_filters_by_role_search_and_status(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    make_user(db_session, "jdoe", Role.INSTRUCTOR)
    make_user(db_session, "sstudent", Role.STUDENT)
    inactive = make_user(db_session, "gone", Role.STUDENT)
    inactive.is_active = False
    db_session.commit()

    def usernames(**params: object) -> list[str]:
        response = client.get("/users", params=params, headers=headers)
        assert response.status_code == 200
        return sorted(user["username"] for user in response.json())

    assert usernames() == ["amorgan", "gone", "jdoe", "sstudent"]
    assert usernames(role="student") == ["gone", "sstudent"]
    assert usernames(search="JDO") == ["jdoe"]
    assert usernames(include_inactive=False) == ["amorgan", "jdoe", "sstudent"]


def test_list_users_never_returns_password_hash(
    client: TestClient, headers: dict[str, str]
) -> None:
    users = client.get("/users", headers=headers).json()

    assert all("password_hash" not in user for user in users)


# --- Creating ---------------------------------------------------------------


def test_create_instructor_with_coordinator(
    client: TestClient, coordinator: User, headers: dict[str, str]
) -> None:
    response = client.post(
        "/users",
        headers=headers,
        json={
            "username": "NewProf",
            "email": "NewProf@umkc.edu",
            "full_name": "New Prof",
            "password": "temp-pass-1",
            "role": "instructor",
            "coordinator_id": coordinator.id,
            "min_course_load": 1,
            "max_course_load": 2,
        },
    )

    assert response.status_code == 201
    user = response.json()
    assert user["username"] == "newprof"
    assert user["role"] == "instructor"
    assert user["coordinator_name"] == "Amorgan"
    assert (user["min_course_load"], user["max_course_load"]) == (1, 2)
    assert can_log_in(client, "newprof", "temp-pass-1")


def test_create_coordinator(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(
        "/users",
        headers=headers,
        json={
            "username": "boss",
            "email": "boss@umkc.edu",
            "full_name": "Boss",
            "password": "temp-pass-1",
            "role": "coordinator",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "coordinator"


def test_create_non_instructor_ignores_coordinator(
    client: TestClient, coordinator: User, headers: dict[str, str]
) -> None:
    response = client.post(
        "/users",
        headers=headers,
        json={
            "username": "stu",
            "email": "stu@umkc.edu",
            "full_name": "Stu",
            "password": "temp-pass-1",
            "role": "student",
            "coordinator_id": coordinator.id,
        },
    )

    assert response.status_code == 201
    assert response.json()["coordinator_id"] is None


@pytest.mark.parametrize(
    "changes, status",
    [
        ({"username": "amorgan"}, 409),
        ({"email": "AMorgan@umkc.edu"}, 409),
        ({"email": "not-an-email"}, 422),
        ({"password": "short"}, 422),
        ({"role": "admin"}, 422),
        ({"min_course_load": 4, "max_course_load": 2}, 422),
    ],
    ids=[
        "taken-username",
        "taken-email",
        "bad-email",
        "short-password",
        "unknown-role",
        "loads-reversed",
    ],
)
def test_create_user_rejects_bad_input(
    client: TestClient, headers: dict[str, str], changes: dict, status: int
) -> None:
    body = {
        "username": "newuser",
        "email": "newuser@umkc.edu",
        "full_name": "New User",
        "password": "temp-pass-1",
        "role": "student",
    }

    response = client.post("/users", headers=headers, json={**body, **changes})

    assert response.status_code == status


def test_create_instructor_rejects_non_coordinator_as_coordinator(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)

    response = client.post(
        "/users",
        headers=headers,
        json={
            "username": "newprof",
            "email": "newprof@umkc.edu",
            "full_name": "New Prof",
            "password": "temp-pass-1",
            "role": "instructor",
            "coordinator_id": student.id,
        },
    )

    assert response.status_code == 422


# --- Editing ----------------------------------------------------------------


def test_update_details(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    user = make_user(db_session, "jdoe", Role.STUDENT)

    response = client.patch(
        f"/users/{user.id}",
        headers=headers,
        json={"full_name": "Jane Q. Doe", "email": "Jane@UMKC.edu"},
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Jane Q. Doe"
    assert response.json()["email"] == "jane@umkc.edu"


def test_update_rejects_taken_email(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    user = make_user(db_session, "jdoe", Role.STUDENT)

    response = client.patch(
        f"/users/{user.id}", headers=headers, json={"email": "amorgan@umkc.edu"}
    )

    assert response.status_code == 409


def test_update_unknown_user_returns_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.patch("/users/999", headers=headers, json={})

    assert response.status_code == 404


def test_deactivated_user_cannot_log_in_until_reactivated(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    user = make_user(db_session, "jdoe", Role.STUDENT)

    client.patch(
        f"/users/{user.id}", headers=headers, json={"is_active": False}
    )
    assert not can_log_in(client, "jdoe", PASSWORD)

    client.patch(f"/users/{user.id}", headers=headers, json={"is_active": True})
    assert can_log_in(client, "jdoe", PASSWORD)


@pytest.mark.parametrize(
    "changes, detail",
    [
        ({"role": "student"}, "You cannot change your own role"),
        ({"is_active": False}, "You cannot deactivate yourself"),
    ],
)
def test_coordinator_cannot_lock_themselves_out(
    client: TestClient,
    coordinator: User,
    headers: dict[str, str],
    changes: dict,
    detail: str,
) -> None:
    response = client.patch(
        f"/users/{coordinator.id}", headers=headers, json=changes
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_update_rejects_reversed_course_loads(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)

    response = client.patch(
        f"/users/{instructor.id}",
        headers=headers,
        json={"min_course_load": 9},
    )

    assert response.status_code == 422


def test_assign_and_unassign_instructor_coordinator(
    client: TestClient,
    db_session: Session,
    coordinator: User,
    headers: dict[str, str],
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)

    assigned = client.patch(
        f"/users/{instructor.id}",
        headers=headers,
        json={"coordinator_id": coordinator.id},
    )
    unassigned = client.patch(
        f"/users/{instructor.id}",
        headers=headers,
        json={"coordinator_id": None},
    )

    assert assigned.json()["coordinator_id"] == coordinator.id
    assert unassigned.json()["coordinator_id"] is None


# --- Role changes -----------------------------------------------------------


def test_student_to_instructor_drops_enrollments(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)
    _, courses = make_semester(db_session, "Fall 2026", ["CS101"])
    db_session.add(Enrollment(student_id=student.id, course_id=courses[0].id))
    db_session.commit()

    response = client.patch(
        f"/users/{student.id}", headers=headers, json={"role": "instructor"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "instructor"
    assert db_session.query(Enrollment).count() == 0


def test_instructor_to_student_drops_preferences_and_coordinator(
    client: TestClient,
    db_session: Session,
    coordinator: User,
    headers: dict[str, str],
) -> None:
    instructor = make_user(
        db_session, "jdoe", Role.INSTRUCTOR, coordinator_id=coordinator.id
    )
    _, courses = make_semester(db_session, "Fall 2026", ["CS101"])
    db_session.add(
        CourseInstructor(
            course_id=courses[0].id,
            instructor_id=instructor.id,
            preference=CoursePreference.PREFERRED,
        )
    )
    db_session.commit()

    response = client.patch(
        f"/users/{instructor.id}", headers=headers, json={"role": "student"}
    )

    assert response.status_code == 200
    assert response.json()["coordinator_id"] is None
    assert db_session.query(CourseInstructor).count() == 0


def test_instructor_in_a_schedule_keeps_role(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)
    semester, courses = make_semester(db_session, "Fall 2026", ["CS101"])
    room = Room(name="Room A", building="Flarsheim", capacity=40)
    slot = TimeSlot(hour=9, label="9:00 AM")
    schedule = Schedule(
        semester_id=semester.id,
        status=ScheduleStatus.PUBLISHED,
        fitness=1.0,
        generation_found=1,
        generations_run=1,
    )
    db_session.add_all([room, slot, schedule])
    db_session.flush()
    db_session.add(
        ScheduleEntry(
            schedule_id=schedule.id,
            course_id=courses[0].id,
            instructor_id=instructor.id,
            room_id=room.id,
            time_slot_id=slot.id,
        )
    )
    db_session.commit()

    response = client.patch(
        f"/users/{instructor.id}", headers=headers, json={"role": "student"}
    )

    assert response.status_code == 409
    db_session.refresh(instructor)
    assert instructor.role == Role.INSTRUCTOR


def test_coordinator_role_change_unassigns_their_instructors(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    other = make_user(db_session, "dcho", Role.COORDINATOR)
    instructor = make_user(
        db_session, "jdoe", Role.INSTRUCTOR, coordinator_id=other.id
    )

    response = client.patch(
        f"/users/{other.id}", headers=headers, json={"role": "instructor"}
    )

    assert response.status_code == 200
    db_session.refresh(instructor)
    assert instructor.coordinator_id is None


# --- Passwords --------------------------------------------------------------


def test_reset_password(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    user = make_user(db_session, "jdoe", Role.STUDENT)

    response = client.put(
        f"/users/{user.id}/password",
        headers=headers,
        json={"password": "brand-new-pass"},
    )

    assert response.status_code == 200
    assert not can_log_in(client, "jdoe", PASSWORD)
    assert can_log_in(client, "jdoe", "brand-new-pass")


def test_reset_password_rejects_short_password(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    user = make_user(db_session, "jdoe", Role.STUDENT)

    response = client.put(
        f"/users/{user.id}/password", headers=headers, json={"password": "x"}
    )

    assert response.status_code == 422


# --- Course assignments -----------------------------------------------------


def test_set_enrollments_replaces_only_that_semester(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)
    fall, fall_courses = make_semester(
        db_session, "Fall 2026", ["CS101", "CS201"]
    )
    _, spring_courses = make_semester(db_session, "Spring 2027", ["CS301"])
    db_session.add_all(
        [
            Enrollment(student_id=student.id, course_id=fall_courses[0].id),
            Enrollment(student_id=student.id, course_id=spring_courses[0].id),
        ]
    )
    db_session.commit()

    response = client.put(
        f"/users/{student.id}/enrollments",
        headers=headers,
        json={"semester_id": fall.id, "course_ids": [fall_courses[1].id]},
    )

    assert response.status_code == 200
    courses = client.get(f"/users/{student.id}/courses", headers=headers).json()
    assert sorted(c["code"] for c in courses) == ["CS201", "CS301"]
    assert {c["relation"] for c in courses} == {"enrolled"}


def test_set_enrollments_rejects_course_from_other_semester(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)
    fall, _ = make_semester(db_session, "Fall 2026", ["CS101"])
    _, spring_courses = make_semester(db_session, "Spring 2027", ["CS301"])

    response = client.put(
        f"/users/{student.id}/enrollments",
        headers=headers,
        json={"semester_id": fall.id, "course_ids": [spring_courses[0].id]},
    )

    assert response.status_code == 422


def test_set_enrollments_only_for_students(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)
    fall, courses = make_semester(db_session, "Fall 2026", ["CS101"])

    response = client.put(
        f"/users/{instructor.id}/enrollments",
        headers=headers,
        json={"semester_id": fall.id, "course_ids": [courses[0].id]},
    )

    assert response.status_code == 422


def test_set_enrollments_unknown_semester_returns_404(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)

    response = client.put(
        f"/users/{student.id}/enrollments",
        headers=headers,
        json={"semester_id": 999, "course_ids": []},
    )

    assert response.status_code == 404


def test_set_teaching_preferences(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)
    fall, courses = make_semester(db_session, "Fall 2026", ["CS101", "CS201"])

    response = client.put(
        f"/users/{instructor.id}/teaching",
        headers=headers,
        json={
            "semester_id": fall.id,
            "preferred": [courses[0].id],
            "qualified": [courses[1].id],
        },
    )

    assert response.status_code == 200
    courses = client.get(
        f"/users/{instructor.id}/courses", headers=headers
    ).json()
    assert {(c["code"], c["relation"]) for c in courses} == {
        ("CS101", "preferred"),
        ("CS201", "qualified"),
    }


def test_set_teaching_rejects_overlap(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    instructor = make_user(db_session, "jdoe", Role.INSTRUCTOR)
    fall, courses = make_semester(db_session, "Fall 2026", ["CS101"])

    response = client.put(
        f"/users/{instructor.id}/teaching",
        headers=headers,
        json={
            "semester_id": fall.id,
            "preferred": [courses[0].id],
            "qualified": [courses[0].id],
        },
    )

    assert response.status_code == 422


def test_set_teaching_only_for_instructors(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    student = make_user(db_session, "sstudent", Role.STUDENT)
    fall, courses = make_semester(db_session, "Fall 2026", ["CS101"])

    response = client.put(
        f"/users/{student.id}/teaching",
        headers=headers,
        json={"semester_id": fall.id, "preferred": [courses[0].id]},
    )

    assert response.status_code == 422


# --- Semesters --------------------------------------------------------------


def test_list_semesters_and_courses(
    client: TestClient, db_session: Session, headers: dict[str, str]
) -> None:
    fall, _ = make_semester(db_session, "Fall 2026", ["CS201", "CS101"])
    old = Semester(name="Spring 2026", is_active=False)
    db_session.add(old)
    db_session.commit()

    semesters = client.get("/semesters", headers=headers).json()
    courses = client.get(
        f"/semesters/{fall.id}/courses", headers=headers
    ).json()

    assert [s["name"] for s in semesters] == ["Fall 2026", "Spring 2026"]
    assert [c["code"] for c in courses] == ["CS101", "CS201"]


def test_unknown_semester_courses_returns_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/semesters/999/courses", headers=headers)

    assert response.status_code == 404
