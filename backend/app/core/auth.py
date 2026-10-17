"""Authentication integration points for protected API endpoints."""

from fastapi import Depends, HTTPException, status

from app.api.deps import CurrentUser, get_current_user
from app.models.common import Role
from app.models.user import User


def current_user(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Resolve the user from the shared signed access-token dependency."""
    return user


def coordinator_only(user: User = Depends(current_user)) -> User:
    """Require a coordinator account."""
    if user.role != Role.COORDINATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coordinator access required",
        )
    return user


def instructor_only(user: User = Depends(current_user)) -> User:
    """Require an instructor account."""
    if user.role != Role.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor access required",
        )
    return user
