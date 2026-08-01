from __future__ import annotations

import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from xong.config import get_database_url

PLUGINS = set(os.environ.get("XONG_PLUGINS", "").split(","))


def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_readyz_verifies_migrated_schema(client: TestClient):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "schema": "009"}


def test_readyz_rejects_wrong_schema(client: TestClient, monkeypatch):
    monkeypatch.setattr("xong.app.SCHEMA_REVISION", "999")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database schema 009; expected 999"


def test_untrusted_host_is_rejected(client: TestClient):
    response = client.get("/healthz", headers={"Host": "attacker.example"})
    assert response.status_code == 400


def test_me_creates_user_and_default_list(client: TestClient):
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "testuser"
    assert body["tz"] == "UTC"

    context = client.get("/api/v1/auth/context")
    assert context.status_code == 200
    assert context.json() == {
        "actor": "testuser",
        "subject": "testuser",
        "is_agent": False,
    }

    lists = client.get("/api/v1/lists").json()
    assert len(lists) == 1
    assert lists[0]["name"] == "My tasks"  # no Accept-Language -> en default


def test_default_list_localized_by_accept_language(client: TestClient):
    cases = [
        ("vi-user", "vi-VN,vi;q=0.9", "Việc của tôi"),
        ("zh-user", "zh-CN,zh;q=0.9", "我的事项"),
        ("en-user", "en-US,en;q=0.9", "My tasks"),
    ]
    for username, accept, expected in cases:
        headers = {"Remote-User": username, "Accept-Language": accept}
        assert client.get("/api/v1/me", headers=headers).status_code == 200
        lists = client.get("/api/v1/lists", headers=headers).json()
        assert lists[0]["name"] == expected, (username, lists[0]["name"])


def test_task_crud_and_complete(client: TestClient):
    created = client.post("/api/v1/tasks", json={"title": "Call supplier"}).json()
    assert created["title"] == "Call supplier"
    assert created["completed_at"] is None
    tid = created["id"]

    tasks = client.get("/api/v1/tasks").json()
    assert any(t["id"] == tid for t in tasks)

    done = client.post(f"/api/v1/tasks/{tid}/complete").json()
    assert done["completed_at"] is not None

    open_tasks = client.get("/api/v1/tasks").json()
    assert not any(t["id"] == tid for t in open_tasks)

    undid = client.post(f"/api/v1/tasks/{tid}/uncomplete").json()
    assert undid["completed_at"] is None


def test_focus_max_three(client: TestClient):
    ids = []
    for i in range(4):
        t = client.post("/api/v1/tasks", json={"title": f"Do step {i}"}).json()
        ids.append(t["id"])

    ok = client.post("/api/v1/focus", json={"task_ids": ids[:3]})
    assert ok.status_code == 200
    assert len(ok.json()["task_ids"]) == 3

    bad = client.post("/api/v1/focus", json={"task_ids": ids})
    assert bad.status_code in (400, 422)


def test_today_and_streak(client: TestClient):
    t = client.post("/api/v1/tasks", json={"title": "Send report"}).json()
    client.post(f"/api/v1/tasks/{t['id']}/complete")
    today = client.get("/api/v1/today").json()
    assert today["streak"] >= 1
    assert "focus" in today
    assert "overdue" in today


def test_weekly_recap(client: TestClient):
    t = client.post("/api/v1/tasks", json={"title": "Win one"}).json()
    client.post(f"/api/v1/tasks/{t['id']}/complete")
    r = client.get("/api/v1/recap/weekly").json()
    assert r["total"] >= 1
    assert r["streak"] >= 1
    assert len(r["days"]) == 7


def test_events(client: TestClient):
    t = client.post("/api/v1/tasks", json={"title": "Event task"}).json()
    client.post(f"/api/v1/tasks/{t['id']}/complete")
    events = client.get("/api/v1/events").json()
    types = {e["event_type"] for e in events}
    assert "task_created" in types
    assert "task_completed" in types


def test_agent_api_key_flow(client: TestClient):
    raw = "xong_test_agent_key_abc123"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (key_hash, agent_name, acts_for) "
                "VALUES (:h, :n, :a)"
            ),
            {"h": key_hash, "n": "agent", "a": ["user-one"]},
        )
    engine.dispose()

    headers = {
        "Authorization": f"Bearer {raw}",
        "X-Acts-For": "user-one",
    }
    context = client.get("/api/v1/auth/context", headers=headers)
    assert context.status_code == 200
    assert context.json() == {
        "actor": "agent",
        "subject": "user-one",
        "is_agent": True,
    }

    r = client.post(
        "/api/v1/tasks",
        json={"title": "Agent task for user-one"},
        headers=headers,
    )
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["created_by"] == "agent"

    # Wrong acts-for
    bad = client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {raw}", "X-Acts-For": "user-two"},
    )
    assert bad.status_code == 403

    # Missing X-Acts-For
    miss = client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert miss.status_code == 400

    done = client.post(f"/api/v1/tasks/{tid}/complete", headers=headers)
    assert done.status_code == 200

    events = client.get("/api/v1/events", headers=headers).json()
    assert any(e["event_type"] == "task_completed" for e in events)
    assert any(e["actor"] == "agent" for e in events)


def test_vague_heuristic_flag(client: TestClient):
    vague = client.post("/api/v1/tasks", json={"title": "báo cáo"}).json()
    assert vague["looks_vague"] is True

    clear = client.post("/api/v1/tasks", json={"title": "Call vendor about yarn"}).json()
    assert clear["looks_vague"] is False

    with_next = client.post(
        "/api/v1/tasks",
        json={"title": "báo cáo", "next_action": "Mở file Excel"},
    ).json()
    assert with_next["looks_vague"] is False


def test_ui_today_renders(client: TestClient):
    client.post("/api/v1/tasks", json={"title": "UI task"})
    r = client.get("/")
    assert r.status_code == 200
    assert "Hôm nay" in r.text
    assert "Xong" in r.text
    assert "UI task" in r.text


def test_ui_complete(client: TestClient):
    t = client.post("/api/v1/tasks", json={"title": "Check me"}).json()
    r = client.post(f"/ui/tasks/{t['id']}/complete")
    assert r.status_code == 200
    open_tasks = client.get("/api/v1/tasks").json()
    assert not any(x["id"] == t["id"] for x in open_tasks)


def test_new_task_goes_to_top(client: TestClient):
    a = client.post("/api/v1/tasks", json={"title": "First"}).json()
    b = client.post("/api/v1/tasks", json={"title": "Second"}).json()
    tasks = client.get("/api/v1/tasks").json()
    assert tasks[0]["id"] == b["id"]
    assert tasks[1]["id"] == a["id"]


def _agent_key(agent: str, acts_for: list[str]) -> str:
    raw = f"xong_{agent}_" + "x" * 20
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (key_hash, agent_name, acts_for) "
                "VALUES (:h, :n, :a)"
            ),
            {"h": key_hash, "n": agent, "a": acts_for},
        )
    engine.dispose()
    return raw


@pytest.mark.skipif("files" not in PLUGINS, reason="files plugin disabled")
def test_attachment_link_add_list_delete(client: TestClient, tmp_path):
    t = client.post("/api/v1/tasks", json={"title": "Task with a link"}).json()
    r = client.post(
        f"/api/v1/tasks/{t['id']}/attachments/link",
        json={"url": "https://bravo.example/doc/123", "filename": "Contract"},
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["kind"] == "url"
    assert att["url"] == "https://bravo.example/doc/123"

    lst = client.get(f"/api/v1/tasks/{t['id']}/attachments").json()
    assert len(lst) == 1 and lst[0]["id"] == att["id"]

    # reject non-http url
    bad = client.post(
        f"/api/v1/tasks/{t['id']}/attachments/link",
        json={"url": "javascript:alert(1)"},
    )
    assert bad.status_code == 422

    d = client.delete(f"/api/v1/attachments/{att['id']}")
    assert d.status_code == 204
    assert client.get(f"/api/v1/tasks/{t['id']}/attachments").json() == []


@pytest.mark.skipif("files" not in PLUGINS, reason="files plugin disabled")
def test_attachment_file_roundtrip(client: TestClient, tmp_path, monkeypatch):
    from xong import config

    monkeypatch.setenv("XONG_FILES_DIR", str(tmp_path))
    config.get_files_dir.cache_clear()

    t = client.post("/api/v1/tasks", json={"title": "Task with a file"}).json()
    content = b"hello xong file"
    r = client.post(
        f"/api/v1/tasks/{t['id']}/attachments/file",
        files={"file": ("note.txt", content, "text/plain")},
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["kind"] == "file"
    assert att["size_bytes"] == len(content)

    # file landed under the per-user subfolder (testuser/<task>/...)
    import os

    users = os.listdir(tmp_path)
    assert "testuser" in users, users

    dl = client.get(f"/api/v1/attachments/{att['id']}/download")
    assert dl.status_code == 200
    assert dl.content == content

    # reject disallowed type
    bad = client.post(
        f"/api/v1/tasks/{t['id']}/attachments/file",
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 415


@pytest.mark.skipif("files" not in PLUGINS, reason="files plugin disabled")
def test_attachment_cross_user_segregation(client: TestClient, tmp_path, monkeypatch):
    from xong import config

    monkeypatch.setenv("XONG_FILES_DIR", str(tmp_path))
    config.get_files_dir.cache_clear()

    # agent acts for user-one, agent_two acts for user-two — distinct users
    agent = _agent_key("agent", ["user-one"])
    agent_two = _agent_key("agent_two", ["user-two"])
    sh = {"Authorization": f"Bearer {agent}", "X-Acts-For": "user-one"}
    nh = {"Authorization": f"Bearer {agent_two}", "X-Acts-For": "user-two"}

    # user-one makes a task + a file attachment
    lt = client.post("/api/v1/tasks", json={"title": "User One private"}, headers=sh).json()
    la = client.post(
        f"/api/v1/tasks/{lt['id']}/attachments/file",
        files={"file": ("secret.txt", b"user-one only", "text/plain")},
        headers=sh,
    ).json()

    # user-two must NOT list, download, or delete user-one's attachment
    assert client.get(
        f"/api/v1/tasks/{lt['id']}/attachments", headers=nh
    ).status_code == 404
    assert client.get(
        f"/api/v1/attachments/{la['id']}/download", headers=nh
    ).status_code == 404
    assert client.delete(
        f"/api/v1/attachments/{la['id']}", headers=nh
    ).status_code == 404

    # owner still can
    assert client.get(
        f"/api/v1/attachments/{la['id']}/download", headers=sh
    ).status_code == 200


@pytest.mark.skipif("assistant" not in PLUGINS, reason="assistant plugin disabled")
def test_assistant_detection(client: TestClient):
    # no api key acts for testuser yet -> no assistant
    r = client.get("/api/v1/assistant")
    assert r.status_code == 200
    assert r.json() == {"has_assistant": False, "name": None}

    # register an agent that acts for testuser
    _agent_key("agent_two", ["testuser"])
    r2 = client.get("/api/v1/assistant")
    assert r2.json() == {"has_assistant": True, "name": "agent_two"}


@pytest.mark.skipif("assistant" not in PLUGINS, reason="assistant plugin disabled")
def test_assistant_command_requires_assistant(client: TestClient):
    # testuser has no assistant -> 404, not a crash
    r = client.post("/api/v1/assistant/command", json={"text": "do a thing"})
    assert r.status_code == 404


@pytest.mark.skipif("assistant" not in PLUGINS, reason="assistant plugin disabled")
def test_assistant_command_rejects_agents(client: TestClient):
    raw = _agent_key("agent_two", ["testuser"])
    r = client.post(
        "/api/v1/assistant/command",
        json={"text": "hi"},
        headers={"Authorization": f"Bearer {raw}", "X-Acts-For": "testuser"},
    )
    assert r.status_code == 403
