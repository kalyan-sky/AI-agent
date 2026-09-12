"""OAuth 2.0 client-credentials — design notes and JWT validation helper.

This service's primary auth is the static API-key allowlist in `api_key.py`
(appropriate for n8n / internal service callers). This module documents and
implements the piece that would let a *real* OAuth2 client-credentials flow
plug into the same `Principal`-shaped dependency without touching route
code, and provides the JWT validation used if/when `OAUTH_TOKEN_URL` is set:

    1. A client (e.g. an external system, or n8n's OAuth2 credential type)
       obtains an access token from `OAUTH_TOKEN_URL` using
       `grant_type=client_credentials` + its `client_id`/`client_secret`.
    2. That token — a signed JWT — is sent as `Authorization: Bearer <jwt>`.
    3. `get_current_principal_oauth` below verifies the JWT's signature,
       issuer, and expiry (never trusting unverified claims), then maps a
       `role` claim to our `Role` enum the same way `api_key.py` does for
       static keys.

We do not fetch tokens ourselves here (this service is a resource server,
not an OAuth client) and we never accept an unverified/`alg=none` JWT.
"""
from jose import JWTError, jwt

from app.config import Settings
from app.security.authorization import Role


class InvalidTokenError(Exception):
    pass


def validate_access_token(token: str, settings: Settings) -> Role:
    """Verify a client-credentials JWT and return the caller's role.

    Raises InvalidTokenError on any signature, issuer, expiry, or claim
    problem — callers must map this to an HTTP 401, never fall back to a
    default role.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require_exp": True, "require_iat": True},
        )
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    role_claim = claims.get("role")
    try:
        return Role[role_claim]
    except (KeyError, TypeError) as exc:
        raise InvalidTokenError(f"unknown or missing role claim: {role_claim!r}") from exc
