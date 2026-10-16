"""Schedule generation and modification-request endpoints."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import modifications as mods
from app.api.deps import CurrentUser, require_role
from app.api.scheduler import InfeasibleError, generate_schedule
from app.db.session import get_db
from app.models.common import Role, ScheduleStatus
from app.models.schedule import Schedule, ScheduleEntry

router = APIRouter(tags=["scheduling"])


def _rows(db: Session, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


def _records(messages: list[str]) -> list[dict[str, str]]:
    """Schedule.soft_violations is typed list[dict[str, str]], so store dicts."""
    return [{"message": m} for m in messages]


# --------------------------------------------------------------------------- #
# Generate (instructor)
# --------------------------------------------------------------------------- #
class GenerateIn(BaseModel):
    semester_id: int | None = None  # defaults to the active semester


@router.post("/schedules/generate")
def generate(
    body: GenerateIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.INSTRUCTOR)),
) -> dict:
    """Run the scheduler for a semester and save the result as a draft."""
    semester_id = (
        body.semester_id
        or db.execute(
            text("SELECT id FROM semesters WHERE is_active = :t"), {"t": True}
        ).scalar()
    )
    if semester_id is None:
        raise HTTPException(status_code=404, detail="No active semester")

    def q(sql, **p):
        return db.execute(text(sql), p).all()

    try:
        result = generate_schedule(
            q("SELECT id, name, zone, capacity FROM rooms"),
            q("SELECT id, label, hour FROM time_slots"),
            q(
                "SELECT id, full_name, min_course_load, max_course_load FROM users "
                "WHERE role = 'instructor' AND is_active = :t",
                t=True,
            ),
            q(
                "SELECT id, code, enrollment FROM courses WHERE semester_id = :s",
                s=semester_id,
            ),
            q(
                "SELECT ci.course_id, ci.instructor_id, ci.preference FROM course_instructors ci "
                "JOIN courses c ON c.id = ci.course_id WHERE c.semester_id = :s",
                s=semester_id,
            ),
            q(
                "SELECT r.course_a_id, r.course_b_id, r.rule_type FROM course_pair_rules r "
                "JOIN courses c ON c.id = r.course_a_id WHERE c.semester_id = :s",
                s=semester_id,
            ),
        )
    except InfeasibleError as e:
        raise HTTPException(status_code=422, detail=str(e))

    schedule = Schedule(
        semester_id=semester_id,
        created_by_id=user.id,
        status=ScheduleStatus.DRAFT,
        fitness=result.fitness,
        generation_found=result.generation_found,
        generations_run=result.generations_run,
        report={
            **result.report,
            "soft_violations": _records(result.report["soft_violations"]),
            "hard_violations": _records(result.report["hard_violations"]),
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(schedule)
    db.flush()
    db.add_all(
        ScheduleEntry(schedule_id=schedule.id, **e) for e in result.entries
    )
    db.commit()
    return {
        "schedule_id": schedule.id,
        "fitness": result.fitness,
        "generation_found": result.generation_found,
        "generations_run": result.generations_run,
        "hard_violations": result.report["hard_violations"],
        "soft_violations": result.report["soft_violations"],
    }


# --------------------------------------------------------------------------- #
# Modification requests
# --------------------------------------------------------------------------- #
class RequestIn(BaseModel):
    entry_id: int
    modification_type: Literal["slot", "location"]
    value: int
    reason: str = ""


class ReviewIn(BaseModel):
    accept: bool
    comment: str | None = None


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/modifications/options")
def options(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role(Role.INSTRUCTOR, Role.COORDINATOR)
    ),
) -> dict:
    """Dropdown data for the request form: rooms, time slots, and my published courses."""
    return {
        "rooms": _rows(
            db, "SELECT id, name, building, capacity FROM rooms ORDER BY name"
        ),
        "time_slots": _rows(
            db, "SELECT id, label FROM time_slots ORDER BY hour"
        ),
        "my_entries": _rows(
            db,
            "SELECT e.id, c.code AS course_code, r.name AS room_name, t.label AS time_slot_label "
            "FROM schedule_entries e "
            "JOIN schedules s ON s.id = e.schedule_id JOIN semesters sem ON sem.id = s.semester_id "
            "JOIN courses c ON c.id = e.course_id JOIN rooms r ON r.id = e.room_id "
            "JOIN time_slots t ON t.id = e.time_slot_id "
            "WHERE e.instructor_id = :me AND s.status = 'published' AND sem.is_active = :t",
            me=user.id,
            t=True,
        ),
    }


@router.get("/modifications")
def list_requests(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role(Role.INSTRUCTOR, Role.COORDINATOR)
    ),
) -> list[dict]:
    """Instructors see their own requests; coordinators see those assigned to them."""
    scope = (
        "m.assigned_to_id = :me OR m.assigned_to_id IS NULL"
        if user.role == Role.COORDINATOR
        else "m.requester_id = :me"
    )
    return _rows(
        db,
        "SELECT m.id, m.status, m.reason, m.reviewer_comment, m.created_at, m.resolved_at, "
        "u.full_name AS requester, c.code AS course_code, "
        "r.name AS current_room, t.label AS current_slot, "
        "pr.name AS proposed_room, pt.label AS proposed_slot "
        "FROM modification_requests m "
        "JOIN schedule_entries e ON e.id = m.schedule_entry_id "
        "JOIN courses c ON c.id = e.course_id JOIN rooms r ON r.id = e.room_id "
        "JOIN time_slots t ON t.id = e.time_slot_id JOIN users u ON u.id = m.requester_id "
        "LEFT JOIN rooms pr ON pr.id = m.proposed_room_id "
        "LEFT JOIN time_slots pt ON pt.id = m.proposed_time_slot_id "
        f"WHERE {scope} ORDER BY m.created_at DESC",
        me=user.id,
    )


@router.post("/modifications")
def create_request(
    body: RequestIn,
    user: CurrentUser = Depends(require_role(Role.INSTRUCTOR)),
) -> dict:
    req = _call(
        mods.request_modification,
        body.entry_id,
        body.modification_type,
        body.value,
        body.reason,
        requester_id=user.id,
    )
    return {"id": req.id}


@router.post("/modifications/{request_id}/review")
def review_request(
    request_id: int,
    body: ReviewIn,
    user: CurrentUser = Depends(require_role(Role.COORDINATOR)),
) -> dict:
    req = _call(
        mods.review_modification, request_id, user.id, body.accept, body.comment
    )
    return {"id": req.id, "status": getattr(req.status, "value", req.status)}
