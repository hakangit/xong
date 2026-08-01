"""Multi-tenant auth: the autoconfig document and OIDC token validation.

These exist because the iOS client can be pointed at ANY organization's Xong
server, so the identity path must be provider-agnostic and must not weaken the
existing agent API-key path.
"""

from __future__ import annotations

import datetime as dt
import secrets

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from xong import config, oidc

ISSUER = "https://id.example.test"


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc_env(monkeypatch, rsa_key):
    """Point the app at a fake issuer whose signing key we control."""
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "xong-ios")
    monkeypatch.setenv("OIDC_SCOPES", "openid profile api:aud")
    monkeypatch.setenv("XONG_ORG_NAME", "Example Co")
    config.get_oidc_issuer.cache_clear()
    config.get_oidc_audience.cache_clear()
    config.get_oidc_client_id.cache_clear()
    config.get_oidc_scopes.cache_clear()
    config.get_org_name.cache_clear()
    config.get_public_api_base.cache_clear()

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
    config.get_oidc_client_id.cache_clear()
    config.get_oidc_scopes.cache_clear()
    config.get_org_name.cache_clear()


def make_token(key, **claims):
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "iss": ISSUER,
        "sub": "user-123",
        "exp": now + dt.timedelta(minutes=10),
        "iat": now,
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def test_agent_api_keys_are_never_parsed_as_jwts():
    """The Bearer header carries two different credential types. If an opaque
    agent key were mistaken for a JWT, every agent request would 401 — so the
    discriminator has to hold for the key format the CLI actually issues."""
    for _ in range(200):
        assert not oidc.looks_like_jwt(f"xong_{secrets.token_urlsafe(32)}")

    assert oidc.looks_like_jwt("header.payload.signature")


def test_valid_token_authenticates_and_creates_user(client: TestClient, oidc_env, rsa_key):
    token = make_token(rsa_key, preferred_username="user-one", name="User One Nguyen")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["username"] == "user-one"


def test_token_signed_by_another_key_is_rejected(client: TestClient, oidc_env):
    """A token the issuer never signed must not authenticate — this is the
    whole point of validating against JWKS rather than decoding claims."""
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(attacker_key, preferred_username="user-one")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_expired_token_is_rejected(client: TestClient, oidc_env, rsa_key):
    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "user-123",
            "preferred_username": "user-one",
            "exp": now - dt.timedelta(minutes=1),
            "iat": now - dt.timedelta(minutes=10),
        },
        rsa_key,
        algorithm="RS256",
    )

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_username_falls_back_when_preferred_username_absent():
    """Not every provider issues preferred_username; identity must still
    resolve rather than 500."""
    assert oidc.username_from_claims({"email": "a@b.test", "sub": "x"}) == "a@b.test"
    assert oidc.username_from_claims({"sub": "x"}) == "x"

    with pytest.raises(oidc.OIDCError):
        oidc.username_from_claims({})


def test_configured_audience_is_required(client: TestClient, oidc_env, rsa_key, monkeypatch):
    monkeypatch.setenv("OIDC_AUDIENCE", "xong-api")
    config.get_oidc_audience.cache_clear()
    try:
        accepted = make_token(rsa_key, aud="xong-api")
        rejected = make_token(rsa_key, aud="another-api")

        assert client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {accepted}"}
        ).status_code == 200
        assert client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {rejected}"}
        ).status_code == 401
    finally:
        config.get_oidc_audience.cache_clear()


def test_token_with_small_clock_skew_is_accepted(client: TestClient, oidc_env, rsa_key):
    """Minor clock differences must not reject an otherwise valid fresh token."""
    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "user-123",
            "preferred_username": "user-one",
            "iat": now + dt.timedelta(seconds=5),
            "nbf": now + dt.timedelta(seconds=5),
            "exp": now + dt.timedelta(minutes=10),
        },
        rsa_key,
        algorithm="RS256",
    )

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.json()


def test_token_expired_beyond_clock_skew_is_rejected(client: TestClient, oidc_env, rsa_key):
    """Clock tolerance must not admit a token that is clearly expired."""
    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "user-123",
            "preferred_username": "user-one",
            "iat": now - dt.timedelta(hours=2),
            "exp": now - dt.timedelta(hours=1),
        },
        rsa_key,
        algorithm="RS256",
    )

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_config_document_advertises_oidc_when_configured(client: TestClient, oidc_env):
    response = client.get("/.well-known/xong-config")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["name"] == "Example Co"
    assert body["api_base"].endswith("/api/v1")
    assert body["auth"]["type"] == "oidc"
    assert body["auth"]["issuer"] == ISSUER
    assert body["auth"]["client_id"] == "xong-ios"
    assert body["auth"]["scopes"] == "openid profile api:aud"


def test_endpoints_survive_the_frontend_mount(monkeypatch, tmp_path):
    """StaticFiles mounted at "/" matches every path, so anything registered
    after it is unreachable. The container sets XONG_STATIC_DIR, so the wrong
    ordering makes orchestrator health checks return 404."""
    import importlib

    (tmp_path / "index.html").write_text("<html></html>")
    monkeypatch.setenv("XONG_STATIC_DIR", str(tmp_path))

    import xong.app

    importlib.reload(xong.app)
    try:
        with TestClient(xong.app.app) as c:
            assert c.get("/healthz").status_code == 200
            assert c.get("/.well-known/xong-config").status_code == 200
            assert c.get("/").status_code == 200
    finally:
        monkeypatch.delenv("XONG_STATIC_DIR", raising=False)
        importlib.reload(xong.app)


def test_preflight_from_ios_shell_succeeds(client: TestClient):
    """The iOS shell's origin is xong-app://localhost, so every request is
    preflighted. If the preflight 405s the frontend silently falls back to its
    local cache — the app looks healthy while syncing nothing."""
    response = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "xong-app://localhost",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "xong-app://localhost"


def test_preflight_from_unknown_origin_is_not_allowed(client: TestClient):
    """Multi-tenant server: a wildcard would let any website script against a
    logged-in session. Only configured origins may get the CORS header."""
    response = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_config_document_reports_none_without_an_idp(client: TestClient, monkeypatch):
    """A deployment behind trusted forward-auth has no client-side token; the
    client must be told that rather than being sent to a nonexistent IdP."""
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
    config.get_oidc_issuer.cache_clear()
    config.get_oidc_client_id.cache_clear()
    body = client.get("/.well-known/xong-config").json()

    assert body["auth"]["type"] == "none"
    assert "issuer" not in body["auth"]

    config.get_oidc_issuer.cache_clear()
    config.get_oidc_client_id.cache_clear()
