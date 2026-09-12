"""API key authentication.

Keys are configured as `API_KEYS=key1:role1,key2:role2` (see Settings).
This is intentionally simple — a static allowlist suitable for a service
talking to n8n / internal callers. `oauth.py` documents how a real OAuth2
client-credentials flow would plug in alongside this without changing the
route-level dependency shape.
"""

from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.security.authorization import Role


@dataclass(frozen=True)
class Principal:
    api_key: str
    role: Role


@lru_cache
def _load_key_map(api_keys_raw: str) -> dict[str, Role]:
    mapping: dict[str, Role] = {}
    for entry in api_keys_raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, _, role_name = entry.partition(":")
        try:
            mapping[key] = Role[role_name]
        except KeyError:
            continue  # malformed entry in config — never crash the process over it
    return mapping


def get_current_principal(
    request: Request, settings: Settings = Depends(get_settings)
) -> Principal:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = auth_header[len("bearer ") :].strip()
    key_map = _load_key_map(settings.api_keys)
    role = key_map.get(api_key)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(api_key=api_key, role=role)
