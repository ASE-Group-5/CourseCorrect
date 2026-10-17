"""Generated schedules (stories 3, 4, 6, 9)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import ScheduleStatus, db_enum, utcnow
from app.models.course import Course, Semester
from app.models.resources import Room, TimeSlot
from app.models.user import User


class Schedule(Base):
    """One generated timetable for a semester."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ScheduleStatus] = mapped_column(
        db_enum(ScheduleStatus, "schedule_status"), default=ScheduleStatus.DRAFT
    )
    fitness: Mapped[float]
    generation_found: Mapped[int]
    generations_run: Mapped[int]
    # Soft-constraint violations and per-generation fitness history.
    report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    semester: Mapped[Semester] = relationship()
    created_by: Mapped[Optional[User]] = relationship()
    entries: Mapped[list["ScheduleEntry"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleEntry.id",
    )

    @property
    def soft_violations(self) -> list[dict[str, str]]:
        return (self.report or {}).get("soft_violations", [])

    @property
    def history(self) -> list[dict[str, Any]]:
        return (self.report or {}).get("history", [])


class ScheduleEntry(Base):
    """One course placed in a room, at a time, with an instructor."""

    __tablename__ = "schedule_entries"
    __table_args__ = (UniqueConstraint("schedule_id", "course_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id"))
    fitness: Mapped[float] = mapped_column(default=0.0)

    schedule: Mapped[Schedule] = relationship(back_populates="entries")
    course: Mapped[Course] = relationship(lazy="joined")
    instructor: Mapped[User] = relationship(lazy="joined")
    room: Mapped[Room] = relationship(lazy="joined")
    time_slot: Mapped[TimeSlot] = relationship(lazy="joined")
