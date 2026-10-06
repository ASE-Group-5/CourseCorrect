"""Semesters, courses, who can teach them, and who is enrolled."""

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CoursePreference, PairRuleType, db_enum
from app.models.user import User


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class Course(Base):
    """A course (or one section of it) offered in a semester."""

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("semester_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    enrollment: Mapped[int]

    semester: Mapped[Semester] = relationship()
    instructor_links: Mapped[list["CourseInstructor"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseInstructor(Base):
    """Instructor preference for a course (a constraint for story 3)."""

    __tablename__ = "course_instructors"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    instructor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preference: Mapped[CoursePreference] = mapped_column(
        db_enum(CoursePreference, "course_preference")
    )

    course: Mapped[Course] = relationship(back_populates="instructor_links")
    instructor: Mapped[User] = relationship()


class CoursePairRule(Base):
    """Extra scheduling rule tying two courses together (story 3)."""

    __tablename__ = "course_pair_rules"
    __table_args__ = (
        CheckConstraint("course_a_id <> course_b_id", name="different_courses"),
        UniqueConstraint("course_a_id", "course_b_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_a_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE")
    )
    course_b_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE")
    )
    rule_type: Mapped[PairRuleType] = mapped_column(
        db_enum(PairRuleType, "pair_rule_type")
    )


class Enrollment(Base):
    """A student taking a course (story 9: students view their schedule)."""

    __tablename__ = "enrollments"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )

    student: Mapped[User] = relationship()
    course: Mapped[Course] = relationship()


__all__ = [
    "Course",
    "CourseInstructor",
    "CoursePairRule",
    "Enrollment",
    "Semester",
]
