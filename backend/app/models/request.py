"""Instructor requests to change a schedule (stories 5, 6, 7)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import RequestStatus, db_enum, utcnow
from app.models.resources import Room, TimeSlot
from app.models.schedule import ScheduleEntry
from app.models.user import User


class ModificationRequest(Base):
    """An instructor suggests a change; only a coordinator can act on it."""

    __tablename__ = "modification_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_entry_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_entries.id", ondelete="CASCADE"), index=True
    )
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    # The requester's assigned coordinator at the time of the request.
    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    proposed_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL")
    )
    proposed_time_slot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("time_slots.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RequestStatus] = mapped_column(
        db_enum(RequestStatus, "request_status"), default=RequestStatus.PENDING
    )
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewer_comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    entry: Mapped[ScheduleEntry] = relationship()
    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    assigned_to: Mapped[Optional[User]] = relationship(
        foreign_keys=[assigned_to_id]
    )
    reviewed_by: Mapped[Optional[User]] = relationship(
        foreign_keys=[reviewed_by_id]
    )
    proposed_room: Mapped[Optional[Room]] = relationship()
    proposed_time_slot: Mapped[Optional[TimeSlot]] = relationship()
