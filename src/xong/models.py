from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from xong.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Lowercased. A linking hint only — identity is keyed by user_identities.
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    tz: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    lists: Mapped[list[List]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    focus_items: Mapped[list[Focus]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserIdentity(Base):
    """Maps an external identity to a user row. OIDC guarantees `sub` is stable
    only within an issuer, so the provider carries the issuer; `email` and
    `preferred_username` are mutable and must never be keys."""

    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # "oidc:<issuer>" or "proxy"
    subject: Mapped[str] = mapped_column(Text, nullable=False)  # OIDC sub, or Remote-User
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class List(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped[User] = relationship(back_populates="lists")
    tasks: Mapped[list[Task]] = relationship(
        back_populates="list", cascade="all, delete-orphan", order_by="Task.position"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    next_action: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    when_where: Mapped[str | None] = mapped_column(String(512), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    list: Mapped[List] = relationship(back_populates="tasks")


class Focus(Base):
    __tablename__ = "focus"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "task_id", name="uq_focus_user_date_task"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    user: Mapped[User] = relationship(back_populates="focus_items")
    task: Mapped[Task] = relationship()


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    acts_for: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # denormalized owner for fast segregation + storage pathing; a task's
    # owner never changes (tasks don't move between users).
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # "file" | "url"
    # file: server-managed storage; url: the external link (storage_path null)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # path RELATIVE to the files volume root: "<username>/<task_id>/<uuid>-<name>"
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped[Task] = relationship()


class OrgPerson(Base):
    __tablename__ = "org_people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    department_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    site: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    manager_username: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'merged', 'retired')",
            name="ck_skills_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id"), nullable=True
    )

    claims: Mapped[list[SkillClaim]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    aliases: Mapped[list[SkillAlias]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    merged_into: Mapped[Skill | None] = relationship(
        remote_side="Skill.id",
        foreign_keys=[merged_into_id],
    )
    outgoing_edges: Mapped[list[SkillEdge]] = relationship(
        back_populates="src_skill",
        foreign_keys="SkillEdge.src_skill_id",
    )
    incoming_edges: Mapped[list[SkillEdge]] = relationship(
        back_populates="dst_skill",
        foreign_keys="SkillEdge.dst_skill_id",
    )
    teaching_sessions: Mapped[list[TeachingSession]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    usage_events: Mapped[list[SkillUsageEvent]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    decision_traces: Mapped[list[DecisionTrace]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillClaim(Base):
    __tablename__ = "skill_claims"
    __table_args__ = (
        CheckConstraint(
            "subject_kind IN ('person', 'agent')",
            name="ck_skill_claims_subject_kind",
        ),
        CheckConstraint(
            "kind IN ('can_do', 'knows_about', 'owns_process')",
            name="ck_skill_claims_kind",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_skill_claims_confidence",
        ),
        UniqueConstraint(
            "skill_id",
            "subject_kind",
            "subject",
            "kind",
            name="uq_skill_claim_subject",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    skill: Mapped[Skill] = relationship(back_populates="claims")


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        Index("uq_skill_aliases_alias", "alias", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    skill: Mapped[Skill] = relationship(back_populates="aliases")


class SkillEdge(Base):
    __tablename__ = "skill_edges"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('requires', 'generalizes')",
            name="ck_skill_edges_kind",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_skill_edges_confidence",
        ),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name="ck_skill_edges_status",
        ),
        UniqueConstraint(
            "src_skill_id",
            "dst_skill_id",
            "kind",
            name="uq_skill_edge",
        ),
        CheckConstraint(
            "src_skill_id <> dst_skill_id",
            name="ck_skill_edge_no_self",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    dst_skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    src_skill: Mapped[Skill] = relationship(
        back_populates="outgoing_edges",
        foreign_keys=[src_skill_id],
    )
    dst_skill: Mapped[Skill] = relationship(
        back_populates="incoming_edges",
        foreign_keys=[dst_skill_id],
    )


class TeachingSession(Base):
    __tablename__ = "teaching_sessions"
    __table_args__ = (
        Index("ix_teaching_skill", "skill_id"),
        Index("ix_teaching_teacher", "teacher"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    teacher: Mapped[str] = mapped_column(
        ForeignKey("org_people.username"), nullable=False
    )
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    first_clean_run_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    corrections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    skill: Mapped[Skill] = relationship(back_populates="teaching_sessions")


class SkillUsageEvent(Base):
    __tablename__ = "skill_usage_events"
    __table_args__ = (
        CheckConstraint(
            "subject_kind IN ('person', 'agent')",
            name="ck_skill_usage_events_subject_kind",
        ),
        Index("ix_skill_usage_skill", "skill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    source_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")

    skill: Mapped[Skill] = relationship(back_populates="usage_events")


class DecisionTrace(Base):
    __tablename__ = "decision_traces"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('decision', 'boundary')",
            name="ck_decision_traces_kind",
        ),
        CheckConstraint(
            "approval IN ('explicit', 'standing_rule', 'corrected')",
            name="ck_decision_traces_approval",
        ),
        CheckConstraint(
            "outcome IN ('pending', 'ok', 'corrected', 'superseded')",
            name="ck_decision_traces_outcome",
        ),
        Index("ix_traces_skill", "skill_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL only for boundary restatements — a decision without a human anchor
    # is rejected at the API (poisoning defence #1).
    approver: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("decision_traces.id"), nullable=True
    )
    trust: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', situation || ' ' || decision)", persisted=True),
        nullable=True,
    )

    skill: Mapped[Skill] = relationship(back_populates="decision_traces")


class LogicalField(Base):
    """A concept ("contract_number") that procedures reference instead of a letter."""

    __tablename__ = "logical_fields"
    __table_args__ = (
        UniqueConstraint("concept_key", name="uq_logical_fields_concept_key"),
        CheckConstraint(
            "datatype IN ('string', 'number', 'integer', 'boolean', 'date', 'datetime', 'any')",
            name="ck_logical_fields_datatype",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concept_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    datatype: Mapped[str] = mapped_column(Text, nullable=False)
    table_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parse_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    unique_in_sheet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    bindings: Mapped[list[ColumnBinding]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )


class ManagedFile(Base):
    __tablename__ = "managed_files"
    __table_args__ = (
        UniqueConstraint("path", "sheet_name", name="uq_managed_files_path_sheet"),
        CheckConstraint("header_row >= 1", name="ck_managed_files_header_row"),
        CheckConstraint("first_data_row > header_row", name="ck_managed_files_first_data_row"),
        Index("ix_managed_files_owner", "owner_person_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_name: Mapped[str] = mapped_column(Text, nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_data_row: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    owner_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_people.id", ondelete="SET NULL"), nullable=True
    )
    notify_channel: Mapped[str] = mapped_column(Text, nullable=False, default="")
    excel_table_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shadow_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    bindings: Mapped[list[ColumnBinding]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class ColumnBinding(Base):
    __tablename__ = "column_bindings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'auto_rebound', 'pending_review', 'retired')",
            name="ck_column_bindings_status",
        ),
        CheckConstraint("bound_by IN ('human', 'auto')", name="ck_column_bindings_bound_by"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_column_bindings_confidence"
        ),
        CheckConstraint(
            "column_letter ~ '^[A-Z]{1,3}$'", name="ck_column_bindings_column_letter"
        ),
        CheckConstraint(
            "status <> 'active' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL"
            " AND bound_by = 'human')",
            name="ck_column_bindings_active_is_verified",
        ),
        Index(
            "uq_column_bindings_live",
            "file_id",
            "field_id",
            unique=True,
            postgresql_where=text("status <> 'retired'"),
        ),
        Index("ix_column_bindings_file", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("managed_files.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("logical_fields.id", ondelete="CASCADE"), nullable=False
    )
    column_letter: Mapped[str] = mapped_column(Text, nullable=False)
    header_text_exact: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    bound_by: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    file: Mapped[ManagedFile] = relationship(back_populates="bindings")
    field: Mapped[LogicalField] = relationship(back_populates="bindings")
    fingerprints: Mapped[list[ColumnFingerprint]] = relationship(
        back_populates="binding", cascade="all, delete-orphan"
    )


class ColumnFingerprint(Base):
    __tablename__ = "column_fingerprints"
    __table_args__ = (Index("ix_column_fingerprints_binding", "binding_id", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    binding_id: Mapped[int] = mapped_column(
        ForeignKey("column_bindings.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    header_normalized: Mapped[str] = mapped_column(Text, nullable=False, default="")
    header_aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    dtype_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    distinct_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    null_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_regex_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    minhash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sample_values: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    binding: Mapped[ColumnBinding] = relationship(back_populates="fingerprints")


class BindingEvent(Base):
    __tablename__ = "binding_events"
    __table_args__ = (
        CheckConstraint(
            "event IN ('exact_match', 'auto_rebind', 'escalated', 'human_confirmed',"
            " 'write_blocked', 'proposed', 'shadow')",
            name="ck_binding_events_event",
        ),
        Index("ix_binding_events_file", "file_id", "created_at"),
        Index("ix_binding_events_binding", "binding_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    binding_id: Mapped[int | None] = mapped_column(
        ForeignKey("column_bindings.id", ondelete="SET NULL"), nullable=True
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("managed_files.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    old_col: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_col: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    runner_up_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
