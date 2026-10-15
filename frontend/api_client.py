"""Thin wrapper around HTTP calls to the CourseCorrect backend."""

from typing import Any

import requests

from config import get_backend_url

# Generous timeout: free-tier backends can take ~1 minute to wake from sleep.
DEFAULT_TIMEOUT_SECONDS = 60


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error.

    `status_code` is the HTTP status (None if the backend was unreachable) and
    `detail` is the backend's readable error message.
    """

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(f"{status_code}: {detail}" if status_code else detail)
        self.status_code = status_code
        self.detail = detail


def format_detail(detail: Any) -> str:
    """Turn FastAPI validation errors (a list) into readable lines."""
    if not isinstance(detail, list):
        return str(detail)
    lines = []
    for error in detail:
        field = ".".join(str(part) for part in error.get("loc", [])[1:])
        message = error.get("msg", "")
        lines.append(f"{field}: {message}" if field else message)
    return "\n".join(lines)


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
            detail = format_detail(response.json().get("detail", response.text))
        except ValueError:
            detail = response.text
        raise BackendError(detail, response.status_code)
    return response.json()


def get_health() -> dict[str, str]:
    """Calls the backend liveness endpoint."""
    return request("GET", "/health")


def get_db_health() -> dict[str, str]:
    """Calls the backend database readiness endpoint."""
    return request("GET", "/health/db")
