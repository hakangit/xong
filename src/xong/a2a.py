from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from xong import __version__, services
from xong.auth import AuthContext, require_bearer_auth
from xong.config import get_public_url
from xong.db import get_db
from xong.schemas import TaskCreate

router = APIRouter()

OPERATIONS = {
    "list_tasks": "List the authenticated user's tasks",
    "create_task": "Create a task for the authenticated user",
    "complete_task": "Complete a task owned by the authenticated user",
    "today": "Show today's task view",
    "get_focus": "Get the current focus tasks",
    "set_focus": "Set up to three focus tasks",
}


def _execute(operation: str, arguments: dict[str, Any], ctx: AuthContext, db: Session):
    if operation == "list_tasks":
        tasks = services.list_tasks(
            db, ctx.user, include_completed=bool(arguments.get("include_completed", False))
        )
        return [services.task_to_out(task).model_dump(mode="json") for task in tasks]
    if operation == "create_task":
        task = services.create_task(
            db,
            ctx.user,
            ctx.actor,
            TaskCreate(title=arguments.get("title", ""), list_id=arguments.get("list_id")),
        )
        return services.task_to_out(task).model_dump(mode="json")
    if operation == "complete_task":
        task = services.complete_task(db, ctx.user, ctx.actor, int(arguments["task_id"]))
        return services.task_to_out(task).model_dump(mode="json")
    if operation == "today":
        return services.get_today(db, ctx.user).model_dump(mode="json")
    if operation == "get_focus":
        return services.get_focus(db, ctx.user).model_dump(mode="json")
    if operation == "set_focus":
        return services.set_focus(
            db, ctx.user, ctx.actor, [int(value) for value in arguments.get("task_ids", [])]
        ).model_dump(mode="json")
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unsupported A2A operation")


@router.get("/.well-known/agent-card.json")
def agent_card(request: Request):
    base = get_public_url() or str(request.base_url).rstrip("/")
    return {
        "name": "Xong",
        "description": "Task management for an authenticated Xong user.",
        "supportedInterfaces": [
            {"url": f"{base}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "version": __version__,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
        "securityRequirements": [{"bearer": []}],
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": name,
                "name": name.replace("_", " ").title(),
                "description": description,
                "tags": ["tasks"],
            }
            for name, description in OPERATIONS.items()
        ],
    }


@router.post("/a2a")
def send_message(
    body: dict[str, Any],
    ctx: AuthContext = Depends(require_bearer_auth),
    db: Session = Depends(get_db),
):
    request_id = body.get("id")
    if body.get("jsonrpc") != "2.0" or body.get("method") not in {
        "SendMessage",
        "message/send",
    }:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    message = (body.get("params") or {}).get("message") or {}
    parts = message.get("parts") or []
    data = next((part.get("data") for part in parts if isinstance(part.get("data"), dict)), None)
    if not data:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "A data part with operation is required"},
        }
    result = _execute(data.get("operation", ""), data.get("arguments") or {}, ctx, db)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "messageId": str(uuid.uuid4()),
            "role": "agent",
            "parts": [{"data": {"result": result}}],
        },
    }
