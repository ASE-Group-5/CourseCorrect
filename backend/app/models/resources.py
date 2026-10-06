"""Physical resources the scheduler allocates: rooms and time slots."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    building: Mapped[str] = mapped_column(String(50))
    # Rooms in different zones are far apart; an instructor with back-to-back
    # classes in different zones is penalised.
    zone: Mapped[str] = mapped_column(String(50), default="")
    capacity: Mapped[int]


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 24-hour clock start time. Slots one hour apart count as back-to-back.
    hour: Mapped[int] = mapped_column(unique=True)
    label: Mapped[str] = mapped_column(String(20), unique=True)
