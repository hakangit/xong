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
    defaults = {
        "display_name": "Unnamed",
        "email": None,
        "title": None,
        "department": None,
        "department_raw": None,
        "site": None,
        "manager_username": None,
        "active": True,
    }
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        for supplied in people:
            person = {**defaults, **supplied}
            connection.execute(
                text(
                    """
                    INSERT INTO org_people (
                        username, display_name, email, title, department,
                        department_raw, site, manager_username, active, synced_at
                    ) VALUES (
                        :username, :display_name, :email, :title, :department,
                        :department_raw, :site, :manager_username, :active, now()
                    )
                    """
                ),
                person,
            )
    engine.dispose()


def _agent_key(agent: str, acts_for: list[str]) -> tuple[str, dict[str, str]]:
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
    return raw, {"Authorization": f"Bearer {raw}", "X-Acts-For": acts_for[0]}


def _flatten_tree(node: dict) -> list[dict]:
    return [node, *[item for child in node["direct_reports"] for item in _flatten_tree(child)]]


def test_people_filters_and_profile_relationships(client: TestClient):
    _seed_people(
        {
            "username": "boss",
            "display_name": "Mai Boss",
            "department": "Accounting",
            "site": "MS",
        },
        {
            "username": "an",
            "display_name": "An Nguyen",
            "department": "Accounting",
            "department_raw": "ACCOUNTING",
            "site": "MS",
            "manager_username": "boss",
        },
        {
            "username": "bob",
            "display_name": "Bob Tran",
            "department": "Production",
            "site": "HS",
            "manager_username": "an",
            "active": False,
        },
    )

    filtered = client.get(
        "/api/v1/org/people", params={"q": "NGUY", "dept": "Accounting", "site": "ms"}
    )
    assert filtered.status_code == 200
    assert [person["username"] for person in filtered.json()] == ["an"]
    assert client.get("/api/v1/org/people", params={"active": "false"}).json()[0][
        "username"
    ] == "bob"

    profile = client.get("/api/v1/org/people/boss")
    assert profile.status_code == 200
    assert profile.json()["manager"] is None
    assert [person["username"] for person in profile.json()["direct_reports"]] == ["an"]

    an = client.get("/api/v1/org/people/an").json()
    assert an["manager"] == {"username": "boss", "display_name": "Mai Boss"}


def test_chain_is_cycle_safe(client: TestClient):
    _seed_people(
        {"username": "a", "display_name": "A", "manager_username": "b"},
        {"username": "b", "display_name": "B", "manager_username": "a"},
    )
    chain = client.get("/api/v1/org/chain/a")
    assert chain.status_code == 200
    assert [person["username"] for person in chain.json()] == ["a", "b"]


def test_tree_depth_is_capped_at_five(client: TestClient):
    people = [{"username": "root", "display_name": "Root"}]
    for number in range(1, 8):
        people.append(
            {
                "username": f"p{number}",
                "display_name": f"Person {number}",
                "manager_username": "root" if number == 1 else f"p{number - 1}",
            }
        )
    _seed_people(*people)

    response = client.get("/api/v1/org/tree/root", params={"depth": 99})
    assert response.status_code == 200
    flat = _flatten_tree(response.json())
    assert max(person["depth"] for person in flat) == 5
    assert "p6" not in {person["username"] for person in flat}


def test_skill_creation_claim_upsert_and_validation(client: TestClient):
    _seed_people({"username": "an", "display_name": "An Nguyen"})
    created = client.post(
        "/api/v1/skills",
        json={"name": "Fix Dye Machines", "description": "Mechanical diagnosis"},
    )
    assert created.status_code == 201
    assert created.json()["slug"] == "fix-dye-machines"
    assert created.json()["created_by"] == "testuser"
    assert client.post("/api/v1/skills", json={"name": "Fix Dye Machines"}).status_code == 409

    first = client.post(
        "/api/v1/skills/fix-dye-machines/claims",
        json={
            "subject_kind": "person",
            "subject": "AN",
            "kind": "can_do",
            "confidence": 0.7,
            "note": "Initial",
        },
    )
    second = client.post(
        "/api/v1/skills/fix-dye-machines/claims",
        json={
            "subject_kind": "person",
            "subject": "an",
            "kind": "can_do",
            "confidence": 0.95,
            "note": "Observed twice",
        },
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    detail = client.get("/api/v1/skills/fix-dye-machines").json()
    assert detail["claim_count"] == 1
    assert detail["claims"][0]["confidence"] == 0.95
    assert detail["claims"][0]["note"] == "Observed twice"
    assert detail["claims"][0]["source"] == "testuser"

    missing = client.post(
        "/api/v1/skills/fix-dye-machines/claims",
        json={"subject_kind": "person", "subject": "nobody", "kind": "knows_about"},
    )
    assert missing.status_code == 404


def test_who_can_ranking_uses_kind_at_equal_confidence(client: TestClient):
    _seed_people(
        {"username": "an", "display_name": "An", "department": "Dyeing", "site": "MD"},
        {"username": "bob", "display_name": "Bob", "department": "Dyeing", "site": "MD"},
    )
    assert client.post(
        "/api/v1/skills", json={"name": "Dye recipe", "tags": ["color"]}
    ).status_code == 201
    for subject, kind in (("an", "knows_about"), ("bob", "can_do")):
        response = client.post(
            "/api/v1/skills/dye-recipe/claims",
            json={
                "subject_kind": "person",
                "subject": subject,
                "kind": kind,
                "confidence": 0.8,
            },
        )
        assert response.status_code == 200

    ranked = client.get("/api/v1/org/who-can", params={"q": "color"})
    assert ranked.status_code == 200
    assert [result["subject"] for result in ranked.json()] == ["bob", "an"]
    assert ranked.json()[0]["department"] == "Dyeing"


def test_agent_and_browser_read_write_provenance(client: TestClient):
    _seed_people({"username": "an", "display_name": "An"})
    _raw, headers = _agent_key("agent", ["user-one"])

    human = client.post("/api/v1/skills", json={"name": "Human Skill"})
    agent = client.post("/api/v1/skills", json={"name": "Agent Skill"}, headers=headers)
    assert human.json()["created_by"] == "testuser"
    assert agent.json()["created_by"] == "agent"

    claim = client.post(
        "/api/v1/skills/agent-skill/claims",
        json={"subject_kind": "agent", "subject": "agent", "kind": "owns_process"},
        headers=headers,
    )
    assert claim.status_code == 200
    assert claim.json()["source"] == "agent"
    assert client.get("/api/v1/org/people", headers=headers).status_code == 200
    assert client.get("/api/v1/skills", headers={"Remote-User": "an"}).status_code == 200


def test_merge_preserves_higher_confidence_claim_and_provenance(client: TestClient):
    _seed_people(
        {"username": "an", "display_name": "An"},
        {"username": "bob", "display_name": "Bob"},
    )
    assert client.post(
        "/api/v1/skills", json={"name": "Dye Fix", "slug": "dye-fix"}
    ).status_code == 201
    assert client.post(
        "/api/v1/skills", json={"name": "Machine Repair", "slug": "machine-repair"}
    ).status_code == 201

    # Canonical has weaker claim; loser has stronger with distinct provenance.
    weak = client.post(
        "/api/v1/skills/dye-fix/claims",
        json={
            "subject_kind": "person",
            "subject": "an",
            "kind": "can_do",
            "confidence": 0.4,
            "note": "hearsay",
        },
    )
    assert weak.status_code == 200
    # Agent authors the stronger loser claim so source/provenance differ.
    _raw, agent_headers = _agent_key("agent-two", ["user-one"])
    strong = client.post(
        "/api/v1/skills/machine-repair/claims",
        json={
            "subject_kind": "person",
            "subject": "an",
            "kind": "can_do",
            "confidence": 0.9,
            "note": "watched twice",
        },
        headers=agent_headers,
    )
    assert strong.status_code == 200
    strong_source = strong.json()["source"]
    assert strong_source == "agent-two"

    # Loser-only claim must migrate too.
    only_loser = client.post(
        "/api/v1/skills/machine-repair/claims",
        json={
            "subject_kind": "person",
            "subject": "bob",
            "kind": "knows_about",
            "confidence": 0.7,
            "note": "shadowed",
        },
        headers=agent_headers,
    )
    assert only_loser.status_code == 200

    merged = client.post("/api/v1/skills/machine-repair/merge-into/dye-fix")
    assert merged.status_code == 200
    assert merged.json()["slug"] == "dye-fix"

    detail = client.get("/api/v1/skills/dye-fix").json()
    claims = {(c["subject"], c["kind"]): c for c in detail["claims"]}
    assert claims[("an", "can_do")]["confidence"] == 0.9
    assert claims[("an", "can_do")]["source"] == "agent-two"
    assert "merged from machine-repair" in claims[("an", "can_do")]["note"]
    assert claims[("an", "can_do")]["note"].startswith("watched twice")
    assert claims[("bob", "knows_about")]["confidence"] == 0.7
    assert "merged from machine-repair" in claims[("bob", "knows_about")]["note"]

    # Loser row survives as merged; alias resolves to canonical.
    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status, merged_into_id FROM skills "
                "WHERE slug = 'machine-repair'"
            )
        ).one()
        assert row.status == "merged"
        assert row.merged_into_id is not None
        alias = conn.execute(
            text("SELECT skill_id FROM skill_aliases WHERE alias = 'machine-repair'")
        ).one()
        assert alias.skill_id == row.merged_into_id
        leftover = conn.execute(
            text("SELECT count(*) FROM skill_claims WHERE skill_id = :id"),
            {"id": row.id},
        ).scalar()
        assert leftover == 0
    engine.dispose()

    via_alias = client.get("/api/v1/skills/machine-repair")
    assert via_alias.status_code == 200
    assert via_alias.json()["slug"] == "dye-fix"


def test_post_skill_collision_on_alias_is_409(client: TestClient):
    """POST /skills must 409 on skill_aliases even when the value is not a skills.slug."""
    assert client.post(
        "/api/v1/skills", json={"name": "Alpha", "slug": "alpha-skill"}
    ).status_code == 201
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        skill_id = conn.execute(
            text("SELECT id FROM skills WHERE slug = 'alpha-skill'")
        ).scalar()
        assert skill_id is not None
        # Alias-only value: present in skill_aliases, absent from skills.slug.
        conn.execute(
            text(
                "INSERT INTO skill_aliases (alias, skill_id, source) "
                "VALUES ('alias-only-name', :skill_id, 'test')"
            ),
            {"skill_id": skill_id},
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM skills WHERE slug = 'alias-only-name'")
            ).scalar()
            == 0
        )
    engine.dispose()

    collision = client.post(
        "/api/v1/skills", json={"name": "Alias Collision", "slug": "alias-only-name"}
    )
    assert collision.status_code == 409


def test_agent_cannot_merge_skills(client: TestClient):
    _raw, headers = _agent_key("agent", ["user-one"])
    assert client.post("/api/v1/skills", json={"name": "A", "slug": "skill-a"}).status_code == 201
    assert client.post("/api/v1/skills", json={"name": "B", "slug": "skill-b"}).status_code == 201
    denied = client.post(
        "/api/v1/skills/skill-b/merge-into/skill-a", headers=headers
    )
    assert denied.status_code == 403


def test_cycle_rejected_by_database_trigger(client: TestClient):
    for name in ("s1", "s2", "s3"):
        assert client.post(
            "/api/v1/skills", json={"name": name, "slug": name}
        ).status_code == 201

    e12 = client.post(
        "/api/v1/skills/s1/edges",
        json={"dst_slug": "s2", "kind": "requires", "confidence": 0.8},
    )
    e23 = client.post(
        "/api/v1/skills/s2/edges",
        json={"dst_slug": "s3", "kind": "requires", "confidence": 0.8},
    )
    assert e12.status_code == e23.status_code == 201
    assert e12.json()["status"] == "approved"  # human creates approved

    cycle = client.post(
        "/api/v1/skills/s3/edges",
        json={"dst_slug": "s1", "kind": "requires", "confidence": 0.5},
    )
    assert cycle.status_code == 409
    assert "cycle" in cycle.json()["detail"].lower()


def test_deep_requires_chain_terminates_via_path_depth_guard(client: TestClient):
    # Chain s0 -> s1 -> ... -> s8; closure depth cap is 4 (depths 0..3).
    for i in range(9):
        assert client.post(
            "/api/v1/skills", json={"name": f"Skill {i}", "slug": f"deep-{i}"}
        ).status_code == 201
    for i in range(8):
        resp = client.post(
            f"/api/v1/skills/deep-{i}/edges",
            json={"dst_slug": f"deep-{i + 1}", "kind": "requires", "confidence": 0.9},
        )
        assert resp.status_code == 201, resp.text

    closure = client.get("/api/v1/skills/deep-0/requires-closure")
    assert closure.status_code == 200
    rows = closure.json()
    depths = {row["slug"]: row["depth"] for row in rows}
    assert depths["deep-0"] == 0
    assert max(row["depth"] for row in rows) < 4
    assert "deep-3" in depths
    assert "deep-4" not in depths
    assert "deep-8" not in depths


def test_derived_never_outranks_direct_on_who_can(client: TestClient):
    _seed_people(
        {"username": "an", "display_name": "An", "department": "Dyeing", "site": "MD"},
        {"username": "bob", "display_name": "Bob", "department": "Dyeing", "site": "MD"},
    )
    assert client.post(
        "/api/v1/skills", json={"name": "Color science", "slug": "color-science"}
    ).status_code == 201
    assert client.post(
        "/api/v1/skills", json={"name": "Dye recipe", "slug": "dye-recipe"}
    ).status_code == 201

    # color-science generalizes dye-recipe (claim on general → weak on specific)
    edge = client.post(
        "/api/v1/skills/color-science/edges",
        json={
            "dst_slug": "dye-recipe",
            "kind": "generalizes",
            "confidence": 1.0,
            "note": "parent",
        },
    )
    assert edge.status_code == 201
    assert edge.json()["status"] == "approved"

    # An has high-confidence claim on general skill only → derived on dye-recipe
    assert client.post(
        "/api/v1/skills/color-science/claims",
        json={
            "subject_kind": "person",
            "subject": "an",
            "kind": "can_do",
            "confidence": 1.0,
        },
    ).status_code == 200
    # Bob has lower direct claim on dye-recipe
    assert client.post(
        "/api/v1/skills/dye-recipe/claims",
        json={
            "subject_kind": "person",
            "subject": "bob",
            "kind": "can_do",
            "confidence": 0.5,
        },
    ).status_code == 200

    ranked = client.get("/api/v1/org/who-can", params={"q": "dye-recipe"})
    assert ranked.status_code == 200
    rows = ranked.json()
    assert rows, "expected who-can results"
    # Derived conf = 1.0 * 1.0 * 0.8 = 0.8 > bob's 0.5, so an ranks first by conf.
    an_rows = [r for r in rows if r["subject"] == "an"]
    bao_rows = [r for r in rows if r["subject"] == "bob"]
    assert an_rows and bao_rows
    assert an_rows[0]["derived"] is True
    assert an_rows[0]["via_skill"] == "color-science"
    assert abs(an_rows[0]["confidence"] - 0.8) < 1e-9
    assert bao_rows[0]["derived"] is False
    assert bao_rows[0]["via_skill"] is None

    # Give An a direct claim on dye-recipe with low conf — direct must appear,
    # and no inferior derived row for the same subject+skill.
    assert client.post(
        "/api/v1/skills/dye-recipe/claims",
        json={
            "subject_kind": "person",
            "subject": "an",
            "kind": "can_do",
            "confidence": 0.3,
        },
    ).status_code == 200
    ranked2 = client.get("/api/v1/org/who-can", params={"q": "dye-recipe"}).json()
    an2 = [r for r in ranked2 if r["subject"] == "an" and r["skill_slug"] == "dye-recipe"]
    assert len(an2) == 1
    assert an2[0]["derived"] is False
    assert an2[0]["confidence"] == 0.3
    assert an2[0]["via_skill"] is None


def test_rejected_edge_invisible_to_who_can_transitive(client: TestClient):
    _seed_people(
        {"username": "an", "display_name": "An"},
        {"username": "bob", "display_name": "Bob"},
    )
    for slug in ("root-skill", "dep-a", "dep-b"):
        assert client.post(
            "/api/v1/skills", json={"name": slug, "slug": slug}
        ).status_code == 201

    # root requires dep-a (approved) and dep-b (will reject)
    e_a = client.post(
        "/api/v1/skills/root-skill/edges",
        json={"dst_slug": "dep-a", "kind": "requires", "confidence": 0.9},
    )
    e_b = client.post(
        "/api/v1/skills/root-skill/edges",
        json={"dst_slug": "dep-b", "kind": "requires", "confidence": 0.9},
    )
    assert e_a.status_code == e_b.status_code == 201
    rejected = client.patch(
        f"/api/v1/skills/edges/{e_b.json()['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reviewed_by"] == "testuser"

    # Claims: an covers root + dep-a; bob covers only dep-b (rejected path)
    for subject, skill, conf in (
        ("an", "root-skill", 0.8),
        ("an", "dep-a", 0.7),
        ("bob", "dep-b", 0.95),
    ):
        assert client.post(
            f"/api/v1/skills/{skill}/claims",
            json={
                "subject_kind": "person",
                "subject": subject,
                "kind": "can_do",
                "confidence": conf,
            },
        ).status_code == 200

    closure = client.get("/api/v1/skills/root-skill/requires-closure").json()
    slugs = {row["slug"] for row in closure}
    assert "dep-a" in slugs
    assert "dep-b" not in slugs

    ranking = client.get("/api/v1/skills/root-skill/who-can-transitive")
    assert ranking.status_code == 200
    by_subject = {row["subject"]: row for row in ranking.json()}
    assert "bob" not in by_subject  # only claimed on rejected branch
    assert by_subject["an"]["covered"] == 2
    assert by_subject["an"]["full_cover"] is True
    assert by_subject["an"]["weakest_link"] == 0.7
    assert set(by_subject["an"]["via"]) == {"dep-a", "root-skill"}


def test_agent_cannot_approve_edges(client: TestClient):
    _raw, headers = _agent_key("agent", ["user-one"])
    assert client.post("/api/v1/skills", json={"name": "X", "slug": "edge-x"}).status_code == 201
    assert client.post("/api/v1/skills", json={"name": "Y", "slug": "edge-y"}).status_code == 201

    proposed = client.post(
        "/api/v1/skills/edge-x/edges",
        json={"dst_slug": "edge-y", "kind": "requires", "confidence": 0.6},
        headers=headers,
    )
    assert proposed.status_code == 201
    assert proposed.json()["status"] == "proposed"
    edge_id = proposed.json()["id"]

    denied = client.patch(
        f"/api/v1/skills/edges/{edge_id}",
        json={"status": "approved"},
        headers=headers,
    )
    assert denied.status_code == 403

    # Prove DB unchanged after agent PATCH 403 — still proposed.
    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        status_row = conn.execute(
            text("SELECT status, reviewed_by FROM skill_edges WHERE id = :id"),
            {"id": edge_id},
        ).one()
        assert status_row.status == "proposed"
        assert status_row.reviewed_by is None
    engine.dispose()

    # Rejected stickiness: agent re-proposal after human reject stays rejected.
    human_reject = client.patch(
        f"/api/v1/skills/edges/{edge_id}",
        json={"status": "rejected"},
    )
    assert human_reject.status_code == 200
    reprop = client.post(
        "/api/v1/skills/edge-x/edges",
        json={
            "dst_slug": "edge-y",
            "kind": "requires",
            "confidence": 0.95,
            "note": "try again",
        },
        headers=headers,
    )
    assert reprop.status_code == 201
    assert reprop.json()["status"] == "rejected"
    assert reprop.json()["confidence"] == 0.95
    assert reprop.json()["note"] == "try again"


def test_edge_docstring_semantics_and_human_approved(client: TestClient):
    """Human POST creates approved; requires vs generalizes are distinct kinds."""
    assert client.post("/api/v1/skills", json={"name": "P", "slug": "parent"}).status_code == 201
    assert client.post("/api/v1/skills", json={"name": "C", "slug": "child"}).status_code == 201
    req = client.post(
        "/api/v1/skills/parent/edges",
        json={"dst_slug": "child", "kind": "requires", "confidence": 0.7},
    )
    gen = client.post(
        "/api/v1/skills/parent/edges",
        json={"dst_slug": "child", "kind": "generalizes", "confidence": 0.6},
    )
    assert req.status_code == gen.status_code == 201
    assert req.json()["status"] == "approved"
    assert gen.json()["status"] == "approved"
    assert req.json()["kind"] == "requires"
    assert gen.json()["kind"] == "generalizes"
    assert req.json()["id"] != gen.json()["id"]


def test_diamond_closure_dedup_and_full_cover(client: TestClient):
    """root→A,B and A,B→C: unique closure rows, required_count=4, full_cover achievable."""
    _seed_people({"username": "an", "display_name": "An"})
    for slug in ("diamond-root", "diamond-a", "diamond-b", "diamond-c"):
        assert client.post(
            "/api/v1/skills", json={"name": slug, "slug": slug}
        ).status_code == 201
    for src, dst in (
        ("diamond-root", "diamond-a"),
        ("diamond-root", "diamond-b"),
        ("diamond-a", "diamond-c"),
        ("diamond-b", "diamond-c"),
    ):
        assert client.post(
            f"/api/v1/skills/{src}/edges",
            json={"dst_slug": dst, "kind": "requires", "confidence": 0.9},
        ).status_code == 201

    closure = client.get("/api/v1/skills/diamond-root/requires-closure").json()
    slugs = [row["slug"] for row in closure]
    assert len(slugs) == len(set(slugs)) == 4
    assert set(slugs) == {"diamond-root", "diamond-a", "diamond-b", "diamond-c"}
    by_slug = {row["slug"]: row["depth"] for row in closure}
    assert by_slug["diamond-root"] == 0
    assert by_slug["diamond-c"] == 2  # min depth, not duplicated at another depth

    for skill in ("diamond-root", "diamond-a", "diamond-b", "diamond-c"):
        assert client.post(
            f"/api/v1/skills/{skill}/claims",
            json={
                "subject_kind": "person",
                "subject": "an",
                "kind": "can_do",
                "confidence": 0.8,
            },
        ).status_code == 200

    ranking = client.get("/api/v1/skills/diamond-root/who-can-transitive").json()
    assert len(ranking) == 1
    row = ranking[0]
    assert row["subject"] == "an"
    assert row["required_count"] == 4
    assert row["covered"] == 4
    assert row["full_cover"] is True
    assert set(row["via"]) == {"diamond-root", "diamond-a", "diamond-b", "diamond-c"}


def test_merge_rewires_edges_both_directions_and_self_removal(client: TestClient):
    """Outgoing + incoming rewires, collision strength, sticky rejected+reviewer, self-drop."""
    for slug in ("canon", "loser", "out-target", "in-source"):
        assert client.post(
            "/api/v1/skills", json={"name": slug, "slug": slug}
        ).status_code == 201

    # Outgoing from loser (will rewire canon→out-target); self-edge loser→canon drops.
    assert client.post(
        "/api/v1/skills/loser/edges",
        json={
            "dst_slug": "out-target",
            "kind": "requires",
            "confidence": 0.95,
            "note": "out-strong",
        },
    ).status_code == 201
    assert client.post(
        "/api/v1/skills/loser/edges",
        json={"dst_slug": "canon", "kind": "requires", "confidence": 0.5},
    ).status_code == 201

    # Incoming to loser (will rewire in-source→canon).
    assert client.post(
        "/api/v1/skills/in-source/edges",
        json={
            "dst_slug": "loser",
            "kind": "requires",
            "confidence": 0.7,
            "note": "in-mid",
        },
    ).status_code == 201

    # Collision on outgoing: canon already has weaker approved edge to out-target.
    weak_out = client.post(
        "/api/v1/skills/canon/edges",
        json={
            "dst_slug": "out-target",
            "kind": "requires",
            "confidence": 0.4,
            "note": "canon-weak",
        },
    )
    assert weak_out.status_code == 201

    # Collision on incoming: canon already has rejected edge from in-source (higher conf
    # will come from loser side for assertion fields, but rejected stickiness + reviewer).
    eng = create_engine(get_database_url())
    with eng.begin() as conn:
        ids = {
            row.slug: row.id
            for row in conn.execute(
                text("SELECT id, slug FROM skills WHERE slug IN ('canon', 'in-source')")
            )
        }
        # Insert rejected edge that would conflict with incoming rewire; trigger skips rejected.
        conn.execute(
            text(
                """
                INSERT INTO skill_edges (
                    src_skill_id, dst_skill_id, kind, confidence, note, source,
                    status, reviewed_by
                ) VALUES (
                    :src, :dst, 'requires', 0.2, 'pre-reject', 'seed',
                    'rejected', 'reviewer-alice'
                )
                """
            ),
            {"src": ids["in-source"], "dst": ids["canon"]},
        )
    eng.dispose()

    assert client.post("/api/v1/skills/loser/merge-into/canon").status_code == 200

    eng = create_engine(get_database_url())
    with eng.connect() as conn:
        edges = list(
            conn.execute(
                text(
                    """
                    SELECT src.slug AS src, dst.slug AS dst, e.kind, e.confidence,
                           e.note, e.source, e.status, e.reviewed_by
                    FROM skill_edges e
                    JOIN skills src ON src.id = e.src_skill_id
                    JOIN skills dst ON dst.id = e.dst_skill_id
                    ORDER BY src.slug, dst.slug, e.kind
                    """
                )
            ).mappings()
        )
        # No edges still point at loser; no self-edge canon→canon.
        assert all(e["src"] != "loser" and e["dst"] != "loser" for e in edges)
        assert not any(e["src"] == e["dst"] for e in edges)

        by_pair = {(e["src"], e["dst"], e["kind"]): e for e in edges}
        # Outgoing rewire: higher conf from loser wins assertion provenance.
        out = by_pair[("canon", "out-target", "requires")]
        assert out["confidence"] == 0.95
        assert "out-strong" in out["note"]
        assert "merged from loser" in out["note"]
        assert out["status"] == "approved"

        # Incoming rewire: higher conf from loser (0.7) wins fields; rejected sticky
        # keeps reviewed_by from the rejected row (reviewer-alice), not NULL.
        inc = by_pair[("in-source", "canon", "requires")]
        assert inc["confidence"] == 0.7
        assert "in-mid" in inc["note"]
        assert "merged from loser" in inc["note"]
        assert inc["status"] == "rejected"
        assert inc["reviewed_by"] == "reviewer-alice"
    eng.dispose()


def test_cycle_trigger_allows_harmless_update_blocks_approve_closing_cycle(
    client: TestClient,
):
    for name in ("cu1", "cu2", "cu3"):
        assert client.post(
            "/api/v1/skills", json={"name": name, "slug": name}
        ).status_code == 201

    e12 = client.post(
        "/api/v1/skills/cu1/edges",
        json={"dst_slug": "cu2", "kind": "requires", "confidence": 0.8},
    )
    e23 = client.post(
        "/api/v1/skills/cu2/edges",
        json={"dst_slug": "cu3", "kind": "requires", "confidence": 0.8},
    )
    assert e12.status_code == e23.status_code == 201
    edge_12_id = e12.json()["id"]

    # Harmless upsert/update of existing edge must succeed (NEW.id excluded from path).
    upsert = client.post(
        "/api/v1/skills/cu1/edges",
        json={
            "dst_slug": "cu2",
            "kind": "requires",
            "confidence": 0.85,
            "note": "bump",
        },
    )
    assert upsert.status_code == 201
    assert upsert.json()["id"] == edge_12_id
    assert upsert.json()["confidence"] == 0.85

    # Insert rejected reverse edge via SQL (trigger skips rejected) then PATCH approve → 409.
    eng = create_engine(get_database_url())
    with eng.begin() as conn:
        ids = {
            row.slug: row.id
            for row in conn.execute(
                text("SELECT id, slug FROM skills WHERE slug IN ('cu1', 'cu3')")
            )
        }
        edge_id = conn.execute(
            text(
                """
                INSERT INTO skill_edges (
                    src_skill_id, dst_skill_id, kind, confidence, note, source, status
                ) VALUES (
                    :src, :dst, 'requires', 0.5, 'latent cycle', 'seed', 'rejected'
                )
                RETURNING id
                """
            ),
            {"src": ids["cu3"], "dst": ids["cu1"]},
        ).scalar()
    eng.dispose()

    approve = client.patch(
        f"/api/v1/skills/edges/{edge_id}",
        json={"status": "approved"},
    )
    assert approve.status_code == 409
    assert "cycle" in approve.json()["detail"].lower()

    eng = create_engine(get_database_url())
    with eng.connect() as conn:
        still = conn.execute(
            text("SELECT status FROM skill_edges WHERE id = :id"),
            {"id": edge_id},
        ).scalar()
        assert still == "rejected"
    eng.dispose()


def test_merged_into_resolver_fails_on_cycle_and_over_depth(client: TestClient):
    """Resolver fails loudly on visited cycle or chain still open after 5 hops."""
    for i in range(7):
        assert client.post(
            "/api/v1/skills", json={"name": f"m{i}", "slug": f"merge-chain-{i}"}
        ).status_code == 201

    eng = create_engine(get_database_url())
    with eng.begin() as conn:
        ids = {
            row.slug: row.id
            for row in conn.execute(
                text(
                    "SELECT id, slug FROM skills WHERE slug LIKE 'merge-chain-%' "
                    "ORDER BY slug"
                )
            )
        }
        # Chain of 6 hops: 0→1→2→3→4→5→6 (exceeds cap 5).
        for i in range(6):
            conn.execute(
                text(
                    "UPDATE skills SET status = 'merged', merged_into_id = :tgt "
                    "WHERE id = :src"
                ),
                {
                    "src": ids[f"merge-chain-{i}"],
                    "tgt": ids[f"merge-chain-{i + 1}"],
                },
            )
    eng.dispose()

    over = client.get("/api/v1/skills/merge-chain-0")
    assert over.status_code == 500
    assert "depth" in over.json()["detail"].lower()

    # Cycle A→B→A
    assert client.post(
        "/api/v1/skills", json={"name": "cyc-a", "slug": "cyc-a"}
    ).status_code == 201
    assert client.post(
        "/api/v1/skills", json={"name": "cyc-b", "slug": "cyc-b"}
    ).status_code == 201
    eng = create_engine(get_database_url())
    with eng.begin() as conn:
        ids = {
            row.slug: row.id
            for row in conn.execute(
                text("SELECT id, slug FROM skills WHERE slug IN ('cyc-a', 'cyc-b')")
            )
        }
        conn.execute(
            text(
                "UPDATE skills SET status = 'merged', merged_into_id = :b WHERE id = :a"
            ),
            {"a": ids["cyc-a"], "b": ids["cyc-b"]},
        )
        conn.execute(
            text(
                "UPDATE skills SET status = 'merged', merged_into_id = :a WHERE id = :b"
            ),
            {"a": ids["cyc-a"], "b": ids["cyc-b"]},
        )
    eng.dispose()

    cyc = client.get("/api/v1/skills/cyc-a")
    assert cyc.status_code == 409
    assert "cycle" in cyc.json()["detail"].lower()

    # Dangling merged_into_id (temporarily drop FK so corrupt data can exist).
    assert client.post(
        "/api/v1/skills", json={"name": "dang", "slug": "dangling-src"}
    ).status_code == 201
    eng = create_engine(get_database_url())
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE skills DROP CONSTRAINT fk_skills_merged_into_id"))
        conn.execute(
            text(
                "UPDATE skills SET status = 'merged', merged_into_id = 999999 "
                "WHERE slug = 'dangling-src'"
            )
        )
    eng.dispose()
    try:
        dang = client.get("/api/v1/skills/dangling-src")
        assert dang.status_code == 500
        assert "dangling" in dang.json()["detail"].lower()
    finally:
        eng = create_engine(get_database_url())
        with eng.begin() as conn:
            conn.execute(
                text(
                    "UPDATE skills SET merged_into_id = NULL "
                    "WHERE merged_into_id = 999999"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE skills ADD CONSTRAINT fk_skills_merged_into_id "
                    "FOREIGN KEY (merged_into_id) REFERENCES skills(id)"
                )
            )
        eng.dispose()
