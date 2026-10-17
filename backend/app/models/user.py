"""User accounts (students, instructors, coordinators)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import Role, db_enum, utcnow


class User(Base):
    """Stories 1-2 (login / account creation) and the role for every story."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(db_enum(Role, "role"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Instructors only: the coordinator who receives their change requests
    # (story 5) and the course-load limits the scheduler aims for.
    coordinator_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    min_course_load: Mapped[int] = mapped_column(default=3)
    max_course_load: Mapped[int] = mapped_column(default=4)

    coordinator: Mapped[Optional["User"]] = relationship(remote_side="User.id")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role.value})>"
