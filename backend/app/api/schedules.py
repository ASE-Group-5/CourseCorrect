"""Schedule query endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_role
from app.db.session import get_db
from app.models.common import Role, ScheduleStatus
from app.models.course import Enrollment
from app.models.schedule import Schedule, ScheduleEntry
from app.models.user import User

router = APIRouter(tags=["schedules"])


def check_can_view(current_user: CurrentUser, username: str) -> None:
    """Only coordinators may view someone else's schedule."""
    if (
        current_user.role != Role.COORDINATOR
        and current_user.username != username
    ):
        raise HTTPException(
            status_code=403, detail="You can only view your own schedule"
        )


@router.get("/schedules/instructor/{username}")
def instructor_schedule(
    username: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_role(Role.INSTRUCTOR, Role.COORDINATOR)
    ),
) -> list[dict]:
    """Return the published schedule entries for the given instructor."""
    check_can_view(current_user, username)
    user = db.query(User).filter(User.username == username).first()
    if user is None or user.role != Role.INSTRUCTOR:
        raise HTTPException(status_code=404, detail="Instructor not found")

    schedule = (
        db.query(Schedule)
        .join(Schedule.semester)
        .filter(
            Schedule.status == ScheduleStatus.PUBLISHED,
            Schedule.semester.has(is_active=True),
        )
        .first()
    )
    if schedule is None:
        return []

    entries = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.schedule_id == schedule.id,
            ScheduleEntry.instructor_id == user.id,
        )
        .all()
    )

    return [
        {
            "course_code": entry.course.code,
            "course_name": entry.course.name,
            "room_name": entry.room.name,
            "room_building": entry.room.building,
            "time_slot_label": entry.time_slot.label,
        }
        for entry in entries
    ]


@router.get("/schedules/student/{username}")
def student_schedule(
    username: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_role(Role.STUDENT, Role.COORDINATOR)
    ),
) -> list[dict]:
    """Return the published schedule entries for the given student's classes."""
    check_can_view(current_user, username)
    user = db.query(User).filter(User.username == username).first()
    if user is None or user.role != Role.STUDENT:
        raise HTTPException(status_code=404, detail="Student not found")

    schedule = (
        db.query(Schedule)
        .join(Schedule.semester)
        .filter(
            Schedule.status == ScheduleStatus.PUBLISHED,
            Schedule.semester.has(is_active=True),
        )
        .first()
    )
    if schedule is None:
        return []

    enrolled_course_ids = [
        row.course_id
        for row in db.query(Enrollment).filter(Enrollment.student_id == user.id)
    ]
    if not enrolled_course_ids:
        return []

    entries = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.schedule_id == schedule.id,
            ScheduleEntry.course_id.in_(enrolled_course_ids),
        )
        .all()
    )

    return [
        {
            "course_code": entry.course.code,
            "course_name": entry.course.name,
            "room_name": entry.room.name,
            "room_building": entry.room.building,
            "time_slot_label": entry.time_slot.label,
            "instructor_name": entry.instructor.full_name,
        }
        for entry in entries
    ]
