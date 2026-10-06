"""Shared enums and helpers for ORM models."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum as SAEnum


class Role(str, enum.Enum):
    """What a user is allowed to do in the app."""

    STUDENT = "student"
    INSTRUCTOR = "instructor"
    COORDINATOR = "coordinator"


class CoursePreference(str, enum.Enum):
    """How an instructor relates to a course."""

    PREFERRED = "preferred"
    QUALIFIED = "qualified"  # Acceptable, but not the first choice.


class PairRuleType(str, enum.Enum):
    """Scheduling rule between two specific courses."""

    SPREAD = "spread"  # Sections of one course: keep far apart in the day.
    RELATED = "related"  # Courses students often take together: keep close.


class ScheduleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


def db_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Stores an enum as a plain VARCHAR holding the enum *values*."""

    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
