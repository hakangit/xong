from unittest.mock import patch

from fastapi.testclient import TestClient

from xong import assistant, config
from xong.app import create_app


def _app(monkeypatch, plugins: str, router_base: str | None = None):
    monkeypatch.setenv("XONG_PLUGINS", plugins)
    if router_base is None:
        monkeypatch.delenv("XONG_ROUTER_BASE", raising=False)
    else:
        monkeypatch.setenv("XONG_ROUTER_BASE", router_base)
    config.get_plugins.cache_clear()
    assistant.router_base.cache_clear()
    return create_app()


def test_disabled_plugin_routes_are_absent(monkeypatch):
    """Disabled routes return 404 so off and absent are indistinguishable."""
    with TestClient(_app(monkeypatch, "")) as client:
        assert client.get("/api/v1/assistant").status_code == 404
        assert client.get("/api/v1/org/people").status_code == 404
        assert client.get("/api/v1/tasks/1/attachments").status_code == 404
        assert client.post("/mcp").status_code == 404
        assert client.get("/.well-known/agent-card.json").status_code == 404
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_config_version_bump_preserves_existing_fields(monkeypatch):
    with TestClient(_app(monkeypatch, "org,files,mcp,a2a")) as client:
        body = client.get("/.well-known/xong-config").json()

    assert body["version"] == 2
    assert body["name"] == "Xong"
    assert body["api_base"].endswith("/api/v1")
    assert body["auth"] == {"type": "none"}
    assert body["capabilities"] == ["files", "org", "mcp", "a2a"]


def test_unconfigured_assistant_is_not_advertised(monkeypatch):
    with patch("xong.app.logger.warning") as warning:
        with TestClient(_app(monkeypatch, "assistant")) as client:
            body = client.get("/.well-known/xong-config").json()
            assert client.get("/api/v1/assistant").status_code == 404

    assert body["capabilities"] == []
    warning.assert_called_once()
    assert "XONG_ROUTER_BASE is unset" in warning.call_args.args[0]


def test_schema_revision_matches_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert head == config.SCHEMA_REVISION
