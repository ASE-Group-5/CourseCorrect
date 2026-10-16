"""Semester and course lookups for coordinators (used to assign courses)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.common import Role
from app.models.course import Course, Semester

router = APIRouter(
    tags=["semesters"], dependencies=[Depends(require_role(Role.COORDINATOR))]
)


@router.get("/semesters")
def list_semesters(db: Session = Depends(get_db)) -> list[dict]:
    """All semesters, the active ones first."""
    semesters = (
        db.query(Semester)
        .order_by(Semester.is_active.desc(), Semester.name)
        .all()
    )
    return [
        {"id": s.id, "name": s.name, "is_active": s.is_active}
        for s in semesters
    ]


@router.get("/semesters/{semester_id}/courses")
def semester_courses(
    semester_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    """The courses offered in a semester."""
    if db.get(Semester, semester_id) is None:
        raise HTTPException(status_code=404, detail="Semester not found")
    courses = (
        db.query(Course)
        .filter(Course.semester_id == semester_id)
        .order_by(Course.code)
        .all()
    )
    return [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "enrollment": c.enrollment,
        }
        for c in courses
    ]
