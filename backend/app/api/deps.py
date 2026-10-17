"""Route dependencies: who is logged in, and what they may do.

Every route except the public ones (health checks, login and account
creation) must depend on `get_current_user` or `require_role`.

The logged-in user comes from the signed token, not the database, so these
checks cost no query. A change to a user (role, deactivation) therefore takes
effect when their token expires (ACCESS_TOKEN_EXPIRE_MINUTES) or they log in
again. Login itself always checks the database.
"""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.models.common import Role

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """The logged-in user, as carried in their token."""

    id: int
    username: str
    email: str
    full_name: str
    role: Role


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Return the logged-in user, or respond 401."""
    not_authenticated = HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    claims = (
        decode_access_token(credentials.credentials) if credentials else None
    )
    if claims is None:  # No token, or an invalid or expired one.
        raise not_authenticated
    try:
        role = Role(claims["role"])
    except ValueError:
        raise not_authenticated from None
    return CurrentUser(**{**claims, "role": role})


def require_role(*roles: Role) -> Callable[..., CurrentUser]:
    """Return a dependency that only lets users with one of the roles in.

    Example: `Depends(require_role(Role.COORDINATOR))`.
    """

    def check_role(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403, detail="Not allowed for your role"
            )
        return user

    return check_role
