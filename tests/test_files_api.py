from __future__ import annotations

import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from xong.config import get_database_url

pytestmark = pytest.mark.skipif(
    "files" not in os.environ.get("XONG_PLUGINS", "").split(","),
    reason="files plugin disabled",
)


def _seed_person(username: str, display_name: str = "Someone") -> None:
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO org_people (username, display_name, active, synced_at) "
                "VALUES (:u, :d, true, now())"
            ),
            {"u": username, "d": display_name},
        )
    engine.dispose()


def _agent_key(agent: str, acts_for: list[str]) -> dict[str, str]:
    raw = f"xong_{agent}_" + "x" * 20
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO api_keys (key_hash, agent_name, acts_for) "
                "VALUES (:key_hash, :agent_name, :acts_for)"
            ),
            {"key_hash": key_hash, "agent_name": agent, "acts_for": acts_for},
        )
    engine.dispose()
    return {"Authorization": f"Bearer {raw}", "X-Acts-For": acts_for[0]}


def _mk_field(client: TestClient, key: str, **kw) -> dict:
    payload = {"concept_key": key, "datatype": "string", **kw}
    response = client.post("/api/v1/files/fields", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _mk_file(client: TestClient, **kw) -> dict:
    payload = {
        "path": "/data/orders.xlsx",
        "sheet_name": "Payment",
        "header_row": 1,
        "first_data_row": 2,
        **kw,
    }
    response = client.post("/api/v1/files/managed", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _mk_binding(client: TestClient, file_id: int, key: str, letter: str, **kw) -> dict:
    payload = {"concept_key": key, "column_letter": letter, **kw}
    response = client.post(f"/api/v1/files/managed/{file_id}/bindings", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_field_and_file_crud_roundtrip(client: TestClient):
    _seed_person("alice", "Alice")
    field = _mk_field(
        client,
        "contract_number",
        description="Processing contract",
        parse_rule=None,
        unique_in_sheet=True,
    )
    assert field["concept_key"] == "contract_number"
    assert field["created_by"] == "testuser"

    dup = client.post(
        "/api/v1/files/fields", json={"concept_key": "contract_number", "datatype": "string"}
    )
    assert dup.status_code == 409

    bad = client.post(
        "/api/v1/files/fields", json={"concept_key": "Contract Number", "datatype": "string"}
    )
    assert bad.status_code == 422

    file = _mk_file(client, owner_username="alice", notify_channel="chat:alice")
    assert file["owner_username"] == "alice"
    assert file["shadow_mode"] is True

    same = client.post(
        "/api/v1/files/managed",
        json={
            "path": "/data/orders.xlsx",
            "sheet_name": "Payment",
        },
    )
    assert same.status_code == 409

    patched = client.patch(
        f"/api/v1/files/managed/{file['id']}", json={"shadow_mode": False, "first_data_row": 3}
    )
    assert patched.status_code == 200
    assert patched.json()["shadow_mode"] is False
    assert patched.json()["first_data_row"] == 3

    bad_rows = client.patch(f"/api/v1/files/managed/{file['id']}", json={"header_row": 9})
    assert bad_rows.status_code == 422


def test_bundle_carries_fields_bindings_fingerprints_and_config(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number", unique_in_sheet=True)
    _mk_field(client, "usd_price_excl_vat", datatype="number", parse_rule="plain_number")
    file = _mk_file(client, owner_username="alice")

    _mk_binding(
        client,
        file["id"],
        "contract_number",
        "N",
        header_text_exact="Contract",
        fingerprint={
            "header_normalized": "contract",
            "header_aliases": ["contract", "contract no", "số hđ"],
            "dtype_profile": {"str": 1.0},
            "distinct_ratio": 0.4,
            "null_ratio": 0.1,
            "minhash_hex": "00ff10",
            "sample_values": ["MS-2506-01", "MS-2506-02"],
        },
    )
    _mk_binding(client, file["id"], "usd_price_excl_vat", "P", header_text_exact="USD\nexcl VAT")

    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle")
    assert bundle.status_code == 200
    body = bundle.json()
    assert body["config"]["auto_rebind_min_score"] == 0.85
    assert body["config"]["weights"]["minhash"] == 0.3
    assert body["file"]["sheet_name"] == "Payment"

    by_key = {b["concept_key"]: b for b in body["bindings"]}
    assert set(by_key) == {"contract_number", "usd_price_excl_vat"}
    contract = by_key["contract_number"]
    assert contract["column_letter"] == "N"
    assert contract["status"] == "active"
    assert contract["write_eligible"] is True
    assert contract["field"]["unique_in_sheet"] is True
    assert contract["fingerprint"]["header_aliases"] == ["contract", "contract no", "số hđ"]
    assert contract["fingerprint"]["minhash_hex"] == "00ff10"
    assert by_key["usd_price_excl_vat"]["fingerprint"] is None
    assert by_key["usd_price_excl_vat"]["field"]["parse_rule"] == "plain_number"


def test_agents_cannot_create_fields_files_or_verified_bindings(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    headers = _agent_key("agent", ["alice"])

    assert (
        client.post(
            "/api/v1/files/fields",
            json={"concept_key": "sneaky", "datatype": "string"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/files/managed",
            json={"path": "/x.xlsx", "sheet_name": "S"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/files/managed/{file['id']}/bindings",
            json={"concept_key": "contract_number", "column_letter": "N"},
            headers=headers,
        ).status_code
        == 403
    )
    # And no logical field snuck in.
    assert [f["concept_key"] for f in client.get("/api/v1/files/fields").json()] == [
        "contract_number"
    ]


def test_agent_proposal_lands_pending_and_cannot_displace_a_verified_binding(
    client: TestClient,
):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    _mk_field(client, "quantity_order", datatype="number")
    file = _mk_file(client, owner_username="alice")
    headers = _agent_key("agent", ["alice"])

    proposal = client.post(
        f"/api/v1/files/managed/{file['id']}/proposals",
        json={
            "concept_key": "quantity_order",
            "column_letter": "v",
            "header_text_exact": "Số lượng Order",
            "confidence": 0.7,
        },
        headers=headers,
    )
    assert proposal.status_code == 201, proposal.text
    body = proposal.json()
    assert body["status"] == "pending_review"
    assert body["bound_by"] == "auto"
    assert body["column_letter"] == "V"
    assert body["write_eligible"] is False

    # Human-verified binding is untouchable by proposals.
    _mk_binding(client, file["id"], "contract_number", "N")
    blocked = client.post(
        f"/api/v1/files/managed/{file['id']}/proposals",
        json={"concept_key": "contract_number", "column_letter": "B", "confidence": 0.9},
        headers=headers,
    )
    assert blocked.status_code == 409

    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle").json()
    by_key = {b["concept_key"]: b for b in bundle["bindings"]}
    assert by_key["contract_number"]["column_letter"] == "N"
    assert by_key["contract_number"]["write_eligible"] is True


def test_auto_rebind_event_moves_column_and_revokes_write_eligibility(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N", header_text_exact="Contract")
    headers = _agent_key("agent", ["alice"])

    event = client.post(
        f"/api/v1/files/managed/{file['id']}/events",
        json={
            "binding_id": binding["id"],
            "event": "auto_rebind",
            "old_col": "N",
            "new_col": "O",
            "score": 0.93,
            "runner_up_score": 0.41,
            "detail": {"reason": "column inserted before N"},
        },
        headers=headers,
    )
    assert event.status_code == 201, event.text
    assert event.json()["actor"] == "agent"

    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle").json()
    moved = bundle["bindings"][0]
    assert moved["column_letter"] == "O"
    assert moved["status"] == "auto_rebound"
    assert moved["bound_by"] == "auto"
    # THE rule: an auto-rebound binding is never write-eligible.
    assert moved["write_eligible"] is False
    assert moved["verified_by"] is None


def test_shadow_events_log_without_changing_the_binding(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N")
    headers = _agent_key("agent", ["alice"])

    for score in (0.91, 0.88):
        response = client.post(
            f"/api/v1/files/managed/{file['id']}/events",
            json={
                "binding_id": binding["id"],
                "event": "auto_rebind",
                "old_col": "N",
                "new_col": "O",
                "score": score,
                "shadow": True,
            },
            headers=headers,
        )
        assert response.status_code == 201

    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle").json()
    unchanged = bundle["bindings"][0]
    assert unchanged["column_letter"] == "N"
    assert unchanged["status"] == "active"
    assert unchanged["write_eligible"] is True

    events = client.get(f"/api/v1/files/managed/{file['id']}/events").json()
    shadow_events = [e for e in events if e["shadow"]]
    assert len(shadow_events) == 2
    assert {e["score"] for e in shadow_events} == {0.91, 0.88}


def test_confirm_is_owner_only_and_restores_write_eligibility(client: TestClient):
    _seed_person("alice")
    _seed_person("someoneelse")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N")
    headers = _agent_key("agent", ["alice"])

    client.post(
        f"/api/v1/files/managed/{file['id']}/events",
        json={"binding_id": binding["id"], "event": "auto_rebind", "new_col": "O", "score": 0.9},
        headers=headers,
    )

    # Agent may not confirm, even acting for the owner.
    assert (
        client.post(
            f"/api/v1/files/bindings/{binding['id']}/confirm",
            json={"column_letter": "O"},
            headers=headers,
        ).status_code
        == 403
    )
    # Nor may a human who is not the file owner.
    assert (
        client.post(
            f"/api/v1/files/bindings/{binding['id']}/confirm",
            json={"column_letter": "O"},
            headers={"Remote-User": "someoneelse"},
        ).status_code
        == 403
    )

    confirmed = client.post(
        f"/api/v1/files/bindings/{binding['id']}/confirm",
        json={"column_letter": "O", "header_text_exact": "Contract"},
        headers={"Remote-User": "alice"},
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["status"] == "active"
    assert body["bound_by"] == "human"
    assert body["verified_by"] == "alice"
    assert body["write_eligible"] is True

    events = client.get(f"/api/v1/files/managed/{file['id']}/events").json()
    assert events[0]["event"] == "human_confirmed"
    assert events[0]["old_col"] == "O"


def test_agent_cannot_forge_a_human_confirmed_event(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N")
    headers = _agent_key("agent", ["alice"])

    response = client.post(
        f"/api/v1/files/managed/{file['id']}/events",
        json={"binding_id": binding["id"], "event": "human_confirmed", "new_col": "O"},
        headers=headers,
    )
    assert response.status_code == 403


def test_rebinding_a_field_retires_the_previous_binding(client: TestClient):
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    first = _mk_binding(client, file["id"], "contract_number", "N")
    second = _mk_binding(client, file["id"], "contract_number", "O")
    assert first["id"] != second["id"]

    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle").json()
    assert [b["column_letter"] for b in bundle["bindings"]] == ["O"]


def test_agent_cannot_poison_a_human_binding_fingerprint(client: TestClient):
    # Defence-in-depth for the write gate: an agent may not push a fingerprint
    # whose header disagrees with the human-recorded header on a human-verified
    # binding — that only ever reflects a mis-resolve and corrupts the read
    # signal the resolver stores.
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N",
                          header_text_exact="Contract")
    headers = _agent_key("agent", ["alice"])

    poison = client.post(
        f"/api/v1/files/bindings/{binding['id']}/fingerprints",
        json={"header_normalized": "note", "sample_values": ["ghi chú mới"]},
        headers=headers,
    )
    assert poison.status_code == 409

    # A matching-header refresh from an agent is fine.
    ok = client.post(
        f"/api/v1/files/bindings/{binding['id']}/fingerprints",
        json={"header_normalized": "contract", "sample_values": ["HD-2506-001"]},
        headers=headers,
    )
    assert ok.status_code == 201


def test_auto_rebind_event_requires_a_qualifying_score(client: TestClient):
    # An agent cannot fabricate a low-confidence auto_rebind to discard a human
    # verification and repoint reads at an arbitrary column.
    _seed_person("alice")
    _mk_field(client, "contract_number")
    file = _mk_file(client, owner_username="alice")
    binding = _mk_binding(client, file["id"], "contract_number", "N",
                          header_text_exact="Contract")
    headers = _agent_key("agent", ["alice"])

    for bad in (
        {"score": 0.01, "runner_up_score": 0.0},   # below min_score
        {"score": 0.90, "runner_up_score": 0.85},  # margin too small
        {},                                         # no score at all
    ):
        resp = client.post(
            f"/api/v1/files/managed/{file['id']}/events",
            json={"binding_id": binding["id"], "event": "auto_rebind",
                  "old_col": "N", "new_col": "ZZ", **bad},
            headers=headers,
        )
        assert resp.status_code == 422, (bad, resp.text)

    # The human binding is untouched by the rejected events.
    bundle = client.get(f"/api/v1/files/managed/{file['id']}/bundle").json()
    still = bundle["bindings"][0]
    assert still["column_letter"] == "N"
    assert still["write_eligible"] is True
