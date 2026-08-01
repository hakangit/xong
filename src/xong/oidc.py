"""Generic OIDC access-token validation.

Nothing here is vendor-specific: any provider that publishes
`/.well-known/openid-configuration` works, which is what lets a Xong server be
deployed by an organization running any standards-compliant OIDC provider.
anything else.
"""

from __future__ import annotations

import json
import urllib.request
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from xong.config import get_oidc_audience, get_oidc_issuer

ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
DISCOVERY_PATH = "/.well-known/openid-configuration"


class OIDCError(Exception):
    """Token could not be validated."""


def looks_like_jwt(token: str) -> bool:
    """Distinguishes a JWT from an opaque agent API key.

    Agent keys come from `secrets.token_urlsafe`, whose alphabet is
    [A-Za-z0-9_-] — it never contains a dot, so this split is unambiguous.
    """
    return token.count(".") == 2


@lru_cache
def _discovery(issuer: str) -> dict:
    with urllib.request.urlopen(issuer + DISCOVERY_PATH, timeout=10) as response:
        return json.loads(response.read())


@lru_cache
def _jwk_client(jwks_uri: str) -> PyJWKClient:
    # PyJWKClient caches keys and refetches on unknown kid, so key rotation
    # does not need a restart.
    return PyJWKClient(jwks_uri, cache_keys=True)


def validate_token(token: str) -> dict:
    """Verifies signature, issuer, expiry and (when configured) audience.

    Returns the token claims.
    """
    issuer = get_oidc_issuer()
    if not issuer:
        raise OIDCError("OIDC_ISSUER is not configured")

    try:
        metadata = _discovery(issuer)
        jwks_uri = metadata["jwks_uri"]
        signing_key = _jwk_client(jwks_uri).get_signing_key_from_jwt(token)
    except Exception as exc:  # network, malformed discovery, unknown kid
        raise OIDCError(f"Cannot resolve signing key: {exc}") from exc

    audience = get_oidc_audience()
    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            issuer=metadata.get("issuer", issuer),
            audience=audience,
            options={"verify_aud": audience is not None, "require": ["exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(str(exc)) from exc


def username_from_claims(claims: dict) -> str:
    """Maps token claims to a Xong username, matching the Remote-User identity
    a trusted reverse-proxy path may also create."""
    for claim in ("preferred_username", "email", "sub"):
        value = (claims.get(claim) or "").strip()
        if value:
            return value
    raise OIDCError("No usable identity claim in token")
