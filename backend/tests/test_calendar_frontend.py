"""Focused Streamlit tests for the Google Calendar account-change action."""

import importlib
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_connected_instructor_can_start_account_change(monkeypatch) -> None:
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    monkeypatch.syspath_prepend(str(frontend))
    api_client = importlib.import_module("api_client")
    calls = []

    def fake_request(method, path, **_kwargs):
        calls.append((method, path))
        if path == "/calendar/status":
            return {
                "connected": True,
                "linked": True,
                "reconnect_required": False,
                "demo_dates_enabled": False,
            }
        if path == "/calendar/oauth/connect":
            return {"authorization_url": "https://accounts.google.test/authorize"}
        return []

    monkeypatch.setattr(api_client, "request", fake_request)
    app = AppTest.from_file(str(frontend / "views" / "schedules.py"))
    app.session_state["auth_user"] = {
        "role": "instructor",
        "username": "jdoe",
    }
    app.session_state["auth_token"] = "test-token"
    app.run()

    assert any(button.label == "Change Google Account" for button in app.button)
    change_button = next(
        button for button in app.button if button.label == "Change Google Account"
    )
    change_button.click().run()

    assert ("GET", "/calendar/oauth/connect") in calls
    assert any(link.label == "Continue with Google" for link in app.get("link_button"))
