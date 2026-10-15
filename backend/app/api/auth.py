"""Login and account creation endpoints (stories 1-2)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.common import Role
from app.models.user import User

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    """Self sign-up. Accounts created this way are always students."""

    username: str = Field(
        min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$"
    )
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)

    @field_validator("username", "full_name", mode="before")
    @classmethod
    def strip_spaces(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("username", "email")
    @classmethod
    def lowercase(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes long")
        return value


def user_to_dict(user: User | CurrentUser) -> dict:
    """Return the public fields of a user (never the password hash)."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
    }


def token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user_to_dict(user)),
        "token_type": "bearer",
        "user": user_to_dict(user),
    }


@router.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """Log in with a username and password (acceptance criteria 1.1, 1.2)."""
    username = body.username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid login")
    return token_response(user)


@router.post("/auth/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    """Create a student account and log it in (acceptance criteria 2.1, 2.2)."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username is already taken")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(
            status_code=409, detail="Email is already registered"
        )

    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=Role.STUDENT,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # Lost a race with a matching sign-up.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Username or email is already registered"
        ) from exc
    db.refresh(user)
    return token_response(user)


@router.get("/auth/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the logged-in user (read from their token, not the database)."""
    return user_to_dict(user)
