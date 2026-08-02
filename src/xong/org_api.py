from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, not_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from xong.auth import AuthContext, require_auth
from xong.db import get_db
from xong.models import (
    ApiKey,
    DecisionTrace,
    OrgPerson,
    Skill,
    SkillAlias,
    SkillClaim,
    SkillEdge,
    SkillUsageEvent,
    TeachingSession,
)

router = APIRouter(prefix="/api/v1")

MERGE_DEPTH_CAP = 5
REQUIRES_DEPTH_CAP = 4
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# Poisoning defence #4: an agent-written trace stays low-trust and tagged
# until a human confirms it. Humans may write any trust they like.
AGENT_MAX_TRUST = 0.3
AUTO_EXTRACT_TAG = "auto-extract"
TRACE_CHAIN_DEPTH_CAP = 5
TRACE_LIMIT = 100


class SkillCreate(BaseModel):
    slug: str | None = None
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class ClaimCreate(BaseModel):
    subject_kind: Literal["person", "agent"]
    subject: str = Field(min_length=1)
    kind: Literal["can_do", "knows_about", "owns_process"]
    confidence: float = Field(default=0.6, ge=0, le=1)
    note: str = ""


class EdgeCreate(BaseModel):
    dst_slug: str = Field(min_length=1)
    kind: Literal["requires", "generalizes"]
    confidence: float = Field(default=0.6, ge=0, le=1)
    note: str = ""


class EdgeStatusPatch(BaseModel):
    status: Literal["proposed", "approved", "rejected"]


class TeachingCreate(BaseModel):
    teacher: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    correction: bool = False
    source_ref: str | None = None
    summary: str | None = None


class CleanRunCreate(BaseModel):
    confidence_before: float | None = Field(default=None, ge=0, le=1)
    confidence_after: float | None = Field(default=None, ge=0, le=1)


class TraceCreate(BaseModel):
    kind: Literal["decision", "boundary"]
    situation: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    options: list = Field(default_factory=list)
    approver: str | None = None
    approval: Literal["explicit", "standing_rule", "corrected"] = "explicit"
    trust: float = Field(default=AGENT_MAX_TRUST, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    source_ref: str = ""


class TracePatch(BaseModel):
    outcome: Literal["ok", "corrected", "superseded"]
    superseded_by: int | None = None


class UsageCreate(BaseModel):
    subject_kind: Literal["person", "agent"]
    subject: str = Field(min_length=1)
    source_ref: str | None = None


def _person(person: OrgPerson) -> dict:
    return {
        "id": person.id,
        "username": person.username,
        "display_name": person.display_name,
        "email": person.email,
        "title": person.title,
        "department": person.department,
        "department_raw": person.department_raw,
        "site": person.site,
        "manager_username": person.manager_username,
        "active": person.active,
        "synced_at": person.synced_at,
    }


def _skill(skill: Skill, claim_count: int | None = None) -> dict:
    result = {
        "id": skill.id,
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description,
        "tags": skill.tags,
        "created_by": skill.created_by,
        "created_at": skill.created_at,
        "status": skill.status,
        "merged_into_id": skill.merged_into_id,
    }
    if claim_count is not None:
        result["claim_count"] = claim_count
    return result


def _claim(claim: SkillClaim, display_name: str | None = None) -> dict:
    return {
        "id": claim.id,
        "skill_id": claim.skill_id,
        "subject_kind": claim.subject_kind,
        "subject": claim.subject,
        "display_name": display_name,
        "kind": claim.kind,
        "confidence": claim.confidence,
        "note": claim.note,
        "source": claim.source,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


def _edge(edge: SkillEdge, src_slug: str | None = None, dst_slug: str | None = None) -> dict:
    return {
        "id": edge.id,
        "src_skill_id": edge.src_skill_id,
        "dst_skill_id": edge.dst_skill_id,
        "src_slug": src_slug,
        "dst_slug": dst_slug,
        "kind": edge.kind,
        "confidence": edge.confidence,
        "note": edge.note,
        "source": edge.source,
        "status": edge.status,
        "reviewed_by": edge.reviewed_by,
        "created_at": edge.created_at,
        "updated_at": edge.updated_at,
    }


def _teaching(session: TeachingSession, teacher_name: str | None = None) -> dict:
    return {
        "id": session.id,
        "skill_id": session.skill_id,
        "teacher": session.teacher,
        "teacher_name": teacher_name,
        "agent": session.agent,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "first_clean_run_at": session.first_clean_run_at,
        "corrections": session.corrections,
        "summary": session.summary,
        "source_ref": session.source_ref,
        "confidence_before": session.confidence_before,
        "confidence_after": session.confidence_after,
        "created_by": session.created_by,
        "created_at": session.created_at,
    }


def _usage(event: SkillUsageEvent) -> dict:
    return {
        "id": event.id,
        "skill_id": event.skill_id,
        "subject_kind": event.subject_kind,
        "subject": event.subject,
        "used_at": event.used_at,
        "source_ref": event.source_ref,
    }


def _trace(trace: DecisionTrace, chain: list[dict] | None = None,
           supersedes: list[int] | None = None) -> dict:
    return {
        "id": trace.id,
        "skill_id": trace.skill_id,
        "kind": trace.kind,
        "situation": trace.situation,
        "options": trace.options,
        "decision": trace.decision,
        "approver": trace.approver,
        "approval": trace.approval,
        "outcome": trace.outcome,
        "superseded_by": trace.superseded_by,
        "trust": trace.trust,
        "tags": list(trace.tags or []),
        "source_ref": trace.source_ref,
        "created_by": trace.created_by,
        "created_at": trace.created_at,
        # Supersession chain: rows that replaced this one, newest last.
        "chain": chain or [],
        # Rows this one replaced (the other direction of the same chain).
        "supersedes": supersedes or [],
    }


def _skill_match(q: str):
    pattern = f"%{q}%"
    return or_(
        Skill.slug.ilike(pattern),
        Skill.name.ilike(pattern),
        Skill.description.ilike(pattern),
        Skill.tags.overlap([q]),
    )


def _get_person(db: Session, username: str) -> OrgPerson:
    person = db.scalar(select(OrgPerson).where(OrgPerson.username == username.lower()))
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person not found")
    return person


def _follow_merged_into(db: Session, skill: Skill) -> Skill:
    """Follow merged_into chain to the canonical skill (depth cap 5).

    Fails loudly on cycle, dangling FK, or chain still open after 5 hops.
    """
    current = skill
    visited: set[int] = set()
    for _ in range(MERGE_DEPTH_CAP):
        if current.merged_into_id is None:
            return current
        if current.id in visited:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Skill merge chain contains a cycle",
            )
        visited.add(current.id)
        nxt = db.get(Skill, current.merged_into_id)
        if nxt is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Skill merge chain has a dangling merged_into_id",
            )
        current = nxt
    if current.merged_into_id is not None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Skill merge chain exceeds depth limit",
        )
    return current


def _find_skill(db: Session, slug: str) -> Skill:
    """Resolve slug via direct match or alias, without following merge chains."""
    skill = db.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        alias = db.scalar(select(SkillAlias).where(SkillAlias.alias == slug))
        if alias is not None:
            skill = db.get(Skill, alias.skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return skill


def _get_skill(db: Session, slug: str) -> Skill:
    """Resolve slug via direct match or alias, then follow merged_into (depth 5)."""
    return _follow_merged_into(db, _find_skill(db, slug))


def _slug_or_alias_taken(db: Session, slug: str) -> bool:
    return (
        db.scalar(select(Skill.id).where(Skill.slug == slug)) is not None
        or db.scalar(select(SkillAlias.id).where(SkillAlias.alias == slug)) is not None
    )


def _skill_lineage_ids(db: Session, canonical_ids: set[int]) -> set[int]:
    if not canonical_ids:
        return set()
    lineage = (
        select(Skill.id.label("id"))
        .where(Skill.id.in_(canonical_ids))
        .cte("skill_lineage", recursive=True)
    )
    children = select(Skill.id.label("id")).join(
        lineage, Skill.merged_into_id == lineage.c.id
    )
    lineage = lineage.union(children)
    return set(db.scalars(select(lineage.c.id)))


def _edge_status_filter(include_proposed: bool) -> str:
    if include_proposed:
        return "e.status IN ('approved', 'proposed')"
    return "e.status = 'approved'"


@router.get("/org/people")
def get_people(
    q: str | None = None,
    dept: str | None = None,
    site: str | None = None,
    active: bool | None = True,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    stmt = select(OrgPerson)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(OrgPerson.username.ilike(pattern), OrgPerson.display_name.ilike(pattern))
        )
    if dept:
        stmt = stmt.where(OrgPerson.department == dept)
    if site:
        stmt = stmt.where(OrgPerson.site == site.upper())
    if active is not None:
        stmt = stmt.where(OrgPerson.active.is_(active))
    people = db.scalars(stmt.order_by(OrgPerson.display_name, OrgPerson.username).limit(200))
    return [_person(person) for person in people]


@router.get("/org/people/{username}")
def get_person(
    username: str,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    person = _get_person(db, username)
    manager = None
    if person.manager_username:
        manager_row = db.scalar(
            select(OrgPerson).where(OrgPerson.username == person.manager_username)
        )
        if manager_row:
            manager = {
                "username": manager_row.username,
                "display_name": manager_row.display_name,
            }
    reports = db.scalars(
        select(OrgPerson)
        .where(OrgPerson.manager_username == person.username)
        .order_by(OrgPerson.display_name, OrgPerson.username)
    )
    claim_rows = db.execute(
        select(SkillClaim, Skill.name, Skill.slug)
        .join(Skill, Skill.id == SkillClaim.skill_id)
        .where(
            SkillClaim.subject_kind == "person",
            SkillClaim.subject == person.username,
        )
        .order_by(Skill.name, SkillClaim.kind)
    )
    result = _person(person)
    result["manager"] = manager
    result["direct_reports"] = [
        {"username": report.username, "display_name": report.display_name}
        for report in reports
    ]
    result["skill_claims"] = [
        {
            **_claim(claim, person.display_name),
            "skill_name": skill_name,
            "skill_slug": skill_slug,
        }
        for claim, skill_name, skill_slug in claim_rows
    ]
    taught_skill_ids = db.scalars(
        select(TeachingSession.skill_id)
        .where(
            TeachingSession.teacher == person.username,
            TeachingSession.first_clean_run_at.is_not(None),
        )
        .distinct()
    )
    canonical_ids: set[int] = set()
    for skill_id in taught_skill_ids:
        taught_skill = db.get(Skill, skill_id)
        if taught_skill is not None:
            canonical_ids.add(_follow_merged_into(db, taught_skill).id)
    lineage_ids = _skill_lineage_ids(db, canonical_ids)
    passes = 0
    if lineage_ids:
        passes = db.scalar(
            select(func.count(func.distinct(SkillUsageEvent.id))).where(
                SkillUsageEvent.skill_id.in_(lineage_ids),
                SkillUsageEvent.subject != person.username,
            )
        ) or 0
    result["weave"] = {"threads": len(canonical_ids), "passes": passes}
    return result


@router.get("/org/chain/{username}")
def get_chain(
    username: str,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    current = _get_person(db, username)
    chain: list[dict] = []
    visited: set[str] = set()
    for _hop in range(15):
        if current.username in visited:
            break
        visited.add(current.username)
        chain.append(_person(current))
        if not current.manager_username or current.manager_username in visited:
            break
        manager = db.scalar(
            select(OrgPerson).where(OrgPerson.username == current.manager_username)
        )
        if manager is None:
            break
        current = manager
    return chain


@router.get("/org/tree/{username}")
def get_tree(
    username: str,
    depth: int = Query(default=3, ge=0),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    root = _get_person(db, username)
    capped_depth = min(depth, 5)
    rows = db.execute(
        text(
            """
            WITH RECURSIVE subtree AS (
                SELECT id, username, display_name, email, title, department,
                       department_raw, site, manager_username, active, synced_at,
                       0 AS depth, ARRAY[username]::text[] AS path
                FROM org_people
                WHERE username = :username
                UNION ALL
                SELECT p.id, p.username, p.display_name, p.email, p.title, p.department,
                       p.department_raw, p.site, p.manager_username, p.active, p.synced_at,
                       subtree.depth + 1, subtree.path || p.username
                FROM org_people AS p
                JOIN subtree ON p.manager_username = subtree.username
                WHERE subtree.depth < :depth
                  AND NOT p.username = ANY(subtree.path)
            )
            SELECT id, username, display_name, email, title, department,
                   department_raw, site, manager_username, active, synced_at, depth
            FROM subtree
            ORDER BY depth, display_name, username
            """
        ),
        {"username": root.username, "depth": capped_depth},
    ).mappings()
    nodes: dict[str, dict] = {}
    ordered_rows = list(rows)
    for row in ordered_rows:
        nodes[row["username"]] = {
            **{key: row[key] for key in row if key != "depth"},
            "depth": row["depth"],
            "direct_reports": [],
        }
    for row in ordered_rows[1:]:
        parent = nodes.get(row["manager_username"])
        if parent is not None:
            parent["direct_reports"].append(nodes[row["username"]])
    return nodes[root.username]


@router.get("/org/departments")
def get_departments(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    rows = db.execute(
        select(OrgPerson.department, OrgPerson.site, func.count(OrgPerson.id))
        .where(OrgPerson.department.is_not(None), OrgPerson.active.is_(True))
        .group_by(OrgPerson.department, OrgPerson.site)
        .order_by(OrgPerson.department)
    )
    departments: dict[str, dict] = {}
    for department, site, count in rows:
        item = departments.setdefault(
            department,
            {
                "department": department,
                "people_count": 0,
                "sites": {site_code: 0 for site_code in ("MS", "HS", "JM", "MD")},
            },
        )
        item["people_count"] += count
        if site in item["sites"]:
            item["sites"][site] += count
    return list(departments.values())


@router.get("/skills")
def get_skills(
    q: str | None = None,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    stmt = (
        select(Skill, func.count(SkillClaim.id).label("claim_count"))
        .outerjoin(SkillClaim, SkillClaim.skill_id == Skill.id)
        .group_by(Skill.id)
        .order_by(Skill.name, Skill.slug)
    )
    if q:
        stmt = stmt.where(_skill_match(q))
    return [_skill(skill, count) for skill, count in db.execute(stmt)]


@router.post("/skills", status_code=201)
def post_skill(
    body: SkillCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    slug = body.slug or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")
    if not slug or not SLUG_RE.fullmatch(slug):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="slug must be kebab-case",
        )
    if _slug_or_alias_taken(db, slug):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Skill slug already exists")
    skill = Skill(
        slug=slug,
        name=body.name,
        description=body.description,
        tags=body.tags,
        created_by=ctx.actor,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return _skill(skill, 0)


@router.get("/skills/{slug}")
def get_skill(
    slug: str,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    skill = _get_skill(db, slug)
    person = OrgPerson
    rows = db.execute(
        select(SkillClaim, person.display_name)
        .outerjoin(
            person,
            (SkillClaim.subject_kind == "person")
            & (person.username == SkillClaim.subject),
        )
        .where(SkillClaim.skill_id == skill.id)
        .order_by(SkillClaim.confidence.desc(), SkillClaim.id)
    )
    result = _skill(skill, len(skill.claims))
    result["claims"] = [_claim(claim, display_name) for claim, display_name in rows]
    lineage_ids = _skill_lineage_ids(db, {skill.id})
    teaching_rows = db.execute(
        select(TeachingSession, OrgPerson.display_name)
        .join(OrgPerson, OrgPerson.username == TeachingSession.teacher)
        .where(TeachingSession.skill_id.in_(lineage_ids))
        .order_by(TeachingSession.started_at, TeachingSession.id)
    )
    result["taught_by"] = [
        _teaching(session, teacher_name) for session, teacher_name in teaching_rows
    ]
    return result


@router.post("/skills/{slug}/teaching", status_code=201)
def post_teaching(
    slug: str,
    body: TeachingCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    skill = _get_skill(db, slug)
    teacher = body.teacher.strip().lower()
    agent = body.agent.strip()
    if not teacher or not agent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="teacher and agent are required",
        )
    if teacher != ctx.user.username.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Teaching may only be recorded for the authenticated teacher",
        )
    if ctx.is_agent and agent != ctx.actor:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Agents may only record their own teaching sessions",
        )
    person = db.scalar(select(OrgPerson).where(OrgPerson.username == teacher))
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    if db.scalar(select(ApiKey.id).where(ApiKey.agent_name == agent).limit(1)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")

    db.scalar(select(Skill).where(Skill.id == skill.id).with_for_update())
    session = db.scalar(
        select(TeachingSession)
        .where(
            TeachingSession.skill_id == skill.id,
            TeachingSession.teacher == teacher,
            TeachingSession.agent == agent,
            TeachingSession.ended_at.is_(None),
        )
        .order_by(TeachingSession.id)
        .limit(1)
    )
    source_ref = (body.source_ref or "").strip()
    summary = (body.summary or "").strip()
    if session is None:
        session = TeachingSession(
            skill_id=skill.id,
            teacher=teacher,
            agent=agent,
            started_at=datetime.now(timezone.utc),
            corrections=1 if body.correction else 0,
            source_ref=source_ref,
            summary=summary,
            created_by=ctx.actor,
        )
        db.add(session)
    else:
        if body.correction:
            session.corrections += 1
        if source_ref and source_ref not in session.source_ref.splitlines():
            session.source_ref = "\n".join(filter(None, (session.source_ref, source_ref)))
        if summary:
            session.summary = summary
    db.commit()
    db.refresh(session)
    return _teaching(session, person.display_name)


@router.post("/skills/{slug}/teaching/{session_id}/clean-run")
def post_clean_run(
    slug: str,
    session_id: int,
    body: CleanRunCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    skill = _get_skill(db, slug)
    session = db.scalar(
        select(TeachingSession)
        .where(
            TeachingSession.id == session_id,
            TeachingSession.skill_id == skill.id,
        )
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Teaching session not found")
    allowed = (
        ctx.actor == session.agent and ctx.user.username.lower() == session.teacher
        if ctx.is_agent
        else ctx.user.username.lower() == session.teacher
    )
    if not allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the session teacher or agent may record a clean run",
        )
    if session.first_clean_run_at is None:
        now = datetime.now(timezone.utc)
        session.first_clean_run_at = now
        session.ended_at = session.ended_at or now
        session.confidence_before = body.confidence_before
        session.confidence_after = body.confidence_after
    db.commit()
    db.refresh(session)
    teacher_name = db.scalar(
        select(OrgPerson.display_name).where(OrgPerson.username == session.teacher)
    )
    return _teaching(session, teacher_name)


@router.post("/skills/{slug}/usage", status_code=201)
def post_usage(
    slug: str,
    body: UsageCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    skill = _get_skill(db, slug)
    subject = body.subject.strip()
    if body.subject_kind == "person":
        subject = subject.lower()
        if db.scalar(select(OrgPerson.id).where(OrgPerson.username == subject)) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person not found")
    elif db.scalar(select(ApiKey.id).where(ApiKey.agent_name == subject).limit(1)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")

    own_person = body.subject_kind == "person" and subject == ctx.user.username.lower()
    own_agent = body.subject_kind == "agent" and ctx.is_agent and subject == ctx.actor
    if (ctx.is_agent and not (own_agent or own_person)) or (
        not ctx.is_agent and not own_person
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Usage may only be recorded for the authenticated subject",
        )
    event = SkillUsageEvent(
        skill_id=skill.id,
        subject_kind=body.subject_kind,
        subject=subject,
        used_at=datetime.now(timezone.utc),
        source_ref=(body.source_ref or "").strip(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _usage(event)


@router.post("/skills/{slug}/claims")
def post_claim(
    slug: str,
    body: ClaimCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    skill = _get_skill(db, slug)
    subject = body.subject.lower() if body.subject_kind == "person" else body.subject
    if body.subject_kind == "person":
        if db.scalar(select(OrgPerson.id).where(OrgPerson.username == subject)) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person not found")
    elif db.scalar(select(ApiKey.id).where(ApiKey.agent_name == subject).limit(1)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent not found")

    stmt = (
        insert(SkillClaim)
        .values(
            skill_id=skill.id,
            subject_kind=body.subject_kind,
            subject=subject,
            kind=body.kind,
            confidence=body.confidence,
            note=body.note,
            source=ctx.actor,
        )
        .on_conflict_do_update(
            constraint="uq_skill_claim_subject",
            set_={
                "confidence": body.confidence,
                "note": body.note,
                # The claim now reflects THIS caller's assertion; leaving the
                # original source would attribute the new confidence to whoever
                # first created the claim.
                "source": ctx.actor,
                "updated_at": func.now(),
            },
        )
        .returning(SkillClaim.id)
    )
    claim_id = db.scalar(stmt)
    db.commit()
    claim = db.get(SkillClaim, claim_id)
    return _claim(claim)


@router.delete("/skills/{slug}/claims/{claim_id}", status_code=204)
def delete_claim(
    slug: str,
    claim_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    skill = _get_skill(db, slug)
    claim = db.scalar(
        select(SkillClaim).where(
            SkillClaim.id == claim_id,
            SkillClaim.skill_id == skill.id,
        )
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if ctx.is_agent and claim.source != ctx.actor:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Agents can only delete their own claims",
        )
    db.delete(claim)
    db.commit()


@router.post("/skills/{slug}/merge-into/{canonical}")
def merge_skill(
    slug: str,
    canonical: str,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Merge loser skill into canonical. Human-only.

    Loser survives as status='merged' with merged_into_id set (slug reserved).
    Claims migrate via INSERT..SELECT ON CONFLICT, keeping the higher-confidence
    assertion and its full provenance (source, note with merged-from suffix,
    timestamps). Edges migrate with equivalent conflict handling and rejected
    stickiness. Alias row is added for the loser slug.
    """
    if ctx.is_agent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only humans may merge skills",
        )

    # Resolve the loser without following merge chains so we operate on the
    # named row; the winner resolves to its canonical form.
    loser = _find_skill(db, slug)
    winner = _follow_merged_into(db, _find_skill(db, canonical))
    if loser.id == winner.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a skill into itself",
        )
    if loser.status == "merged":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Skill is already merged",
        )

    loser_slug = loser.slug
    loser_id = loser.id
    winner_id = winner.id
    suffix = f" [merged from {loser_slug}]"

    # Claims: higher confidence wins with full provenance of the winner.
    db.execute(
        text(
            """
            INSERT INTO skill_claims (
                skill_id, subject_kind, subject, kind,
                confidence, note, source, created_at, updated_at
            )
            SELECT
                :winner_id, subject_kind, subject, kind,
                confidence,
                note || :suffix,
                source, created_at, updated_at
            FROM skill_claims
            WHERE skill_id = :loser_id
            ON CONFLICT ON CONSTRAINT uq_skill_claim_subject
            DO UPDATE SET
                confidence = EXCLUDED.confidence,
                note = EXCLUDED.note,
                source = EXCLUDED.source,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            WHERE EXCLUDED.confidence > skill_claims.confidence
            """
        ),
        {
            "winner_id": winner_id,
            "loser_id": loser_id,
            "suffix": suffix,
        },
    )
    db.execute(
        text("DELETE FROM skill_claims WHERE skill_id = :loser_id"),
        {"loser_id": loser_id},
    )

    # Higher conf wins assertion fields; rejected is sticky; reviewed_by follows
    # the row that supplies rejected status (not conf, not the approved side).
    edge_conflict_set = """
                confidence = CASE
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.confidence ELSE skill_edges.confidence
                END,
                note = CASE
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.note ELSE skill_edges.note
                END,
                source = CASE
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.source ELSE skill_edges.source
                END,
                created_at = CASE
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.created_at ELSE skill_edges.created_at
                END,
                updated_at = CASE
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.updated_at ELSE skill_edges.updated_at
                END,
                status = CASE
                    WHEN skill_edges.status = 'rejected'
                      OR EXCLUDED.status = 'rejected'
                    THEN 'rejected'
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.status
                    ELSE skill_edges.status
                END,
                reviewed_by = CASE
                    WHEN skill_edges.status = 'rejected'
                      AND EXCLUDED.status = 'rejected' THEN
                        CASE
                            WHEN EXCLUDED.confidence > skill_edges.confidence
                            THEN EXCLUDED.reviewed_by
                            ELSE skill_edges.reviewed_by
                        END
                    WHEN skill_edges.status = 'rejected' THEN skill_edges.reviewed_by
                    WHEN EXCLUDED.status = 'rejected' THEN EXCLUDED.reviewed_by
                    WHEN EXCLUDED.confidence > skill_edges.confidence
                    THEN EXCLUDED.reviewed_by
                    ELSE skill_edges.reviewed_by
                END
    """

    # Edges with src = loser → rewire to winner (skip self-loops).
    db.execute(
        text(
            f"""
            INSERT INTO skill_edges (
                src_skill_id, dst_skill_id, kind, confidence, note, source,
                status, reviewed_by, created_at, updated_at
            )
            SELECT
                :winner_id, e.dst_skill_id, e.kind, e.confidence,
                e.note || :suffix,
                e.source, e.status, e.reviewed_by, e.created_at, e.updated_at
            FROM skill_edges AS e
            WHERE e.src_skill_id = :loser_id
              AND e.dst_skill_id <> :winner_id
            ON CONFLICT ON CONSTRAINT uq_skill_edge
            DO UPDATE SET
            {edge_conflict_set}
            """
        ),
        {
            "winner_id": winner_id,
            "loser_id": loser_id,
            "suffix": suffix,
        },
    )

    # Edges with dst = loser → rewire to winner (skip self-loops).
    db.execute(
        text(
            f"""
            INSERT INTO skill_edges (
                src_skill_id, dst_skill_id, kind, confidence, note, source,
                status, reviewed_by, created_at, updated_at
            )
            SELECT
                e.src_skill_id, :winner_id, e.kind, e.confidence,
                e.note || :suffix,
                e.source, e.status, e.reviewed_by, e.created_at, e.updated_at
            FROM skill_edges AS e
            WHERE e.dst_skill_id = :loser_id
              AND e.src_skill_id <> :winner_id
            ON CONFLICT ON CONSTRAINT uq_skill_edge
            DO UPDATE SET
            {edge_conflict_set}
            """
        ),
        {
            "winner_id": winner_id,
            "loser_id": loser_id,
            "suffix": suffix,
        },
    )
    db.execute(
        text(
            "DELETE FROM skill_edges "
            "WHERE src_skill_id = :loser_id OR dst_skill_id = :loser_id"
        ),
        {"loser_id": loser_id},
    )

    # Point existing aliases of the loser at the winner; reserve loser slug.
    db.execute(
        text(
            "UPDATE skill_aliases SET skill_id = :winner_id WHERE skill_id = :loser_id"
        ),
        {"winner_id": winner_id, "loser_id": loser_id},
    )
    existing_alias = db.scalar(
        select(SkillAlias.id).where(SkillAlias.alias == loser_slug)
    )
    if existing_alias is None:
        db.add(
            SkillAlias(alias=loser_slug, skill_id=winner_id, source=ctx.actor)
        )
    else:
        db.execute(
            text(
                "UPDATE skill_aliases SET skill_id = :winner_id "
                "WHERE alias = :alias"
            ),
            {"winner_id": winner_id, "alias": loser_slug},
        )

    loser.status = "merged"
    loser.merged_into_id = winner_id
    db.commit()
    db.refresh(winner)
    return _skill(winner)


@router.post("/skills/{slug}/edges", status_code=201)
def post_edge(
    slug: str,
    body: EdgeCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Create or upsert a skill edge.

    src requires dst = performing src entails ability dst; src generalizes dst =
    claim on src implies WEAK capability on dst, never reverse.

    Agents create proposed edges; humans create approved edges. Re-proposal
    upserts; a rejected existing row remains rejected unless a human flips it
    via PATCH.
    """
    src = _get_skill(db, slug)
    dst = _get_skill(db, body.dst_slug)
    if src.id == dst.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Edge cannot connect a skill to itself",
        )

    initial_status = "proposed" if ctx.is_agent else "approved"
    reviewed_by = None if ctx.is_agent else ctx.actor

    existing = db.scalar(
        select(SkillEdge).where(
            SkillEdge.src_skill_id == src.id,
            SkillEdge.dst_skill_id == dst.id,
            SkillEdge.kind == body.kind,
        )
    )
    if existing is not None:
        existing.confidence = body.confidence
        existing.note = body.note
        existing.source = ctx.actor
        existing.updated_at = datetime.now(timezone.utc)
        if existing.status == "rejected":
            # Rejected stickiness: re-proposal does not un-reject.
            pass
        elif not ctx.is_agent:
            existing.status = "approved"
            existing.reviewed_by = ctx.actor
        # agent re-proposal on proposed/approved: keep status
        try:
            db.commit()
        except (IntegrityError, DBAPIError) as exc:
            db.rollback()
            msg = str(getattr(exc, "orig", exc)).lower()
            if "cycle" in msg:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="skill edge would create a cycle",
                ) from exc
            raise
        db.refresh(existing)
        return _edge(existing, src.slug, dst.slug)

    edge = SkillEdge(
        src_skill_id=src.id,
        dst_skill_id=dst.id,
        kind=body.kind,
        confidence=body.confidence,
        note=body.note,
        source=ctx.actor,
        status=initial_status,
        reviewed_by=reviewed_by,
    )
    db.add(edge)
    try:
        db.commit()
    except (IntegrityError, DBAPIError) as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "cycle" in msg:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="skill edge would create a cycle",
            ) from exc
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Edge conflict",
        ) from exc
    db.refresh(edge)
    return _edge(edge, src.slug, dst.slug)


@router.patch("/skills/edges/{edge_id}")
def patch_edge(
    edge_id: int,
    body: EdgeStatusPatch,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Change edge status. Human-only; agents receive 403.

    Supports proposed / approved / rejected. Sets reviewed_by to the human actor.
    """
    if ctx.is_agent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only humans may change edge status",
        )
    edge = db.get(SkillEdge, edge_id)
    if edge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Edge not found")
    edge.status = body.status
    edge.reviewed_by = ctx.actor
    edge.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except (IntegrityError, DBAPIError) as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "cycle" in msg:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="skill edge would create a cycle",
            ) from exc
        raise
    db.refresh(edge)
    src = db.get(Skill, edge.src_skill_id)
    dst = db.get(Skill, edge.dst_skill_id)
    return _edge(
        edge,
        src.slug if src else None,
        dst.slug if dst else None,
    )


@router.get("/skills/{slug}/requires-closure")
def requires_closure(
    slug: str,
    include_proposed: bool = Query(default=False),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Approved requires edges only (depth < 4, path-array guard).

    Pass include_proposed=true to also traverse proposed edges for exploration.
    Default remains approved-only.
    """
    _ = ctx
    skill = _get_skill(db, slug)
    status_sql = _edge_status_filter(include_proposed)
    rows = db.execute(
        text(
            f"""
            WITH RECURSIVE closure AS (
                SELECT s.id, s.slug, s.name, 0 AS depth,
                       ARRAY[s.id]::int[] AS path
                FROM skills AS s
                WHERE s.id = :root_id
                UNION ALL
                SELECT dst.id, dst.slug, dst.name, c.depth + 1,
                       c.path || dst.id
                FROM closure AS c
                JOIN skill_edges AS e
                  ON e.src_skill_id = c.id
                 AND e.kind = 'requires'
                 AND {status_sql}
                JOIN skills AS dst ON dst.id = e.dst_skill_id
                WHERE c.depth + 1 < :depth_cap
                  AND NOT dst.id = ANY (c.path)
            ),
            deduped AS (
                SELECT DISTINCT ON (id) id, slug, name, depth
                FROM closure
                ORDER BY id, depth
            )
            SELECT id, slug, name, depth
            FROM deduped
            ORDER BY depth, slug
            """
        ),
        {"root_id": skill.id, "depth_cap": REQUIRES_DEPTH_CAP},
    ).mappings()
    return [
        {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "depth": row["depth"],
        }
        for row in rows
    ]


@router.get("/skills/{slug}/who-can-transitive")
def who_can_transitive(
    slug: str,
    include_proposed: bool = Query(default=False),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Coverage ranking over the requires-closure of a skill.

    Uses approved requires edges only by default (rejected/proposed invisible).
    Per subject: covered count, full_cover, weakest_link = MIN confidence
    (never average), via array of covered skill slugs.
    Order: full_cover DESC, covered DESC, weakest_link DESC.
    """
    _ = ctx
    skill = _get_skill(db, slug)
    status_sql = _edge_status_filter(include_proposed)
    rows = db.execute(
        text(
            f"""
            WITH RECURSIVE closure AS (
                SELECT s.id, s.slug, 0 AS depth, ARRAY[s.id]::int[] AS path
                FROM skills AS s
                WHERE s.id = :root_id
                UNION ALL
                SELECT dst.id, dst.slug, c.depth + 1, c.path || dst.id
                FROM closure AS c
                JOIN skill_edges AS e
                  ON e.src_skill_id = c.id
                 AND e.kind = 'requires'
                 AND {status_sql}
                JOIN skills AS dst ON dst.id = e.dst_skill_id
                WHERE c.depth + 1 < :depth_cap
                  AND NOT dst.id = ANY (c.path)
            ),
            required AS (
                SELECT DISTINCT ON (id) id, slug, depth
                FROM closure
                ORDER BY id, depth
            ),
            required_count AS (
                SELECT count(*)::int AS total FROM required
            ),
            best_claim AS (
                SELECT
                    sc.subject_kind,
                    sc.subject,
                    sc.skill_id,
                    r.slug AS skill_slug,
                    max(sc.confidence) AS confidence
                FROM skill_claims AS sc
                JOIN required AS r ON r.id = sc.skill_id
                GROUP BY sc.subject_kind, sc.subject, sc.skill_id, r.slug
            ),
            coverage AS (
                SELECT
                    bc.subject_kind,
                    bc.subject,
                    count(*)::int AS covered,
                    min(bc.confidence) AS weakest_link,
                    array_agg(bc.skill_slug ORDER BY bc.skill_slug) AS via
                FROM best_claim AS bc
                GROUP BY bc.subject_kind, bc.subject
            )
            SELECT
                c.subject_kind,
                c.subject,
                p.display_name,
                p.department,
                p.site,
                c.covered,
                c.weakest_link,
                c.via,
                (c.covered = rc.total) AS full_cover,
                rc.total AS required_count
            FROM coverage AS c
            CROSS JOIN required_count AS rc
            LEFT JOIN org_people AS p
              ON c.subject_kind = 'person' AND p.username = c.subject
            ORDER BY
                full_cover DESC,
                c.covered DESC,
                c.weakest_link DESC,
                c.subject
            """
        ),
        {"root_id": skill.id, "depth_cap": REQUIRES_DEPTH_CAP},
    ).mappings()
    return [
        {
            "subject_kind": row["subject_kind"],
            "subject": row["subject"],
            "display_name": row["display_name"],
            "department": row["department"],
            "site": row["site"],
            "covered": row["covered"],
            "required_count": row["required_count"],
            "full_cover": row["full_cover"],
            "weakest_link": row["weakest_link"],
            "via": list(row["via"] or []),
        }
        for row in rows
    ]


_KIND_RANK = {"can_do": 0, "owns_process": 1, "knows_about": 2}


@router.get("/org/who-can")
def who_can(
    q: str = Query(min_length=1),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Who can do skills matching q, including one-hop generalizes expansion.

    Direct claims outrank derived for the same subject+skill. Derived
    confidence = claim.confidence * edge.confidence * 0.8; every derived row
    carries via_skill (the general skill). Direct rows expose via_skill=null.

    Ordering: confidence DESC, kind priority (can_do, owns_process, knows_about),
    direct before derived at equal confidence, then stable tie-breaks.
    """
    _ = ctx
    person = OrgPerson

    # Direct claims on skills matching q — no preliminary LIMIT; final cap after merge.
    direct_rows = db.execute(
        select(SkillClaim, Skill, person.display_name, person.department, person.site)
        .join(Skill, Skill.id == SkillClaim.skill_id)
        .outerjoin(
            person,
            (SkillClaim.subject_kind == "person")
            & (person.username == SkillClaim.subject),
        )
        .where(_skill_match(q))
        .order_by(SkillClaim.confidence.desc(), SkillClaim.id)
    ).all()

    direct_keys: set[tuple[str, str, int]] = set()
    results: list[dict] = []
    for claim, skill, display_name, department, site in direct_rows:
        direct_keys.add((claim.subject_kind, claim.subject, skill.id))
        results.append(
            {
                "subject_kind": claim.subject_kind,
                "subject": claim.subject,
                "display_name": display_name,
                "department": department,
                "site": site,
                "kind": claim.kind,
                "confidence": claim.confidence,
                "note": claim.note,
                "source": claim.source,
                "skill_slug": skill.slug,
                "skill_name": skill.name,
                "skill": {"slug": skill.slug, "name": skill.name},
                "via_skill": None,
                "derived": False,
                "_claim_id": claim.id,
            }
        )

    # One-hop generalizes: claim on src implies weak capability on dst.
    # No preliminary LIMIT — suppress against all directs, then final LIMIT 50.
    derived_sql = text(
        """
        SELECT
            sc.id AS claim_id,
            sc.subject_kind,
            sc.subject,
            p.display_name,
            p.department,
            p.site,
            sc.kind,
            (sc.confidence * e.confidence * 0.8) AS confidence,
            sc.note,
            sc.source,
            dst.slug AS skill_slug,
            dst.name AS skill_name,
            dst.id AS skill_id,
            src.slug AS via_skill
        FROM skill_edges AS e
        JOIN skills AS src ON src.id = e.src_skill_id
        JOIN skills AS dst ON dst.id = e.dst_skill_id
        JOIN skill_claims AS sc ON sc.skill_id = src.id
        LEFT JOIN org_people AS p
          ON sc.subject_kind = 'person' AND p.username = sc.subject
        WHERE e.kind = 'generalizes'
          AND e.status = 'approved'
          AND (
              dst.slug ILIKE :pattern
              OR dst.name ILIKE :pattern
              OR dst.description ILIKE :pattern
              OR :q = ANY (dst.tags)
          )
        ORDER BY confidence DESC, sc.id
        """
    )
    pattern = f"%{q}%"
    derived_rows = db.execute(derived_sql, {"pattern": pattern, "q": q}).mappings()

    # Keep best derived per (subject_kind, subject, skill_id); skip if direct exists.
    best_derived: dict[tuple[str, str, int], dict] = {}
    for row in derived_rows:
        key = (row["subject_kind"], row["subject"], row["skill_id"])
        if key in direct_keys:
            continue
        existing = best_derived.get(key)
        if existing is None or row["confidence"] > existing["confidence"]:
            best_derived[key] = {
                "subject_kind": row["subject_kind"],
                "subject": row["subject"],
                "display_name": row["display_name"],
                "department": row["department"],
                "site": row["site"],
                "kind": row["kind"],
                "confidence": float(row["confidence"]),
                "note": row["note"],
                "source": row["source"],
                "skill_slug": row["skill_slug"],
                "skill_name": row["skill_name"],
                "skill": {"slug": row["skill_slug"], "name": row["skill_name"]},
                "via_skill": row["via_skill"],
                "derived": True,
                "_claim_id": row["claim_id"],
            }

    results.extend(best_derived.values())

    results.sort(
        key=lambda item: (
            -float(item["confidence"]),
            _KIND_RANK.get(item["kind"], 3),
            1 if item.get("derived") else 0,
            item.get("_claim_id") or 0,
            item["subject"],
            item.get("skill_slug") or "",
        )
    )
    for item in results:
        item.pop("_claim_id", None)
    return results[:50]


def _skill_owner(db: Session, skill_id: int) -> dict | None:
    """The owns_process claimant — whose rules the boundary rows are."""
    row = db.execute(
        select(SkillClaim.subject, OrgPerson.display_name)
        .outerjoin(OrgPerson, OrgPerson.username == SkillClaim.subject)
        .where(
            SkillClaim.skill_id == skill_id,
            SkillClaim.subject_kind == "person",
            SkillClaim.kind == "owns_process",
        )
        .order_by(SkillClaim.confidence.desc(), SkillClaim.id)
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"username": row[0], "display_name": row[1] or row[0]}


def _trace_chains(
    db: Session, traces: list[DecisionTrace]
) -> tuple[dict[int, list[dict]], dict[int, list[int]]]:
    """Forward supersession chain per trace, plus the rows each one replaced."""
    forward: dict[int, list[dict]] = {}
    for trace in traces:
        chain: list[dict] = []
        seen = {trace.id}
        current = trace.superseded_by
        for _hop in range(TRACE_CHAIN_DEPTH_CAP):
            if current is None:
                break
            nxt = db.get(DecisionTrace, current)
            if nxt is None or nxt.id in seen:
                break
            chain.append(
                {
                    "id": nxt.id,
                    "decision": nxt.decision,
                    "outcome": nxt.outcome,
                    "created_at": nxt.created_at,
                }
            )
            seen.add(nxt.id)
            current = nxt.superseded_by
        forward[trace.id] = chain

    ids = [trace.id for trace in traces]
    backward: dict[int, list[int]] = {trace_id: [] for trace_id in ids}
    if ids:
        rows = db.execute(
            select(DecisionTrace.superseded_by, DecisionTrace.id)
            .where(DecisionTrace.superseded_by.in_(ids))
            .order_by(DecisionTrace.id)
        )
        for parent_id, child_id in rows:
            backward.setdefault(parent_id, []).append(child_id)
    return forward, backward


def _trace_query(
    q: str | None,
    include_superseded: bool,
    include_corrected: bool,
):
    """Filter + order shared by the skill-scoped and cross-skill endpoints.

    Order: boundaries first (age never invalidates an "ask me" rule), then
    outcome='ok' by recency, then pending. Corrected rows are anti-precedents
    and only appear on request.
    """
    stmt = select(DecisionTrace)
    if not include_superseded:
        stmt = stmt.where(DecisionTrace.outcome != "superseded")
    if not include_corrected:
        stmt = stmt.where(DecisionTrace.outcome != "corrected")
    if q:
        # Escape LIKE metacharacters so a query of '%' or '_' matches those
        # literal characters instead of every row.
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                DecisionTrace.search_tsv.op("@@")(
                    func.websearch_to_tsquery("simple", q)
                ),
                # Short/partial queries produce no lexeme match — the ILIKE arm
                # keeps "den" finding "finishing-denim".
                DecisionTrace.situation.ilike(pattern, escape="\\"),
                DecisionTrace.decision.ilike(pattern, escape="\\"),
            )
        )
    # A boundary ranks first ONLY once confirmed — a human approved it, or a
    # human authored it (auto-extract marks machine-written, unconfirmed rows).
    # An unconfirmed agent-written boundary must not sit atop the owner's
    # rulebook presented as their rule; it ranks with ordinary pending rows.
    confirmed_boundary = and_(
        DecisionTrace.kind == "boundary",
        DecisionTrace.approver.isnot(None),
        not_(DecisionTrace.tags.any("auto-extract")),
    )
    rank = case(
        (confirmed_boundary, 0),
        (DecisionTrace.outcome == "ok", 1),
        (DecisionTrace.outcome == "pending", 2),
        else_=3,
    )
    # Confirmed boundaries read as a stated rulebook, so they keep the order the
    # owner taught them in; everything else is newest-first.
    boundary_order = case((confirmed_boundary, DecisionTrace.id), else_=0)
    return stmt.order_by(
        rank,
        boundary_order,
        DecisionTrace.created_at.desc(),
        DecisionTrace.id.desc(),
    )


def _traces_payload(db: Session, traces: list[DecisionTrace]) -> list[dict]:
    forward, backward = _trace_chains(db, traces)
    return [
        _trace(trace, forward.get(trace.id), backward.get(trace.id))
        for trace in traces
    ]


@router.post("/skills/{slug}/traces", status_code=201)
def post_trace(
    slug: str,
    body: TraceCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Record a decision or a boundary against a skill.

    Poisoning defence #1: kind='decision' without an identified human approver
    is refused — no human anchor, no trace.
    """
    skill = _get_skill(db, slug)
    approver = (body.approver or "").strip().lower() or None
    if body.kind == "decision" and approver is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="kind='decision' requires an approver (human anchor)",
        )
    if approver is not None and db.scalar(
        select(OrgPerson.id).where(OrgPerson.username == approver)
    ) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Approver not found")

    tags = [tag.strip() for tag in body.tags if tag.strip()]
    trust = body.trust
    if ctx.is_agent:
        trust = min(trust, AGENT_MAX_TRUST)
        if AUTO_EXTRACT_TAG not in tags:
            tags.append(AUTO_EXTRACT_TAG)

    trace = DecisionTrace(
        skill_id=skill.id,
        kind=body.kind,
        situation=body.situation.strip(),
        options=body.options,
        decision=body.decision.strip(),
        approver=approver,
        approval=body.approval,
        # outcome is feedback, never an author's claim: it starts pending and
        # only a human PATCH moves it (defence #5).
        outcome="pending",
        trust=trust,
        tags=tags,
        source_ref=body.source_ref.strip(),
        created_by=ctx.actor,
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return _trace(trace)


@router.get("/skills/{slug}/traces")
def get_skill_traces(
    slug: str,
    q: str | None = None,
    include_superseded: bool = Query(default=False),
    include_corrected: bool = Query(default=False),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    skill = _get_skill(db, slug)
    lineage_ids = _skill_lineage_ids(db, {skill.id})
    stmt = _trace_query(q, include_superseded, include_corrected).where(
        DecisionTrace.skill_id.in_(lineage_ids)
    )
    traces = list(db.scalars(stmt.limit(TRACE_LIMIT)))
    return {
        "skill": _skill(skill),
        "owner": _skill_owner(db, skill.id),
        "traces": _traces_payload(db, traces),
    }


@router.get("/traces")
def get_traces(
    q: str | None = None,
    include_superseded: bool = Query(default=False),
    include_corrected: bool = Query(default=False),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Cross-skill precedent search — same ordering as the skill-scoped view."""
    _ = ctx
    stmt = _trace_query(q, include_superseded, include_corrected)
    traces = list(db.scalars(stmt.limit(TRACE_LIMIT)))
    payload = _traces_payload(db, traces)
    slugs = {
        skill_id: (slug_value, name)
        for skill_id, slug_value, name in db.execute(
            select(Skill.id, Skill.slug, Skill.name).where(
                Skill.id.in_({trace.skill_id for trace in traces} or {0})
            )
        )
    }
    for item in payload:
        slug_value, name = slugs.get(item["skill_id"], (None, None))
        item["skill_slug"] = slug_value
        item["skill_name"] = name
    return payload


@router.patch("/traces/{trace_id}")
def patch_trace(
    trace_id: int,
    body: TracePatch,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Outcome feedback. Humans only — an agent may not grade its own precedent."""
    if ctx.is_agent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only humans may change a trace outcome",
        )
    trace = db.get(DecisionTrace, trace_id)
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trace not found")

    # Only the skill's process owner (or the person who approved this trace) may
    # regrade it. Without this, any authenticated employee could mark another
    # team's boundary 'corrected' — which removes it from default retrieval,
    # silently deleting the owner's "ask me" rule from what agents see.
    owner = _skill_owner(db, trace.skill_id)
    owner_name = owner["username"] if owner else None
    if ctx.actor not in {owner_name, trace.approver}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the skill's owner or the trace's approver may change it",
        )

    if body.superseded_by is not None:
        if body.outcome != "superseded":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="superseded_by requires outcome='superseded'",
            )
        if body.superseded_by == trace.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A trace cannot supersede itself",
            )
        replacement = db.get(DecisionTrace, body.superseded_by)
        if replacement is None or replacement.skill_id != trace.skill_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Superseding trace not found on this skill",
            )
        trace.superseded_by = replacement.id
    trace.outcome = body.outcome
    db.commit()
    db.refresh(trace)
    forward, backward = _trace_chains(db, [trace])
    return _trace(trace, forward.get(trace.id), backward.get(trace.id))
