from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, Request
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from xong import __version__, services
from xong.auth import AuthContext, resolve_auth
from xong.config import get_allowed_hosts, get_cors_origins, get_public_url
from xong.db import get_session_factory
from xong.schemas import TaskCreate

_auth_context: ContextVar[AuthContext | None] = ContextVar("xong_mcp_auth", default=None)

mcp = MCPServer(
    "Xong",
    description="Manage the authenticated user's Xong tasks.",
    version=__version__,
)


def _context() -> AuthContext:
    ctx = _auth_context.get()
    if ctx is None:
        raise RuntimeError("MCP request has no authenticated principal")
    return ctx


def _task_json(task) -> dict[str, Any]:
    return services.task_to_out(task).model_dump(mode="json")


@mcp.tool()
def list_tasks(include_completed: bool = False) -> list[dict[str, Any]]:
    """List tasks owned by the authenticated user."""
    ctx = _context()
    with get_session_factory()() as db:
        return [
            _task_json(task)
            for task in services.list_tasks(
                db, ctx.user, include_completed=include_completed
            )
        ]


@mcp.tool()
def create_task(title: str, list_id: int | None = None) -> dict[str, Any]:
    """Create a task for the authenticated user."""
    ctx = _context()
    with get_session_factory()() as db:
        body = TaskCreate(title=title, list_id=list_id)
        task = services.create_task(db, ctx.user, ctx.actor, body)
        return _task_json(task)


@mcp.tool()
def complete_task(task_id: int) -> dict[str, Any]:
    """Complete one task owned by the authenticated user."""
    ctx = _context()
    with get_session_factory()() as db:
        return _task_json(services.complete_task(db, ctx.user, ctx.actor, task_id))


@mcp.tool()
def today() -> dict[str, Any]:
    """Show today's task view for the authenticated user."""
    ctx = _context()
    with get_session_factory()() as db:
        return services.get_today(db, ctx.user).model_dump(mode="json")


@mcp.tool()
def get_focus() -> dict[str, Any]:
    """Get the authenticated user's current focus tasks."""
    ctx = _context()
    with get_session_factory()() as db:
        return services.get_focus(db, ctx.user).model_dump(mode="json")


@mcp.tool()
def set_focus(task_ids: list[int]) -> dict[str, Any]:
    """Set up to three focus tasks for the authenticated user."""
    ctx = _context()
    with get_session_factory()() as db:
        return services.set_focus(db, ctx.user, ctx.actor, task_ids).model_dump(mode="json")


class MCPAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        authorization = request.headers.get("Authorization")
        base = get_public_url() or str(request.base_url).rstrip("/")
        metadata_url = base + "/.well-known/oauth-protected-resource"
        challenge = f'Bearer resource_metadata="{metadata_url}"'
        if not authorization or not authorization.lower().startswith("bearer "):
            response = JSONResponse(
                {"detail": "Bearer authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": challenge},
            )
            await response(scope, receive, send)
            return
        with get_session_factory()() as db:
            try:
                ctx = resolve_auth(
                    request,
                    db=db,
                    authorization=authorization,
                    x_acts_for=request.headers.get("X-Acts-For"),
                    remote_user=None,
                    accept_language=request.headers.get("Accept-Language"),
                )
            except HTTPException as exc:
                headers = {"WWW-Authenticate": challenge} if exc.status_code == 401 else None
                response = JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code, headers=headers
                )
                await response(scope, receive, send)
                return

        token = _auth_context.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            _auth_context.reset(token)


def streamable_http_app():
    transport = mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(get_allowed_hosts()),
            allowed_origins=list(get_cors_origins()),
        ),
    )
    return MCPAuthMiddleware(transport), mcp.session_manager
