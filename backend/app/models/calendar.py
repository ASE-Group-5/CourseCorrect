"""Link between a user and their personal calendar (story 8)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import utcnow
from app.models.user import User


class CalendarLink(Base):
    """A user's connected external calendar. At most one per user."""

    __tablename__ = "calendar_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(30), default="google")
    calendar_id: Mapped[str] = mapped_column(String(255))
    # Must be encrypted at rest before real tokens are stored (story 8).
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    user: Mapped[User] = relationship()
    event_syncs: Mapped[list["CalendarEventSync"]] = relationship(
        back_populates="calendar_link", cascade="all, delete-orphan"
    )


class CalendarOAuthState(Base):
    """One-time OAuth state bound to an instructor and callback nonce."""

    __tablename__ = "calendar_oauth_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class CalendarEventSync(Base):
    """Maps a stable CourseCorrect event key to a Google event ID."""

    __tablename__ = "calendar_event_syncs"
    __table_args__ = (
        UniqueConstraint("calendar_link_id", "event_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_link_id: Mapped[int] = mapped_column(
        ForeignKey("calendar_links.id", ondelete="CASCADE"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(255))
    google_event_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    calendar_link: Mapped[CalendarLink] = relationship(back_populates="event_syncs")
