"""Route a Xong user's typed command to THEIR own AI agent (the configured agent).

Detection: a user has an assistant iff some api_key's `acts_for` names them —
the same key the agent already uses to manage their tasks. The agent is always
derived from the authenticated user, never from client input, so a user can
only ever command their own agent.

Dispatch: LiteLLM's A2A gateway (JSON-RPC message/send). The agent runs with
its full toolset (it has the xong skill + its company tools) and returns text.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.request
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from xong.auth import AuthContext, require_auth
from xong.db import get_db
from xong.models import ApiKey
from xong.schemas import AssistantCommand, AssistantInfo, AssistantReply

router = APIRouter(prefix="/api/v1")


@lru_cache
def router_base() -> str:
    return os.environ.get("XONG_ROUTER_BASE", "").strip().rstrip("/")


@lru_cache
def router_key() -> str:
    return os.environ.get("XONG_ROUTER_KEY", "").strip()


def assistant_for(db: Session, username: str) -> str | None:
    """Return the agent_name that acts for this user, or None."""
    row = (
        db.query(ApiKey.agent_name)
        .filter(ApiKey.acts_for.any(username))
        .order_by(ApiKey.id.asc())
        .first()
    )
    return row[0] if row else None


def _http_json(url: str, payload: dict | None, timeout: int) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={
            "Authorization": f"Bearer {router_key()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


@lru_cache(maxsize=32)
def _agent_id(agent_name: str) -> str | None:
    agents = _http_json(f"{router_base()}/v1/agents", None, 15)
    for a in agents if isinstance(agents, list) else []:
        if a.get("agent_name") == agent_name:
            return a.get("agent_id")
    return None


def send_command(agent_name: str, text: str, message_id: str, timeout: int = 90) -> str:
    """Dispatch text to the agent via A2A; return its reply text."""
    agent_id = _agent_id(agent_name)
    if not agent_id:
        raise RuntimeError(f"assistant '{agent_name}' not registered on router")
    payload = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "kind": "message",
                "messageId": message_id,
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    resp = _http_json(
        f"{router_base()}/a2a/{agent_id}/message/send", payload, timeout
    )
    result = resp.get("result") or {}
    # a2a reply shape: result.message.parts[].text OR result.artifacts[].parts[]
    msg = result.get("message") or {}
    parts = msg.get("parts") or []
    if not parts:
        for art in result.get("artifacts") or []:
            parts.extend(art.get("parts") or [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    reply = "\n".join(t for t in texts if t).strip()
    return reply or "(no reply)"


@router.get("/assistant", response_model=AssistantInfo)
def assistant_info(
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if ctx.is_agent:
        return AssistantInfo(has_assistant=False)
    name = assistant_for(db, ctx.user.username)
    return AssistantInfo(has_assistant=name is not None, name=name)


@router.post("/assistant/command", response_model=AssistantReply)
def assistant_command(
    body: AssistantCommand,
    ctx: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if ctx.is_agent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Agents cannot command")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Empty command")
    # Agent is derived from the authenticated user — never from client input.
    name = assistant_for(db, ctx.user.username)
    if not name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No assistant for this user")
    if not router_key():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assistant routing not configured",
        )
    framed = (
        f"[Xong command from {ctx.user.username}] {text}\n\n"
        "You are their Xong assistant. Use your xong skill to act on their list "
        "when relevant, then reply briefly with what you did."
    )
    msg_id = f"xong-{ctx.user.id}-{secrets.token_hex(6)}"
    try:
        reply = send_command(name, framed, msg_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Assistant did not respond: {exc}",
        ) from exc
    return AssistantReply(name=name, reply=reply)
