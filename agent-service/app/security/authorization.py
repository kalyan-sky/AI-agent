"""Role-based authorization.

Roles form a strict hierarchy: admin > operator > viewer. `require_role`
returns a FastAPI dependency that 403s if the caller's role is below the
minimum required for the endpoint. The import of `get_current_principal`
is deferred to break the api_key.py <-> authorization.py import cycle
(api_key.py needs `Role` from here; this module needs the principal
dependency from there).
"""
from enum import IntEnum

from fastapi import Depends, HTTPException, status


class Role(IntEnum):
    viewer = 1
    operator = 2
    admin = 3


def require_role(minimum: Role):
    from app.security.api_key import Principal, get_current_principal

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role < minimum:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Requires role '{minimum.name}' or higher; "
                    f"caller has '{principal.role.name}'"
                ),
            )
        return principal

    return dependency
