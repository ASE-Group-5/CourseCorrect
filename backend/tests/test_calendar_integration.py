"""Mocked tests for independent Google Calendar integration."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import calendar_oauth
from app.api.deps import get_current_user
from app.main import app
from app.models.calendar import (
    CalendarEventSync,
    CalendarLink,
    CalendarOAuthState,
)
from app.models.common import Role
from app.models.user import User
from app.services.calendar import push_events
from app.services.calendar_security import (
    decrypt_refresh_token,
    encrypt_refresh_token,
)


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (
            type("InvalidClientError", (Exception,), {"error": "invalid_client"})(),
            "invalid_client_credentials",
        ),
        (
            type("InvalidGrantError", (Exception,), {"error": "invalid_grant"})(),
            "invalid_or_expired_authorization_code",
        ),
        (
            type(
                "RedirectUriMismatch",
                (Exception,),
                {"error": "redirect_uri_mismatch"},
            )(),
            "redirect_uri_mismatch",
        ),
    ],
)
def test_oauth_error_categories_are_sanitized(error, category) -> None:
    assert calendar_oauth._oauth_error_category(error) == category


def test_invalid_state_is_logged_without_sensitive_values(
    client: TestClient, caplog
) -> None:
    caplog.set_level("WARNING", logger="app.api.calendar_oauth")

    response = client.get("/calendar/oauth/callback?state=unknown&code=code")

    assert response.status_code == 400
    assert "category=oauth_state_validation_failure" in caplog.text
    assert "unknown" not in caplog.text
    assert "code" not in caplog.text


def instructor() -> User:
    return User(
        id=3,
        username="praman",
        email="praman@example.com",
        full_name="Priya Raman",
        password_hash="x",
        role=Role.INSTRUCTOR,
    )


def test_oauth_state_rejects_unknown_or_replayed_state(client: TestClient) -> None:
    response = client.get("/calendar/oauth/callback?state=unknown&code=code")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OAuth state"


def test_oauth_callback_requires_state_and_code(client: TestClient) -> None:
    response = client.get("/calendar/oauth/callback")
    assert response.status_code == 422


def test_oauth_flow_does_not_generate_unpersisted_pkce_verifier() -> None:
    flow = calendar_oauth._flow("safe-state")
    assert flow.autogenerate_code_verifier is False
    flow.redirect_uri = "http://localhost:8000/calendar/oauth/callback"
    url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    assert "code_challenge" not in url


def test_oauth_connect_binds_state_and_links_encrypted_refresh_token(
    client: TestClient, db_session, monkeypatch
) -> None:
    user = instructor()
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    class FakeFlow:
        credentials = SimpleNamespace(refresh_token="google-refresh-token")

        def authorization_url(self, **_kwargs):
            return "https://accounts.google.test/authorize", None

        def fetch_token(self, *, code):
            assert code == "auth-code"

    captured = {}

    def make_flow(state=None):
        captured["state"] = state
        return FakeFlow()

    monkeypatch.setattr(calendar_oauth, "_flow", make_flow)
    connect = client.get("/calendar/oauth/connect")
    assert connect.status_code == 200
    state = db_session.query(CalendarOAuthState).one()

    callback = client.get(
        f"/calendar/oauth/callback?state={captured['state']}&code=auth-code"
    )
    assert callback.status_code == 200
    link = db_session.query(CalendarLink).one()
    assert decrypt_refresh_token(link.refresh_token) == "google-refresh-token"
    assert state.used_at is not None
    replay = client.get(
        f"/calendar/oauth/callback?state={captured['state']}&code=auth-code"
    )
    assert replay.status_code == 400


def test_successful_reconnection_replaces_existing_encrypted_token(
    client: TestClient, db_session, monkeypatch
) -> None:
    user = instructor()
    existing_link = CalendarLink(
        user_id=user.id,
        provider="google",
        calendar_id="primary",
        refresh_token=encrypt_refresh_token("old-refresh-token"),
    )
    db_session.add_all([user, existing_link])
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    class FakeFlow:
        credentials = SimpleNamespace(refresh_token="new-refresh-token")

        def authorization_url(self, **_kwargs):
            return "https://accounts.google.test/authorize", None

        def fetch_token(self, *, code):
            assert code == "auth-code"

    captured = {}
    monkeypatch.setattr(
        calendar_oauth,
        "_flow",
        lambda state=None: (captured.update(state=state) or FakeFlow()),
    )
    assert client.get("/calendar/oauth/connect").status_code == 200
    callback = client.get(
        f"/calendar/oauth/callback?state={captured['state']}&code=auth-code"
    )

    assert callback.status_code == 200
    db_session.refresh(existing_link)
    assert db_session.query(CalendarLink).count() == 1
    assert decrypt_refresh_token(existing_link.refresh_token) == "new-refresh-token"


def test_failed_reconnection_preserves_existing_link(
    client: TestClient, db_session, monkeypatch
) -> None:
    user = instructor()
    existing_link = CalendarLink(
        user_id=user.id,
        provider="google",
        calendar_id="primary",
        refresh_token=encrypt_refresh_token("old-refresh-token"),
    )
    db_session.add_all([user, existing_link])
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    class FailedFlow:
        credentials = SimpleNamespace(refresh_token=None)

        def authorization_url(self, **_kwargs):
            return "https://accounts.google.test/authorize", None

        def fetch_token(self, *, code):
            raise RuntimeError("authorization failed")

    captured = {}
    monkeypatch.setattr(
        calendar_oauth,
        "_flow",
        lambda state=None: (captured.update(state=state) or FailedFlow()),
    )
    assert client.get("/calendar/oauth/connect").status_code == 200
    response = client.get(
        f"/calendar/oauth/callback?state={captured['state']}&code=auth-code"
    )

    assert response.status_code == 400
    db_session.refresh(existing_link)
    assert db_session.query(CalendarLink).count() == 1
    assert decrypt_refresh_token(existing_link.refresh_token) == "old-refresh-token"


def test_only_instructors_can_start_oauth(client: TestClient, db_session) -> None:
    user = instructor()
    user.role = Role.STUDENT
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    response = client.get("/calendar/oauth/connect")
    assert response.status_code == 403


def test_encryption_round_trip_does_not_store_plaintext() -> None:
    encrypted = encrypt_refresh_token("refresh-token")
    assert encrypted != "refresh-token"
    assert decrypt_refresh_token(encrypted) == "refresh-token"


def test_duplicate_prevention_and_partial_failure(db_session) -> None:
    link = CalendarLink(
        id=1,
        user_id=3,
        calendar_id="primary",
        refresh_token=encrypt_refresh_token("refresh-token"),
    )
    db_session.add(link)
    db_session.commit()

    class FakeService:
        inserted = []

        def __init__(self, _link):
            pass

        def insert_event(self, event):
            if event["summary"] == "fail":
                raise RuntimeError("temporary Google failure")
            self.inserted.append(event["summary"])
            return {"id": f"google-{len(self.inserted)}"}

    first = {
        "_coursecorrect_event_key": "entry-1-2027-01-11",
        "summary": "first",
        "start": {"dateTime": "2027-01-11T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2027-01-11T10:00:00", "timeZone": "UTC"},
    }
    with pytest.raises(RuntimeError):
        push_events(
            db_session,
            link,
            [first, {**first, "_coursecorrect_event_key": "entry-2", "summary": "fail"}],
            FakeService,
        )
    assert db_session.query(CalendarEventSync).count() == 1
    assert push_events(db_session, link, [first], FakeService) == 0


def test_revoked_google_authorization_is_reported(monkeypatch) -> None:
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    from app.services.calendar import GoogleCalendarService

    link = CalendarLink(
        user_id=3,
        calendar_id="primary",
        refresh_token=encrypt_refresh_token("refresh-token"),
    )

    def revoked(self, _request):
        raise RefreshError("revoked")

    monkeypatch.setattr(Credentials, "refresh", revoked)
    with pytest.raises(ValueError, match="revoked"):
        GoogleCalendarService(link).insert_event(
            {
                "summary": "Synthetic class",
                "start": {"dateTime": "2027-01-11T09:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2027-01-11T10:00:00", "timeZone": "UTC"},
            }
        )


def test_missing_calendar_is_not_connected(
    client: TestClient, db_session, monkeypatch
) -> None:
    monkeypatch.setenv("CALENDAR_DEMO_MODE", "false")
    user = instructor()
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    response = client.get("/calendar/status")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "linked": False,
        "reconnect_required": False,
        "provider": "google",
        "demo_dates_enabled": False,
    }


def test_revoked_credentials_require_reconnection(
    client: TestClient, db_session, monkeypatch
) -> None:
    user = instructor()
    link = CalendarLink(
        user_id=user.id,
        provider="google",
        calendar_id="primary",
        refresh_token=encrypt_refresh_token("revoked-refresh-token"),
    )
    db_session.add_all([user, link])
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    def revoked(_self):
        raise ValueError("Google Calendar authorization was revoked")

    monkeypatch.setattr(
        "app.services.calendar.GoogleCalendarService.validate_credentials",
        revoked,
    )
    response = client.get("/calendar/status")

    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["linked"] is True
    assert response.json()["reconnect_required"] is True
