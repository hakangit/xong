from __future__ import annotations

import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from xong.config import get_database_url

PLUGINS = set(os.environ.get("XONG_PLUGINS", "").split(","))


def _agent_headers(acts_for: str = "user-one") -> dict[str, str]:
    raw = "xong_protocol_" + "x" * 24
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO api_keys (key_hash, agent_name, acts_for) "
                "VALUES (:key_hash, :agent_name, :acts_for)"
            ),
            {
                "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
                "agent_name": "protocol-agent",
                "acts_for": [acts_for],
            },
        )
    engine.dispose()
    return {"Authorization": f"Bearer {raw}", "X-Acts-For": acts_for}


def _mcp_request(client: TestClient, method: str, params: dict, headers: dict):
    return client.post(
        "/mcp",
        headers={"Accept": "application/json, text/event-stream", **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


@pytest.mark.skipif("mcp" not in PLUGINS, reason="mcp plugin disabled")
def test_mcp_requires_known_bearer_key(client: TestClient):
    missing = _mcp_request(client, "tools/list", {}, {})
    assert missing.status_code == 401
    assert "resource_metadata=" in missing.headers["www-authenticate"]

    unknown = _mcp_request(
        client,
        "tools/list",
        {},
        {"Authorization": "Bearer xong_valid_format_but_unknown", "X-Acts-For": "user-one"},
    )
    assert unknown.status_code == 401


@pytest.mark.skipif("mcp" not in PLUGINS, reason="mcp plugin disabled")
def test_mcp_lists_tools_and_manages_tasks_for_acts_for_user(client: TestClient):
    headers = _agent_headers()
    initialized = _mcp_request(
        client,
        "initialize",
        {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
        headers,
    )
    assert initialized.status_code == 200, initialized.text

    tools = _mcp_request(client, "tools/list", {}, headers)
    assert tools.status_code == 200, tools.text
    names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert names == {
        "list_tasks",
        "create_task",
        "complete_task",
        "today",
        "get_focus",
        "set_focus",
    }

    created = _mcp_request(
        client,
        "tools/call",
        {"name": "create_task", "arguments": {"title": "Created through MCP"}},
        headers,
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["result"]["structuredContent"]["id"]

    completed = _mcp_request(
        client,
        "tools/call",
        {"name": "complete_task", "arguments": {"task_id": task_id}},
        headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["result"]["structuredContent"]["completed_at"]


@pytest.mark.skipif("a2a" not in PLUGINS, reason="a2a plugin disabled")
def test_a2a_ignores_client_user_and_uses_authenticated_principal(client: TestClient):
    headers = _agent_headers("user-one")
    response = client.post(
        "/a2a",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": "a2a-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "message-1",
                    "parts": [
                        {
                            "data": {
                                "operation": "create_task",
                                "arguments": {
                                    "title": "A2A scoped task",
                                    "user": "user-two",
                                },
                            }
                        }
                    ],
                }
            },
        },
    )
    assert response.status_code == 200, response.text

    lien_tasks = client.get("/api/v1/tasks", headers=headers).json()
    assert [task["title"] for task in lien_tasks] == ["A2A scoped task"]
