"""Excel semantic layer: logical fields, managed files, column bindings.

Procedures reference logical fields ("contract_number"), never column letters.
This API is the registry the resolver library (hermes-fleet overlay/lib/sheetmap)
reads its bundle from and writes its binding events back to.

Authority rules, in one place because everything else depends on them:

* Creating/editing logical fields and managed files is HUMAN-ONLY.
* An agent may POST binding events and teach-time proposals. A proposal lands as
  status='pending_review' — never active, never write-eligible.
* Promoting a binding to 'active' (the only status writes may go through) is
  HUMAN-ONLY, and when the file has an owner, only that owner.
* Agents may record an auto-rebind (status='auto_rebound'). That status is
  read-only by construction: the resolver refuses writes through it and the
  DB check constraint refuses 'active' without a human verifier.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from xong import services, storage
from xong.auth import AuthContext, require_auth
from xong.db import get_db
from xong.models import (
    BindingEvent,
    ColumnBinding,
    ColumnFingerprint,
    LogicalField,
    ManagedFile,
    OrgPerson,
)
from xong.schemas import AttachmentOut, LinkCreate

router = APIRouter(prefix="/api/v1/files")
attachments_router = APIRouter(prefix="/api/v1")

CONCEPT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
COLUMN_LETTER_RE = re.compile(r"^[A-Z]{1,3}$")

DATATYPES = ("string", "number", "integer", "boolean", "date", "datetime", "any")

# Resolver knobs. Shipped in the resolve bundle so the thresholds are tuned from
# shadow data by changing this file (and redeploying xong) rather than by
# redeploying every agent that embeds the library.
RESOLVER_CONFIG = {
    "auto_rebind_min_score": 0.85,
    "auto_rebind_min_margin": 0.15,
    "weights": {"header": 0.4, "dtype": 0.2, "minhash": 0.3, "position": 0.1},
    "sample_rows": 200,
    "minhash_num_perm": 128,
}


@attachments_router.get(
    "/tasks/{task_id}/attachments", response_model=list[AttachmentOut]
)
def get_attachments(
    task_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.list_attachments(db, ctx.user, task_id)


@attachments_router.post(
    "/tasks/{task_id}/attachments/link",
    response_model=AttachmentOut,
    status_code=201,
)
def post_attachment_link(
    task_id: int,
    body: LinkCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.add_link(db, ctx.user, ctx.actor, task_id, body.url, body.filename)


@attachments_router.post(
    "/tasks/{task_id}/attachments/file",
    response_model=AttachmentOut,
    status_code=201,
)
def post_attachment_file(
    task_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.add_file(db, ctx.user, ctx.actor, task_id, file)


@attachments_router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    att = services.attachment_owned(db, ctx.user, attachment_id)
    if att.kind != "file" or not att.storage_path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Not a file attachment")
    headers = {"Content-Disposition": f'attachment; filename="{att.filename or "file"}"'}
    return StreamingResponse(
        storage.open_read(att.storage_path),
        media_type=att.content_type or "application/octet-stream",
        headers=headers,
    )


@attachments_router.delete("/attachments/{attachment_id}", status_code=204)
def remove_attachment(
    attachment_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    services.delete_attachment(db, ctx.user, ctx.actor, attachment_id)


class LogicalFieldIn(BaseModel):
    concept_key: str = Field(min_length=1, max_length=128)
    description: str = ""
    datatype: Literal["string", "number", "integer", "boolean", "date", "datetime", "any"] = (
        "string"
    )
    table_schema: dict = Field(default_factory=dict)
    parse_rule: str | None = None
    unique_in_sheet: bool = True


class LogicalFieldPatch(BaseModel):
    description: str | None = None
    datatype: (
        Literal["string", "number", "integer", "boolean", "date", "datetime", "any"] | None
    ) = None
    table_schema: dict | None = None
    parse_rule: str | None = None
    unique_in_sheet: bool | None = None


class ManagedFileIn(BaseModel):
    path: str = Field(min_length=1)
    sheet_name: str = Field(min_length=1)
    header_row: int = Field(default=1, ge=1)
    first_data_row: int = Field(default=2, ge=2)
    owner_username: str | None = None
    notify_channel: str = ""
    excel_table_name: str | None = None
    shadow_mode: bool = True


class ManagedFilePatch(BaseModel):
    header_row: int | None = Field(default=None, ge=1)
    first_data_row: int | None = Field(default=None, ge=2)
    owner_username: str | None = None
    notify_channel: str | None = None
    excel_table_name: str | None = None
    shadow_mode: bool | None = None


class FingerprintIn(BaseModel):
    header_normalized: str = ""
    header_aliases: list[str] = Field(default_factory=list)
    dtype_profile: dict = Field(default_factory=dict)
    distinct_ratio: float | None = None
    null_ratio: float | None = None
    value_regex_profile: dict = Field(default_factory=dict)
    minhash_hex: str | None = None
    sample_values: list[str] = Field(default_factory=list)


class BindingIn(BaseModel):
    """Human-verified binding. Only a human can create one of these."""

    concept_key: str = Field(min_length=1)
    column_letter: str = Field(min_length=1, max_length=3)
    header_text_exact: str = ""
    note: str = ""
    fingerprint: FingerprintIn | None = None


class ProposalIn(BaseModel):
    """Teach-time proposal from an agent. Lands as pending_review, never active."""

    concept_key: str = Field(min_length=1)
    column_letter: str = Field(min_length=1, max_length=3)
    header_text_exact: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    note: str = ""
    fingerprint: FingerprintIn | None = None


class BindingEventIn(BaseModel):
    binding_id: int | None = None
    concept_key: str | None = None
    event: Literal[
        "exact_match",
        "auto_rebind",
        "escalated",
        "human_confirmed",
        "write_blocked",
        "proposed",
        "shadow",
    ]
    old_col: str | None = None
    new_col: str | None = None
    score: float | None = None
    runner_up_score: float | None = None
    shadow: bool = False
    detail: dict = Field(default_factory=dict)


class ConfirmIn(BaseModel):
    """Owner answering the escalation: 'yes, the field now lives in column X'."""

    column_letter: str = Field(min_length=1, max_length=3)
    header_text_exact: str = ""
    note: str = ""
    fingerprint: FingerprintIn | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_human(ctx: AuthContext, action: str) -> None:
    if ctx.is_agent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"{action} is human-only; agents may only propose (POST /proposals)",
        )


def _require_owner(ctx: AuthContext, file: ManagedFile, db: Session, action: str) -> None:
    """Human, and — when the file has an owner — that owner."""
    _require_human(ctx, action)
    if file.owner_person_id is None:
        return
    owner = db.get(OrgPerson, file.owner_person_id)
    if owner is None:
        return
    if ctx.actor.lower() != owner.username.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"{action} is reserved for the file owner ({owner.username})",
        )


def _field_json(field: LogicalField) -> dict:
    return {
        "id": field.id,
        "concept_key": field.concept_key,
        "description": field.description,
        "datatype": field.datatype,
        "table_schema": field.table_schema,
        "parse_rule": field.parse_rule,
        "unique_in_sheet": field.unique_in_sheet,
        "created_by": field.created_by,
        "created_at": field.created_at,
    }


def _file_json(file: ManagedFile, owner_username: str | None = None) -> dict:
    return {
        "id": file.id,
        "path": file.path,
        "sheet_name": file.sheet_name,
        "header_row": file.header_row,
        "first_data_row": file.first_data_row,
        "owner_person_id": file.owner_person_id,
        "owner_username": owner_username,
        "notify_channel": file.notify_channel,
        "excel_table_name": file.excel_table_name,
        "shadow_mode": file.shadow_mode,
        "created_by": file.created_by,
        "created_at": file.created_at,
    }


def _binding_json(binding: ColumnBinding, concept_key: str | None = None) -> dict:
    return {
        "id": binding.id,
        "file_id": binding.file_id,
        "field_id": binding.field_id,
        "concept_key": concept_key,
        "column_letter": binding.column_letter,
        "header_text_exact": binding.header_text_exact,
        "status": binding.status,
        "confidence": float(binding.confidence),
        "bound_by": binding.bound_by,
        "verified_at": binding.verified_at,
        "verified_by": binding.verified_by,
        "note": binding.note,
        # The single fact the library must not get wrong.
        "write_eligible": binding.status == "active" and binding.bound_by == "human",
    }


def _fingerprint_json(fp: ColumnFingerprint) -> dict:
    return {
        "id": fp.id,
        "binding_id": fp.binding_id,
        "captured_at": fp.captured_at,
        "header_normalized": fp.header_normalized,
        "header_aliases": fp.header_aliases,
        "dtype_profile": fp.dtype_profile,
        "distinct_ratio": fp.distinct_ratio,
        "null_ratio": fp.null_ratio,
        "value_regex_profile": fp.value_regex_profile,
        "minhash_hex": fp.minhash.hex() if fp.minhash else None,
        "sample_values": fp.sample_values,
    }


def _event_json(event: BindingEvent) -> dict:
    return {
        "id": event.id,
        "binding_id": event.binding_id,
        "file_id": event.file_id,
        "event": event.event,
        "old_col": event.old_col,
        "new_col": event.new_col,
        "score": event.score,
        "runner_up_score": event.runner_up_score,
        "shadow": event.shadow,
        "actor": event.actor,
        "detail": event.detail,
        "created_at": event.created_at,
    }


def _get_file(db: Session, file_id: int) -> ManagedFile:
    file = db.get(ManagedFile, file_id)
    if file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Managed file not found")
    return file


def _get_field(db: Session, concept_key: str) -> LogicalField:
    field = db.scalar(select(LogicalField).where(LogicalField.concept_key == concept_key))
    if field is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Logical field {concept_key!r} not found"
        )
    return field


def _owner_username(db: Session, file: ManagedFile) -> str | None:
    if file.owner_person_id is None:
        return None
    owner = db.get(OrgPerson, file.owner_person_id)
    return owner.username if owner else None


_WS_RE = re.compile(r"\s+")


def _norm_header(value: str) -> str:
    """Match the sheetmap client's norm_header: NFC, collapse whitespace,
    strip, casefold. Kept in sync deliberately — a divergence would let a
    header that the client considers matching be rejected here (or vice versa).
    """
    import unicodedata

    text = unicodedata.normalize("NFC", str(value or ""))
    return _WS_RE.sub(" ", text.replace("\n", " ")).strip().casefold()


def _normalize_letter(letter: str) -> str:
    value = letter.strip().upper()
    if not COLUMN_LETTER_RE.match(value):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"column_letter must be A..ZZZ, got {letter!r}",
        )
    return value


def _store_fingerprint(db: Session, binding: ColumnBinding, payload: FingerprintIn) -> None:
    minhash: bytes | None = None
    if payload.minhash_hex:
        try:
            minhash = bytes.fromhex(payload.minhash_hex)
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="minhash_hex is not valid hex"
            ) from None
    db.add(
        ColumnFingerprint(
            binding_id=binding.id,
            header_normalized=payload.header_normalized,
            header_aliases=payload.header_aliases,
            dtype_profile=payload.dtype_profile,
            distinct_ratio=payload.distinct_ratio,
            null_ratio=payload.null_ratio,
            value_regex_profile=payload.value_regex_profile,
            minhash=minhash,
            sample_values=payload.sample_values,
        )
    )


def _retire_live_binding(db: Session, file_id: int, field_id: int) -> ColumnBinding | None:
    """Retire whatever currently occupies (file, field) so the new row is unique."""
    existing = db.scalar(
        select(ColumnBinding).where(
            ColumnBinding.file_id == file_id,
            ColumnBinding.field_id == field_id,
            ColumnBinding.status != "retired",
        )
    )
    if existing is not None:
        existing.status = "retired"
        existing.updated_at = _now()
        db.flush()
    return existing


# --------------------------------------------------------------------------
# logical fields
# --------------------------------------------------------------------------


@router.get("/fields")
def list_fields(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    fields = db.scalars(select(LogicalField).order_by(LogicalField.concept_key))
    return [_field_json(f) for f in fields]


@router.post("/fields", status_code=status.HTTP_201_CREATED)
def create_field(
    payload: LogicalFieldIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _require_human(ctx, "Creating a logical field")
    key = payload.concept_key.strip().lower()
    if not CONCEPT_KEY_RE.match(key):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="concept_key must be snake_case: ^[a-z][a-z0-9_]*$",
        )
    field = LogicalField(
        concept_key=key,
        description=payload.description,
        datatype=payload.datatype,
        table_schema=payload.table_schema,
        parse_rule=payload.parse_rule,
        unique_in_sheet=payload.unique_in_sheet,
        created_by=ctx.actor,
    )
    db.add(field)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Logical field {key!r} already exists"
        ) from None
    db.refresh(field)
    return _field_json(field)


@router.get("/fields/{concept_key}")
def get_field(
    concept_key: str,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    return _field_json(_get_field(db, concept_key))


@router.patch("/fields/{concept_key}")
def patch_field(
    concept_key: str,
    payload: LogicalFieldPatch,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _require_human(ctx, "Editing a logical field")
    field = _get_field(db, concept_key)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(field, key, value)
    field.updated_at = _now()
    db.commit()
    db.refresh(field)
    return _field_json(field)


# --------------------------------------------------------------------------
# managed files
# --------------------------------------------------------------------------


@router.get("/managed")
def list_managed_files(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    files = db.scalars(select(ManagedFile).order_by(ManagedFile.path, ManagedFile.sheet_name))
    return [_file_json(f, _owner_username(db, f)) for f in files]


@router.post("/managed", status_code=status.HTTP_201_CREATED)
def create_managed_file(
    payload: ManagedFileIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _require_human(ctx, "Registering a managed file")
    if payload.first_data_row <= payload.header_row:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="first_data_row must be greater than header_row",
        )
    owner_id = None
    if payload.owner_username:
        owner = db.scalar(
            select(OrgPerson).where(OrgPerson.username == payload.owner_username.lower())
        )
        if owner is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"owner_username {payload.owner_username!r} not in org_people",
            )
        owner_id = owner.id
    file = ManagedFile(
        path=payload.path,
        sheet_name=payload.sheet_name,
        header_row=payload.header_row,
        first_data_row=payload.first_data_row,
        owner_person_id=owner_id,
        notify_channel=payload.notify_channel,
        excel_table_name=payload.excel_table_name,
        shadow_mode=payload.shadow_mode,
        created_by=ctx.actor,
    )
    db.add(file)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="That path + sheet is already registered",
        ) from None
    db.refresh(file)
    return _file_json(file, _owner_username(db, file))


@router.get("/managed/{file_id}")
def get_managed_file(
    file_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    file = _get_file(db, file_id)
    return _file_json(file, _owner_username(db, file))


@router.patch("/managed/{file_id}")
def patch_managed_file(
    file_id: int,
    payload: ManagedFilePatch,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _require_human(ctx, "Editing a managed file")
    file = _get_file(db, file_id)
    data = payload.model_dump(exclude_unset=True)
    if "owner_username" in data:
        username = data.pop("owner_username")
        if username is None:
            file.owner_person_id = None
        else:
            owner = db.scalar(select(OrgPerson).where(OrgPerson.username == username.lower()))
            if owner is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"owner_username {username!r} not in org_people",
                )
            file.owner_person_id = owner.id
    for key, value in data.items():
        setattr(file, key, value)
    if file.first_data_row <= file.header_row:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="first_data_row must be greater than header_row",
        )
    file.updated_at = _now()
    db.commit()
    db.refresh(file)
    return _file_json(file, _owner_username(db, file))


# --------------------------------------------------------------------------
# resolve bundle — what the resolver library reads on every file open
# --------------------------------------------------------------------------


@router.get("/managed/{file_id}/bundle")
def get_resolve_bundle(
    file_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    file = _get_file(db, file_id)
    rows = db.execute(
        select(ColumnBinding, LogicalField)
        .join(LogicalField, LogicalField.id == ColumnBinding.field_id)
        .where(ColumnBinding.file_id == file.id, ColumnBinding.status != "retired")
        .order_by(LogicalField.concept_key)
    ).all()

    bindings = []
    for binding, field in rows:
        latest = db.scalar(
            select(ColumnFingerprint)
            .where(ColumnFingerprint.binding_id == binding.id)
            .order_by(ColumnFingerprint.captured_at.desc(), ColumnFingerprint.id.desc())
            .limit(1)
        )
        entry = _binding_json(binding, field.concept_key)
        entry["field"] = _field_json(field)
        entry["fingerprint"] = _fingerprint_json(latest) if latest else None
        bindings.append(entry)

    return {
        "file": _file_json(file, _owner_username(db, file)),
        "config": RESOLVER_CONFIG,
        "bindings": bindings,
    }


# --------------------------------------------------------------------------
# bindings
# --------------------------------------------------------------------------


@router.post("/managed/{file_id}/bindings", status_code=status.HTTP_201_CREATED)
def create_binding(
    file_id: int,
    payload: BindingIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Human-verified binding — the only kind writes may ever go through."""
    file = _get_file(db, file_id)
    # Setup is human-only but not owner-only: whoever teaches the procedure
    # registers the map. Answering a live escalation IS owner-only — see
    # /bindings/{id}/confirm — because that is the decision the owner alone
    # can actually make about their own spreadsheet.
    _require_human(ctx, "Creating a verified binding")
    field = _get_field(db, payload.concept_key)
    letter = _normalize_letter(payload.column_letter)
    _retire_live_binding(db, file.id, field.id)
    binding = ColumnBinding(
        file_id=file.id,
        field_id=field.id,
        column_letter=letter,
        header_text_exact=payload.header_text_exact,
        status="active",
        confidence=1.0,
        bound_by="human",
        verified_at=_now(),
        verified_by=ctx.actor,
        note=payload.note,
    )
    db.add(binding)
    db.flush()
    if payload.fingerprint is not None:
        _store_fingerprint(db, binding, payload.fingerprint)
    db.add(
        BindingEvent(
            binding_id=binding.id,
            file_id=file.id,
            event="human_confirmed",
            new_col=letter,
            actor=ctx.actor,
            detail={"reason": "binding created by human"},
        )
    )
    db.commit()
    db.refresh(binding)
    return _binding_json(binding, field.concept_key)


@router.post("/managed/{file_id}/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(
    file_id: int,
    payload: ProposalIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Teach-time proposal. Agents allowed; result is pending_review, never active.

    The LLM-side prompting that produces these lives in the agent, not here —
    this endpoint is deliberately a dumb sink so the model never touches an
    active binding.
    """
    file = _get_file(db, file_id)
    field = _get_field(db, payload.concept_key)
    letter = _normalize_letter(payload.column_letter)
    existing = db.scalar(
        select(ColumnBinding).where(
            ColumnBinding.file_id == file.id,
            ColumnBinding.field_id == field.id,
            ColumnBinding.status != "retired",
        )
    )
    if existing is not None and existing.status == "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"{payload.concept_key!r} already has a human-verified binding "
                f"({existing.column_letter}); a proposal cannot displace it"
            ),
        )
    _retire_live_binding(db, file.id, field.id)
    binding = ColumnBinding(
        file_id=file.id,
        field_id=field.id,
        column_letter=letter,
        header_text_exact=payload.header_text_exact,
        status="pending_review",
        confidence=payload.confidence,
        bound_by="auto" if ctx.is_agent else "human",
        note=payload.note,
    )
    db.add(binding)
    db.flush()
    if payload.fingerprint is not None:
        _store_fingerprint(db, binding, payload.fingerprint)
    db.add(
        BindingEvent(
            binding_id=binding.id,
            file_id=file.id,
            event="proposed",
            new_col=letter,
            score=payload.confidence,
            actor=ctx.actor,
            detail={"note": payload.note},
        )
    )
    db.commit()
    db.refresh(binding)
    return _binding_json(binding, field.concept_key)


@router.post("/bindings/{binding_id}/confirm")
def confirm_binding(
    binding_id: int,
    payload: ConfirmIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """The owner answering an escalation. Promotes to active + human-verified."""
    binding = db.get(ColumnBinding, binding_id)
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Binding not found")
    file = _get_file(db, binding.file_id)
    _require_owner(ctx, file, db, "Confirming a binding")
    old_col = binding.column_letter
    letter = _normalize_letter(payload.column_letter)
    binding.column_letter = letter
    if payload.header_text_exact:
        binding.header_text_exact = payload.header_text_exact
    binding.status = "active"
    binding.confidence = 1.0
    binding.bound_by = "human"
    binding.verified_at = _now()
    binding.verified_by = ctx.actor
    if payload.note:
        binding.note = payload.note
    binding.updated_at = _now()
    if payload.fingerprint is not None:
        _store_fingerprint(db, binding, payload.fingerprint)
    db.add(
        BindingEvent(
            binding_id=binding.id,
            file_id=file.id,
            event="human_confirmed",
            old_col=old_col,
            new_col=letter,
            actor=ctx.actor,
            detail={"note": payload.note},
        )
    )
    db.commit()
    db.refresh(binding)
    field = db.get(LogicalField, binding.field_id)
    return _binding_json(binding, field.concept_key if field else None)


@router.post("/bindings/{binding_id}/fingerprints", status_code=status.HTTP_201_CREATED)
def add_fingerprint(
    binding_id: int,
    payload: FingerprintIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Refresh the stored fingerprint after a successful resolve. Agents allowed.

    Defence-in-depth: the resolver's write gate anchors on header_text_exact,
    not on this fingerprint, so a poisoned fingerprint can no longer grant
    writes. Even so, an agent may not push a fingerprint whose header disagrees
    with the human-recorded header on a human-verified binding — that only ever
    reflects a mis-resolve, and letting it through corrupts the read signal too.
    """
    binding = db.get(ColumnBinding, binding_id)
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Binding not found")
    if ctx.is_agent and binding.bound_by == "human" and binding.header_text_exact:
        posted = _norm_header(payload.header_normalized or "")
        recorded = _norm_header(binding.header_text_exact)
        if posted and posted != recorded:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "Fingerprint header does not match the human-verified "
                    "binding; a rebind must go through the escalation flow"
                ),
            )
    _store_fingerprint(db, binding, payload)
    db.commit()
    latest = db.scalar(
        select(ColumnFingerprint)
        .where(ColumnFingerprint.binding_id == binding.id)
        .order_by(ColumnFingerprint.id.desc())
        .limit(1)
    )
    return _fingerprint_json(latest)


# --------------------------------------------------------------------------
# binding events — the shadow-run ledger
# --------------------------------------------------------------------------


@router.post("/managed/{file_id}/events", status_code=status.HTTP_201_CREATED)
def create_event(
    file_id: int,
    payload: BindingEventIn,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Agents post here. An auto_rebind event also moves the binding's column.

    It never makes the binding write-eligible: status becomes 'auto_rebound',
    which the check constraint forbids from carrying a human verifier.
    """
    file = _get_file(db, file_id)
    binding = None
    if payload.binding_id is not None:
        binding = db.get(ColumnBinding, payload.binding_id)
        if binding is None or binding.file_id != file.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Binding not found on this file"
            )
    elif payload.concept_key:
        field = _get_field(db, payload.concept_key)
        binding = db.scalar(
            select(ColumnBinding).where(
                ColumnBinding.file_id == file.id,
                ColumnBinding.field_id == field.id,
                ColumnBinding.status != "retired",
            )
        )

    new_col = _normalize_letter(payload.new_col) if payload.new_col else None
    if payload.event == "human_confirmed" and ctx.is_agent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="An agent may not record a human_confirmed event",
        )
    if payload.event == "auto_rebind" and binding is not None and not payload.shadow:
        # A real auto-rebind cleared the resolver's threshold; an event that
        # claims one must carry a score that actually meets it, or a single
        # agent call could discard a human verification and repoint reads at an
        # arbitrary column. Confidence stays defensible.
        min_score = RESOLVER_CONFIG["auto_rebind_min_score"]
        min_margin = RESOLVER_CONFIG["auto_rebind_min_margin"]
        score = payload.score if payload.score is not None else 0.0
        runner_up = payload.runner_up_score if payload.runner_up_score is not None else 0.0
        if score < min_score or (score - runner_up) < min_margin:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"auto_rebind requires score >= {min_score} and margin "
                    f">= {min_margin}; got score={score}, runner_up={runner_up}"
                ),
            )
        if binding.status == "active" and binding.bound_by == "human":
            # Losing the human verification is the point: the column moved, so
            # the human's confirmation no longer applies to it.
            binding.verified_at = None
            binding.verified_by = None
        binding.status = "auto_rebound"
        binding.bound_by = "auto"
        binding.confidence = payload.score if payload.score is not None else binding.confidence
        if new_col:
            binding.column_letter = new_col
        binding.updated_at = _now()

    event = BindingEvent(
        binding_id=binding.id if binding is not None else None,
        file_id=file.id,
        event=payload.event,
        old_col=payload.old_col,
        new_col=new_col,
        score=payload.score,
        runner_up_score=payload.runner_up_score,
        shadow=payload.shadow,
        actor=ctx.actor,
        detail=payload.detail,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_json(event)


@router.get("/managed/{file_id}/events")
def list_events(
    file_id: int,
    limit: int = 200,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _ = ctx
    file = _get_file(db, file_id)
    events = db.scalars(
        select(BindingEvent)
        .where(BindingEvent.file_id == file.id)
        .order_by(BindingEvent.created_at.desc(), BindingEvent.id.desc())
        .limit(max(1, min(limit, 1000)))
    )
    return [_event_json(e) for e in events]
