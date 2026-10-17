"""Tests for the login gate that protects every non-public route."""

import base64
import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.common import Role
from app.models.user import User

AuthHeaders = Callable[[User], dict[str, str]]

# Routes anyone may call without logging in.
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("GET", "/health/db"),
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("GET", "/calendar/oauth/callback"),
}


def protected_routes() -> list[tuple[str, str]]:
    """Every API route (read from the OpenAPI schema) that is not public."""
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if (method.upper(), path) not in PUBLIC_ROUTES
    ]


def test_route_listing_finds_routes() -> None:
    """Guards the gate test below against silently checking nothing."""
    routes = protected_routes()

    assert ("GET", "/auth/me") in routes
    assert ("GET", "/schedules/student/{username}") in routes


@pytest.mark.parametrize("method, path", protected_routes())
def test_non_public_routes_require_login(
    client: TestClient, method: str, path: str
) -> None:
    """A new route that forgets the login gate fails here."""
    url = re.sub(r"\{[^}]+\}", "1", path)  # "/items/{id}" -> "/items/1"

    response = client.request(method, url)

    assert response.status_code == 401, f"{method} {path} is not protected"


@pytest.fixture()
def coordinator_only_client(db_session: Session) -> Iterator[TestClient]:
    """A tiny app with one coordinator-only route, sharing the test DB."""
    gated = FastAPI()

    @gated.get("/coordinators-only")
    def coordinators_only(
        user: CurrentUser = Depends(require_role(Role.COORDINATOR)),
    ) -> dict[str, str]:
        return {"username": user.username}

    def override_get_db() -> Iterator[Session]:
        yield db_session

    gated.dependency_overrides[get_db] = override_get_db
    with TestClient(gated) as test_client:
        yield test_client


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


def test_require_role_allows_listed_role(
    coordinator_only_client: TestClient,
    db_session: Session,
    auth_headers: AuthHeaders,
) -> None:
    coordinator = make_user(db_session, "amorgan", Role.COORDINATOR)

    response = coordinator_only_client.get(
        "/coordinators-only", headers=auth_headers(coordinator)
    )

    assert response.status_code == 200
    assert response.json() == {"username": "amorgan"}


@pytest.mark.parametrize("role", [Role.STUDENT, Role.INSTRUCTOR])
def test_require_role_rejects_other_roles(
    coordinator_only_client: TestClient,
    db_session: Session,
    auth_headers: AuthHeaders,
    role: Role,
) -> None:
    user = make_user(db_session, "someone", role)

    response = coordinator_only_client.get(
        "/coordinators-only", headers=auth_headers(user)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed for your role"


def test_require_role_rejects_anonymous(
    coordinator_only_client: TestClient,
) -> None:
    response = coordinator_only_client.get("/coordinators-only")

    assert response.status_code == 401


def bearer(claims: dict) -> dict[str, str]:
    """Sign arbitrary claims with the app's real key (to forge test tokens)."""
    settings = get_settings()
    token = jwt.encode(
        claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return {"Authorization": f"Bearer {token}"}


def valid_claims(**changes: object) -> dict:
    claims = {
        "sub": "7",
        "username": "jdoe",
        "email": "jdoe@umkc.edu",
        "full_name": "Jane Doe",
        "role": "instructor",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return {**claims, **changes}


def test_requests_read_user_from_token_not_database(
    client: TestClient,
) -> None:
    """No user row exists, yet a validly signed token is accepted."""
    response = client.get("/auth/me", headers=bearer(valid_claims()))

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "username": "jdoe",
        "email": "jdoe@umkc.edu",
        "full_name": "Jane Doe",
        "role": "instructor",
    }


def test_expired_token_is_rejected(client: TestClient) -> None:
    expired = valid_claims(
        exp=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    response = client.get("/auth/me", headers=bearer(expired))

    assert response.status_code == 401


def test_token_with_edited_role_is_rejected(
    client: TestClient, db_session: Session, auth_headers: AuthHeaders
) -> None:
    """Changing the role inside a token breaks its signature."""
    student = make_user(db_session, "sstudent", Role.STUDENT)
    token = auth_headers(student)["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "coordinator"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode())
    forged_token = f"{header}.{forged.decode().rstrip('=')}.{signature}"

    response = client.get(
        "/schedules/student/other",
        headers={"Authorization": f"Bearer {forged_token}"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "7", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        valid_claims(role="superuser"),
        {key: value for key, value in valid_claims().items() if key != "exp"},
    ],
    ids=["id-only-token", "unknown-role", "no-expiry"],
)
def test_incomplete_or_invalid_tokens_are_rejected(
    client: TestClient, claims: dict
) -> None:
    response = client.get("/auth/me", headers=bearer(claims))

    assert response.status_code == 401
