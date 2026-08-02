from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from xong import oidc
from xong.config import DEFAULT_LIST_NAME, get_dev_user, get_link_domains
from xong.db import get_db
from xong.models import ApiKey, List, User, UserIdentity


@dataclass
class AuthContext:
    user: User
    actor: str  # username or agent name
    is_agent: bool


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"xong_{secrets.token_urlsafe(32)}"


DEFAULT_LIST_NAMES = {"vi": DEFAULT_LIST_NAME, "en": "My tasks", "zh": "我的事项"}


def default_list_name(accept_language: str | None) -> str:
    lang = (accept_language or "").strip().lower()
    for code in ("vi", "zh", "en"):
        if lang.startswith(code):
            return DEFAULT_LIST_NAMES[code]
    return DEFAULT_LIST_NAMES["en"]


def _create_user(
    db: Session,
    username: str,
    email: str | None,
    display_name: str | None,
    accept_language: str | None,
) -> User:
    # username is a display handle, not an identity key — a collision with an
    # UNLINKED account means a different person (or one the operator must link
    # manually), so pick a free handle rather than piggyback on the row.
    handle, n = username, 1
    while db.query(User.id).filter(User.username == handle).one_or_none() is not None:
        n += 1
        handle = f"{username}-{n}"
    user = User(
        username=handle,
        display_name=display_name or username,
        email=email,
    )
    db.add(user)
    db.flush()
    default_list = List(
        owner_id=user.id,
        name=default_list_name(accept_language),
        position=0,
        archived=False,
    )
    db.add(default_list)
    return user


def resolve_identity(
    db: Session,
    provider: str,
    subject: str,
    *,
    email: str | None = None,
    username: str | None = None,
    display_name: str | None = None,
    accept_language: str | None = None,
) -> User:
    """Identity is keyed on (provider, subject) — never on email or username,
    which OIDC documents as mutable. A trusted email may LINK a new identity
    to an existing account once, but only for domains the operator claims via
    XONG_LINK_DOMAINS; after that the stored identity row wins, so address
    changes or reuse can never move anyone's tasks."""
    identity = (
        db.query(UserIdentity)
        .filter(UserIdentity.provider == provider, UserIdentity.subject == subject)
        .one_or_none()
    )
    if identity is not None:
        return db.query(User).filter(User.id == identity.user_id).one()

    email = (email or "").strip().lower() or None
    if email and email.rsplit("@", 1)[-1] in get_link_domains():
        user = db.query(User).filter(func.lower(User.email) == email).one_or_none()
        if user is not None:
            db.add(UserIdentity(provider=provider, subject=subject, user_id=user.id))
            db.commit()
            return user

    # If the address is already on another account but linking didn't fire
    # (domain not claimed, or email unverified), the new account must not
    # claim it — lower(email) is unique so storing it would fail, and silently
    # attaching to the other row is exactly what the rules forbid.
    if email is not None:
        taken = db.query(User.id).filter(func.lower(User.email) == email).one_or_none()
        if taken is not None:
            email = None
    user = _create_user(db, username or subject, email, display_name, accept_language)
    db.add(UserIdentity(provider=provider, subject=subject, user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


def resolve_auth(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_acts_for: str | None = Header(default=None, alias="X-Acts-For"),
    remote_user: str | None = Header(default=None, alias="Remote-User"),
    remote_email: str | None = Header(default=None, alias="Remote-Email"),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> AuthContext:
    challenge = {"WWW-Authenticate": "Bearer"}
    # Bearer is either a human's OIDC access token or an agent's API key.
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if not raw:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
                headers=challenge,
            )

        # Human: OIDC access token from a native/web client.
        if oidc.looks_like_jwt(raw):
            try:
                claims = oidc.validate_token(raw)
                username = oidc.username_from_claims(claims)
            except oidc.OIDCError as exc:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {exc}",
                    headers=challenge,
                ) from exc
            # email is a linking hint only, and only when the IdP vouches for it.
            verified_email = claims.get("email") if claims.get("email_verified") else None
            user = resolve_identity(
                db,
                provider=f"oidc:{claims['iss']}",
                subject=claims["sub"],
                email=verified_email,
                username=username,
                display_name=claims.get("name"),
                accept_language=accept_language,
            )
            return AuthContext(user=user, actor=user.username, is_agent=False)

        key_hash = hash_api_key(raw)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).one_or_none()
        if api_key is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers=challenge,
            )
        if not x_acts_for:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="X-Acts-For header required for agent requests",
            )
        acts_for = x_acts_for.strip()
        if acts_for not in (api_key.acts_for or []):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Agent may not act for '{acts_for}'",
            )
        # acts_for names a directory account, i.e. the same namespace as
        # Remote-User — resolving it through the SAME proxy identity keeps
        # agent-created tasks on the account the human sees in every client.
        user = resolve_identity(db, provider="proxy", subject=acts_for)
        return AuthContext(user=user, actor=api_key.agent_name, is_agent=True)

    # Human: Remote-User or DEV_USER
    username = (remote_user or "").strip() or get_dev_user()
    if not username:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (Remote-User or DEV_USER)",
            headers=challenge,
        )
    # Remote-Email comes from the forward-auth proxy (Authelia), which is the
    # trust boundary here — it never reaches us unauthenticated.
    user = resolve_identity(
        db,
        provider="proxy",
        subject=username,
        email=(remote_email or "").strip() or None,
        accept_language=accept_language,
    )
    return AuthContext(user=user, actor=user.username, is_agent=False)


def require_auth(ctx: AuthContext = Depends(resolve_auth)) -> AuthContext:
    return ctx


def require_bearer_auth(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_acts_for: str | None = Header(default=None, alias="X-Acts-For"),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolve_auth(
        db=db,
        authorization=authorization,
        x_acts_for=x_acts_for,
        remote_user=None,
        remote_email=None,
        accept_language=accept_language,
    )
