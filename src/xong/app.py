from __future__ import annotations

import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from xong import assistant
from xong.a2a import router as a2a_router
from xong.api import router as api_router
from xong.config import (
    SCHEMA_REVISION,
    get_allowed_hosts,
    get_cors_origins,
    get_oidc_client_id,
    get_oidc_issuer,
    get_oidc_scopes,
    get_org_name,
    get_plugins,
    get_public_api_base,
    get_public_url,
)
from xong.db import get_db
from xong.files_api import attachments_router
from xong.files_api import router as files_router
from xong.mcp_server import streamable_http_app
from xong.org_api import router as org_router
from xong.ui import router as ui_router

STATIC_DIR = Path(__file__).resolve().parent / "static"
logger = logging.getLogger(__name__)
mimetypes.add_type("image/webp", ".webp")


def create_app() -> FastAPI:
    enabled = set(get_plugins())
    if "assistant" in enabled and not assistant.router_base():
        logger.warning(
            "assistant plugin requested but XONG_ROUTER_BASE is unset; plugin disabled"
        )
        enabled.remove("assistant")

    mcp_transport = None
    mcp_session_manager = None
    if "mcp" in enabled:
        mcp_transport, mcp_session_manager = streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if mcp_session_manager is None:
            yield
            return
        async with mcp_session_manager.run():
            yield

    app = FastAPI(
        title="Xong",
        description="Gamified task list — xong = done.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.capabilities = tuple(name for name in get_plugins() if name in enabled)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_cors_origins()),
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Acts-For"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(get_allowed_hosts()))

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(api_router)
    if "org" in enabled:
        app.include_router(org_router)
    if "files" in enabled:
        app.include_router(attachments_router)
        app.include_router(files_router)
    if "assistant" in enabled:
        app.include_router(assistant.router)
    if "a2a" in enabled:
        app.include_router(a2a_router)
    if "mcp" in enabled:
        app.mount("/mcp", mcp_transport, name="mcp")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz(db: Session = Depends(get_db)):
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != SCHEMA_REVISION:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database schema {revision}; expected {SCHEMA_REVISION}",
            )
        return {"ok": True, "schema": revision}

    @app.get("/.well-known/xong-config")
    def xong_config(request: Request):
        issuer = get_oidc_issuer()
        client_id = get_oidc_client_id()
        api_base = get_public_api_base() or str(request.base_url).rstrip("/") + "/api/v1"

        if issuer and client_id:
            auth = {
                "type": "oidc",
                "issuer": issuer,
                "client_id": client_id,
                "scopes": get_oidc_scopes(),
            }
        else:
            auth = {"type": "none"}

        return {
            "version": 2,
            "name": get_org_name(),
            "api_base": api_base,
            "auth": auth,
            "capabilities": list(request.app.state.capabilities),
        }

    if "mcp" in enabled:

        @app.get("/.well-known/oauth-protected-resource")
        def oauth_protected_resource(request: Request):
            base = get_public_url() or str(request.base_url).rstrip("/")
            issuer = get_oidc_issuer()
            return {
                "resource": f"{base}/mcp/",
                "authorization_servers": [issuer] if issuer else [],
                "bearer_methods_supported": ["header"],
            }

    frontend_dir = os.environ.get("XONG_STATIC_DIR")
    if frontend_dir and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        app.include_router(ui_router)
    return app


app = create_app()
