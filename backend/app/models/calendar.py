"""Link between a user and their personal calendar (story 8)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
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
