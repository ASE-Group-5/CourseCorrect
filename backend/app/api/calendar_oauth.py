"""Google Calendar OAuth connection endpoints."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.models.calendar import CalendarLink, CalendarOAuthState
from app.models.common import Role
from app.services.calendar import GoogleCalendarService
from app.services.calendar_demo import demo_mode_enabled
from app.services.calendar_security import (
    decrypt_refresh_token,
    encrypt_refresh_token,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])
logger = logging.getLogger(__name__)
SCOPES = ("https://www.googleapis.com/auth/calendar.events",)
STATE_TTL = timedelta(minutes=10)


def _oauth_error_category(error: Exception) -> str:
    """Classify an OAuth error without logging its potentially sensitive text."""
    safe_fields = [
        getattr(error, "error", ""),
        getattr(error, "error_description", ""),
        getattr(error, "description", ""),
        *error.args,
    ]
    safe_text = " ".join(
        str(part).lower() for part in safe_fields if isinstance(part, str)
    )
    error_type = type(error).__name__.lower()
    if "redirect_uri_mismatch" in safe_text or "redirect uri mismatch" in safe_text:
        return "redirect_uri_mismatch"
    if "invalid_client" in safe_text or "unauthorized_client" in safe_text:
        return "invalid_client_credentials"
    if (
        "invalid_grant" in safe_text
        or "authorization code" in safe_text
        or "expired code" in safe_text
    ):
        return "invalid_or_expired_authorization_code"
    if "clientauthentication" in error_type:
        return "invalid_client_credentials"
    return "oauth_token_exchange_failure"


def _log_oauth_failure(category: str, error: Exception) -> None:
    """Log only safe OAuth diagnostic metadata."""
    logger.warning(
        "Google Calendar OAuth failure category=%s exception_type=%s",
        category,
        type(error).__name__,
    )


def _flow(state: str | None = None):
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        logger.error(
            "Google Calendar OAuth failure category=invalid_client_credentials "
            "exception_type=configuration"
        )
        raise HTTPException(
            status_code=503, detail="Google Calendar OAuth is not configured"
        )
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise HTTPException(
            status_code=503, detail="Google Calendar dependencies are not installed"
        ) from exc
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=list(SCOPES),
        state=state,
        autogenerate_code_verifier=False,
    )


@router.get("/oauth/connect")
def connect_google_calendar(
    user: CurrentUser = Depends(require_role(Role.INSTRUCTOR)),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Start OAuth and bind the one-time state to the instructor."""
    state = secrets.token_urlsafe(32)
    db.add(
        CalendarOAuthState(
            user_id=user.id,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + STATE_TTL,
        )
    )
    db.commit()
    flow = _flow(state)
    flow.redirect_uri = get_settings().google_redirect_uri
    authorization_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return {"authorization_url": authorization_url}


@router.get("/oauth/callback")
def google_calendar_callback(
    state: str,
    code: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Validate one-time state, exchange code, and encrypt the refresh token."""
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    oauth_state = (
        db.query(CalendarOAuthState)
        .filter(CalendarOAuthState.state_hash == state_hash)
        .first()
    )
    now = datetime.now(timezone.utc)
    expires_at = (
        oauth_state.expires_at.replace(tzinfo=timezone.utc)
        if oauth_state is not None and oauth_state.expires_at.tzinfo is None
        else oauth_state.expires_at if oauth_state is not None else None
    )
    if (
        oauth_state is None
        or oauth_state.used_at is not None
        or expires_at <= now
    ):
        logger.warning(
            "Google Calendar OAuth failure category=oauth_state_validation_failure "
            "exception_type=state_validation"
        )
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    flow = _flow(state)
    flow.redirect_uri = get_settings().google_redirect_uri
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        _log_oauth_failure(_oauth_error_category(exc), exc)
        raise HTTPException(status_code=400, detail="Google authorization failed") from exc
    refresh_token = getattr(flow.credentials, "refresh_token", None)
    if not refresh_token:
        logger.warning(
            "Google Calendar OAuth failure category=missing_refresh_token "
            "exception_type=credential_response"
        )
        raise HTTPException(status_code=400, detail="Google did not provide a refresh token")

    link = (
        db.query(CalendarLink)
        .filter(CalendarLink.user_id == oauth_state.user_id)
        .first()
    )
    try:
        encrypted_refresh_token = encrypt_refresh_token(refresh_token)
    except Exception as exc:
        logger.error(
            "Google Calendar OAuth failure category=token_encryption_failure "
            "exception_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(status_code=400, detail="Google authorization failed") from exc

    if link is None:
        link = CalendarLink(
            user_id=oauth_state.user_id,
            provider="google",
            calendar_id="primary",
            refresh_token=encrypted_refresh_token,
        )
        db.add(link)
    else:
        link.provider = "google"
        link.calendar_id = "primary"
        link.refresh_token = encrypted_refresh_token
    oauth_state.used_at = now
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "Google Calendar OAuth failure category=database_persistence_failure "
            "exception_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(status_code=400, detail="Google authorization failed") from exc
    return {"status": "connected", "provider": "google"}


@router.get("/status")
def calendar_status(
    user: CurrentUser = Depends(require_role(Role.INSTRUCTOR)),
    db: Session = Depends(get_db),
) -> dict[str, bool | str]:
    """Report connected only when encrypted credentials can be decrypted."""
    link = db.query(CalendarLink).filter(CalendarLink.user_id == user.id).first()
    connected = False
    reconnect_required = False
    linked = link is not None
    if link and link.refresh_token:
        try:
            decrypt_refresh_token(link.refresh_token)
            GoogleCalendarService(link).validate_credentials()
            connected = True
        except (RuntimeError, ValueError):
            reconnect_required = True
    return {
        "connected": connected,
        "linked": linked,
        "reconnect_required": reconnect_required,
        "provider": "google",
        "demo_dates_enabled": demo_mode_enabled(),
    }
