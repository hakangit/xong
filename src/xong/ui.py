from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from xong import services
from xong.auth import AuthContext, require_auth
from xong.db import get_db
from xong.schemas import TaskCreate, TaskUpdate

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _calm_due_label(task, today) -> str | None:
    """Calm overdue/due label — never shaming."""
    if not task.due_at:
        return None
    # due_at is aware; compare dates in a simple way via iso date string
    due_date = task.due_at.date() if hasattr(task.due_at, "date") else task.due_at
    # For TaskOut, due_at is datetime
    if hasattr(task.due_at, "astimezone"):
        # We don't have user tz here easily; use date part only if naive-ish
        try:
            due_date = task.due_at.date()
        except Exception:
            return None
    if due_date < today:
        days = (today - due_date).days
        if days == 1:
            return "từ hôm qua"
        return f"từ {days} ngày trước"
    if due_date == today:
        return "hôm nay"
    return None


templates.env.globals["calm_due_label"] = _calm_due_label


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    data = services.get_today(db, ctx.user)
    lists = services.list_lists(db, ctx.user)
    return templates.TemplateResponse(
        request,
        "today.html",
        {
            "user": ctx.user,
            "data": data,
            "lists": lists,
            "page": "today",
        },
    )


@router.get("/lists/{list_id}", response_class=HTMLResponse)
def list_view(
    list_id: int,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    lst = services.list_owned(db, ctx.user, list_id)
    tasks = services.list_tasks(db, ctx.user, list_id=list_id, include_completed=False)
    task_outs = [services.task_to_out(t) for t in tasks]
    lists = services.list_lists(db, ctx.user)
    focus = services.get_focus(db, ctx.user)
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "user": ctx.user,
            "list": lst,
            "tasks": task_outs,
            "lists": lists,
            "focus_ids": set(focus.task_ids),
            "page": "list",
        },
    )


@router.get("/recap", response_class=HTMLResponse)
def recap_view(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    recap = services.weekly_recap(db, ctx.user)
    lists = services.list_lists(db, ctx.user)
    return templates.TemplateResponse(
        request,
        "recap.html",
        {
            "user": ctx.user,
            "recap": recap,
            "lists": lists,
            "page": "recap",
        },
    )


@router.post("/ui/tasks", response_class=HTMLResponse)
def ui_add_task(
    request: Request,
    title: str = Form(...),
    list_id: int | None = Form(default=None),
    next_action: str | None = Form(default=None),
    due_at: str | None = Form(default=None),
    when_where: str | None = Form(default=None),
    redirect_to: str = Form(default="/"),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    due = None
    if due_at and due_at.strip():
        # Accept date or datetime-local
        raw = due_at.strip()
        try:
            if "T" in raw:
                due = __import__("datetime").datetime.fromisoformat(raw)
            else:
                from datetime import datetime
                from zoneinfo import ZoneInfo

                d = datetime.strptime(raw, "%Y-%m-%d").date()
                tz = ZoneInfo(ctx.user.tz)
                due = datetime.combine(d, datetime.min.time().replace(hour=17), tzinfo=tz)
        except ValueError:
            due = None

    body = TaskCreate(
        title=title,
        list_id=list_id,
        next_action=next_action or None,
        due_at=due,
        when_where=when_where or None,
    )
    services.create_task(db, ctx.user, ctx.actor, body)

    if request.headers.get("HX-Request"):
        return RedirectResponse(redirect_to, status_code=303)
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/ui/tasks/{task_id}/complete", response_class=HTMLResponse)
def ui_complete(
    task_id: int,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    services.complete_task(db, ctx.user, ctx.actor, task_id)
    # Empty body — client JS handles animation then htmx swaps out the row
    return HTMLResponse("", status_code=200)


@router.post("/ui/tasks/{task_id}/focus-toggle", response_class=HTMLResponse)
def ui_focus_toggle(
    task_id: int,
    request: Request,
    redirect_to: str = Form(default="/"),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    focus = services.get_focus(db, ctx.user)
    ids = list(focus.task_ids)
    if task_id in ids:
        ids = [i for i in ids if i != task_id]
    else:
        if len(ids) >= 3:
            # Silently keep max 3 — do not shame
            return RedirectResponse(redirect_to, status_code=303)
        ids.append(task_id)
    services.set_focus(db, ctx.user, ctx.actor, ids)
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/ui/tasks/{task_id}/next-action", response_class=HTMLResponse)
def ui_next_action(
    task_id: int,
    next_action: str = Form(...),
    redirect_to: str = Form(default="/"),
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    services.update_task(
        db,
        ctx.user,
        ctx.actor,
        task_id,
        TaskUpdate(next_action=next_action.strip() or None),
    )
    return RedirectResponse(redirect_to, status_code=303)
