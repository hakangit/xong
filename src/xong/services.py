from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from xong import storage
from xong.config import (
    ALLOWED_UPLOAD_TYPES,
    FOCUS_MAX,
    MAX_UPLOAD_BYTES,
    get_plugins,
)
from xong.heuristics import looks_vague
from xong.models import Attachment, Event, Focus, List, Skill, Task, TeachingSession, User
from xong.schemas import (
    DayWins,
    FocusOut,
    ListCreate,
    ListOut,
    ListUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TeachingWin,
    TodayOut,
    WeeklyRecapOut,
)


def user_today(user: User) -> date:
    try:
        tz = ZoneInfo(user.tz)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def user_now(user: User) -> datetime:
    try:
        tz = ZoneInfo(user.tz)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


def log_event(
    db: Session,
    *,
    user_id: int,
    event_type: str,
    actor: str,
    payload: dict | None = None,
) -> Event:
    ev = Event(
        user_id=user_id,
        event_type=event_type,
        actor=actor,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(ev)
    return ev


def task_to_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        list_id=task.list_id,
        title=task.title,
        next_action=task.next_action,
        notes=task.notes,
        due_at=task.due_at,
        when_where=task.when_where,
        position=task.position,
        created_by=task.created_by,
        completed_at=task.completed_at,
        created_at=task.created_at,
        looks_vague=looks_vague(task.title, task.next_action),
    )


def get_default_list(db: Session, user: User) -> List:
    lst = (
        db.query(List)
        .filter(List.owner_id == user.id, List.archived.is_(False))
        .order_by(List.position, List.id)
        .first()
    )
    if lst is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No default list")
    return lst


def list_owned(db: Session, user: User, list_id: int) -> List:
    lst = db.query(List).filter(List.id == list_id, List.owner_id == user.id).one_or_none()
    if lst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="List not found")
    return lst


def task_owned(db: Session, user: User, task_id: int) -> Task:
    task = (
        db.query(Task)
        .join(List, Task.list_id == List.id)
        .filter(Task.id == task_id, List.owner_id == user.id)
        .one_or_none()
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def create_list(db: Session, user: User, body: ListCreate) -> List:
    pos = body.position
    if pos is None:
        max_pos = (
            db.query(func.coalesce(func.max(List.position), -1))
            .filter(List.owner_id == user.id)
            .scalar()
        )
        pos = max_pos + 1
    lst = List(owner_id=user.id, name=body.name, position=pos, archived=False)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return lst


def update_list(db: Session, user: User, list_id: int, body: ListUpdate) -> List:
    lst = list_owned(db, user, list_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(lst, k, v)
    db.commit()
    db.refresh(lst)
    return lst


def delete_list(db: Session, user: User, list_id: int) -> None:
    lst = list_owned(db, user, list_id)
    # Keep at least one non-archived list
    others = (
        db.query(List)
        .filter(List.owner_id == user.id, List.id != list_id, List.archived.is_(False))
        .count()
    )
    if others == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only active list",
        )
    db.delete(lst)
    db.commit()


def list_lists(db: Session, user: User, *, include_archived: bool = False) -> list[List]:
    q = db.query(List).filter(List.owner_id == user.id)
    if not include_archived:
        q = q.filter(List.archived.is_(False))
    return q.order_by(List.position, List.id).all()


def create_task(db: Session, user: User, actor: str, body: TaskCreate) -> Task:
    list_id = body.list_id
    if list_id is None:
        lst = get_default_list(db, user)
        list_id = lst.id
    else:
        list_owned(db, user, list_id)

    # New tasks go to the top (Wunderlist style)
    if body.position is None:
        min_pos = (
            db.query(func.coalesce(func.min(Task.position), 1))
            .filter(Task.list_id == list_id)
            .scalar()
        )
        position = min_pos - 1
    else:
        position = body.position

    task = Task(
        list_id=list_id,
        title=body.title.strip(),
        next_action=body.next_action,
        notes=body.notes,
        due_at=body.due_at,
        when_where=body.when_where,
        position=position,
        created_by=actor,
    )
    db.add(task)
    db.flush()
    log_event(
        db,
        user_id=user.id,
        event_type="task_created",
        actor=actor,
        payload={"task_id": task.id, "title": task.title},
    )
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, user: User, actor: str, task_id: int, body: TaskUpdate) -> Task:
    task = task_owned(db, user, task_id)
    data = body.model_dump(exclude_unset=True)
    if "list_id" in data and data["list_id"] is not None:
        list_owned(db, user, data["list_id"])
    if "title" in data and data["title"] is not None:
        data["title"] = data["title"].strip()
    for k, v in data.items():
        setattr(task, k, v)
    log_event(
        db,
        user_id=user.id,
        event_type="task_updated",
        actor=actor,
        payload={"task_id": task.id},
    )
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user: User, actor: str, task_id: int) -> None:
    task = task_owned(db, user, task_id)
    log_event(
        db,
        user_id=user.id,
        event_type="task_deleted",
        actor=actor,
        payload={"task_id": task.id, "title": task.title},
    )
    db.delete(task)  # cascades attachment rows
    db.commit()
    if "files" in get_plugins():
        storage.delete_task_dir(user.username, task_id)


def complete_task(db: Session, user: User, actor: str, task_id: int) -> Task:
    task = task_owned(db, user, task_id)
    if task.completed_at is None:
        task.completed_at = datetime.now(timezone.utc)
        log_event(
            db,
            user_id=user.id,
            event_type="task_completed",
            actor=actor,
            payload={"task_id": task.id, "title": task.title},
        )
        db.commit()
        db.refresh(task)
    return task


def uncomplete_task(db: Session, user: User, actor: str, task_id: int) -> Task:
    task = task_owned(db, user, task_id)
    if task.completed_at is not None:
        task.completed_at = None
        log_event(
            db,
            user_id=user.id,
            event_type="task_uncompleted",
            actor=actor,
            payload={"task_id": task.id, "title": task.title},
        )
        db.commit()
        db.refresh(task)
    return task


def list_tasks(
    db: Session,
    user: User,
    *,
    list_id: int | None = None,
    include_completed: bool = False,
) -> list[Task]:
    q = (
        db.query(Task)
        .join(List, Task.list_id == List.id)
        .filter(List.owner_id == user.id)
    )
    if list_id is not None:
        list_owned(db, user, list_id)
        q = q.filter(Task.list_id == list_id)
    if not include_completed:
        q = q.filter(Task.completed_at.is_(None))
    return q.order_by(Task.position, Task.id).all()


def set_focus(db: Session, user: User, actor: str, task_ids: list[int]) -> FocusOut:
    if len(task_ids) > FOCUS_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Today's 3: max {FOCUS_MAX} tasks",
        )
    # Deduplicate preserving order
    seen: set[int] = set()
    unique_ids: list[int] = []
    for tid in task_ids:
        if tid not in seen:
            seen.add(tid)
            unique_ids.append(tid)
    if len(unique_ids) > FOCUS_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Today's 3: max {FOCUS_MAX} tasks",
        )

    today = user_today(user)
    tasks_out: list[TaskOut] = []
    for tid in unique_ids:
        task = task_owned(db, user, tid)
        if task.completed_at is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Task {tid} is already completed",
            )
        tasks_out.append(task_to_out(task))

    db.query(Focus).filter(Focus.user_id == user.id, Focus.date == today).delete()
    for tid in unique_ids:
        db.add(Focus(user_id=user.id, date=today, task_id=tid))
    log_event(
        db,
        user_id=user.id,
        event_type="focus_set",
        actor=actor,
        payload={"date": today.isoformat(), "task_ids": unique_ids},
    )
    db.commit()
    return FocusOut(date=today, task_ids=unique_ids, tasks=tasks_out)


def get_focus(db: Session, user: User, on_date: date | None = None) -> FocusOut:
    d = on_date or user_today(user)
    rows = (
        db.query(Focus)
        .filter(Focus.user_id == user.id, Focus.date == d)
        .order_by(Focus.id)
        .all()
    )
    tasks: list[TaskOut] = []
    ids: list[int] = []
    for row in rows:
        task = db.query(Task).filter(Task.id == row.task_id).one_or_none()
        if task and task.completed_at is None:
            ids.append(task.id)
            tasks.append(task_to_out(task))
    return FocusOut(date=d, task_ids=ids, tasks=tasks)


def completion_dates(db: Session, user: User) -> set[date]:
    """Distinct local dates with ≥1 completion."""
    try:
        tz = ZoneInfo(user.tz)
    except Exception:
        tz = ZoneInfo("UTC")

    events = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.event_type == "task_completed")
        .all()
    )
    days: set[date] = set()
    for ev in events:
        local = ev.created_at.astimezone(tz)
        days.add(local.date())
    return days


def compute_streak(db: Session, user: User) -> int:
    days = completion_dates(db, user)
    if not days:
        return 0
    today = user_today(user)
    # Streak counts consecutive days ending today or yesterday (if none today yet)
    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_today(db: Session, user: User) -> TodayOut:
    today = user_today(user)
    try:
        tz = ZoneInfo(user.tz)
    except Exception:
        tz = ZoneInfo("UTC")

    start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=1)

    focus = get_focus(db, user, today)
    focus_ids = set(focus.task_ids)

    open_tasks = (
        db.query(Task)
        .join(List, Task.list_id == List.id)
        .filter(List.owner_id == user.id, Task.completed_at.is_(None))
        .order_by(Task.position, Task.id)
        .all()
    )

    due_today: list[TaskOut] = []
    overdue: list[TaskOut] = []
    for t in open_tasks:
        if t.id in focus_ids:
            continue
        if t.due_at is None:
            continue
        due_local = t.due_at.astimezone(tz)
        if start <= due_local < end:
            due_today.append(task_to_out(t))
        elif due_local < start:
            overdue.append(task_to_out(t))

    default_list = get_default_list(db, user)
    due_ids = {t.id for t in due_today} | {t.id for t in overdue}
    default_tasks = [
        task_to_out(t)
        for t in open_tasks
        if t.list_id == default_list.id and t.id not in focus_ids and t.id not in due_ids
    ]

    return TodayOut(
        date=today,
        streak=compute_streak(db, user),
        focus=focus.tasks,
        due_today=due_today,
        overdue=overdue,
        default_list=ListOut.model_validate(default_list),
        default_tasks=default_tasks,
    )


def weekly_recap(db: Session, user: User) -> WeeklyRecapOut:
    try:
        tz = ZoneInfo(user.tz)
    except Exception:
        tz = ZoneInfo("UTC")
    today = user_today(user)
    week_start = today - timedelta(days=6)

    events = (
        db.query(Event)
        .filter(
            Event.user_id == user.id,
            Event.event_type == "task_completed",
            Event.created_at >= datetime.combine(week_start, datetime.min.time(), tzinfo=tz),
        )
        .order_by(Event.created_at)
        .all()
    )

    by_day: dict[date, list[str]] = {week_start + timedelta(days=i): [] for i in range(7)}
    for ev in events:
        local_d = ev.created_at.astimezone(tz).date()
        if local_d not in by_day:
            continue
        title = ""
        if ev.payload:
            try:
                title = json.loads(ev.payload).get("title", "")
            except (json.JSONDecodeError, TypeError):
                title = ""
        by_day[local_d].append(title or "(xong)")

    days = [
        DayWins(date=d, count=len(titles), titles=titles)
        for d, titles in sorted(by_day.items())
    ]
    total = sum(d.count for d in days)
    best = max(days, key=lambda d: d.count) if days else None
    best_day = best.date if best and best.count > 0 else None
    best_count = best.count if best else 0

    recap_start = datetime.combine(week_start, datetime.min.time(), tzinfo=tz)
    recap_end = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    teaching_rows = db.execute(
        select(TeachingSession, Skill.name, Skill.slug)
        .join(Skill, Skill.id == TeachingSession.skill_id)
        .where(
            TeachingSession.teacher == user.username.lower(),
            TeachingSession.first_clean_run_at >= recap_start,
            TeachingSession.first_clean_run_at < recap_end,
        )
        .order_by(TeachingSession.first_clean_run_at, TeachingSession.id)
    )
    teaching_sessions = [
        TeachingWin(
            session_id=session.id,
            agent=session.agent,
            agent_display=session.agent[:1].upper() + session.agent[1:],
            skill_name=skill_name,
            skill_slug=skill_slug,
            first_clean_run_at=session.first_clean_run_at,
        )
        for session, skill_name, skill_slug in teaching_rows
    ]

    return WeeklyRecapOut(
        streak=compute_streak(db, user),
        total=total,
        best_day=best_day,
        best_day_count=best_count,
        days=days,
        teaching_sessions=teaching_sessions,
    )


def list_events(
    db: Session,
    user: User,
    *,
    since: datetime | None = None,
    limit: int = 100,
) -> list[Event]:
    q = db.query(Event).filter(Event.user_id == user.id)
    if since is not None:
        q = q.filter(Event.created_at >= since)
    return q.order_by(Event.id.asc()).limit(min(limit, 500)).all()


# ---------------------------------------------------------------- attachments

def list_attachments(db: Session, user: User, task_id: int) -> list[Attachment]:
    task_owned(db, user, task_id)  # 404s if not this user's task
    return (
        db.query(Attachment)
        .filter(Attachment.task_id == task_id, Attachment.owner_id == user.id)
        .order_by(Attachment.id.asc())
        .all()
    )


def attachment_owned(db: Session, user: User, attachment_id: int) -> Attachment:
    att = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.owner_id == user.id)
        .one_or_none()
    )
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return att


def add_link(
    db: Session, user: User, actor: str, task_id: int, url: str, label: str | None
) -> Attachment:
    task = task_owned(db, user, task_id)
    url = (url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="URL must start with http:// or https://",
        )
    att = Attachment(
        task_id=task.id,
        owner_id=user.id,
        kind="url",
        url=url,
        filename=(label or "").strip() or None,
        created_by=actor,
    )
    db.add(att)
    log_event(
        db, user_id=user.id, event_type="attachment_added", actor=actor,
        payload={"task_id": task.id, "kind": "url"},
    )
    db.commit()
    db.refresh(att)
    return att


def add_file(
    db: Session, user: User, actor: str, task_id: int, upload
) -> Attachment:
    task = task_owned(db, user, task_id)
    ctype = (upload.content_type or "application/octet-stream").split(";")[0].strip()
    if ctype not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type not allowed: {ctype}",
        )
    rel = storage.build_rel_path(user.username, task.id, upload.filename or "file")
    size = storage.save_stream(rel, upload.file)
    if size == 0:
        storage.delete(rel)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Empty file")
    if size > MAX_UPLOAD_BYTES:
        storage.delete(rel)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    att = Attachment(
        task_id=task.id,
        owner_id=user.id,
        kind="file",
        filename=upload.filename or "file",
        content_type=ctype,
        size_bytes=size,
        storage_path=rel,
        created_by=actor,
    )
    db.add(att)
    log_event(
        db, user_id=user.id, event_type="attachment_added", actor=actor,
        payload={"task_id": task.id, "kind": "file", "size": size},
    )
    db.commit()
    db.refresh(att)
    return att


def delete_attachment(db: Session, user: User, actor: str, attachment_id: int) -> None:
    att = attachment_owned(db, user, attachment_id)
    if att.kind == "file" and att.storage_path:
        storage.delete(att.storage_path)
    log_event(
        db, user_id=user.id, event_type="attachment_removed", actor=actor,
        payload={"task_id": att.task_id, "attachment_id": att.id},
    )
    db.delete(att)
    db.commit()
