"""Modification request endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import coordinator_only
from app.db.session import get_db
from app.models.common import RequestStatus
from app.models.request import ModificationRequest
from app.models.user import User

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("/open")
def open_requests(
    _coordinator: User = Depends(coordinator_only),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return pending requests visible to coordinators."""
    requests = (
        db.query(ModificationRequest)
        .filter(ModificationRequest.status == RequestStatus.PENDING)
        .order_by(ModificationRequest.created_at)
        .all()
    )
    return [
        {
            "id": request.id,
            "instructor": request.requester.full_name,
            "instructor_username": request.requester.username,
            "course_code": request.entry.course.code,
            "course_name": request.entry.course.name,
            "reason": request.reason,
            "status": request.status.value,
            "created_at": request.created_at.isoformat(),
            "requested_room": (
                request.proposed_room.name if request.proposed_room else None
            ),
            "requested_time": (
                request.proposed_time_slot.label
                if request.proposed_time_slot
                else None
            ),
        }
        for request in requests
    ]
