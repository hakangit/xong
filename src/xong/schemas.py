from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    position: int | None = None


class ListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    position: int | None = None
    archived: bool | None = None


class ListOut(BaseModel):
    id: int
    owner_id: int
    name: str
    position: int
    archived: bool

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    list_id: int | None = None
    next_action: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    when_where: str | None = None
    position: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    next_action: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    when_where: str | None = None
    position: int | None = None
    list_id: int | None = None


class TaskOut(BaseModel):
    id: int
    list_id: int
    title: str
    next_action: str | None
    notes: str | None
    due_at: datetime | None
    when_where: str | None
    position: int
    created_by: str
    completed_at: datetime | None
    created_at: datetime
    looks_vague: bool = False

    model_config = {"from_attributes": True}


class FocusSet(BaseModel):
    task_ids: list[int] = Field(max_length=3)


class FocusOut(BaseModel):
    date: date
    task_ids: list[int]
    tasks: list[TaskOut]


class TodayOut(BaseModel):
    date: date
    streak: int
    focus: list[TaskOut]
    due_today: list[TaskOut]
    overdue: list[TaskOut]
    default_list: ListOut
    default_tasks: list[TaskOut]


class DayWins(BaseModel):
    date: date
    count: int
    titles: list[str]


class TeachingWin(BaseModel):
    session_id: int
    agent: str
    agent_display: str
    skill_name: str
    skill_slug: str
    first_clean_run_at: datetime


class WeeklyRecapOut(BaseModel):
    streak: int
    total: int
    best_day: date | None
    best_day_count: int
    days: list[DayWins]
    teaching_sessions: list[TeachingWin]


class EventOut(BaseModel):
    id: int
    user_id: int
    event_type: str
    payload: str | None
    created_at: datetime
    actor: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    tz: str

    model_config = {"from_attributes": True}


class AuthContextOut(BaseModel):
    actor: str
    subject: str
    is_agent: bool


class LinkCreate(BaseModel):
    url: str
    filename: str | None = None  # optional label


class AttachmentOut(BaseModel):
    id: int
    task_id: int
    kind: str  # "file" | "url"
    url: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AssistantInfo(BaseModel):
    has_assistant: bool
    name: str | None = None


class AssistantCommand(BaseModel):
    text: str


class AssistantReply(BaseModel):
    name: str
    reply: str
