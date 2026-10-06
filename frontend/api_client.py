"""Thin wrapper around HTTP calls to the CourseCorrect backend."""

from typing import Any

import requests

from config import get_backend_url

# Generous timeout: free-tier backends can take ~1 minute to wake from sleep.
DEFAULT_TIMEOUT_SECONDS = 60


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error."""


def request(
    method: str, path: str, token: str | None = None, **kwargs: Any
) -> Any:
    """Sends a request to the backend and returns the decoded JSON body."""
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{get_backend_url()}{path}"
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise BackendError(f"Could not reach backend at {url}: {exc}") from exc
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise BackendError(f"{response.status_code}: {detail}")
    return response.json()


def get_health() -> dict[str, str]:
    """Calls the backend liveness endpoint."""
    return request("GET", "/health")


def get_db_health() -> dict[str, str]:
    """Calls the backend database readiness endpoint."""
    return request("GET", "/health/db")
