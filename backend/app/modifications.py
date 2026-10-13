from datetime import datetime, timezone

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models import ModificationRequest

MODIFICATION_TYPES = ("slot", "location", "instructor")

REQUESTABLE_TYPES = ("slot", "location")


def _value(x):
    """Enum member or plain string -> string."""
    return getattr(x, "value", x)


def _now():
    return datetime.now(timezone.utc)


# Lookups
def _entry(db, entry_id):
    row = db.execute(
        text(
            "SELECT e.id, e.schedule_id, e.course_id, e.instructor_id, "
            "e.room_id, e.time_slot_id, c.enrollment "
            "FROM schedule_entries e JOIN courses c ON c.id = e.course_id "
            "WHERE e.id = :id"
        ),
        {"id": entry_id},
    ).first()
    if row is None:
        raise ValueError(f"No schedule entry found with ID {entry_id}")
    return row


def _user(db, user_id, what="user"):
    row = db.execute(
        text("SELECT * FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    if row is None:
        raise ValueError(f"No {what} found with ID {user_id}")
    return row


def _coordinator_of(db, instructor_id):
    instructor = _user(db, instructor_id, "instructor")
    if instructor.coordinator_id is None:
        raise ValueError(f"Instructor {instructor_id} has no coordinator")
    return _user(db, instructor.coordinator_id, "coordinator")


def get_instructor_from_schedule(entry_id):
    with SessionLocal() as db:
        return _user(db, _entry(db, entry_id).instructor_id, "instructor")


def get_coordinator_from_instructor(instructor_id):
    with SessionLocal() as db:
        return _coordinator_of(db, instructor_id)


def get_coordinator_from_schedule(entry_id):
    with SessionLocal() as db:
        return _coordinator_of(db, _entry(db, entry_id).instructor_id)


# Applying a change
def _apply_changes(db, entry_id, changes):
    """Validate and apply"""
    entry = _entry(db, entry_id)
    room_id = changes.get("location", entry.room_id)
    slot_id = changes.get("slot", entry.time_slot_id)
    instructor_id = changes.get("instructor", entry.instructor_id)

    if "location" in changes:
        room = db.execute(
            text("SELECT name, capacity FROM rooms WHERE id = :id"),
            {"id": room_id},
        ).first()
        if room is None:
            raise ValueError(f"No room found with ID {room_id}")
        if room.capacity < entry.enrollment:
            raise ValueError(
                f"Room {room.name} (capacity {room.capacity}) is too small "
                f"for {entry.enrollment} students"
            )

    if "slot" in changes:
        if (
            db.execute(
                text("SELECT 1 FROM time_slots WHERE id = :id"), {"id": slot_id}
            ).first()
            is None
        ):
            raise ValueError(f"No time slot found with ID {slot_id}")

    if "instructor" in changes:
        linked = db.execute(
            text(
                "SELECT 1 FROM course_instructors "
                "WHERE course_id = :course AND instructor_id = :instructor"
            ),
            {"course": entry.course_id, "instructor": instructor_id},
        ).first()
        if linked is None:
            raise ValueError(
                f"Instructor {instructor_id} is not linked to course {entry.course_id}"
            )

    # Clash checks look only at the same schedule, and never at the entry itself.
    base = (
        "SELECT 1 FROM schedule_entries WHERE schedule_id = :schedule "
        "AND id <> :id AND time_slot_id = :slot AND "
    )
    params = {"schedule": entry.schedule_id, "id": entry_id, "slot": slot_id}
    if "slot" in changes or "location" in changes:
        if db.execute(
            text(base + "room_id = :room"), {**params, "room": room_id}
        ).first():
            raise ValueError("That room is already booked at that time")
    if "slot" in changes or "instructor" in changes:
        if db.execute(
            text(base + "instructor_id = :instructor"),
            {**params, "instructor": instructor_id},
        ).first():
            raise ValueError(
                "That instructor already teaches another course at that time"
            )

    db.execute(
        text(
            "UPDATE schedule_entries SET room_id = :room, time_slot_id = :slot, "
            "instructor_id = :instructor WHERE id = :id"
        ),
        {
            "room": room_id,
            "slot": slot_id,
            "instructor": instructor_id,
            "id": entry_id,
        },
    )


def modify_schedule(entry_id, modification_type, value):
    """Apply a change directly"""
    if modification_type not in MODIFICATION_TYPES:
        raise ValueError(f"Invalid modification type: {modification_type}")
    with SessionLocal() as db:
        _apply_changes(db, entry_id, {modification_type: value})
        db.commit()


# --------------------------------------------------------------------------- #
# Request and review
# --------------------------------------------------------------------------- #
def request_modification(
    entry_id, modification_type, value, reason="", *, requester_id
):
    """An instructor asks to move their course to another time slot or room."""
    if modification_type == "instructor":
        raise ValueError(
            "Instructor changes can't be requested: modification_requests has no "
            "proposed instructor column. A coordinator can use modify_schedule()."
        )
    if modification_type not in REQUESTABLE_TYPES:
        raise ValueError(f"Invalid modification type: {modification_type}")

    with SessionLocal() as db:
        entry = _entry(db, entry_id)
        if entry.instructor_id != requester_id:
            raise PermissionError(
                "Only the instructor teaching a course can request changes to it"
            )
        instructor = _user(db, requester_id, "instructor")

        if modification_type == "slot":
            table, proposed = "time_slots", {"proposed_time_slot_id": value}
        else:
            table, proposed = "rooms", {"proposed_room_id": value}
        if (
            db.execute(
                text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": value}
            ).first()
            is None
        ):
            raise ValueError(f"No {modification_type} found with ID {value}")

        request = ModificationRequest(
            schedule_entry_id=entry_id,
            requester_id=requester_id,
            assigned_to_id=instructor.coordinator_id,
            reason=reason,
            status="pending",
            created_at=_now(),
            **proposed,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request


def review_modification(request_id, reviewer_id, accept, comment=None):
    """A coordinator accepts or declines a pending request"""
    with SessionLocal() as db:
        request = db.get(ModificationRequest, request_id)
        if request is None:
            raise ValueError(
                f"No modification request found with ID {request_id}"
            )
        if _value(request.status) != "pending":
            raise ValueError(
                f"Request {request_id} has already been {_value(request.status)}"
            )

        reviewer = _user(db, reviewer_id, "reviewer")
        if _value(reviewer.role) != "coordinator":
            raise PermissionError(
                "Only a coordinator can review modification requests"
            )
        if (
            request.assigned_to_id is not None
            and request.assigned_to_id != reviewer_id
        ):
            raise PermissionError(
                "This request is assigned to a different coordinator"
            )

        if accept:
            changes = {}
            if request.proposed_time_slot_id is not None:
                changes["slot"] = request.proposed_time_slot_id
            if request.proposed_room_id is not None:
                changes["location"] = request.proposed_room_id
            if not changes:
                raise ValueError(f"Request {request_id} has no proposed change")
            _apply_changes(db, request.schedule_entry_id, changes)

        request.status = type(request.status)(
            "accepted" if accept else "declined"
        )
        request.reviewed_by_id = reviewer_id
        request.reviewer_comment = comment
        request.resolved_at = _now()
        db.commit()
        db.refresh(request)
        return request
