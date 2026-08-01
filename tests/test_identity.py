"""Identity resolution: one human, many auth paths, ONE user row.

The bug this guards against: OIDC keyed users on preferred_username (often an
email) while forward-auth keyed on Remote-User (a directory account name), so
the same person got two accounts and an empty list on their second client.
That regression is invisible in any single-path test, so these tests cross
paths deliberately.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from xong import config, oidc
from xong.config import get_database_url

ISSUER = "https://id.example.test"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc_env(monkeypatch, rsa_key):
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    config.get_oidc_issuer.cache_clear()
    config.get_oidc_audience.cache_clear()

    class FakeSigningKey:
        key = rsa_key.public_key()

    class FakeJWKClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr(
        oidc, "_discovery", lambda issuer: {"issuer": ISSUER, "jwks_uri": ISSUER + "/keys"}
    )
    monkeypatch.setattr(oidc, "_jwk_client", lambda uri: FakeJWKClient())
    yield
    config.get_oidc_issuer.cache_clear()


@pytest.fixture
def link_domains(monkeypatch):
    monkeypatch.setenv("XONG_LINK_DOMAINS", "example.test")
    config.get_link_domains.cache_clear()
    yield
    config.get_link_domains.cache_clear()


def make_token(key, **claims):
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "iss": ISSUER,
        "sub": "sub-alice",
        "exp": now + dt.timedelta(minutes=10),
        "iat": now,
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def user_rows():
    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, username, email FROM users ORDER BY id")).fetchall()
    engine.dispose()
    return rows


def identity_rows():
    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT provider, subject, user_id FROM user_identities ORDER BY id")
        ).fetchall()
    engine.dispose()
    return rows


def test_forward_auth_then_oidc_resolves_to_one_user(
    client: TestClient, oidc_env, link_domains, rsa_key
):
    """The exact reported symptom: sign in on desktop (Remote-User), then on
    iOS (OIDC). Without linking, the iOS list is empty because it's a second
    account."""
    r = client.get(
        "/api/v1/me", headers={"Remote-User": "alice", "Remote-Email": "Alice@Example.Test"}
    )
    assert r.status_code == 200

    token = make_token(
        rsa_key,
        preferred_username="alice@example.test",
        email="alice@example.test",
        email_verified=True,
    )
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"

    assert len(user_rows()) == 1
    assert {(p, s) for p, s, _ in identity_rows()} == {
        ("proxy", "alice"),
        (f"oidc:{ISSUER}", "sub-alice"),
    }


def test_no_link_domains_means_no_auto_linking(client: TestClient, oidc_env, rsa_key):
    """Safe by default: a fresh deployment must opt in per domain, otherwise a
    matching address on any IdP would be an account-takeover path."""
    client.get("/api/v1/me", headers={"Remote-User": "alice", "Remote-Email": "alice@example.test"})
    token = make_token(rsa_key, email="alice@example.test", email_verified=True)
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert len(user_rows()) == 2


def test_unverified_email_never_links(client: TestClient, oidc_env, link_domains, rsa_key):
    """`email` without `email_verified` is attacker-settable on many IdPs; it
    must not link even for a claimed domain."""
    client.get("/api/v1/me", headers={"Remote-User": "alice", "Remote-Email": "alice@example.test"})
    token = make_token(rsa_key, email="alice@example.test")
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert len(user_rows()) == 2


def test_agent_acts_for_lands_on_the_forward_auth_account(client: TestClient):
    """acts_for and Remote-User are the same directory namespace; the agent
    writing to a DIFFERENT row than the human sees was the same split-account
    bug one layer down."""
    client.get("/api/v1/me", headers={"Remote-User": "bob"})

    raw = "xong_identity_test_key"
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO api_keys (key_hash, agent_name, acts_for) VALUES (:h, :n, :a)"),
            {"h": hashlib.sha256(raw.encode()).hexdigest(), "n": "agent", "a": ["bob"]},
        )
    engine.dispose()

    r = client.post(
        "/api/v1/tasks",
        json={"title": "from the agent"},
        headers={"Authorization": f"Bearer {raw}", "X-Acts-For": "bob"},
    )
    assert r.status_code in (200, 201)
    assert len(user_rows()) == 1

    r = client.get("/api/v1/today", headers={"Remote-User": "bob"})
    titles = [t["title"] for t in r.json()["default_tasks"]]
    assert "from the agent" in titles


def test_identity_wins_over_changed_email(client: TestClient, oidc_env, link_domains, rsa_key):
    """Link once, then the stored identity row resolves — an email change (or
    address reuse by a new hire) must never move anyone's tasks."""
    token = make_token(rsa_key, email="alice@example.test", email_verified=True)
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    before = user_rows()

    moved = make_token(rsa_key, email="other@example.test", email_verified=True)
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {moved}"})

    assert user_rows() == before


def test_username_collision_creates_a_new_handle(client: TestClient, oidc_env, rsa_key):
    """An OIDC arrival whose preferred_username equals an existing UNLINKED
    account's username must not silently take over that account — usernames
    are display handles, not keys."""
    client.get("/api/v1/me", headers={"Remote-User": "alice"})
    token = make_token(rsa_key, preferred_username="alice")
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["username"] == "alice-2"
    assert len(user_rows()) == 2
