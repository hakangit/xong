from __future__ import annotations

import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from xong.config import get_database_url

pytestmark = pytest.mark.skipif(
    "org" not in os.environ.get("XONG_PLUGINS", "").split(","),
    reason="org plugin disabled",
)


def _seed_people(*people: dict) -> None:
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        for person in people:
            connection.execute(
                text(
                    "INSERT INTO org_people (username, display_name, active, synced_at) "
                    "VALUES (:username, :display_name, true, now())"
                ),
                person,
            )
    engine.dispose()


def _agent_key(agent: str, acts_for: list[str]) -> tuple[str, dict[str, str]]:
    raw = f"xong_{agent}_" + "x" * 20
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO api_keys (key_hash, agent_name, acts_for) "
                "VALUES (:key_hash, :agent_name, :acts_for)"
            ),
            {
                "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
                "agent_name": agent,
                "acts_for": acts_for,
            },
        )
    engine.dispose()
    return raw, {"Authorization": f"Bearer {raw}", "X-Acts-For": acts_for[0]}


def _create_skill(client: TestClient, slug: str = "woven-contracts") -> None:
    response = client.post(
        "/api/v1/skills",
        json={"name": "Woven contracts", "slug": slug},
    )
    assert response.status_code == 201


def test_teaching_open_increment_clean_run_and_computed_views(client: TestClient):
    _seed_people(
        {"username": "alice", "display_name": "Alice"},
        {"username": "bob", "display_name": "Bảo"},
    )
    _raw, agent_headers = _agent_key("agent", ["alice"])
    _create_skill(client)

    opened = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={
            "teacher": "ALICE",
            "agent": "agent",
            "correction": True,
            "source_ref": "rc:first",
            "summary": "Bản đầu",
        },
    )
    assert opened.status_code == 201
    session_id = opened.json()["id"]
    assert opened.json()["teacher"] == "alice"
    assert opened.json()["corrections"] == 1

    incremented = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={
            "teacher": "alice",
            "agent": "agent",
            "correction": True,
            "source_ref": "rc:second",
            "summary": "Bản sửa",
        },
    )
    assert incremented.json()["id"] == session_id
    assert incremented.json()["corrections"] == 2
    assert incremented.json()["source_ref"] == "rc:first\nrc:second"
    assert incremented.json()["summary"] == "Bản sửa"

    unchanged = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={
            "teacher": "alice",
            "agent": "agent",
            "source_ref": "rc:second",
            "summary": "",
        },
    ).json()
    assert unchanged["corrections"] == 2
    assert unchanged["source_ref"] == "rc:first\nrc:second"
    assert unchanged["summary"] == "Bản sửa"

    cleaned = client.post(
        f"/api/v1/skills/woven-contracts/teaching/{session_id}/clean-run",
        headers=agent_headers,
        json={"confidence_before": 0.2, "confidence_after": 0.8},
    )
    assert cleaned.status_code == 200
    first = cleaned.json()
    assert first["first_clean_run_at"] == first["ended_at"]

    repeated = client.post(
        f"/api/v1/skills/woven-contracts/teaching/{session_id}/clean-run",
        headers=agent_headers,
        json={"confidence_before": 0.4, "confidence_after": 0.9},
    ).json()
    assert repeated["first_clean_run_at"] == first["first_clean_run_at"]
    assert repeated["ended_at"] == first["ended_at"]
    assert repeated["confidence_before"] == 0.2
    assert repeated["confidence_after"] == 0.8

    detail = client.get("/api/v1/skills/woven-contracts").json()
    assert detail["taught_by"] == [
        {
            **first,
            "teacher_name": "Alice",
        }
    ]

    own = client.post(
        "/api/v1/skills/woven-contracts/usage",
        headers={"Remote-User": "alice"},
        json={"subject_kind": "person", "subject": "ALICE"},
    )
    assert own.status_code == 201
    assert client.get("/api/v1/org/people/alice").json()["weave"] == {
        "threads": 1,
        "passes": 0,
    }
    other = client.post(
        "/api/v1/skills/woven-contracts/usage",
        headers={"Remote-User": "bob"},
        json={"subject_kind": "person", "subject": "BOB", "source_ref": "xong:42"},
    )
    assert other.status_code == 201
    assert other.json()["subject"] == "bob"
    assert client.get("/api/v1/org/people/alice").json()["weave"] == {
        "threads": 1,
        "passes": 1,
    }

    recap = client.get(
        "/api/v1/recap/weekly", headers={"Remote-User": "alice"}
    ).json()
    assert recap["teaching_sessions"][0]["agent_display"] == "Agent"
    assert recap["teaching_sessions"][0]["skill_name"] == "Woven contracts"


def test_teaching_and_usage_validation_and_authorization(client: TestClient):
    _seed_people(
        {"username": "alice", "display_name": "Alice"},
        {"username": "bob", "display_name": "Bảo"},
    )
    _raw, agent_headers = _agent_key("agent", ["alice", "bob"])
    _create_skill(client)

    wrong_agent = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={"teacher": "alice", "agent": "agent-two"},
    )
    assert wrong_agent.status_code == 403
    wrong_teacher = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={"teacher": "bob", "agent": "agent"},
    )
    assert wrong_teacher.status_code == 403
    human_other = client.post(
        "/api/v1/skills/woven-contracts/usage",
        headers={"Remote-User": "alice"},
        json={"subject_kind": "person", "subject": "bob"},
    )
    assert human_other.status_code == 403
    agent_other = client.post(
        "/api/v1/skills/woven-contracts/usage",
        headers=agent_headers,
        json={"subject_kind": "person", "subject": "bob"},
    )
    assert agent_other.status_code == 403

    opened = client.post(
        "/api/v1/skills/woven-contracts/teaching",
        headers=agent_headers,
        json={"teacher": "alice", "agent": "agent"},
    ).json()
    bad_confidence = client.post(
        f"/api/v1/skills/woven-contracts/teaching/{opened['id']}/clean-run",
        headers=agent_headers,
        json={"confidence_after": 1.1},
    )
    assert bad_confidence.status_code == 422
    wrong_actor = client.post(
        f"/api/v1/skills/woven-contracts/teaching/{opened['id']}/clean-run",
        headers={"Remote-User": "bob"},
        json={},
    )
    assert wrong_actor.status_code == 403


def test_teaching_history_and_weave_follow_skill_merges(client: TestClient):
    _seed_people(
        {"username": "alice", "display_name": "Alice"},
        {"username": "bob", "display_name": "Bảo"},
    )
    _raw, agent_headers = _agent_key("agent", ["alice"])
    _create_skill(client, "contract-old")
    _create_skill(client, "contract-canonical")

    opened = client.post(
        "/api/v1/skills/contract-old/teaching",
        headers=agent_headers,
        json={"teacher": "alice", "agent": "agent"},
    ).json()
    cleaned = client.post(
        f"/api/v1/skills/contract-old/teaching/{opened['id']}/clean-run",
        headers=agent_headers,
        json={"confidence_after": 0.8},
    )
    assert cleaned.status_code == 200
    assert client.post(
        "/api/v1/skills/contract-old/merge-into/contract-canonical"
    ).status_code == 200

    canonical = client.get("/api/v1/skills/contract-canonical").json()
    via_alias = client.get("/api/v1/skills/contract-old").json()
    assert [item["id"] for item in canonical["taught_by"]] == [opened["id"]]
    assert [item["id"] for item in via_alias["taught_by"]] == [opened["id"]]

    alias_usage = client.post(
        "/api/v1/skills/contract-old/usage",
        headers={"Remote-User": "bob"},
        json={"subject_kind": "person", "subject": "bob"},
    )
    assert alias_usage.status_code == 201
    assert client.get("/api/v1/org/people/alice").json()["weave"] == {
        "threads": 1,
        "passes": 1,
    }
    canonical_usage = client.post(
        "/api/v1/skills/contract-canonical/usage",
        headers={"Remote-User": "bob"},
        json={"subject_kind": "person", "subject": "bob"},
    )
    assert canonical_usage.status_code == 201
    assert client.get("/api/v1/org/people/alice").json()["weave"] == {
        "threads": 1,
        "passes": 2,
    }
