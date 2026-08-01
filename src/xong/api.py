from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from xong import services
from xong.auth import AuthContext, require_auth
from xong.db import get_db
from xong.schemas import (
    AuthContextOut,
    EventOut,
    FocusOut,
    FocusSet,
    ListCreate,
    ListOut,
    ListUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TodayOut,
    UserOut,
    WeeklyRecapOut,
)

router = APIRouter(prefix="/api/v1")


@router.get("/me", response_model=UserOut)
def me(ctx: AuthContext = Depends(require_auth)):
    return ctx.user


@router.get("/auth/context", response_model=AuthContextOut)
def auth_context(ctx: AuthContext = Depends(require_auth)):
    return AuthContextOut(
        actor=ctx.actor,
        subject=ctx.user.username,
        is_agent=ctx.is_agent,
    )


@router.get("/lists", response_model=list[ListOut])
def get_lists(
    include_archived: bool = False,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.list_lists(db, ctx.user, include_archived=include_archived)


@router.post("/lists", response_model=ListOut, status_code=201)
def post_list(
    body: ListCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.create_list(db, ctx.user, body)


@router.get("/lists/{list_id}", response_model=ListOut)
def get_list(
    list_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.list_owned(db, ctx.user, list_id)


@router.patch("/lists/{list_id}", response_model=ListOut)
def patch_list(
    list_id: int,
    body: ListUpdate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.update_list(db, ctx.user, list_id, body)


@router.delete("/lists/{list_id}", status_code=204)
def remove_list(
    list_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    services.delete_list(db, ctx.user, list_id)


@router.get("/tasks", response_model=list[TaskOut])
def get_tasks(
    list_id: int | None = None,
    include_completed: bool = False,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    tasks = services.list_tasks(
        db, ctx.user, list_id=list_id, include_completed=include_completed
    )
    return [services.task_to_out(t) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def post_task(
    body: TaskCreate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    task = services.create_task(db, ctx.user, ctx.actor, body)
    return services.task_to_out(task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.task_to_out(services.task_owned(db, ctx.user, task_id))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: int,
    body: TaskUpdate,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    task = services.update_task(db, ctx.user, ctx.actor, task_id, body)
    return services.task_to_out(task)


@router.delete("/tasks/{task_id}", status_code=204)
def remove_task(
    task_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    services.delete_task(db, ctx.user, ctx.actor, task_id)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    task = services.complete_task(db, ctx.user, ctx.actor, task_id)
    return services.task_to_out(task)


@router.post("/tasks/{task_id}/uncomplete", response_model=TaskOut)
def uncomplete_task(
    task_id: int,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    task = services.uncomplete_task(db, ctx.user, ctx.actor, task_id)
    return services.task_to_out(task)


@router.get("/today", response_model=TodayOut)
def today(
    user: str | None = Query(default=None, description="Ignored; auth determines user"),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    # Spec says GET /today?user= — auth already scopes to the acting user.
    _ = user
    return services.get_today(db, ctx.user)


@router.post("/focus", response_model=FocusOut)
def post_focus(
    body: FocusSet,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.set_focus(db, ctx.user, ctx.actor, body.task_ids)


@router.get("/focus", response_model=FocusOut)
def get_focus(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.get_focus(db, ctx.user)


@router.get("/recap/weekly", response_model=WeeklyRecapOut)
def recap_weekly(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.weekly_recap(db, ctx.user)


@router.get("/events", response_model=list[EventOut])
def events(
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return services.list_events(db, ctx.user, since=since, limit=limit)
