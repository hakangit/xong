# Architecture

Xong keeps task management small and exposes optional organization capabilities at the
server boundary. A deployment enables capabilities with `XONG_PLUGINS`; disabled routes
are not registered.

## Runtime

```text
Web or native client
        |
        v
FastAPI app assembly
        |
        +-- core task REST API
        +-- optional files, org, assistant, MCP and A2A routes
        |
        v
Service layer -> SQLAlchemy -> PostgreSQL
```

`src/xong/app.py` owns assembly, middleware, discovery documents, health checks, and the
static web mount. `api.py`, `services.py`, `schemas.py`, and `models.py` form the core task
application. Alembic maintains one linear schema chain for every deployment; disabled
capabilities leave their tables unused.

## Identity

Human requests use OIDC Bearer tokens or a trusted reverse-proxy identity. Agent API keys
use the same Bearer header and must name an allowed user with `X-Acts-For`. All REST, MCP,
and A2A operations resolve through this shared authentication path before calling the
service layer.

## Discovery

`/.well-known/xong-config` tells clients the organization name, API base, authentication
mode, and enabled capabilities. MCP deployments also expose OAuth protected-resource
metadata. A2A deployments expose a minimal agent card.

## Clients

`clients/web` is the dependency-free web client served by the container. It is
trilingual and keeps a local cache for unavailable-network behavior. `clients/ios` is a
native SwiftUI client with tenant discovery, OIDC PKCE, Keychain token storage, and a
local engine.

## Operations

The generic distribution uses Docker Compose and runs migrations before startup. Private
deployments should do the same and use `/readyz`, which verifies database connectivity and
the expected Alembic revision. `/healthz` is a process liveness check only.
