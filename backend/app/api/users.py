"""User management endpoints for coordinators.

Coordinators list, create and edit users (including role and active status),
reset passwords, and assign courses: enrollments for students and teaching
preferences for instructors (a constraint for story 3). Users are deactivated,
never deleted, so schedules and requests that mention them stay intact.

Deactivated users cannot log in. Anyone already logged in keeps access until
their token expires (ACCESS_TOKEN_EXPIRE_MINUTES), see app/api/deps.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import Email, FullName, Password, Username
from app.api.deps import CurrentUser, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.common import CoursePreference, Role
from app.models.course import Course, CourseInstructor, Enrollment, Semester
from app.models.schedule import ScheduleEntry
from app.models.user import User

router = APIRouter(
    tags=["users"], dependencies=[Depends(require_role(Role.COORDINATOR))]
)
coordinator = require_role(Role.COORDINATOR)


class CreateUserRequest(BaseModel):
    username: Username
    email: Email
    full_name: FullName
    password: Password
    role: Role
    coordinator_id: int | None = None  # Instructors only.
    min_course_load: int = Field(default=3, ge=0, le=10)
    max_course_load: int = Field(default=4, ge=0, le=10)

    @model_validator(mode="after")
    def loads_in_order(self) -> "CreateUserRequest":
        if self.min_course_load > self.max_course_load:
            raise ValueError("Minimum course load is above the maximum")
        return self


class UpdateUserRequest(BaseModel):
    """Only the fields sent are changed. Send coordinator_id: null to unset."""

    email: Email | None = None
    full_name: FullName | None = None
    role: Role | None = None
    is_active: bool | None = None
    coordinator_id: int | None = None
    min_course_load: int | None = Field(default=None, ge=0, le=10)
    max_course_load: int | None = Field(default=None, ge=0, le=10)


class PasswordRequest(BaseModel):
    password: Password


class EnrollmentsRequest(BaseModel):
    """The student's complete set of courses for one semester."""

    semester_id: int
    course_ids: list[int]


class TeachingRequest(BaseModel):
    """The instructor's complete teaching preferences for one semester."""

    semester_id: int
    preferred: list[int] = []
    qualified: list[int] = []

    @model_validator(mode="after")
    def no_overlap(self) -> "TeachingRequest":
        if set(self.preferred) & set(self.qualified):
            raise ValueError("A course cannot be both preferred and qualified")
        return self


def user_to_admin_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "coordinator_id": user.coordinator_id,
        "coordinator_name": (
            user.coordinator.full_name if user.coordinator else None
        ),
        "min_course_load": user.min_course_load,
        "max_course_load": user.max_course_load,
    }


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def check_coordinator(db: Session, coordinator_id: int | None) -> None:
    """An instructor's coordinator must be an active coordinator."""
    if coordinator_id is None:
        return
    candidate = db.get(User, coordinator_id)
    if (
        candidate is None
        or candidate.role != Role.COORDINATOR
        or not candidate.is_active
    ):
        raise HTTPException(
            status_code=422, detail="Coordinator must be an active coordinator"
        )


def check_email_free(db: Session, email: str, user_id: int | None) -> None:
    owner = db.query(User).filter(User.email == email).first()
    if owner is not None and owner.id != user_id:
        raise HTTPException(
            status_code=409, detail="Email is already registered"
        )


def commit_or_409(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:  # Lost a race with a matching change.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Username or email is already registered"
        ) from exc


def courses_in_semester(
    db: Session, semester_id: int, course_ids: list[int]
) -> None:
    """404 for an unknown semester, 422 if any course is not in it."""
    if db.get(Semester, semester_id) is None:
        raise HTTPException(status_code=404, detail="Semester not found")
    unique_ids = set(course_ids)
    found = (
        db.query(Course.id)
        .filter(Course.id.in_(unique_ids), Course.semester_id == semester_id)
        .count()
    )
    if found != len(unique_ids):
        raise HTTPException(
            status_code=422, detail="Some courses are not in this semester"
        )


def semester_course_ids(db: Session, semester_id: int) -> list[int]:
    return [
        row.id
        for row in db.query(Course.id).filter(Course.semester_id == semester_id)
    ]


def leave_role(db: Session, user: User) -> None:
    """Remove links that only make sense for the user's current role."""
    if user.role == Role.INSTRUCTOR:
        in_schedule = (
            db.query(ScheduleEntry)
            .filter(ScheduleEntry.instructor_id == user.id)
            .first()
        )
        if in_schedule is not None:
            raise HTTPException(
                status_code=409,
                detail="This instructor teaches classes in a schedule. "
                "Reassign those classes before changing their role.",
            )
        db.query(CourseInstructor).filter(
            CourseInstructor.instructor_id == user.id
        ).delete()
        user.coordinator_id = None
    elif user.role == Role.STUDENT:
        db.query(Enrollment).filter(Enrollment.student_id == user.id).delete()
    elif user.role == Role.COORDINATOR:
        db.query(User).filter(User.coordinator_id == user.id).update(
            {User.coordinator_id: None}
        )


@router.get("/users")
def list_users(
    role: Role | None = None,
    search: str = "",
    include_inactive: bool = True,
    db: Session = Depends(get_db),
) -> list[dict]:
    """List users, optionally filtered by role and a name/username/email."""
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    if search.strip():
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            User.username.ilike(pattern)
            | User.full_name.ilike(pattern)
            | User.email.ilike(pattern)
        )
    users = query.order_by(User.role, User.full_name).all()
    return [user_to_admin_dict(user) for user in users]


@router.post("/users", status_code=201)
def create_user(body: CreateUserRequest, db: Session = Depends(get_db)) -> dict:
    """Create a user with any role."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username is already taken")
    check_email_free(db, body.email, None)
    is_instructor = body.role == Role.INSTRUCTOR
    if is_instructor:
        check_coordinator(db, body.coordinator_id)

    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        coordinator_id=body.coordinator_id if is_instructor else None,
        min_course_load=body.min_course_load,
        max_course_load=body.max_course_load,
    )
    db.add(user)
    commit_or_409(db)
    db.refresh(user)
    return user_to_admin_dict(user)


@router.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)) -> dict:
    return user_to_admin_dict(get_user_or_404(db, user_id))


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(coordinator),
) -> dict:
    """Change a user's details, role or active status."""
    user = get_user_or_404(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("email", "full_name", "role", "is_active"):
        if field in changes and changes[field] is None:
            raise HTTPException(
                status_code=422, detail=f"{field} cannot be empty"
            )

    if user.id == current_user.id:
        if changes.get("role", user.role) != user.role:
            raise HTTPException(
                status_code=400, detail="You cannot change your own role"
            )
        if changes.get("is_active") is False:
            raise HTTPException(
                status_code=400, detail="You cannot deactivate yourself"
            )

    if "email" in changes:
        check_email_free(db, changes["email"], user.id)
    new_role = changes.get("role", user.role)
    if new_role != user.role:
        leave_role(db, user)
    if new_role == Role.INSTRUCTOR and "coordinator_id" in changes:
        check_coordinator(db, changes["coordinator_id"])
    elif new_role != Role.INSTRUCTOR:
        changes.pop("coordinator_id", None)

    min_load = changes.get("min_course_load", user.min_course_load)
    max_load = changes.get("max_course_load", user.max_course_load)
    if min_load > max_load:
        raise HTTPException(
            status_code=422, detail="Minimum course load is above the maximum"
        )

    for field, value in changes.items():
        setattr(user, field, value)
    commit_or_409(db)
    db.refresh(user)
    return user_to_admin_dict(user)


@router.put("/users/{user_id}/password")
def reset_password(
    user_id: int, body: PasswordRequest, db: Session = Depends(get_db)
) -> dict:
    """Set a new password for the user (e.g. a temporary one)."""
    user = get_user_or_404(db, user_id)
    user.password_hash = hash_password(body.password)
    db.commit()
    return {"status": "ok"}


@router.get("/users/{user_id}/courses")
def user_courses(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """The user's courses: enrollments (students) or preferences (instructors)."""
    user = get_user_or_404(db, user_id)
    if user.role == Role.STUDENT:
        rows = [
            (link.course, "enrolled")
            for link in db.query(Enrollment).filter(
                Enrollment.student_id == user.id
            )
        ]
    elif user.role == Role.INSTRUCTOR:
        rows = [
            (link.course, link.preference.value)
            for link in db.query(CourseInstructor).filter(
                CourseInstructor.instructor_id == user.id
            )
        ]
    else:
        rows = []
    return [
        {
            "course_id": course.id,
            "code": course.code,
            "name": course.name,
            "semester_id": course.semester_id,
            "semester_name": course.semester.name,
            "relation": relation,
        }
        for course, relation in sorted(rows, key=lambda row: row[0].code)
    ]


@router.put("/users/{user_id}/enrollments")
def set_enrollments(
    user_id: int, body: EnrollmentsRequest, db: Session = Depends(get_db)
) -> dict:
    """Replace a student's courses in one semester."""
    user = get_user_or_404(db, user_id)
    if user.role != Role.STUDENT:
        raise HTTPException(
            status_code=422, detail="Only students can be enrolled in courses"
        )
    courses_in_semester(db, body.semester_id, body.course_ids)

    db.query(Enrollment).filter(
        Enrollment.student_id == user.id,
        Enrollment.course_id.in_(semester_course_ids(db, body.semester_id)),
    ).delete()
    db.add_all(
        Enrollment(student_id=user.id, course_id=course_id)
        for course_id in set(body.course_ids)
    )
    db.commit()
    return {"status": "ok"}


@router.put("/users/{user_id}/teaching")
def set_teaching(
    user_id: int, body: TeachingRequest, db: Session = Depends(get_db)
) -> dict:
    """Replace an instructor's teaching preferences in one semester."""
    user = get_user_or_404(db, user_id)
    if user.role != Role.INSTRUCTOR:
        raise HTTPException(
            status_code=422, detail="Only instructors can be assigned to teach"
        )
    courses_in_semester(db, body.semester_id, body.preferred + body.qualified)

    db.query(CourseInstructor).filter(
        CourseInstructor.instructor_id == user.id,
        CourseInstructor.course_id.in_(
            semester_course_ids(db, body.semester_id)
        ),
    ).delete()
    for course_ids, preference in (
        (body.preferred, CoursePreference.PREFERRED),
        (body.qualified, CoursePreference.QUALIFIED),
    ):
        db.add_all(
            CourseInstructor(
                instructor_id=user.id,
                course_id=course_id,
                preference=preference,
            )
            for course_id in set(course_ids)
        )
    db.commit()
    return {"status": "ok"}
