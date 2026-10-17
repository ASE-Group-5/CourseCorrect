"""Tests for login (acceptance criteria 1.1, 1.2) and account creation
(acceptance criteria 2.1, 2.2)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.common import Role
from app.models.user import User

PASSWORD = "Password123!"

NEW_ACCOUNT = {
    "username": "NewStudent",
    "email": "New.Student@Example.com",
    "full_name": "  New Student  ",
    "password": "s3cure-pass",
}


def make_user(
    db_session: Session,
    username: str,
    role: Role = Role.STUDENT,
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        email=f"{username}@umkc.edu",
        full_name=username.title(),
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user


# --- Story 1: account login -------------------------------------------------


def test_valid_login_returns_token_and_user(
    client: TestClient, db_session: Session
) -> None:
    make_user(db_session, "jdoe", Role.INSTRUCTOR)

    response = client.post(
        "/auth/login", json={"username": "jdoe", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == "jdoe"
    assert body["user"]["role"] == "instructor"
    assert "password_hash" not in body["user"]


def test_login_ignores_username_case_and_spaces(
    client: TestClient, db_session: Session
) -> None:
    make_user(db_session, "jdoe")

    response = client.post(
        "/auth/login", json={"username": " JDoe ", "password": PASSWORD}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "username, password",
    [("jdoe", "wrong-password"), ("nobody", PASSWORD)],
    ids=["wrong-password", "unknown-user"],
)
def test_invalid_login_returns_invalid_login(
    client: TestClient, db_session: Session, username: str, password: str
) -> None:
    make_user(db_session, "jdoe")

    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid login"


def test_inactive_user_cannot_log_in(
    client: TestClient, db_session: Session
) -> None:
    make_user(db_session, "jdoe", is_active=False)

    response = client.post(
        "/auth/login", json={"username": "jdoe", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid login"


def test_login_token_works_on_me(
    client: TestClient, db_session: Session
) -> None:
    make_user(db_session, "amorgan", Role.COORDINATOR)
    token = client.post(
        "/auth/login", json={"username": "amorgan", "password": PASSWORD}
    ).json()["access_token"]

    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "coordinator"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-real-token"}],
    ids=["no-token", "bad-token"],
)
def test_me_requires_valid_token(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401


# --- Story 2: account creation ----------------------------------------------


def test_register_creates_student_and_logs_in(client: TestClient) -> None:
    response = client.post("/auth/register", json=NEW_ACCOUNT)

    assert response.status_code == 201
    user = response.json()["user"]
    assert user["username"] == "newstudent"
    assert user["email"] == "new.student@example.com"
    assert user["full_name"] == "New Student"
    assert user["role"] == "student"

    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["username"] == "newstudent"

    login = client.post(
        "/auth/login",
        json={"username": "newstudent", "password": NEW_ACCOUNT["password"]},
    )
    assert login.status_code == 200


def test_register_cannot_choose_role(client: TestClient) -> None:
    response = client.post(
        "/auth/register", json={**NEW_ACCOUNT, "role": "coordinator"}
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "student"


@pytest.mark.parametrize(
    "changes",
    [
        {"username": None},
        {"email": None},
        {"full_name": None},
        {"password": None},
        {"username": "ab"},
        {"username": "bad name!"},
        {"email": "not-an-email"},
        {"full_name": "   "},
        {"password": "short"},
        {"password": "x" * 73},
    ],
    ids=[
        "missing-username",
        "missing-email",
        "missing-full-name",
        "missing-password",
        "short-username",
        "bad-username-chars",
        "bad-email",
        "blank-full-name",
        "short-password",
        "long-password",
    ],
)
def test_register_rejects_invalid_information(
    client: TestClient, changes: dict
) -> None:
    body = {**NEW_ACCOUNT, **changes}
    body = {key: value for key, value in body.items() if value is not None}

    response = client.post("/auth/register", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes, detail",
    [
        ({"username": "JDOE"}, "Username is already taken"),
        ({"email": "JDoe@umkc.edu"}, "Email is already registered"),
    ],
    ids=["taken-username", "taken-email"],
)
def test_register_rejects_duplicates(
    client: TestClient, db_session: Session, changes: dict, detail: str
) -> None:
    make_user(db_session, "jdoe")

    response = client.post("/auth/register", json={**NEW_ACCOUNT, **changes})

    assert response.status_code == 409
    assert response.json()["detail"] == detail
